import math

import pytest
from pydantic import TypeAdapter, ValidationError

from querivue_agent import hello
from querivue_agent.contracts.values import RuntimeUUID, TypedScalar


SCALAR = TypeAdapter(TypedScalar)


@pytest.mark.parametrize("payload", [
    {"kind": "null", "value": None},
    {"kind": "boolean", "value": True},
    {"kind": "int64", "value": "-9223372036854775808"},
    {"kind": "int64", "value": "9223372036854775807"},
    {"kind": "int64", "value": "0"},
    {"kind": "uint64", "value": "18446744073709551615"},
    {"kind": "uint64", "value": "0"},
    {"kind": "decimal", "value": "1.00", "precision": 3, "scale": 2},
    {"kind": "decimal", "value": "0.01", "precision": 2, "scale": 2},
    {"kind": "decimal", "value": "9" * 38, "precision": 38, "scale": 0},
    {"kind": "float64", "value": -0.0},
    {"kind": "string", "value": "  e\u0301\n\U0001f642"},
    {"kind": "date", "value": "2024-02-29"},
    {"kind": "time", "value": "23:59:59.123456"},
    {"kind": "timestamp", "value": "2024-02-29T12:00:00.000001"},
    {"kind": "timestamptz", "value": "2024-02-29T12:00:00.123456+05:30"},
    {"kind": "timestamptz", "value": "2024-02-29T12:00:00-04:00"},
    {"kind": "timestamptz", "value": "2024-02-29T12:00:00-23:59"},
    {"kind": "timestamptz", "value": "2024-02-29T12:00:00Z"},
])
def test_valid_scalars_preserve_external_values(payload):
    result = SCALAR.validate_python(payload)
    assert result.model_dump() == payload
    assert SCALAR.validate_json(result.model_dump_json()).model_dump() == payload
    if payload["kind"] == "float64":
        assert math.copysign(1, result.value) == -1
        assert math.copysign(1, SCALAR.validate_json(result.model_dump_json()).value) == -1


@pytest.mark.parametrize("kind,value", [
    ("int64", "9223372036854775808"),
    ("int64", "-9223372036854775809"),
    ("int64", "9" * 5000),
    ("uint64", "18446744073709551616"),
    ("uint64", "-1"),
    *[(kind, value) for kind in ("int64", "uint64")
      for value in ("+1", "01", "-0", "1.0", " 1", "1\n", "١", 1, True, b"1")],
    ("null", "null"),
    *[("boolean", value) for value in (0, 1, "true", None)],
    *[("float64", value) for value in (float("inf"), float("-inf"), float("nan"), 1, True, "1.0")],
    *[("string", value) for value in (1, b"text", "\ud800", "\udfff")],
    ("date", "2023-02-29"),
    ("date", "0000-01-01"),
    ("date", "20240229"),
    ("date", "2024-W09-4"),
    ("time", "24:00:00"),
    ("time", "23:59:60"),
    ("time", "12:00"),
    ("time", "12:00:00+05:30"),
    ("time", "12:00:00.1234567"),
    ("timestamp", "2024-02-29 12:00:00"),
    ("timestamp", "2024-02-29T12:00:00Z"),
    ("timestamp", "2024-02-29T12:00:00.1234567"),
    ("timestamp", "2024-02-30T12:00:00"),
    ("timestamptz", "2024-02-29T12:00:00"),
    ("timestamptz", "2024-02-29T12:00:00+0530"),
    ("timestamptz", "2024-02-29T12:00:00+00:60"),
    ("timestamptz", "2024-02-29T12:00:00+24:00"),
    ("timestamptz", "2024-02-29T12:00:00-00:60"),
    ("timestamptz", "2024-02-29T12:00:00-24:00"),
    ("timestamptz", "2024-02-29T12:00:00.1234567+05:30"),
    ("unknown", "anything"),
    ("date", 20240229),
    ("time", 120000),
    ("timestamp", None),
    ("timestamptz", True),
])
def test_rejects_invalid_scalars(kind, value):
    with pytest.raises(ValidationError):
        SCALAR.validate_python({"kind": kind, "value": value})


@pytest.mark.parametrize("updates", [
    {"precision": 0}, {"precision": 39}, {"precision": True}, {"precision": "3"},
    {"scale": -1}, {"scale": 4}, {"scale": True}, {"scale": 2.0},
    {"value": "1.001"}, {"value": "1.0"}, {"value": "10.00"},
    {"value": "1e0"}, {"value": "+1.00"}, {"value": "01.00"}, {"value": 1.0},
])
def test_decimal_requires_exact_declared_precision_and_scale(updates):
    payload = {"kind": "decimal", "value": "1.00", "precision": 3, "scale": 2}
    with pytest.raises(ValidationError):
        SCALAR.validate_python(payload | updates)


@pytest.mark.parametrize("extra", ["owner", "budget", "unexpected"])
@pytest.mark.parametrize("kind,value", [("string", "x"), ("int64", "1"), ("null", None)])
def test_forbids_unknown_fields(extra, kind, value):
    with pytest.raises(ValidationError):
        SCALAR.validate_python({"kind": kind, "value": value, extra: 1})


def test_requires_discriminator_and_value():
    for payload in ({}, {"value": 1}, {"kind": "null"}):
        with pytest.raises(ValidationError):
            SCALAR.validate_python(payload)


def test_runtime_uuid_preserves_canonical_v4():
    value = "123e4567-e89b-42d3-a456-426614174000"
    assert TypeAdapter(RuntimeUUID).validate_python(value) == value


@pytest.mark.parametrize("value", [
    "123E4567-E89B-42D3-A456-426614174000",
    "123e4567e89b42d3a456426614174000",
    "{123e4567-e89b-42d3-a456-426614174000}",
    "123e4567-e89b-12d3-a456-426614174000",
    "123e4567-e89b-42d3-7456-426614174000",
    "invalid", 123, b"123e4567-e89b-42d3-a456-426614174000",
])
def test_rejects_noncanonical_runtime_uuid(value):
    with pytest.raises(ValidationError):
        TypeAdapter(RuntimeUUID).validate_python(value)


def test_existing_hello_export():
    assert hello() == "Hello from querivue-agent!"
