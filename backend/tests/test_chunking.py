"""
Phase 3 tests: legal structure detection, chunking, schema validation.

Run: pytest backend/tests/test_chunking.py -v
(from the nyaya-ai/ root, or with backend/ on PYTHONPATH — see conftest
pattern used across backend/tests)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.cleaning.clean_text import clean_text
from scripts.cleaning.normalize_legal_text import normalize_legal_text
from scripts.chunking.legal_chunker import parse_legal_structure, generic_paragraph_chunks
from scripts.chunking.create_chunks import chunk_document, DocumentMetadata, validate_chunk, slugify

SAMPLE_ACT = (
    "CHAPTER I\n\nPRELIMINARY\n\n"
    "1. Short title.\u2014This Act may be called the Sample Act, 2000.\n\n"
    "CHAPTER XI\n\nOFFENCES\n\n"
    "66C. Punishment for identity theft.\u2014Whoever, fraudulently or dishonestly "
    "make use of the electronic signature of any other person, shall be punished "
    "with imprisonment for a term which may extend to three years.\n\n"
    "67. Punishment for obscene material.\u2014\n"
    "(1) Whoever publishes obscene material shall be punished on first conviction "
    "with imprisonment for a term which may extend to three years.\n"
    "(2) Whoever commits an offence under sub-section (1) shall be punished on "
    "second conviction with imprisonment for a term which may extend to five years."
)

UNSTRUCTURED_TEXT = (
    "In the matter of a dispute regarding a rental agreement, the Tribunal "
    "examined the notice period clause.\n\n"
    "The Tribunal held that thirty days written notice is required by either "
    "party prior to termination of the tenancy.\n\n"
    "The appeal is disposed of with no order as to costs."
)


def _default_meta(**overrides):
    base = dict(
        domain="cyber", document_type="act", act_name="Sample Act, 2000",
        jurisdiction="India", language="en", source="Test fixture", year=2000,
    )
    base.update(overrides)
    return DocumentMetadata(**base)


def test_structure_detection_finds_chapters_and_sections():
    units = parse_legal_structure(SAMPLE_ACT)
    sections = {u.section for u in units}
    assert sections == {"1", "66C", "67"}
    chapters = {u.chapter for u in units if u.section == "66C"}
    assert chapters == {"XI"}


def test_subsection_split_does_not_false_positive_on_inline_references():
    """Regression test: 'an offence under sub-section (1)' inside 67(2)'s
    text must NOT be mistaken for a new subsection boundary."""
    units = parse_legal_structure(SAMPLE_ACT)
    sec_67_units = [u for u in units if u.section == "67"]
    assert len(sec_67_units) == 2
    assert {u.subsection for u in sec_67_units} == {"1", "2"}
    sub2 = next(u for u in sec_67_units if u.subsection == "2")
    assert "second conviction" in sub2.text
    assert sub2.text.count("Whoever commits an offence") == 1  # not duplicated


def test_no_structure_falls_back_to_generic_chunks():
    units = parse_legal_structure(UNSTRUCTURED_TEXT)
    assert units == []
    chunks = generic_paragraph_chunks(UNSTRUCTURED_TEXT, max_chars=1000)
    assert len(chunks) >= 1
    assert "".join(chunks).count("Tribunal") == 2  # both mentions preserved, nothing dropped


def test_generic_chunks_respect_max_chars_without_duplication_bug():
    chunks = generic_paragraph_chunks(UNSTRUCTURED_TEXT, max_chars=120)
    assert len(chunks) > 1
    for c in chunks:
        # allow a little slack for the trailing-sentence overlap, but no chunk
        # should balloon to roughly double max_chars (the bug this guards against)
        assert len(c) <= 120 * 1.5


def test_chunk_document_produces_valid_schema():
    chunks = chunk_document(normalize_legal_text(clean_text(SAMPLE_ACT)), _default_meta())
    assert len(chunks) >= 3
    for c in chunks:
        assert validate_chunk(c) == []
    ids = [c["chunk_id"] for c in chunks]
    assert len(ids) == len(set(ids)), "chunk_ids must be unique"


def test_chunk_document_never_fabricates_source():
    chunks = chunk_document(SAMPLE_ACT, _default_meta(source="Test fixture"))
    assert all(c["source"] == "Test fixture" for c in chunks)


def test_invalid_document_type_rejected():
    try:
        _default_meta(document_type="not_a_real_type")
        assert False, "should have raised ValueError"
    except ValueError:
        pass


def test_slugify_is_filesystem_safe():
    assert slugify("Information Technology Act, 2000") == "information_technology_act_2000"
    assert " " not in slugify("Weird / Name? *2020*")
