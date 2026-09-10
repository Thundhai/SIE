"""Milestone test items 1-7: file type detection for every initially
supported format, plus unsupported-type rejection. Uses the real fixture
files (tests/fixtures/ingestion/), not strings — a magic-byte detector
has to actually see real bytes to be tested meaningfully.
"""

import pytest

from app.ingestion.detection import detect_file_type
from app.ingestion.pipeline import UnsupportedFileTypeError, detect_supported_type
from tests.conftest import load_fixture


@pytest.mark.parametrize(
    "filename,expected_media_type",
    [
        ("sample_procedure.pdf", "application/pdf"),
        (
            "sample_procedure.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        ("sample_ppe_policy.txt", "text/plain"),
        ("sample_incident_register.csv", "text/csv"),
        (
            "sample_incident_register.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        (
            "sample_training.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ),
        ("sample_evacuation.rtf", "application/rtf"),
    ],
)
def test_detect_file_type(filename, expected_media_type):
    data = load_fixture(filename)

    detected = detect_file_type(data, filename=filename)

    assert detected is not None
    assert detected.media_type == expected_media_type


def test_detect_file_type_returns_none_for_unrecognized_content():
    data = load_fixture("unsupported.bin")

    assert detect_file_type(data, filename="unsupported.bin") is None


def test_unsupported_file_type_is_rejected_by_the_pipeline():
    data = load_fixture("unsupported.bin")

    with pytest.raises(UnsupportedFileTypeError):
        detect_supported_type(data, filename="unsupported.bin")


def test_a_recognized_but_unimplemented_format_is_also_rejected():
    """DOC is in detection.py's extension table (so the ingestion
    response can name it specifically) but has no registered adapter —
    still an UnsupportedFileTypeError, not a crash."""
    with pytest.raises(UnsupportedFileTypeError):
        detect_supported_type(b"\xd0\xcf\x11\xe0", filename="legacy.doc")


def test_detection_prefers_magic_bytes_over_a_misleading_extension():
    """A real PDF's content wins even if someone names it .txt."""
    data = load_fixture("sample_procedure.pdf")

    detected = detect_file_type(data, filename="not_really_a_pdf.txt")

    assert detected is not None
    assert detected.media_type == "application/pdf"
