import json

import pytest
from pydantic import TypeAdapter, ValidationError

from querivue_agent.contracts.entry import (
    EntryAccept, EntryAssessment, EntryClarify, EntryOutcome, EntryReject, EntryUnavailable,
    PolicyReason,
)


V1 = "123e4567-e89b-12d3-a456-426614174000"


@pytest.mark.parametrize(
    "payload,model",
    [
        ({"disposition": "accept", "policy_reason": "eligible", "explanation": "Eligible request"}, EntryAccept),
        ({"disposition": "reject", "policy_reason": "policy_block", "explanation": "Blocked"}, EntryReject),
        ({"disposition": "clarify", "policy_reason": "needs_scope", "explanation": "Scope is missing", "question": "Which dataset?"}, EntryClarify),
    ],
)
def test_assessment_variants_round_trip(payload, model):
    adapter = TypeAdapter(EntryAssessment)
    result = adapter.validate_python(payload)
    assert isinstance(result, model)
    assert adapter.validate_json(json.dumps(payload)) == result


def test_unavailable_is_runtime_only_not_an_assessment():
    payload = {"disposition": "unavailable", "error_ref": V1, "explanation": "Provider unavailable", "retryable": True}
    result = TypeAdapter(EntryOutcome).validate_python(payload)
    assert isinstance(result, EntryUnavailable)
    assert result.model_dump() == payload
    with pytest.raises(ValidationError):
        TypeAdapter(EntryAssessment).validate_python(payload)


@pytest.mark.parametrize("disposition", ["accept", "reject", "clarify"])
def test_entry_outcome_contains_all_semantic_variants(disposition):
    payload = {"disposition": disposition, "policy_reason": "eligible", "explanation": "x"}
    if disposition == "clarify":
        payload["question"] = "Clarify?"
    assert TypeAdapter(EntryOutcome).validate_python(payload).disposition == disposition


@pytest.mark.parametrize("valid", ["a", "policy_1", "a" * 64])
def test_policy_reason_valid_identifiers(valid):
    assert TypeAdapter(PolicyReason).validate_python(valid) == valid


@pytest.mark.parametrize("invalid", ["", "1reason", "Upper", "has-hyphen", "é", "a" * 65, 1])
def test_policy_reason_rejects_noncanonical_values(invalid):
    with pytest.raises(ValidationError):
        TypeAdapter(PolicyReason).validate_python(invalid)


def test_entry_records_forbid_missing_unknown_and_operational_fields():
    valid = {"disposition": "accept", "policy_reason": "eligible", "explanation": "x"}
    for field in valid:
        missing = dict(valid)
        del missing[field]
        with pytest.raises(ValidationError):
            EntryAccept.model_validate(missing)
    for field, value in (("answer", "yes"), ("route", "sql"), ("source_id", V1), ("admission_id", V1)):
        with pytest.raises(ValidationError, match="extra_forbidden"):
            EntryAccept.model_validate({**valid, field: value})


def test_entry_text_is_nonblank_and_utf8_bounded():
    valid = {"disposition": "clarify", "policy_reason": "needs_scope", "explanation": "x", "question": "q"}
    for field in ("explanation", "question"):
        with pytest.raises(ValidationError):
            EntryClarify.model_validate({**valid, field: " "})
        with pytest.raises(ValidationError):
            EntryClarify.model_validate({**valid, field: "é" * 2048})


def test_unavailable_requires_canonical_reference_and_strict_bool():
    payload = {"disposition": "unavailable", "error_ref": V1, "explanation": "x", "retryable": False}
    assert EntryUnavailable.model_validate(payload).model_dump() == payload
    with pytest.raises(ValidationError):
        EntryUnavailable.model_validate({**payload, "error_ref": "NOT-A-UUID"})
    with pytest.raises(ValidationError):
        EntryUnavailable.model_validate({**payload, "retryable": 0})
