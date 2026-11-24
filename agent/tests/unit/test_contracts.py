import math

import pytest
from pydantic import TypeAdapter, ValidationError

from querivue_agent import hello
from querivue_agent.contracts.values import CanonicalUUID, RuntimeUUID, TypedScalar


SCALAR = TypeAdapter(TypedScalar)


def test_exact_scalar_and_extra_fields():
    valid = [
        {"kind": "int64", "value": "9223372036854775807"},
        {"kind": "decimal", "value": "1.00", "precision": 3, "scale": 2},
        {"kind": "timestamptz", "value": "2024-02-29T12:00:00.123456+05:30"},
    ]
    for payload in valid:
        scalar = SCALAR.validate_python(payload)
        assert scalar.model_dump() == payload
        assert SCALAR.validate_json(scalar.model_dump_json()) == scalar

    invalid = [
        {"kind": "int64", "value": "9223372036854775808"},
        {"kind": "float64", "value": math.inf},
        {"kind": "timestamptz", "value": "2024-02-29T12:00:00+24:00"},
        {"kind": "string", "value": "x", "runtime_owner": "caller"},
        {"kind": "decimal", "value": "1.00", "precision": 3, "scale": 2, "budget": 1},
    ]
    for payload in invalid:
        with pytest.raises(ValidationError):
            SCALAR.validate_python(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "null", "value": None},
        {"kind": "boolean", "value": True},
        {"kind": "uint64", "value": "18446744073709551615"},
        {"kind": "float64", "value": -0.0},
        {"kind": "date", "value": "2024-02-29"},
        {"kind": "time", "value": "23:59:59.123456"},
        {"kind": "timestamp", "value": "2024-02-29T12:00:00.000001"},
        {"kind": "string", "value": "  e\u0301\n\U0001f642"},
    ],
)
def test_representative_scalar_discriminators_round_trip(payload):
    scalar = SCALAR.validate_python(payload)
    assert scalar.model_dump() == payload


def test_integer_decimal_float_and_temporal_boundaries_reject_malformed_values():
    malformed = [
        {"kind": "int64", "value": "01"},
        {"kind": "uint64", "value": "-1"},
        {"kind": "decimal", "value": "1.0", "precision": 3, "scale": 2},
        {"kind": "float64", "value": 1},
        {"kind": "date", "value": "2023-02-29"},
        {"kind": "time", "value": "23:59:60"},
        {"kind": "timestamp", "value": "2024-02-29T12:00:00Z"},
        {"kind": "timestamptz", "value": "2024-02-29T12:00:00"},
    ]
    for payload in malformed:
        with pytest.raises(ValidationError):
            SCALAR.validate_python(payload)


def test_new_runtime_identity_and_supplied_identity_remain_distinct():
    runtime = "123e4567-e89b-42d3-a456-426614174000"
    supplied = "123e4567-e89b-12d3-a456-426614174000"
    assert TypeAdapter(RuntimeUUID).validate_python(runtime) == runtime
    assert TypeAdapter(CanonicalUUID).validate_python(supplied) == supplied
    with pytest.raises(ValidationError):
        TypeAdapter(RuntimeUUID).validate_python(supplied)
    with pytest.raises(ValidationError):
        TypeAdapter(CanonicalUUID).validate_python(supplied.upper())


def test_existing_hello_export():
    assert hello() == "Hello from querivue-agent!"
