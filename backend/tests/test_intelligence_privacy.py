"""Privacy controls — milestone item 34. Pure unit tests."""

from app.intelligence.privacy import (
    is_sensitive_attribute_key,
    redact_sensitive_attributes,
    safe_description_for_logging,
)


def test_known_sensitive_keys_are_flagged():
    assert is_sensitive_attribute_key("employee_name") is True
    assert is_sensitive_attribute_key("medical_details") is True


def test_ordinary_keys_are_not_flagged():
    assert is_sensitive_attribute_key("equipment_id") is False


def test_redact_sensitive_attributes_masks_only_sensitive_values():
    attrs = {"employee_name": "Jane Doe", "equipment_id": "PUMP-42"}
    redacted = redact_sensitive_attributes(attrs)
    assert redacted["employee_name"] == "[REDACTED]"
    assert redacted["equipment_id"] == "PUMP-42"


def test_redact_sensitive_attributes_preserves_the_key_even_when_redacting():
    redacted = redact_sensitive_attributes({"disciplinary_action": "suspension"})
    assert "disciplinary_action" in redacted
    assert redacted["disciplinary_action"] == "[REDACTED]"


def test_redact_sensitive_attributes_handles_none_and_empty_safely():
    assert redact_sensitive_attributes(None) == {}
    assert redact_sensitive_attributes({}) == {}


def test_safe_description_for_logging_is_redacted_by_default(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.LOG_INTELLIGENCE_EVENT_DESCRIPTION", False)
    assert safe_description_for_logging("Jane Doe was injured.") == "[REDACTED]"


def test_safe_description_for_logging_passes_through_when_explicitly_enabled(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.LOG_INTELLIGENCE_EVENT_DESCRIPTION", True)
    assert safe_description_for_logging("A public statement.") == "A public statement."


def test_safe_description_for_logging_handles_none():
    assert safe_description_for_logging(None) is None
