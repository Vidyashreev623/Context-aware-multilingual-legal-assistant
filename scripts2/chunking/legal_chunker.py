"""
Legal structure detection and chunking (Phase 3, spec sections 14-15).

Two chunking strategies, chosen automatically:

1. STRUCTURED — for Bare Acts / Rules with numbered sections
   ("66C. Punishment for identity theft.\u2014Whoever..."). Parses the
   Act -> Chapter -> Section -> Subsection -> Clause hierarchy and
   produces one chunk per section (or per subsection, if a section is
   long), never splitting mid-provision. This is spec section 14's
   explicit requirement: "Do not simply split every PDF into arbitrary
   500-character chunks."

2. FALLBACK (generic paragraph chunking) — for case law, judgments,
   uploaded user documents (rental agreements, etc.), or any text
   where no numbered-section structure is detected. Groups paragraphs
   into ~max_chars windows with a small sentence-level overlap so
   context isn't lost at chunk boundaries.

This module only detects structure and groups raw text — it does not
know about domains, sources, or the final JSON chunk schema. That
wiring lives in create_chunks.py, which is what actually satisfies the
spec section 15 chunk format.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_CHAPTER_RE = re.compile(r"^\s*CHAPTER\s+([IVXLCDM]+|\d+)\b[.\-\u2013\u2014:]?\s*(.*)$", re.IGNORECASE)
_SECTION_RE = re.compile(r"^\s*(\d{1,4}[A-Z]{0,2})\.\s+(.+)$", re.DOTALL)
# Anchored to the start of a line (not re.search-anywhere): a bare
# "(1)" is only a subsection/clause marker when it opens a line. This
# matters because legal text routinely *references* earlier
# provisions mid-sentence ("an offence under sub-section (1)") — those
# must NOT be mistaken for a new subsection boundary.
_SUBSECTION_RE = re.compile(r"^\s*\((\d{1,3})\)\s+", re.MULTILINE)
_CLAUSE_RE = re.compile(r"^\s*\(([a-z])\)\s+", re.MULTILINE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"])")


@dataclass
class StructuralUnit:
    """One addressable piece of a legal document, ready to become a chunk."""
    chapter: str | None
    chapter_title: str | None
    section: str | None
    section_title: str | None
    subsection: str | None
    clause: str | None
    text: str
    order_index: int = 0


def _split_title_body(remainder: str) -> tuple[str, str]:
    """
    'Punishment for identity theft.\u2014Whoever, fraudulently...'
    -> ('Punishment for identity theft', 'Whoever, fraudulently...')
    Falls back to the first ~120 chars as title if no em-dash marker
    is present (some Acts use ':' or just a period).
    """
    if "\u2014" in remainder:
        title, body = remainder.split("\u2014", 1)
        return title.strip().rstrip("."), body.strip()
    # No em-dash: try 'Title.\nBody' or just treat everything as body.
    match = re.match(r"^([^.\n]{3,120})\.\s+(.+)$", remainder, re.DOTALL)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return "", remainder.strip()


def _split_subsections(section_title: str, body: str) -> list[tuple[str | None, str | None, str]]:
    """
    Splits a section's body on '(1)', '(2)'... subsection markers, and
    within each subsection further splits on '(a)', '(b)'... clause
    markers when present. Returns a flat list of
    (subsection_id_or_None, clause_id_or_None, text) tuples.
    If there are no subsection markers, returns [(None, None, body)].
    """
    sub_matches = list(_SUBSECTION_RE.finditer(body))
    if not sub_matches:
        return [(None, None, body)] if body.strip() else []

    pieces: list[tuple[str | None, str | None, str]] = []
    # Text before the first '(1)' still belongs to the section (a lead-in sentence).
    lead_in = body[: sub_matches[0].start()].strip()
    if lead_in:
        pieces.append((None, None, lead_in))

    for i, m in enumerate(sub_matches):
        sub_id = m.group(1)
        start = m.end()
        end = sub_matches[i + 1].start() if i + 1 < len(sub_matches) else len(body)
        sub_text = body[start:end].strip()

        clause_matches = list(_CLAUSE_RE.finditer(sub_text))
        if not clause_matches:
            pieces.append((sub_id, None, sub_text))
            continue

        sub_lead_in = sub_text[: clause_matches[0].start()].strip()
        if sub_lead_in:
            pieces.append((sub_id, None, sub_lead_in))
        for j, cm in enumerate(clause_matches):
            c_id = cm.group(1)
            c_start = cm.end()
            c_end = clause_matches[j + 1].start() if j + 1 < len(clause_matches) else len(sub_text)
            c_text = sub_text[c_start:c_end].strip()
            if c_text:
                pieces.append((sub_id, c_id, c_text))

    return [p for p in pieces if p[2]]


def parse_legal_structure(text: str) -> list[StructuralUnit]:
    """
    Parses paragraph-separated legal text into StructuralUnits.
    Returns an empty list if no CHAPTER/numbered-section structure is
    found at all — callers should fall back to generic_paragraph_chunks().
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    units: list[StructuralUnit] = []
    current_chapter: str | None = None
    current_chapter_title: str | None = None
    order = 0
    found_any_section = False

    i = 0
    while i < len(paragraphs):
        para = paragraphs[i]

        chapter_match = _CHAPTER_RE.match(para)
        if chapter_match:
            current_chapter = chapter_match.group(1)
            current_chapter_title = chapter_match.group(2).strip()
            # Chapter titles are often on their own short following paragraph
            # (e.g. "CHAPTER I" then "PRELIMINARY" as separate paragraphs).
            if not current_chapter_title and i + 1 < len(paragraphs) and len(paragraphs[i + 1]) < 60:
                current_chapter_title = paragraphs[i + 1].strip()
                i += 1
            i += 1
            continue

        section_match = _SECTION_RE.match(para)
        if section_match:
            found_any_section = True
            section_id = section_match.group(1)
            remainder = section_match.group(2)
            section_title, body = _split_title_body(remainder)
            for subsection, clause, piece_text in _split_subsections(section_title, body):
                units.append(StructuralUnit(
                    chapter=current_chapter,
                    chapter_title=current_chapter_title,
                    section=section_id,
                    section_title=section_title or None,
                    subsection=subsection,
                    clause=clause,
                    text=piece_text,
                    order_index=order,
                ))
                order += 1
            i += 1
            continue

        # Continuation paragraph (e.g. a "Provided that..." proviso on its
        # own paragraph, immediately after a section) — attach to the
        # most recent section's last unit rather than dropping it.
        if units and units[-1].section is not None:
            units[-1].text = f"{units[-1].text}\n\n{para}"
        # else: pre-amble text before any recognizable section; skip —
        # it's typically the Act's long/short title block, not a provision.
        i += 1

    return units if found_any_section else []


def _last_sentence_overlap(finished_text: str, max_overlap_chars: int) -> str:
    """
    Returns the trailing sentence of `finished_text` to seed the next
    chunk with, capped at max_overlap_chars so a single long "sentence"
    (e.g. a paragraph with no internal punctuation) can't balloon the
    next chunk. Returns "" if the only sentence available is too long
    or there's nothing worth carrying forward.
    """
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(finished_text) if s.strip()]
    if not sentences:
        return ""
    tail = sentences[-1].strip()
    if len(tail) > max_overlap_chars or len(tail) >= len(finished_text):
        return ""
    return tail


def generic_paragraph_chunks(text: str, max_chars: int = 1200, overlap_sentences: int = 1) -> list[str]:
    """
    Fallback chunker for text with no detected legal structure (case
    law, judgments, uploaded documents). Greedily accumulates
    paragraphs up to ~max_chars. When a chunk is closed, the trailing
    sentence is carried into the start of the next chunk (capped at
    25% of max_chars) so retrieval doesn't lose context that straddles
    a chunk boundary, without letting overlap dominate the next chunk.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    max_overlap_chars = max_chars // 4
    chunks: list[str] = []
    current = ""

    def close_current(carry_overlap: bool) -> None:
        nonlocal current
        finished = current.strip()
        if finished:
            chunks.append(finished)
        current = _last_sentence_overlap(finished, max_overlap_chars) + "\n\n" if (carry_overlap and finished) else ""

    for para in paragraphs:
        # A single paragraph longer than max_chars on its own: hard-split by sentence first.
        if len(para) > max_chars:
            if current.strip():
                close_current(carry_overlap=True)
            sentences = [s for s in _SENTENCE_SPLIT_RE.split(para) if s.strip()]
            piece = ""
            for sent in sentences:
                if len(piece) + len(sent) + 1 > max_chars and piece.strip():
                    chunks.append(piece.strip())
                    piece = ""
                piece += sent + " "
            current = piece
            continue

        if len(current) + len(para) + 2 > max_chars and current.strip():
            close_current(carry_overlap=True)
        current += para + "\n\n"

    if current.strip():
        chunks.append(current.strip())

    return [c for c in chunks if c.strip()]


def split_long_unit(unit: StructuralUnit, max_chars: int) -> list[StructuralUnit]:
    """If a single subsection/clause is still too long, hard-split it by sentence."""
    if len(unit.text) <= max_chars:
        return [unit]
    sentences = _SENTENCE_SPLIT_RE.split(unit.text)
    pieces: list[str] = []
    piece = ""
    for sent in sentences:
        if len(piece) + len(sent) + 1 > max_chars and piece.strip():
            pieces.append(piece.strip())
            piece = ""
        piece += sent + " "
    if piece.strip():
        pieces.append(piece.strip())

    return [
        StructuralUnit(
            chapter=unit.chapter, chapter_title=unit.chapter_title,
            section=unit.section, section_title=unit.section_title,
            subsection=unit.subsection, clause=unit.clause,
            text=piece, order_index=unit.order_index,
        )
        for piece in pieces
    ]
