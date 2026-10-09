"""
Phase 7 tests: language_service.py's script-based language detection.

Run: pytest backend/tests/test_language_service.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from backend.app.services.language_service import detect_language, resolve_response_language


def test_detects_english():
    assert detect_language("What are the essential elements of a valid contract?") == "en"


def test_detects_hindi_devanagari():
    assert detect_language("वैध अनुबंध के लिए आवश्यक तत्व क्या हैं?") == "hi"


def test_detects_kannada():
    assert detect_language("ಮಾನ್ಯವಾದ ಒಪ್ಪಂದಕ್ಕೆ ಅಗತ್ಯವಾದ ಅಂಶಗಳು ಯಾವುವು?") == "kn"


def test_empty_text_defaults_to_english():
    assert detect_language("") == "en"
    assert detect_language("   ") == "en"


def test_mixed_script_picks_majority_script():
    # Mostly Kannada with one Latin word mixed in.
    text = "ಒಪ್ಪಂದ ಕಾನೂನು contract ಅಡಿಯಲ್ಲಿ ಏನಿದೆ"
    assert detect_language(text) == "kn"


def test_resolve_response_language_honors_explicit_choice():
    # User picked Hindi in the UI even though the message is in English --
    # explicit choice always wins over detection (spec section 36).
    assert resolve_response_language("hi", "What is a contract?") == "hi"


def test_resolve_response_language_auto_detects():
    assert resolve_response_language("auto", "वैध अनुबंध क्या है?") == "hi"
    assert resolve_response_language("auto", "What is a contract?") == "en"
