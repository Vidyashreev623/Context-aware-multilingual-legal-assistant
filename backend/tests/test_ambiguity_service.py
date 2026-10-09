"""
Phase 7 tests: ambiguity_service.py.

Run: pytest backend/tests/test_ambiguity_service.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.app.services.classification_service import classify_query
from backend.app.services.ambiguity_service import detect_ambiguity, CLARIFICATION_TEXT


def test_vague_contract_breach_question_is_ambiguous():
    # Spec section 4's own example.
    q = "What happens if someone breaks a contract?"
    result = detect_ambiguity(q, classify_query(q))
    assert result.ambiguous is True
    assert result.clarification


def test_can_i_file_a_case_is_ambiguous():
    # Spec section 23's own example.
    q = "Can I file a case?"
    result = detect_ambiguity(q, classify_query(q))
    assert result.ambiguous is True


def test_specific_section_lookup_is_not_ambiguous():
    # Spec section 20's own example -- must NOT be flagged just because
    # "66C" isn't a domain keyword.
    q = "What is Section 66C?"
    result = detect_ambiguity(q, classify_query(q))
    assert result.ambiguous is False


def test_query_naming_a_domain_is_not_ambiguous():
    q = "What are the essential elements of a valid contract?"
    result = detect_ambiguity(q, classify_query(q))
    assert result.ambiguous is False


def test_non_english_query_with_clear_domain_is_not_ambiguous():
    # Phase 11: Kannada domain classification now works for real (was
    # a blanket non-English carve-out in Phase 7) -- this stays
    # unambiguous because "ಒಪ್ಪಂದ" (contract) is now actually detected,
    # not because non-English queries are exempted from the check.
    q = "ಮಾನ್ಯವಾದ ಒಪ್ಪಂದಕ್ಕೆ ಅಗತ್ಯವಾದ ಅಂಶಗಳು ಯಾವುವು?"
    classification = classify_query(q)
    assert classification.domain == "contract"
    result = detect_ambiguity(q, classification)
    assert result.ambiguous is False


def test_hindi_query_with_no_domain_keywords_is_now_flagged_ambiguous():
    # Phase 11: the Phase 7 carve-out used to make every non-English
    # query ambiguous=False unconditionally, even ones with genuinely
    # no domain signal. That's fixed now that Hindi has a real keyword
    # table -- a Hindi query naming no domain gets the same
    # low-confidence clarification an equivalent English query would.
    q = "नमस्ते, मुझे कानूनी मदद चाहिए"  # "Hello, I need legal help" -- no domain keyword
    classification = classify_query(q)
    assert classification.domain is None
    result = detect_ambiguity(q, classification)
    assert result.ambiguous is True
    assert result.clarification == CLARIFICATION_TEXT["hi"]


def test_kannada_clarification_is_localized():
    q = "ನಮಸ್ಕಾರ"  # "Hello" -- no domain keyword
    classification = classify_query(q)
    result = detect_ambiguity(q, classification)
    assert result.ambiguous is True
    assert result.clarification == CLARIFICATION_TEXT["kn"]


def test_english_clarification_unchanged():
    q = "Can I file a case?"
    result = detect_ambiguity(q, classify_query(q))
    assert result.clarification == CLARIFICATION_TEXT["en"]
