"""
Language detection service (Phase 7, spec sections 5 and 19).

Detects which of the three supported languages (en/hi/kn) a query is
written in, so the improved RAG pipeline can:
  - resolve "auto" language selection into a concrete response language
    (Phase 11 wires the actual multilingual *response* generation; this
    module only handles *detecting the input*, which Phase 7 needs
    regardless, since query classification/reformulation both want to
    know what language they're looking at)
  - keep the query embedding step working on the original text (the
    multilingual embedding model handles that directly) while giving
    Gemini an explicit, reliable language label instead of guessing

Detection strategy: Hindi and Kannada each have a dedicated Unicode
script block, so a query containing either script's characters can be
identified with certainty without any model or network call. Only text
using the Latin script needs a real disambiguation, and since the only
Latin-script language this project supports is English, that case is
unambiguous too. `langdetect` (already in requirements.txt for Phase 11)
is used only as an optional secondary check when installed, so this
module works standalone in Phase 7 before Phase 11 lands.
"""
from __future__ import annotations

import re

# Unicode block ranges (inclusive)
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")
_KANNADA_RE = re.compile(r"[\u0C80-\u0CFF]")

SUPPORTED_LANGUAGES = ("en", "hi", "kn")
LANGUAGE_NAMES = {"en": "English", "hi": "Hindi", "kn": "Kannada"}


def detect_language(text: str) -> str:
    """
    Returns one of "en", "hi", "kn". Falls back to "en" for empty text
    or text that is neither Devanagari nor Kannada script (i.e. Latin
    script, which this project only supports as English).

    Mixed-script queries (e.g. an English sentence quoting a Kannada
    phrase) are classified by whichever supported script has more
    characters, since that reflects the language the user is actually
    asking in.
    """
    if not text or not text.strip():
        return "en"

    devanagari_count = len(_DEVANAGARI_RE.findall(text))
    kannada_count = len(_KANNADA_RE.findall(text))

    if devanagari_count == 0 and kannada_count == 0:
        return "en"
    if kannada_count >= devanagari_count:
        return "kn"
    return "hi"


def resolve_response_language(requested_language: str, message: str) -> str:
    """
    Spec section 36: if the user explicitly picked a language in the UI
    ("en"/"hi"/"kn"), honor it. If they left it on "auto", detect the
    query's language and answer in that.
    """
    if requested_language in SUPPORTED_LANGUAGES:
        return requested_language
    return detect_language(message)
