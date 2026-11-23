from copy import deepcopy
import json

import pytest
from pydantic import TypeAdapter, ValidationError

from querivue_agent.contracts.budgets import (
    BudgetAdmitted, BudgetDecision, BudgetDenied, BudgetSnapshot, ClockReading,
    CounterAmounts, CounterSnapshot, MoneySnapshot, ProtectedReserve, ReservationRequest,
)


V1 = "123e4567-e89b-12d3-a456-426614174000"
V4 = "123e4567-e89b-42d3-a456-426614174000"
V4_B = "d816d53d-eac8-4d98-978e-97c1bd81f127"
SCOPE = {"project_id": V1, "chat_id": None, "run_id": None, "eligible_dataset_ids": []}
AMOUNTS = {
    "physical_requests": 0, "logical_invocations": 1, "input_tokens": 2,
    "output_tokens": 3, "tool_calls": 4, "query_executions": 5,
    "dispatch_attempts": 6, "active_milliseconds": 7, "wall_milliseconds": 8,
    "output_bytes": 9, "output_files": 10,
}
COUNTER = {"limit": 10, "used": 3, "reserved": 4, "unknown_reserved": 2}
COUNTERS = {name: COUNTER for name in AMOUNTS}
MONEY = {"limit": "100.000", "used": "20.00", "reserved": "3.0000", "unknown_reserved": "1.0", "currency": "USD"}
RESERVE = {"purpose": "answer", "counters": AMOUNTS, "cost_usd": "2.500"}
SNAPSHOT = {"scope": SCOPE, "revision": 0, "counters": COUNTERS, "cost": MONEY, "protected_reserves": [RESERVE]}
REQUEST = {
    "request_id": V4, "scope": SCOPE, "purpose": "model", "counters": AMOUNTS,
    "cost_usd": "0.00", "expected_revision": 0, "idempotency_key": "reserve-1",
}


@pytest.mark.parametrize(
    "model,payload",
    [
        (CounterSnapshot, COUNTER), (MoneySnapshot, MONEY), (CounterAmounts, AMOUNTS),
        (ProtectedReserve, RESERVE), (BudgetSnapshot, SNAPSHOT),
        (ReservationRequest, REQUEST),
        (ClockReading, {"utc_timestamp": "2026-11-23T00:00:00Z", "monotonic_milliseconds": 0, "process_id": V4, "trusted": False}),
    ],
)
def test_public_budget_records_round_trip_and_forbid_extras(model, payload):
    result = model.model_validate(payload)
    assert result.model_dump() == payload
    with pytest.raises(ValidationError, match="extra_forbidden"):
        model.model_validate({**payload, "unlimited": True})


def test_counter_snapshot_enforces_subset_and_total():
    assert CounterSnapshot.model_validate({"limit": 0, "used": 0, "reserved": 0, "unknown_reserved": 0})
    with pytest.raises(ValidationError, match="exceed reserved"):
        CounterSnapshot.model_validate({**COUNTER, "unknown_reserved": 5})
    with pytest.raises(ValidationError, match="exceed limit"):
        CounterSnapshot.model_validate({**COUNTER, "used": 7})
    with pytest.raises(ValidationError):
        CounterSnapshot.model_validate({**COUNTER, "limit": True})


def test_money_snapshot_uses_exact_large_decimal_arithmetic():
    large = "9" * 120
    assert MoneySnapshot.model_validate({"limit": large, "used": large, "reserved": "0.000", "unknown_reserved": "0", "currency": "USD"})
    with pytest.raises(ValidationError, match="exceed reserved"):
        MoneySnapshot.model_validate({**MONEY, "unknown_reserved": "4"})
    with pytest.raises(ValidationError, match="exceed limit"):
        MoneySnapshot.model_validate({**MONEY, "used": "99", "reserved": "2"})


def test_all_counter_amount_fields_are_required_and_absent_is_not_unlimited():
    for field in AMOUNTS:
        payload = deepcopy(AMOUNTS)
        del payload[field]
        with pytest.raises(ValidationError):
            CounterAmounts.model_validate(payload)


def test_budget_counters_require_all_named_snapshots():
    missing = deepcopy(SNAPSHOT)
    del missing["counters"]["output_files"]
    with pytest.raises(ValidationError):
        BudgetSnapshot.model_validate(missing)


def test_protected_reserve_purposes_are_unique():
    with pytest.raises(ValidationError, match="unique"):
        BudgetSnapshot.model_validate({**SNAPSHOT, "protected_reserves": [RESERVE, RESERVE]})


def test_reservation_request_requires_minted_request_id_and_strict_fields():
    with pytest.raises(ValidationError):
        ReservationRequest.model_validate({**REQUEST, "request_id": V1})
    with pytest.raises(ValidationError):
        ReservationRequest.model_validate({**REQUEST, "expected_revision": "0"})
    with pytest.raises(ValidationError):
        ReservationRequest.model_validate({**REQUEST, "idempotency_key": " "})


@pytest.mark.parametrize(
    "payload,model",
    [
        ({"status": "admitted", "reservation_id": V4_B, "request_id": V1, "snapshot": SNAPSHOT}, BudgetAdmitted),
        ({"status": "denied", "request_id": V1, "limit_kind": "cost", "reason": "No capacity", "snapshot": SNAPSHOT}, BudgetDenied),
    ],
)
def test_budget_decision_variants_round_trip(payload, model):
    adapter = TypeAdapter(BudgetDecision)
    result = adapter.validate_python(payload)
    assert isinstance(result, model)
    assert adapter.validate_json(json.dumps(payload)) == result


def test_budget_decision_rejects_unknown_or_mixed_variant_fields():
    adapter = TypeAdapter(BudgetDecision)
    with pytest.raises(ValidationError):
        adapter.validate_python({"status": "pending"})
    with pytest.raises(ValidationError, match="extra_forbidden"):
        adapter.validate_python({
            "status": "admitted", "reservation_id": V4_B, "request_id": V1,
            "snapshot": SNAPSHOT, "reason": "mixed",
        })


def test_clock_reading_keeps_availability_shape_only():
    payload = {"utc_timestamp": "2026-11-23T00:00:00+00:00", "monotonic_milliseconds": 1, "process_id": V4, "trusted": True}
    assert ClockReading.model_validate(payload).model_dump() == payload
    with pytest.raises(ValidationError):
        ClockReading.model_validate({**payload, "trusted": 1})
