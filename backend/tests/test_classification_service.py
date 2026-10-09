"""
Phase 7 tests: classification_service.py's keyword-based domain/query-type/
jurisdiction classification.

Run: pytest backend/tests/test_classification_service.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.app.services.classification_service import classify_query


def test_classifies_contract_domain():
    result = classify_query("What are the essential elements of a valid contract?")
    assert result.domain == "contract"
    assert result.domain_confidence > 0


def test_classifies_cyber_domain():
    result = classify_query("What is identity theft under the Information Technology Act?")
    assert result.domain == "cyber"


def test_classifies_section_lookup_query_type():
    result = classify_query("What is Section 66C?")
    assert result.query_type == "section_lookup"


def test_classifies_penalty_query_type():
    result = classify_query("What is the punishment for cheque bounce?")
    assert result.query_type == "penalty"


def test_classifies_document_analysis_query_type():
    result = classify_query("What is the notice period mentioned in this agreement?")
    assert result.query_type == "document_analysis"


def test_detects_state_jurisdiction():
    result = classify_query("What is the Karnataka law regarding tenant eviction?")
    assert result.state == "Karnataka"
    assert result.jurisdiction == "India"


def test_detects_court():
    result = classify_query("What did the Supreme Court rule on this?")
    assert result.court == "Supreme Court"


def test_no_domain_keywords_returns_none_domain():
    result = classify_query("hello there")
    assert result.domain is None
    assert result.domain_confidence == 0.0


def test_default_query_type_is_general():
    result = classify_query("Tell me something about law")
    assert result.query_type == "general_legal_information"


def test_language_field_matches_detected_language():
    result = classify_query("वैध अनुबंध क्या है?")
    assert result.language == "hi"


def test_as_dict_matches_spec_section_19_shape():
    result = classify_query("What is Section 66C?")
    d = result.as_dict()
    assert set(d.keys()) == {
        "language", "domain", "jurisdiction", "state", "court",
        "query_type", "ambiguity", "confidence",
    }


# --- Phase 11: Hindi/Kannada classification (spec section 5, 47) ---

def test_classifies_hindi_contract_domain():
    result = classify_query("वैध अनुबंध क्या है?")
    assert result.language == "hi"
    assert result.domain == "contract"
    assert result.domain_confidence > 0


def test_classifies_hindi_cyber_domain():
    result = classify_query("साइबर अपराध के तहत पहचान की चोरी क्या है?")
    assert result.language == "hi"
    assert result.domain == "cyber"


def test_classifies_hindi_penalty_query_type():
    result = classify_query("चेक बाउंस के लिए सजा क्या है?")
    assert result.language == "hi"
    assert result.query_type == "penalty"


def test_detects_hindi_state_jurisdiction():
    result = classify_query("कर्नाटक में किरायेदार बेदखली का कानून क्या है?")
    assert result.state == "Karnataka"
    assert result.jurisdiction == "India"


def test_classifies_kannada_cyber_domain():
    result = classify_query("ಭಾರತೀಯ ಸೈಬರ್ ಕಾನೂನಿನ ಅಡಿಯಲ್ಲಿ ಗುರುತಿನ ಕಳ್ಳತನ ಎಂದರೇನು?")
    assert result.language == "kn"
    assert result.domain == "cyber"


def test_classifies_kannada_contract_domain():
    result = classify_query("ಮಾನ್ಯವಾದ ಒಪ್ಪಂದಕ್ಕೆ ಅಗತ್ಯವಾದ ಅಂಶಗಳು ಯಾವುವು?")
    assert result.language == "kn"
    assert result.domain == "contract"


def test_detects_kannada_state_jurisdiction():
    result = classify_query("ಕರ್ನಾಟಕ ಬಾಡಿಗೆದಾರ ಒಕ್ಕಲೆಬ್ಬಿಸುವಿಕೆ ಕಾನೂನು ಏನು?")
    assert result.state == "Karnataka"


def test_hindi_no_domain_keywords_returns_none_domain():
    result = classify_query("नमस्ते")
    assert result.domain is None
    assert result.domain_confidence == 0.0
