import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from querivue_agent.codec import canonical_bytes, decode_record, record_digest
from querivue_agent.config import RoleModelConfig, RunConfig, load_config
from querivue_agent.contracts.common import OwnerFence, Scope, StrictRecord
from querivue_agent.contracts.inputs import PacketMetadata
from querivue_agent.contracts.tools import ExecuteQueryRequest, PreviewRowsRequest
from querivue_agent.contracts.values import (
    BooleanScalar,
    DateScalar,
    DecimalScalar,
    Float64Scalar,
    Int64Scalar,
    NullScalar,
    StringScalar,
    TimeScalar,
    TimestampScalar,
    TimestamptzScalar,
    TypedScalar,
    Uint64Scalar,
)


V1 = "00000000-0000-1000-8000-000000000001"
V1B = "00000000-0000-1000-8000-000000000002"
V4 = "00000000-0000-4000-8000-000000000001"
HASH_A = "a" * 64
HASH_B = "b" * 64
GOLDEN = json.loads((Path(__file__).parents[1] / "fixtures" / "golden" / "canonical.json").read_text(encoding="utf-8"))
CONFIG = Path(__file__).parents[2] / "config" / "development.toml"


class CodecRecord(StrictRecord):
    scalar: TypedScalar
    setting: float | None = None
    scope: Scope
    ordered: list[str]
    metadata: dict[str, Any]


def fields(model: BaseModel) -> dict[str, object]:
    return {name: getattr(model, name) for name in model.__class__.model_fields}


def scope(*dataset_ids: str) -> Scope:
    return Scope(project_id=V1, chat_id=None, run_id=None, eligible_dataset_ids=list(dataset_ids))


def packet(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "packet_id": V4,
        "content_hash": HASH_A,
        "policy_version": "policy-1",
        "configuration_hash": HASH_B,
        "base_snapshot_id": V1,
        "selected_records": [],
        "dependencies": [],
        "coverage": [],
    }
    value.update(changes)
    return value


def _golden_models() -> dict[str, BaseModel]:
    return {
        "query-tagged-bounds-unicode": ExecuteQueryRequest(
            sql="SELECT\n  :i  😀",
            parameters={
                "b": BooleanScalar(kind="boolean", value=True),
                "i": Int64Scalar(kind="int64", value="-9223372036854775808"),
                "n": NullScalar(kind="null", value=None),
                "s": StringScalar(kind="string", value="  Café\n世界 😀  "),
                "u": Uint64Scalar(kind="uint64", value="18446744073709551615"),
            },
        ),
        "decimal-and-float-bits": ExecuteQueryRequest(
            sql="SELECT :decimal",
            parameters={
                "decimal": DecimalScalar(kind="decimal", value="-12.30", precision=4, scale=2),
                "max": Float64Scalar(kind="float64", value=float.fromhex("0x1.fffffffffffffp+1023")),
                "negative_zero": Float64Scalar(kind="float64", value=-0.0),
                "subnormal": Float64Scalar(kind="float64", value=float.fromhex("0x0.0000000000001p-1022")),
            },
        ),
        "temporal-micros-offsets": ExecuteQueryRequest(
            sql="SELECT 1",
            parameters={
                "date": DateScalar(kind="date", value="2026-01-02"),
                "time": TimeScalar(kind="time", value="03:04:05.1"),
                "timestamp": TimestampScalar(kind="timestamp", value="2026-01-02T03:04:05"),
                "timestamptz": TimestamptzScalar(kind="timestamptz", value="2026-01-02T03:04:05.1+05:30"),
                "zero": TimestamptzScalar(kind="timestamptz", value="2026-01-02T03:04:05Z"),
            },
        ),
        "explicit-set-order": OwnerFence(
            scope=Scope(project_id=V1, chat_id=V1B, run_id=V1, eligible_dataset_ids=[V1B, V1]),
            subject_kind="run", subject_id=V1, owner_id=V4,
            generation=1, attempt=1, expected_revision=0,
            lease_expires_at="2026-01-02T03:04:05.000000+00:00",
        ),
        "ordered-list-and-null": PreviewRowsRequest(table_id=V1, columns=["z", "a"], limit=2),
        "schema-defaults-and-null": RoleModelConfig(credential_env="ENTRY_TOKEN"),
    }


def _golden_digest_records() -> dict[str, tuple[str, dict[str, object]]]:
    envelope = {
        "record_kind": "record", "schema_version": 1, "record_id": V1,
        "scope": fields(scope(V1B, V1)), "payload": {"configuration_hash": HASH_A}, "digest": HASH_A,
    }
    return {
        "packet-own-hash": ("packet", packet()),
        "packet-coverage-changed": ("packet", packet(coverage=[{
            "category": "history", "reason": "omitted", "record_refs": [], "explanation": "none",
        }])),
        "packet-config-changed": ("packet", packet(configuration_hash=HASH_A)),
        "packet-dependency-changed": ("packet", packet(dependencies=[{"dataset_id": V1, "snapshot_id": V1B}])),
        "record-own-hash": ("record", envelope),
    }


def test_fixed_jcs_and_digest_golden_vectors() -> None:
    by_name = {item["name"]: item for item in GOLDEN}
    assert canonical_bytes({"\ue000": 1, "😀": 2}).decode() == by_name["utf16-key-order"]["canonical"]
    assert record_digest("typed-preview", 1, {"\ue000": 1, "😀": 2}) == by_name["utf16-key-order"]["digest"]
    for name, model in _golden_models().items():
        vector = by_name[name]
        payload = fields(model)
        assert canonical_bytes(payload).decode() == vector["canonical"]
        assert record_digest("typed-preview", 1, payload) == vector["digest"]
    for name, (family, payload) in _golden_digest_records().items():
        vector = by_name[name]
        assert canonical_bytes(payload).decode() == vector["canonical"]
        assert record_digest(family, 1, payload) == vector["digest"]


@pytest.mark.parametrize(
    ("scalar", "wire"),
    [
        (Float64Scalar(kind="float64", value=-0.0), "8000000000000000"),
        (Float64Scalar(kind="float64", value=float.fromhex("0x0.0000000000001p-1022")), "0000000000000001"),
        (Float64Scalar(kind="float64", value=float.fromhex("0x1.fffffffffffffp+1023")), "7fefffffffffffff"),
    ],
)
def test_float64_bits_round_trip_exactly(scalar: Float64Scalar, wire: str) -> None:
    value = CodecRecord(scalar=scalar, setting=-0.0, scope=scope(), ordered=[], metadata={})
    encoded = canonical_bytes(fields(value))
    assert f'"value":"{wire}"'.encode() in encoded
    decoded = decode_record(encoded, CodecRecord)
    assert decoded.scalar.value.hex() == scalar.value.hex()
    assert math.copysign(1.0, decoded.setting) == -1.0
    assert canonical_bytes(fields(decoded)) == encoded


def test_decimal_and_temporal_wire_forms_preserve_declared_meaning() -> None:
    decimal = CodecRecord(
        scalar=DecimalScalar(kind="decimal", value="-12.30", precision=4, scale=2),
        scope=scope(), ordered=[], metadata={},
    )
    encoded = canonical_bytes(fields(decimal))
    assert encoded == (
        b'{"metadata":{},"ordered":[],"scalar":{"kind":"decimal","precision":4,'
        b'"scale":2,"value":"-1230"},"scope":{"chat_id":null,"eligible_dataset_ids":[],'
        b'"project_id":"00000000-0000-1000-8000-000000000001","run_id":null},"setting":null}'
    )
    assert decode_record(encoded, CodecRecord).scalar.value == "-12.30"

    for scalar, expected in [
        (TimeScalar(kind="time", value="01:02:03.4"), "01:02:03.400000"),
        (TimestampScalar(kind="timestamp", value="2026-01-02T03:04:05"), "2026-01-02T03:04:05.000000"),
        (TimestamptzScalar(kind="timestamptz", value="2026-01-02T03:04:05Z"), "2026-01-02T03:04:05.000000+00:00"),
        (TimestamptzScalar(kind="timestamptz", value="2026-01-02T03:04:05.1+05:30"), "2026-01-02T03:04:05.100000+05:30"),
    ]:
        value = CodecRecord(scalar=scalar, scope=scope(), ordered=[], metadata={})
        wire = canonical_bytes(fields(value))
        assert expected.encode() in wire
        assert canonical_bytes(fields(decode_record(wire, CodecRecord))) == wire


@pytest.mark.parametrize(
    "scalar",
    [
        Int64Scalar(kind="int64", value="-9223372036854775808"),
        Int64Scalar(kind="int64", value="9223372036854775807"),
        Uint64Scalar(kind="uint64", value="18446744073709551615"),
    ],
)
def test_tagged_integer_bounds_are_strings_not_structural_numbers(scalar: TypedScalar) -> None:
    value = CodecRecord(scalar=scalar, scope=scope(), ordered=[], metadata={})
    encoded = canonical_bytes(fields(value))
    assert f'"value":"{scalar.value}"'.encode() in encoded
    assert decode_record(encoded, CodecRecord).scalar == scalar


def test_schema_context_sorts_only_explicit_sets_and_preserves_user_kind_value_dict() -> None:
    value = CodecRecord(
        scalar=Float64Scalar(kind="float64", value=1.0),
        scope=scope(V1B, V1),
        ordered=["z", "a"],
        metadata={"kind": "float64", "value": "not-a-scalar", "rows": [["b"], ["a"]]},
    )
    encoded = canonical_bytes(fields(value))
    assert b'"eligible_dataset_ids":["00000000-0000-1000-8000-000000000001","00000000-0000-1000-8000-000000000002"]' in encoded
    assert b'"ordered":["z","a"]' in encoded
    assert b'"metadata":{"kind":"float64","rows":[["b"],["a"]],"value":"not-a-scalar"}' in encoded
    assert decode_record(encoded, CodecRecord).metadata == value.metadata


def test_packet_manifest_excludes_only_own_hash_and_keeps_coverage_config_dependencies() -> None:
    baseline = packet()
    assert record_digest("packet", 1, baseline) == record_digest("packet", 1, packet(content_hash=HASH_B))
    assert record_digest("packet", 1, baseline) != record_digest("packet", 1, packet(configuration_hash=HASH_A))
    assert record_digest("packet", 1, baseline) != record_digest(
        "packet", 1, packet(coverage=[{"category": "history", "reason": "omitted", "record_refs": [], "explanation": "none"}]),
    )
    assert record_digest("packet", 1, baseline) != record_digest(
        "packet", 1, packet(dependencies=[{"dataset_id": V1, "snapshot_id": V1B}]),
    )
    first = {"dataset_id": V1, "snapshot_id": V1B}
    second = {"dataset_id": V1B, "snapshot_id": V1}
    assert record_digest("packet", 1, packet(dependencies=[first, second])) == record_digest(
        "packet", 1, packet(dependencies=[second, first])
    )


def test_record_envelope_excludes_only_digest_and_binds_scope_kind_version() -> None:
    envelope: dict[str, object] = {
        "record_kind": "record",
        "schema_version": 1,
        "record_id": V1,
        "scope": fields(scope(V1B, V1)),
        "payload": {"configuration_hash": HASH_A, "dependencies": ["b", "a"]},
        "digest": HASH_A,
    }
    assert record_digest("record", 1, envelope) == record_digest("record", 1, {**envelope, "digest": HASH_B})
    assert record_digest("record", 1, envelope) != record_digest(
        "record", 1, {**envelope, "payload": {"configuration_hash": HASH_B, "dependencies": ["b", "a"]}}
    )
    with pytest.raises(ValueError, match="record_kind"):
        record_digest("record", 1, {**envelope, "record_kind": "packet"})


def test_configuration_bytes_never_include_private_credentials() -> None:
    config = load_config(CONFIG, {})
    payload = config.public_payload()
    payload["models"] = {
        "entry": {
            "identity": None,
            "inference": {
                "reasoning": None,
                "temperature": -0.0,
                "seed": None,
                "max_generated_tokens": 1,
                "sampling_overrides_verified": True,
                "reasoning_in_output_budget": True,
            },
            "prompt_hash": None,
            "schema_hash": None,
            "credential_env": "ENTRY_TOKEN",
        }
    }
    config = RunConfig.model_validate(payload)
    secret = "credential-sentinel-do-not-serialize"
    config._set_credentials({"entry": secret})
    encoded = canonical_bytes(fields(config))
    assert secret.encode() not in encoded
    decoded = decode_record(encoded, RunConfig)
    assert math.copysign(1.0, decoded.models["entry"].inference.temperature) == -1.0
    assert canonical_bytes(fields(decoded)) == encoded
    assert record_digest("configuration", 1, config.public_payload())


def test_decode_rejects_duplicates_invalid_json_domains_and_lax_models() -> None:
    valid = b'{"scalar":{"kind":"float64","value":"3ff0000000000000"},"setting":null,"scope":{"project_id":"00000000-0000-1000-8000-000000000001","chat_id":null,"run_id":null,"eligible_dataset_ids":[]},"ordered":[],"metadata":{}}'
    for bad in [
        valid[:-1] + b',"metadata":{}}',
        valid.replace(b'"metadata":{}', b'"metadata":{"x":1,"x":2}'),
        valid.replace(b'"metadata":{}', b'"metadata":{"x":1e999}'),
        valid.replace(b'"metadata":{}', b'"metadata":{"x":1.5}'),
        valid.replace(b'"metadata":{}', b'"metadata":{"x":-1}'),
        valid.replace(b'"metadata":{}', b'"metadata":{"x":"\\ud800"}'),
        valid[:-1] + b',"unknown":1}',
        valid.replace(b'00000000-0000-1000-8000-000000000001', b'not-a-uuid'),
        valid.replace(b'3ff0000000000000', b'7ff0000000000000'),
        valid.replace(
            b'{"kind":"float64","value":"3ff0000000000000"}',
            b'{"kind":"decimal","precision":38,"scale":999999999,"value":"1"}',
        ),
    ]:
        with pytest.raises((ValueError, UnicodeEncodeError)):
            decode_record(bad, CodecRecord)

    class Lax(BaseModel):
        model_config = ConfigDict(extra="ignore")
        value: int

    with pytest.raises(TypeError, match="strict extra-forbid"):
        decode_record(b'{"value":1,"unknown":2}', Lax)


def test_unknown_family_version_and_unsupported_values_are_rejected() -> None:
    with pytest.raises(ValueError, match="unknown record family"):
        record_digest("future", 1, {})
    with pytest.raises(ValueError, match="unknown schema version"):
        record_digest("typed-preview", 2, {})
    envelope = _golden_digest_records()["record-own-hash"][1]
    with pytest.raises(ValueError, match="shape or schema version"):
        record_digest("record", 1, {**envelope, "schema_version": True})
    config = load_config(CONFIG, {}).public_payload()
    with pytest.raises(ValueError):
        decode_record(json.dumps({**config, "schema_version": 2}).encode(), RunConfig)
    with pytest.raises((TypeError, ValueError)):
        canonical_bytes({"object": object()})
    with pytest.raises(ValueError, match="non-finite"):
        canonical_bytes({"value": float("nan")})
    with pytest.raises(ValueError, match="nonnegative"):
        canonical_bytes({"value": -1})


def test_fresh_subprocess_decode_reencode_is_stable() -> None:
    script = """
import json, runpy
from pathlib import Path
from querivue_agent.codec import canonical_bytes, decode_record
ns = runpy.run_path('tests/unit/test_codec.py')
vectors = {item['name']: item for item in json.loads(Path('tests/fixtures/golden/canonical.json').read_text(encoding='utf-8'))}
for name, original in ns['_golden_models']().items():
    data = vectors[name]['canonical'].encode()
    decoded = decode_record(data, type(original))
    assert canonical_bytes(ns['fields'](decoded)) == data, name
print('stable')
"""
    result = subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)
    assert result.stdout.strip() == "stable"
