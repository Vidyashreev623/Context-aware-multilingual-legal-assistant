"""
Ambiguity detection service (Phase 7, spec section 23; Phase 11
removed the non-English carve-out described below now that
classification_service.py has real Hindi/Kannada keyword tables, and
added localized clarification text -- spec section 26 rule 8 "Answer
in requested language" applies to a clarification question exactly
like any other answer).

Decides whether a query has enough information to retrieve and answer
reliably, or whether the assistant should ask a clarifying question
first instead of guessing a domain (spec section 4's contract-breach
example, section 23's "Can I file a case?" example).

Two independent signals trigger ambiguity, either is sufficient:

1. VAGUE PHRASING -- the query matches a known generic-legal-question
   pattern (e.g. "can I file a case", "what happens if [X] breaks/
   violates/fails to honor [agreement]") regardless of what
   classification_service.py guessed, since these patterns are
   generic *by construction* -- they don't name a domain. English-only
   for now (see module-level TODO below).

2. LOW DOMAIN CONFIDENCE -- classification_service.py's domain_confidence
   fell below a threshold, meaning the query's keywords were split
   across multiple domains (or matched none), so retrieval would be
   filtering on a guess rather than a reliable signal (spec section 21:
   "Do not search every document equally when domain information is
   reliable" implies the converse -- don't pretend it's reliable when
   it isn't). This now applies equally to en/hi/kn queries.

Short queries that plainly DO name a domain/section (e.g. "What is
Section 66C?") are never flagged, even though they're short -- ambiguity
is about missing *category* information, not about length.

TODO (future phase, not required by the spec's Phase 11 scope): the
VAGUE_PATTERNS regexes below are still English-only, so a vague Hindi/
Kannada query (equivalent to "can I file a case?") won't be caught by
signal 1 -- it can still be caught by signal 2 if it doesn't happen to
match a domain either, but a vague query that accidentally contains a
domain keyword would slip through. Documented here rather than
silently left as a gap.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.classification_service import QueryClassification

# Deliberately generic legal questions with no named domain/context.
# Matching one of these means the query is ambiguous *regardless* of
# what (if anything) the keyword domain classifier guessed.
VAGUE_PATTERNS = [
    r"^can i (file|sue|take)\b",
    r"\bwhat happens if\b.{0,40}\b(breaks?|violat|fails?|doesn'?t honou?r)\b",
    r"^what (are )?my (legal )?(rights|options)\??$",
    r"^is (this|that) legal\??$",
    r"^what should i do\??$",
    r"^can (he|she|they|someone) be sued\??$",
]

DOMAIN_CONFIDENCE_THRESHOLD = 0.5

# Query types that name their own specific identifier (a section number,
# a case citation) don't need a domain match to be "specific enough" --
# retrieval can proceed on the identifier itself. Without this, "What is
# Section 66C?" (spec section 20's own example of a perfectly answerable
# query) would be wrongly flagged just because "66C" isn't a domain
# keyword.
SELF_SPECIFIC_QUERY_TYPES = {"section_lookup", "case_law"}

# Phase 11: clarification text per response language (spec section 26
# rule 8). Same content as the Phase 7 English CLARIFICATION_TEMPLATE,
# translated -- not a machine-translation call at request time (that
# would cost an extra Gemini call for a fixed, known sentence, which
# spec section 25 explicitly says to avoid).
CLARIFICATION_TEXT = {
    "en": (
        "I can provide a general answer under Indian law, but could you specify "
        "which area this relates to -- consumer, contract, cyber, family, "
        "property, employment, criminal, or another matter? That will let me "
        "point you to the right provisions."
    ),
    "hi": (
        "मैं भारतीय कानून के तहत सामान्य उत्तर दे सकता हूं, लेकिन कृपया बताएं कि "
        "यह किस क्षेत्र से संबंधित है -- उपभोक्ता, अनुबंध, साइबर, पारिवारिक, "
        "संपत्ति, रोजगार, आपराधिक, या कोई अन्य मामला? इससे मैं सही प्रावधानों की "
        "ओर आपका मार्गदर्शन कर सकूंगा।"
    ),
    "kn": (
        "ನಾನು ಭಾರತೀಯ ಕಾನೂನಿನ ಅಡಿಯಲ್ಲಿ ಸಾಮಾನ್ಯ ಉತ್ತರವನ್ನು ನೀಡಬಲ್ಲೆ, ಆದರೆ ಇದು "
        "ಯಾವ ಕ್ಷೇತ್ರಕ್ಕೆ ಸಂಬಂಧಿಸಿದೆ ಎಂದು ದಯವಿಟ್ಟು ತಿಳಿಸಿ -- ಗ್ರಾಹಕ, ಒಪ್ಪಂದ, "
        "ಸೈಬರ್, ಕುಟುಂಬ, ಆಸ್ತಿ, ಉದ್ಯೋಗ, ಕ್ರಿಮಿನಲ್, ಅಥವಾ ಇನ್ಯಾವುದೇ ವಿಷಯ? ಇದರಿಂದ "
        "ಸರಿಯಾದ ಕಾನೂನು ನಿಬಂಧನೆಗಳತ್ತ ನಿಮ್ಮನ್ನು ಮುನ್ನಡೆಸಬಲ್ಲೆ."
    ),
}

# Backward-compat alias for anything importing the Phase 7 name directly.
CLARIFICATION_TEMPLATE = CLARIFICATION_TEXT["en"]


@dataclass
class AmbiguityResult:
    ambiguous: bool
    clarification: str | None = None
    reason: str | None = None


def _matches_vague_pattern(text_lower: str) -> bool:
    return any(re.search(pattern, text_lower) for pattern in VAGUE_PATTERNS)


def detect_ambiguity(
    message: str, classification: QueryClassification, has_documents: bool = False,
) -> AmbiguityResult:
    """
    `has_documents` (Phase 12): True when the user has attached one or
    more uploaded documents to this question (spec section 31). A
    question scoped to a specific uploaded document ("what is the
    notice period?") is answerable directly from that document
    regardless of whether it also names a legal domain -- domain
    ambiguity is a knowledge-base-retrieval concern, not a
    document-analysis one, so it's skipped entirely in this case
    rather than incorrectly asking the user to pick consumer/contract/
    property/etc. for a question that already has its context attached.
    """
    if has_documents:
        return AmbiguityResult(ambiguous=False)

    text_lower = message.lower().strip()
    clarification = CLARIFICATION_TEXT.get(classification.language, CLARIFICATION_TEXT["en"])

    if classification.language == "en" and _matches_vague_pattern(text_lower):
        return AmbiguityResult(
            ambiguous=True,
            clarification=clarification,
            reason="vague_phrasing",
        )

    if classification.query_type in SELF_SPECIFIC_QUERY_TYPES:
        return AmbiguityResult(ambiguous=False)

    if classification.domain is None or classification.domain_confidence < DOMAIN_CONFIDENCE_THRESHOLD:
        return AmbiguityResult(
            ambiguous=True,
            clarification=clarification,
            reason="low_domain_confidence",
        )

    return AmbiguityResult(ambiguous=False)
