
"""
Legal structure detection and chunking (Phase 3, spec sections 14-15).

Two chunking strategies, chosen automatically:

1. STRUCTURED
   Used for Bare Acts / Rules containing numbered legal sections.

   Example:
       66C. Punishment for identity theft.—Whoever...

   The parser detects:

       Act
        └── Chapter
             └── Section
                  └── Subsection
                       └── Clause

   The parser DOES NOT create arbitrary 500-character chunks.

2. FALLBACK
   Used when no reliable numbered-section structure is detected.

   This is intended for:
       - judgments
       - case law
       - contracts
       - uploaded documents
       - other generic legal text

   Paragraphs are grouped into approximately max_chars-sized chunks
   with sentence-level overlap.

Important:
    This module only detects legal structure and groups text.

    It does not know:
        - domain
        - source
        - final JSON schema
        - embedding model
        - vector database

    That wiring belongs in create_chunks.py / later pipeline phases.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# ============================================================================
# REGULAR EXPRESSIONS
# ============================================================================

# Chapter heading:
#
# CHAPTER I
# CHAPTER II
# CHAPTER 1
#
_CHAPTER_RE = re.compile(
    r"^\s*CHAPTER\s+([IVXLCDM]+|\d+)"
    r"\b[.\-\u2013\u2014:]?\s*(.*)$",
    re.IGNORECASE | re.MULTILINE,
)


# Basic section heading.
#
# Examples:
#
# 5. Conditions for a Hindu marriage.—
# 13. Divorce.—
# 13A. Alternate relief...
# 13B. Divorce by mutual consent...
# 21A. Power to transfer...
#
# IMPORTANT:
#   We deliberately limit the numeric part to 1-3 digits.
#
# This prevents extracted years such as:
#
# 1948.
# 1952.
#
# from being interpreted as legal sections.
_SECTION_HEADING_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?P<section>\d{1,3}[A-Z]{0,2})"
    r"\.\s+"
    r"(?P<remainder>.+?)"
    r"(?="
    r"\n\s*\d{1,3}[A-Z]{0,2}\.\s+"
    r"|$"
    r")",
    re.IGNORECASE | re.DOTALL,
)


# Numeric subsection:
#
# (1)
# (2)
# (10)
#
# We intentionally anchor it to the beginning of a line.
#
# A reference such as:
#
# "under sub-section (1)"
#
# must NOT become a new subsection.
#
_SUBSECTION_RE = re.compile(
    r"^\s*\(?\s*(\d{1,3})\s*\)\s+",
    re.MULTILINE,
)


# Alphabetic clause:
#
# (a)
# (b)
# (c)
#
_CLAUSE_RE = re.compile(
    r"^\s*\(\s*([a-z])\s*\)\s+",
    re.MULTILINE | re.IGNORECASE,
)


# Roman-numeral clause:
#
# (i)
# (ii)
# (iii)
# (iv)
#
# This is important for Indian Bare Acts such as the Hindu Marriage Act.
_ROMAN_CLAUSE_RE = re.compile(
    r"^\s*\(\s*"
    r"(i{1,3}|iv|v|vi{0,3}|ix|x{0,3})"
    r"\s*\)\s+",
    re.MULTILINE | re.IGNORECASE,
)


# Sentence splitting.
#
# IMPORTANT:
#   Parentheses are not used as unescaped grouping syntax accidentally.
#
# We use:
#
#     (?<=[.!?])
#
# followed by whitespace and a likely sentence-start character.
#
_SENTENCE_SPLIT_RE = re.compile(
    r"(?<=[.!?])\s+(?=[A-Z(\[\"])",
)


# ============================================================================
# EDITORIAL / AMENDMENT FOOTNOTE DETECTION
# ============================================================================

# Indian Bare Act PDFs often contain amendment-history notes inside the
# extracted text.
#
# Examples:
#
# by Act 68 of 1976, Section 6...
# The brackets and figure "(1)" omitted by Act...
# The word "or" omitted by Act...
# Clause (vi) omitted by Section...
# Certain words omitted by Section...
# (w.e.f. 27-5-1976).
#
# These are NOT legal provisions and must not become sections.
#
_EDITORIAL_LINE_RE = re.compile(
    r"^\s*(?:"
    r"by\s+Act\b"
    r"|the\s+(?:brackets?|word|words|figure|figures|expression|expression[s]?)\b"
    r"|clause\s+\([a-zivx]+\)\s+omitted\b"
    r"|certain\s+words\s+omitted\b"
    r"|\(w\.e\.f\."
    r"|w\.e\.f\."
    r")",
    re.IGNORECASE,
)


# Some extracted amendment notes begin with a footnote number:
#
# 1. The brackets and figure "(1)" omitted...
# 2. by Act 68 of 1976...
#
_EDITORIAL_NUMBERED_LINE_RE = re.compile(
    r"^\s*\d{1,2}\.\s+"
    r"(?:"
    r"the\s+(?:brackets?|word|words|figure|figures|expression)\b"
    r"|by\s+Act\b"
    r"|clause\s+\([a-zivx]+\)\s+omitted\b"
    r"|certain\s+words\s+omitted\b"
    r")",
    re.IGNORECASE,
)


# ============================================================================
# DATA MODEL
# ============================================================================


@dataclass
class StructuralUnit:
    """
    One addressable piece of a legal document.

    This is the intermediate representation used before create_chunks.py
    converts it into the final legal chunk JSON schema.
    """

    chapter: str | None
    chapter_title: str | None

    section: str | None
    section_title: str | None

    subsection: str | None
    clause: str | None

    text: str

    order_index: int = 0


# ============================================================================
# BASIC TEXT CLEANING HELPERS
# ============================================================================


def _clean_ocr_marker(text: str) -> str:
    """
    Remove common OCR/editorial markers that appear immediately before
    legal subsection/clause markers.

    Example:

        1[(ii) at the time of the marriage...

    becomes:

        (ii) at the time of the marriage...

    Also handles:

        [ (ii)
        1[(ii)
        2[(a)

    We do NOT remove arbitrary square brackets from legal text.
    Only markers immediately before a recognized legal marker are cleaned.
    """

    # Numeric footnote directly before subsection/clause.
    text = re.sub(
        r"(?<!\w)\d+\s*\[\s*(?=\(\s*(?:\d{1,3}|[a-z]|i{1,3}|iv|v|vi{0,3}|ix|x{0,3})\s*\))",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # Standalone square bracket immediately before a legal marker.
    text = re.sub(
        r"\[\s*(?=\(\s*(?:\d{1,3}|[a-z]|i{1,3}|iv|v|vi{0,3}|ix|x{0,3})\s*\))",
        "",
        text,
        flags=re.IGNORECASE,
    )

    return text


def _remove_editorial_footnotes(text: str) -> str:
    """
    Remove obvious amendment/editorial notes from extracted Bare Act text.

    This is deliberately conservative.

    We remove only lines that strongly resemble amendment history.

    We do NOT remove normal legal provisions containing phrases such as
    "by Act" in the middle of a sentence.
    """

    lines = text.splitlines()

    cleaned_lines: list[str] = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            cleaned_lines.append("")
            continue

        if _EDITORIAL_LINE_RE.match(stripped):
            continue

        if _EDITORIAL_NUMBERED_LINE_RE.match(stripped):
            continue

        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def _normalize_marker_spacing(text: str) -> str:
    """
    Normalize spacing around legal markers without changing substantive text.

    Examples:

        ( 1 )  -> (1)
        ( a )  -> (a)
        ( ii ) -> (ii)
    """

    text = re.sub(
        r"\(\s*(\d{1,3})\s*\)",
        r"(\1)",
        text,
    )

    text = re.sub(
        r"\(\s*([a-z])\s*\)",
        r"(\1)",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\(\s*(i{1,3}|iv|v|vi{0,3}|ix|x{0,3})\s*\)",
        r"(\1)",
        text,
        flags=re.IGNORECASE,
    )

    return text


def _preprocess_legal_text(text: str) -> str:
    """
    Apply conservative preprocessing before structural parsing.
    """

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    text = _remove_editorial_footnotes(text)

    text = _clean_ocr_marker(text)

    text = _normalize_marker_spacing(text)

    return text


# ============================================================================
# SECTION TITLE / BODY
# ============================================================================


def _split_title_body(remainder: str) -> tuple[str, str]:
    """
    Split:

        Punishment for identity theft.—Whoever...

    into:

        title = "Punishment for identity theft"
        body  = "Whoever..."

    Also supports:

        Section title.
        Body

    If no reliable title/body boundary is found, the whole text is treated
    as the body.
    """

    remainder = remainder.strip()

    # Most Indian Bare Acts use an em dash.
    if "\u2014" in remainder:
        title, body = remainder.split("\u2014", 1)

        return (
            title.strip().rstrip("."),
            body.strip(),
        )

    # Some PDFs use an en dash.
    if "\u2013" in remainder:
        title, body = remainder.split("\u2013", 1)

        # Only treat it as title/body when the title is reasonably short.
        if 3 <= len(title.strip()) <= 160:
            return (
                title.strip().rstrip("."),
                body.strip(),
            )

    # Some extracted PDFs use:
    #
    # Title.
    # Body
    #
    match = re.match(
        r"^([^.\n]{3,160})\.\s+(.+)$",
        remainder,
        re.DOTALL,
    )

    if match:
        return (
            match.group(1).strip(),
            match.group(2).strip(),
        )

    return "", remainder.strip()


# ============================================================================
# SUBSECTION / CLAUSE PARSING
# ============================================================================


def _find_marker_matches(
    body: str,
) -> list[tuple[int, int, str, str]]:
    """
    Find subsection/clause markers in their original order.

    Returns:

        start
        end
        marker_type
        marker_id

    Example:

        (1) -> ("subsection", "1")
        (a) -> ("clause", "a")
        (ii) -> ("clause", "ii")
    """

    matches: list[tuple[int, int, str, str]] = []

    for m in _SUBSECTION_RE.finditer(body):
        matches.append(
            (
                m.start(),
                m.end(),
                "subsection",
                m.group(1),
            )
        )

    for m in _CLAUSE_RE.finditer(body):
        matches.append(
            (
                m.start(),
                m.end(),
                "clause",
                m.group(1).lower(),
            )
        )

    for m in _ROMAN_CLAUSE_RE.finditer(body):
        matches.append(
            (
                m.start(),
                m.end(),
                "clause",
                m.group(1).lower(),
            )
        )

    matches.sort(key=lambda x: (x[0], x[1]))

    # Remove duplicate matches occurring at the same position.
    result: list[tuple[int, int, str, str]] = []

    seen_positions: set[tuple[int, int]] = set()

    for item in matches:
        key = (item[0], item[1])

        if key in seen_positions:
            continue

        seen_positions.add(key)
        result.append(item)

    return result


def _split_subsections(
    section_title: str,
    body: str,
) -> list[tuple[str | None, str | None, str]]:
    """
    Split a section into addressable legal units.

    Handles all of these:

        Section 5:
            (i)
            (ii)
                (a)
                (b)
            (iii)

    And:

        Section 12:
            (1)
                (a)
                (b)
            (2)

    Also handles OCR forms such as:

        1[(ii)

    after preprocessing.

    Output:

        (subsection, clause, text)
    """

    body = _clean_ocr_marker(body)
    body = _normalize_marker_spacing(body)

    # ------------------------------------------------------------------
    # Find numeric subsections first.
    # ------------------------------------------------------------------

    subsection_matches = list(_SUBSECTION_RE.finditer(body))

    if subsection_matches:
        pieces: list[tuple[str | None, str | None, str]] = []

        # Text before first subsection.
        lead_in = body[: subsection_matches[0].start()].strip()

        # The lead-in may contain roman clauses such as (i), (ii).
        if lead_in:
            roman_or_alpha = list(_ROMAN_CLAUSE_RE.finditer(lead_in))

            if roman_or_alpha:
                pieces.extend(
                    _split_clause_region(
                        lead_in,
                        None,
                    )
                )
            else:
                pieces.append(
                    (
                        None,
                        None,
                        lead_in,
                    )
                )

        # Process each numeric subsection.
        for index, match in enumerate(subsection_matches):

            subsection_id = match.group(1)

            start = match.end()

            if index + 1 < len(subsection_matches):
                end = subsection_matches[index + 1].start()
            else:
                end = len(body)

            subsection_text = body[start:end].strip()

            if not subsection_text:
                continue

            clause_pieces = _split_clause_region(
                subsection_text,
                subsection_id,
            )

            pieces.extend(clause_pieces)

        return [
            piece
            for piece in pieces
            if piece[2].strip()
        ]

    # ------------------------------------------------------------------
    # No numeric subsection.
    #
    # This is important for Section 5 of the Hindu Marriage Act:
    #
    # (i)
    # (ii)
    #     (a)
    #     (b)
    #
    # These are clauses directly under the section.
    # ------------------------------------------------------------------

    return _split_clause_region(
        body,
        None,
    )


def _split_clause_region(
    text: str,
    subsection_id: str | None,
) -> list[tuple[str | None, str | None, str]]:
    """
    Split a subsection/section region into clauses.

    Handles:

        (a)
        (b)

    and:

        (i)
        (ii)
        (iii)

    without confusing references in normal sentences.
    """

    marker_matches: list[tuple[int, int, str]] = []

    for match in _CLAUSE_RE.finditer(text):
        marker_matches.append(
            (
                match.start(),
                match.end(),
                match.group(1).lower(),
            )
        )

    for match in _ROMAN_CLAUSE_RE.finditer(text):
        marker_matches.append(
            (
                match.start(),
                match.end(),
                match.group(1).lower(),
            )
        )

    marker_matches.sort(key=lambda x: (x[0], x[1]))

    # Remove duplicates.
    unique: list[tuple[int, int, str]] = []

    seen: set[tuple[int, int]] = set()

    for item in marker_matches:
        key = (item[0], item[1])

        if key in seen:
            continue

        seen.add(key)
        unique.append(item)

    if not unique:
        if text.strip():
            return [
                (
                    subsection_id,
                    None,
                    text.strip(),
                )
            ]

        return []

    pieces: list[tuple[str | None, str | None, str]] = []

    # Text before first clause.
    lead_in = text[: unique[0][0]].strip()

    if lead_in:
        pieces.append(
            (
                subsection_id,
                None,
                lead_in,
            )
        )

    # Each clause.
    for index, (start, marker_end, clause_id) in enumerate(unique):

        if index + 1 < len(unique):
            end = unique[index + 1][0]
        else:
            end = len(text)

        clause_text = text[marker_end:end].strip()

        if clause_text:
            pieces.append(
                (
                    subsection_id,
                    clause_id,
                    clause_text,
                )
            )

    return pieces


# ============================================================================
# LEGAL STRUCTURE PARSER
# ============================================================================


def parse_legal_structure(
    text: str,
) -> list[StructuralUnit]:
    """
    Detect legal sections from normalized text.

    Important protections:

    1. Starts from enacted body when possible.
    2. Removes obvious amendment-history footnotes.
    3. Does not treat years such as 1948 / 1952 as sections.
    4. Supports sections 13A, 13B, 21A, 21B, 21C, etc.
    5. Supports same-line section headings.
    6. Supports numeric subsections.
    7. Supports alphabetic clauses.
    8. Supports roman clauses.
    9. Preserves section hierarchy.
    """

    if not text or not text.strip():
        return []

    # ---------------------------------------------------------------
    # Basic normalization.
    # ---------------------------------------------------------------

    text = _preprocess_legal_text(text)

    # ---------------------------------------------------------------
    # Prefer actual enacted body over table of contents.
    # ---------------------------------------------------------------

    enactment_markers = [
        r"\bBE\s+it\s+enacted\b",
        r"\bBe\s+it\s+enacted\b",
        r"\bBE\s+it\s+enacted\s+by\b",
    ]

    body_start = None

    for marker in enactment_markers:
        match = re.search(
            marker,
            text,
            re.IGNORECASE,
        )

        if match:
            body_start = match.start()
            break

    if body_start is not None:
        text = text[body_start:]

    # ---------------------------------------------------------------
    # Find section headings.
    # ---------------------------------------------------------------

    matches = list(
        _SECTION_HEADING_RE.finditer(text)
    )

    if not matches:
        return []

    units: list[StructuralUnit] = []

    current_chapter: str | None = None
    current_chapter_title: str | None = None

    order = 0

    # ---------------------------------------------------------------
    # Process every candidate section.
    # ---------------------------------------------------------------

    for match in matches:

        section_id = match.group("section").strip()

        remainder = match.group("remainder").strip()

        if not remainder:
            continue

        # -----------------------------------------------------------
        # Reject obvious editorial/amendment candidates.
        # -----------------------------------------------------------

        first_line = remainder.splitlines()[0].strip()

        if _EDITORIAL_LINE_RE.match(first_line):
            continue

        if _EDITORIAL_NUMBERED_LINE_RE.match(first_line):
            continue

        # -----------------------------------------------------------
        # Reject obvious year-like section candidates.
        #
        # This is mostly redundant because the section regex now allows
        # only 1-3 digits, but retained as a safety check.
        # -----------------------------------------------------------

        if len(re.sub(r"[A-Za-z]", "", section_id)) >= 4:
            continue

        # -----------------------------------------------------------
        # Recover chapter from preceding text.
        # -----------------------------------------------------------

        preceding = text[: match.start()]

        chapter_matches = list(
            _CHAPTER_RE.finditer(preceding)
        )

        if chapter_matches:
            chapter_match = chapter_matches[-1]

            current_chapter = (
                chapter_match.group(1).strip()
            )

            current_chapter_title = (
                chapter_match.group(2).strip()
                or None
            )

        # -----------------------------------------------------------
        # Split title and body.
        # -----------------------------------------------------------

        section_title, body = _split_title_body(
            remainder
        )

        body = _clean_ocr_marker(body)

        body = _normalize_marker_spacing(body)

        # -----------------------------------------------------------
        # Remove editorial lines that may still be inside the section.
        # -----------------------------------------------------------

        body = _remove_editorial_footnotes(body)

        body = body.strip()

        if not body:
            continue

        # -----------------------------------------------------------
        # Split section into subsection/clause units.
        # -----------------------------------------------------------

        pieces = _split_subsections(
            section_title,
            body,
        )

        if not pieces:
            pieces = [
                (
                    None,
                    None,
                    body,
                )
            ]

        # -----------------------------------------------------------
        # Create StructuralUnit objects.
        # -----------------------------------------------------------

        for subsection, clause, piece_text in pieces:

            piece_text = piece_text.strip()

            if not piece_text:
                continue

            units.append(
                StructuralUnit(
                    chapter=current_chapter,
                    chapter_title=current_chapter_title,
                    section=section_id,
                    section_title=(
                        section_title
                        or None
                    ),
                    subsection=subsection,
                    clause=clause,
                    text=piece_text,
                    order_index=order,
                )
            )

            order += 1

    return units


# ============================================================================
# SENTENCE OVERLAP
# ============================================================================


def _last_sentence_overlap(
    finished_text: str,
    max_overlap_chars: int,
) -> str:
    """
    Return the trailing sentence of finished_text.

    This is used only by generic fallback chunking.

    The overlap is capped so that a single extremely long sentence cannot
    dominate the next chunk.
    """

    sentences = [
        s
        for s in _SENTENCE_SPLIT_RE.split(
            finished_text
        )
        if s.strip()
    ]

    if not sentences:
        return ""

    tail = sentences[-1].strip()

    if len(tail) > max_overlap_chars:
        return ""

    if len(tail) >= len(
        finished_text.strip()
    ):
        return ""

    return tail


# ============================================================================
# GENERIC FALLBACK CHUNKING
# ============================================================================


def generic_paragraph_chunks(
    text: str,
    max_chars: int = 1200,
    overlap_sentences: int = 1,
) -> list[str]:
    """
    Fallback chunker for text with no detected legal structure.

    Intended for:

        - judgments
        - case law
        - contracts
        - user-uploaded documents
        - generic legal documents

    Paragraphs are greedily accumulated up to approximately max_chars.

    When a chunk closes, the last sentence is carried into the next chunk.
    """

    del overlap_sentences

    paragraphs = [
        p.strip()
        for p in text.split("\n\n")
        if p.strip()
    ]

    if not paragraphs:
        return []

    max_overlap_chars = max_chars // 4

    chunks: list[str] = []

    current = ""

    def close_current(
        carry_overlap: bool,
    ) -> None:
        nonlocal current

        finished = current.strip()

        if finished:
            chunks.append(finished)

        if carry_overlap and finished:
            overlap = _last_sentence_overlap(
                finished,
                max_overlap_chars,
            )

            if overlap:
                current = overlap + "\n\n"
            else:
                current = ""
        else:
            current = ""

    for para in paragraphs:

        # -----------------------------------------------------------
        # Paragraph itself is larger than max_chars.
        # -----------------------------------------------------------

        if len(para) > max_chars:

            if current.strip():
                close_current(
                    carry_overlap=True
                )

            sentences = [
                s
                for s in _SENTENCE_SPLIT_RE.split(
                    para
                )
                if s.strip()
            ]

            # If sentence splitting does not work,
            # use conservative hard splitting.
            if not sentences:
                sentences = [
                    para[i : i + max_chars]
                    for i in range(
                        0,
                        len(para),
                        max_chars,
                    )
                ]

            piece = ""

            for sent in sentences:

                if (
                    len(piece)
                    + len(sent)
                    + 1
                    > max_chars
                    and piece.strip()
                ):
                    chunks.append(
                        piece.strip()
                    )

                    piece = ""

                piece += sent + " "

            current = piece

            continue

        # -----------------------------------------------------------
        # Normal paragraph.
        # -----------------------------------------------------------

        if (
            len(current)
            + len(para)
            + 2
            > max_chars
            and current.strip()
        ):
            close_current(
                carry_overlap=True
            )

        current += para + "\n\n"

    # ---------------------------------------------------------------
    # Final chunk.
    # ---------------------------------------------------------------

    if current.strip():
        chunks.append(
            current.strip()
        )

    return [
        chunk
        for chunk in chunks
        if chunk.strip()
    ]


# ============================================================================
# LONG STRUCTURAL UNITS
# ============================================================================


def split_long_unit(
    unit: StructuralUnit,
    max_chars: int,
) -> list[StructuralUnit]:
    """
    Split a single structural unit only when it exceeds max_chars.

    Structural metadata is preserved.

    The function attempts sentence-level splitting first.

    It NEVER creates a completely unrelated generic chunk because the
    section/subsection/clause identity remains attached to every piece.
    """

    if len(unit.text) <= max_chars:
        return [unit]

    sentences = [
        s
        for s in _SENTENCE_SPLIT_RE.split(
            unit.text
        )
        if s.strip()
    ]

    # If sentence splitting fails, use a safe hard split.
    if not sentences:
        sentences = [
            unit.text[i : i + max_chars]
            for i in range(
                0,
                len(unit.text),
                max_chars,
            )
        ]

    pieces: list[str] = []

    piece = ""

    for sentence in sentences:

        sentence = sentence.strip()

        if not sentence:
            continue

        if (
            len(piece)
            + len(sentence)
            + 1
            > max_chars
            and piece.strip()
        ):
            pieces.append(
                piece.strip()
            )

            piece = ""

        # A single sentence longer than max_chars.
        if len(sentence) > max_chars:

            if piece.strip():
                pieces.append(
                    piece.strip()
                )

                piece = ""

            for start in range(
                0,
                len(sentence),
                max_chars,
            ):
                pieces.append(
                    sentence[
                        start : start + max_chars
                    ].strip()
                )

            continue

        piece += sentence + " "

    if piece.strip():
        pieces.append(
            piece.strip()
        )

    return [
        StructuralUnit(
            chapter=unit.chapter,
            chapter_title=unit.chapter_title,
            section=unit.section,
            section_title=unit.section_title,
            subsection=unit.subsection,
            clause=unit.clause,
            text=piece,
            order_index=unit.order_index,
        )
        for piece in pieces
        if piece.strip()
    ]
