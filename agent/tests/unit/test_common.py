from copy import deepcopy

import pytest
from pydantic import TypeAdapter, ValidationError

from querivue_agent.contracts.common import (
    Hash64, MoneyText, NonblankString, OwnerFence, PositiveCount, Role, SafeCount, Scope,
    TimestampText,
)


V1 = "123e4567-e89b-12d3-a456-426614174000"
V4 = "123e4567-e89b-42d3-a456-426614174000"
V4_B = "d816d53d-eac8-4d98-978e-97c1bd81f127"
SCOPE = {"project_id": V1, "chat_id": V1, "run_id": V4, "eligible_dataset_ids": [V1]}
FENCE = {
    "scope": SCOPE, "subject_kind": "run", "subject_id": V4, "owner_id": V4_B,
    "generation": 1, "attempt": 1, "expected_revision": 0,
    "lease_expires_at": "2026-11-23T12:34:56.123456+05:30",
}


def test_scope_and_owner_fence_round_trip():
    assert Scope.model_validate(SCOPE).model_dump() == SCOPE
    assert OwnerFence.model_validate(FENCE).model_dump() == FENCE


@pytest.mark.parametrize("model,payload", [(Scope, SCOPE), (OwnerFence, FENCE)])
def test_records_require_every_field_and_forbid_extras(model, payload):
    with pytest.raises(ValidationError, match="extra_forbidden"):
        model.model_validate({**payload, "credential": "secret"})
    for field in payload:
        missing = deepcopy(payload)
        del missing[field]
        with pytest.raises(ValidationError):
            model.model_validate(missing)


def test_scope_requires_unique_datasets_and_chat_for_run():
    with pytest.raises(ValidationError, match="unique"):
        Scope.model_validate({**SCOPE, "eligible_dataset_ids": [V1, V1]})
    with pytest.raises(ValidationError, match="requires chat_id"):
        Scope.model_validate({**SCOPE, "chat_id": None})
    assert Scope.model_validate({**SCOPE, "chat_id": None, "run_id": None})


def test_owner_fence_run_identity_and_minted_owner():
    with pytest.raises(ValidationError, match="equal"):
        OwnerFence.model_validate({**FENCE, "subject_id": V1})
    with pytest.raises(ValidationError):
        OwnerFence.model_validate({**FENCE, "owner_id": V1})
    assert OwnerFence.model_validate({**FENCE, "subject_kind": "action", "subject_id": V1})


@pytest.mark.parametrize("alias,valid", [(SafeCount, 0), (PositiveCount, 1)])
def test_count_aliases_are_strict_and_bounded(alias, valid):
    adapter = TypeAdapter(alias)
    assert adapter.validate_python(valid) == valid
    for invalid in (True, str(valid), 9007199254740992, -1):
        with pytest.raises(ValidationError):
            adapter.validate_python(invalid)


def test_text_hash_and_role_aliases_are_concrete():
    assert TypeAdapter(NonblankString).validate_python(" é ") == " é "
    assert TypeAdapter(Hash64).validate_python("a" * 64) == "a" * 64
    assert TypeAdapter(Role).validate_python("supervisor") == "supervisor"
    for alias, invalid in ((NonblankString, "  "), (Hash64, "A" * 64), (Role, "admin")):
        with pytest.raises(ValidationError):
            TypeAdapter(alias).validate_python(invalid)


@pytest.mark.parametrize(
    "valid", ["2026-11-23T12:34:56Z", "2026-11-23T12:34:56.123456+05:30"],
)
def test_timestamp_reuses_exact_offset_spelling(valid):
    assert TypeAdapter(TimestampText).validate_python(valid) == valid


@pytest.mark.parametrize(
    "invalid", ["2026-11-23T12:34:56", "2026-11-23 12:34:56Z", "2026-11-23T12:34:56.1234567Z"],
)
def test_timestamp_rejects_missing_offset_or_noncanonical_precision(invalid):
    with pytest.raises(ValidationError):
        TypeAdapter(TimestampText).validate_python(invalid)


@pytest.mark.parametrize("valid", ["0", "0.00", "1", "1.2300", "9" * 128])
def test_money_preserves_exact_text(valid):
    assert TypeAdapter(MoneyText).validate_python(valid) == valid


@pytest.mark.parametrize(
    "invalid", [0, 1.0, "-1", "+1", "01", ".1", "1.", "1e2", "NaN", "1" * 129],
)
def test_money_rejects_coercion_and_noncanonical_forms(invalid):
    with pytest.raises(ValidationError):
        TypeAdapter(MoneyText).validate_python(invalid)
