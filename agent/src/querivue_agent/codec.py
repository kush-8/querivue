"""Canonical wire encoding and digest boundaries for validated contract records."""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from collections.abc import Mapping
from datetime import datetime, time
from types import UnionType
from typing import Annotated, Any, TypeVar, Union, get_args, get_origin
from uuid import UUID

import rfc8785
from pydantic import BaseModel

from .config import RunConfig
from .contracts.common import Scope
from .contracts.catalog import PreparedSnapshotPayload
from .contracts.evaluation import FixtureCase
from .contracts.evidence import ChartArtifact, EvidenceRef, TabularEvidence
from .contracts.inputs import (
    AnalyticalReplyLink,
    ContextRecord,
    InterpretationRecord,
    LinkedReplyContext,
    ObligationRecord,
    PacketMetadata,
    ReviewInput,
    RevisionContext,
    RunInput,
    ThreadCandidate,
)
from .contracts.records import (
    AnswerResult,
    ClarificationQuestionRecord,
    DirectCandidate,
    NoticeResult,
    OperationDiagnostics,
    ReviewedCandidate,
)
from .contracts.values import (
    DateScalar,
    DecimalScalar,
    Float64Scalar,
    TimeScalar,
    TimestampScalar,
    TimestamptzScalar,
)


T = TypeVar("T", bound=BaseModel)
_MAX_SAFE_INTEGER = 2**53 - 1
_HASH = re.compile(r"[0-9a-f]{64}")
_FAMILY = re.compile(r"[a-z][a-z0-9-]*")
_SUPPORTED_FAMILIES = frozenset({"record", "packet", "review-input", "configuration", "typed-preview"})

# These fields are mathematical sets in the current contracts. Every other list is ordered.
_SET_FIELDS: dict[type[BaseModel], frozenset[str]] = {
    Scope: frozenset({"eligible_dataset_ids"}),
    RunInput: frozenset({"eligible_dataset_ids"}),
    PacketMetadata: frozenset({"dependencies"}),
    ContextRecord: frozenset({"dependencies"}),
    InterpretationRecord: frozenset({"dependencies"}),
    ObligationRecord: frozenset({"dependencies"}),
    ThreadCandidate: frozenset({"dependencies"}),
    LinkedReplyContext: frozenset({"dependencies"}),
    RevisionContext: frozenset({"dependencies"}),
    AnalyticalReplyLink: frozenset({"dependencies"}),
    EvidenceRef: frozenset({"dependencies"}),
    TabularEvidence: frozenset({"dependencies"}),
    ChartArtifact: frozenset({"dependencies"}),
    ClarificationQuestionRecord: frozenset({"source_dependencies"}),
    OperationDiagnostics: frozenset({"source_dependencies"}),
    ReviewedCandidate: frozenset({"dependencies"}),
    DirectCandidate: frozenset({"dependencies"}),
    AnswerResult: frozenset({"dependencies"}),
    NoticeResult: frozenset({"dependencies"}),
    PreparedSnapshotPayload: frozenset({"dependencies"}),
    FixtureCase: frozenset({"dependencies"}),
}


def _float_bits(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("non-finite floats are not canonical records")
    return struct.pack("!d", value).hex()


def _fixed_time(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if "T" in value else time.fromisoformat(value)
    result = parsed.isoformat(timespec="microseconds")
    return result


def _decimal_coefficient(value: DecimalScalar) -> str:
    negative = value.value.startswith("-")
    digits = value.value.removeprefix("-").replace(".", "").lstrip("0") or "0"
    return f"-{digits}" if negative and digits != "0" else digits


def _scalar_payload(value: BaseModel) -> dict[str, object] | None:
    if isinstance(value, DecimalScalar):
        return {"kind": "decimal", "precision": value.precision, "scale": value.scale, "value": _decimal_coefficient(value)}
    if isinstance(value, Float64Scalar):
        return {"kind": "float64", "value": _float_bits(value.value)}
    if isinstance(value, TimeScalar):
        return {"kind": "time", "value": _fixed_time(value.value)}
    if isinstance(value, TimestampScalar):
        return {"kind": "timestamp", "value": _fixed_time(value.value)}
    if isinstance(value, TimestamptzScalar):
        return {"kind": "timestamptz", "value": _fixed_time(value.value)}
    if isinstance(value, DateScalar):
        return {"kind": "date", "value": value.value}
    return None


def _normalize(value: object) -> object:
    if isinstance(value, BaseModel):
        scalar = _scalar_payload(value)
        if scalar is not None:
            return scalar
        fields = value.__class__.model_fields
        normalized = {name: _normalize(getattr(value, name)) for name in fields}
        for field in _SET_FIELDS.get(value.__class__, ()):
            items = normalized[field]
            if not isinstance(items, list):
                raise TypeError(f"set field {value.__class__.__name__}.{field} is not a list")
            encoded = [rfc8785.dumps(item) for item in items]
            if len(encoded) != len(set(encoded)):
                raise ValueError(f"set field {value.__class__.__name__}.{field} contains duplicates")
            normalized[field] = [item for _, item in sorted(zip(encoded, items, strict=True))]
        return normalized
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError("canonical object keys must be strings")
            key.encode("utf-8")
            result[key] = _normalize(item)
        return result
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if value is None or type(value) in (bool, str):
        if isinstance(value, str):
            value.encode("utf-8")
        return value
    if type(value) is int:
        if not 0 <= value <= _MAX_SAFE_INTEGER:
            raise ValueError("structural integer must be a nonnegative safe JSON integer")
        return value
    if type(value) is float:
        return {"kind": "float64", "value": _float_bits(value)}
    raise TypeError(f"unsupported canonical record value: {type(value).__name__}")


def canonical_bytes(record: Mapping[str, object]) -> bytes:
    """Return JCS bytes for validated values; retain nested models for schema metadata."""
    if not isinstance(record, Mapping):
        raise TypeError("record must be a mapping")
    return rfc8785.dumps(_normalize(record))


def _record_payload(record: Mapping[str, object], version: int) -> Mapping[str, object]:
    # This generic stored-reference envelope is the only v1 "record" kind. New concrete
    # kinds need their own family manifest; producers remain responsible for minting v4 IDs.
    expected = {"record_kind", "schema_version", "record_id", "scope", "payload", "digest"}
    if set(record) != expected or type(record.get("schema_version")) is not int or record.get("schema_version") != version:
        raise ValueError("record envelope shape or schema version is invalid")
    if record["record_kind"] != "record":
        raise ValueError("record_kind must bind the record digest family")
    if type(record["record_id"]) is not str or str(UUID(record["record_id"])) != record["record_id"]:
        raise ValueError("record_id must be a canonical UUID")
    validated_scope = Scope.model_validate(record["scope"], strict=True)
    if not isinstance(record["payload"], Mapping):
        raise ValueError("record payload must be an object")
    if type(record["digest"]) is not str or not _HASH.fullmatch(record["digest"]):
        raise ValueError("record digest must be lowercase SHA-256")
    return {
        key: validated_scope if key == "scope" else value
        for key, value in record.items()
        if key != "digest"
    }


def _digest_payload(family: str, version: int, record: Mapping[str, object]) -> Mapping[str, object]:
    if family == "record":
        return _record_payload(record, version)
    if family == "packet":
        validated = PacketMetadata.model_validate(record, strict=True)
        payload = _normalize(validated)
        assert isinstance(payload, dict)
        del payload["content_hash"]
        return payload
    if family == "review-input":
        validated = ReviewInput.model_validate(record, strict=True)
        payload = _normalize(validated)
        assert isinstance(payload, dict) and isinstance(payload["packet"], dict)
        del payload["packet"]["content_hash"]
        return payload
    if family == "configuration":
        validated = RunConfig.model_validate(record, strict=True)
        payload = _normalize(validated)
        assert isinstance(payload, dict)
        return payload
    return record


def record_digest(family: str, version: int, record: Mapping[str, object]) -> str:
    """Hash a supported v1 record using its explicit own-hash manifest."""
    if family not in _SUPPORTED_FAMILIES or not _FAMILY.fullmatch(family):
        raise ValueError("unknown record family")
    if type(version) is not int or version != 1:
        raise ValueError("unknown schema version")
    payload = _digest_payload(family, version, record)
    prefix = f"querivue/{family}/v{version}\n".encode("utf-8")
    return hashlib.sha256(prefix + canonical_bytes(payload)).hexdigest()


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object key: {key}")
        result[key] = value
    return result


def _scalar_input(value: Mapping[str, object], model: type[BaseModel]) -> dict[str, object]:
    result = dict(value)
    if model is Float64Scalar:
        encoded = result.get("value")
        if type(encoded) is not str or not re.fullmatch(r"[0-9a-f]{16}", encoded):
            raise ValueError("float64 value must be 16 lowercase hexadecimal digits")
        result["value"] = struct.unpack("!d", bytes.fromhex(encoded))[0]
    elif model is DecimalScalar:
        coefficient = result.get("value")
        scale = result.get("scale")
        precision = result.get("precision")
        if type(coefficient) is not str or not re.fullmatch(r"(?:0|-[1-9][0-9]*|[1-9][0-9]*)", coefficient):
            raise ValueError("decimal coefficient must be a canonical integer string")
        if type(precision) is not int or type(scale) is not int or not 1 <= precision <= 38 or not 0 <= scale <= precision:
            raise ValueError("decimal precision and scale are invalid")
        negative = coefficient.startswith("-")
        digits = coefficient.removeprefix("-").rjust(scale + 1, "0")
        text = digits if scale == 0 else f"{digits[:-scale]}.{digits[-scale:]}"
        result["value"] = f"-{text}" if negative else text
    elif model is TimeScalar and (
        type(result.get("value")) is not str
        or not re.fullmatch(r"[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}", result["value"])
    ):
        raise ValueError("time must have exactly six fractional digits")
    elif model is TimestampScalar and (
        type(result.get("value")) is not str
        or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}", result["value"])
    ):
        raise ValueError("timestamp must have exactly six fractional digits")
    elif model is TimestamptzScalar and (
        type(result.get("value")) is not str
        or not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}[+-](?:[01][0-9]|2[0-3]):[0-5][0-9]",
            result["value"],
        )
    ):
        raise ValueError("timestamptz must have six fractional digits and a numeric offset")
    return result


def _model_candidates(annotation: object) -> list[type[BaseModel]]:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]
    origin = get_origin(annotation)
    if origin is Annotated:
        return _model_candidates(get_args(annotation)[0])
    if origin in (Union, UnionType):
        return [candidate for arg in get_args(annotation) for candidate in _model_candidates(arg)]
    return []


def _choose_model(annotation: object, value: Mapping[str, object]) -> type[BaseModel] | None:
    candidates = _model_candidates(annotation)
    if len(candidates) == 1:
        return candidates[0]
    for candidate in candidates:
        for discriminator in ("kind", "tag", "role", "status"):
            field = candidate.model_fields.get(discriminator)
            if field is not None and value.get(discriminator) in get_args(field.annotation):
                return candidate
    return None


def _strip_annotated(annotation: object) -> object:
    while get_origin(annotation) is Annotated:
        annotation = get_args(annotation)[0]
    return annotation


def _union_member(annotation: object, origin: object) -> object | None:
    annotation = _strip_annotated(annotation)
    if get_origin(annotation) is origin:
        return annotation
    if get_origin(annotation) in (Union, UnionType):
        for member in get_args(annotation):
            member = _strip_annotated(member)
            if get_origin(member) is origin:
                return member
    return None


def _accepts_float(annotation: object) -> bool:
    annotation = _strip_annotated(annotation)
    if annotation is float:
        return True
    return get_origin(annotation) in (Union, UnionType) and any(
        _strip_annotated(arg) is float for arg in get_args(annotation)
    )


def _decode_value(value: object, annotation: object) -> object:
    list_annotation = _union_member(annotation, list)
    if isinstance(value, list):
        item_annotation = get_args(list_annotation)[0] if list_annotation is not None else Any
        return [_decode_value(item, item_annotation) for item in value]
    if isinstance(value, dict):
        if _accepts_float(annotation) and set(value) == {"kind", "value"} and value.get("kind") == "float64":
            encoded = value.get("value")
            if type(encoded) is not str or not re.fullmatch(r"[0-9a-f]{16}", encoded):
                raise ValueError("float64 value must be 16 lowercase hexadecimal digits")
            decoded_float = struct.unpack("!d", bytes.fromhex(encoded))[0]
            if not math.isfinite(decoded_float):
                raise ValueError("non-finite floats are not canonical records")
            return decoded_float
        model = _choose_model(annotation, value)
        if model is not None:
            source = _scalar_input(value, model)
            decoded = {
                name: _decode_value(source[name], field.annotation)
                for name, field in model.model_fields.items()
                if name in source
            }
            return {**source, **decoded}
        dict_annotation = _union_member(annotation, dict)
        args = get_args(dict_annotation) if dict_annotation is not None else ()
        item_annotation = args[1] if len(args) == 2 else Any
        return {key: _decode_value(item, item_annotation) for key, item in value.items()}
    return value


def _validate_json_tree(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            key.encode("utf-8")
            _validate_json_tree(item)
    elif isinstance(value, list):
        for item in value:
            _validate_json_tree(item)
    elif type(value) is str:
        value.encode("utf-8")
    elif type(value) is int and not 0 <= value <= _MAX_SAFE_INTEGER:
        raise ValueError("structural integer must be a nonnegative safe JSON integer")
    elif type(value) is float:
        if not math.isfinite(value):
            raise ValueError("non-finite floats are not canonical records")
        raise ValueError("raw JSON floats must use the float64 bit wire form")


def decode_record(data: bytes, model: type[T]) -> T:
    """Decode duplicate-safe JSON and validate it against a strict contract model."""
    if type(data) is not bytes:
        raise TypeError("data must be bytes")
    if not isinstance(model, type) or not issubclass(model, BaseModel):
        raise TypeError("model must be a Pydantic model type")
    if model.model_config.get("strict") is not True or model.model_config.get("extra") != "forbid":
        raise TypeError("model must be a strict extra-forbid contract model")
    try:
        parsed = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"invalid JSON constant: {value}")))
    except UnicodeDecodeError as exc:
        raise ValueError("record is not valid UTF-8") from exc
    if not isinstance(parsed, dict):
        raise ValueError("record JSON must be an object")
    _validate_json_tree(parsed)
    decoded = _decode_value(parsed, model)
    return model.model_validate(decoded, strict=True)
