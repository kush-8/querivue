"""Strict external scalar values; decoding and canonical encoding are separate."""

import math
import re
from collections.abc import Callable
from datetime import date, datetime, time
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator


def _unicode(value: str) -> str:
    value.encode("utf-8")
    return value


UnicodeString = Annotated[str, AfterValidator(_unicode)]


def _uuid4(value: str) -> str:
    parsed = UUID(value)
    if str(parsed) != value or parsed.version != 4:
        raise ValueError("expected a canonical lowercase hyphenated UUID v4")
    return value


def _canonical_uuid(value: str) -> str:
    if str(UUID(value)) != value:
        raise ValueError("expected a canonical lowercase hyphenated UUID")
    return value


CanonicalUUID = Annotated[str, Field(strict=True), AfterValidator(_canonical_uuid)]
RuntimeUUID = Annotated[str, Field(strict=True), AfterValidator(_uuid4)]


class _Scalar(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class NullScalar(_Scalar):
    kind: Literal["null"]
    value: None


class BooleanScalar(_Scalar):
    kind: Literal["boolean"]
    value: bool


class Int64Scalar(_Scalar):
    kind: Literal["int64"]
    value: str

    @field_validator("value")
    @classmethod
    def validate_integer(cls, value: str) -> str:
        if not re.fullmatch(r"(?:0|-[1-9][0-9]*|[1-9][0-9]*)", value):
            raise ValueError("expected a canonical decimal integer string")
        # Compare digit strings so arbitrarily large untrusted inputs cannot overflow conversion.
        digits = value.removeprefix("-")
        limit = "9223372036854775808" if value.startswith("-") else "9223372036854775807"
        if len(digits) > len(limit) or (len(digits) == len(limit) and digits > limit):
            raise ValueError("int64 out of range")
        return value


class Uint64Scalar(_Scalar):
    kind: Literal["uint64"]
    value: str

    @field_validator("value")
    @classmethod
    def validate_integer(cls, value: str) -> str:
        if not re.fullmatch(r"(?:0|[1-9][0-9]*)", value):
            raise ValueError("expected a canonical unsigned decimal integer string")
        limit = "18446744073709551615"
        if len(value) > len(limit) or (len(value) == len(limit) and value > limit):
            raise ValueError("uint64 out of range")
        return value


class DecimalScalar(_Scalar):
    kind: Literal["decimal"]
    value: str
    precision: int = Field(ge=1, le=38)
    scale: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_decimal(self) -> "DecimalScalar":
        if self.scale > self.precision:
            raise ValueError("scale exceeds precision")
        if not re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", self.value):
            raise ValueError("expected a plain decimal string")
        integer, _, fraction = self.value.removeprefix("-").partition(".")
        if len(fraction) != self.scale:
            raise ValueError("fractional digits must exactly match scale")
        if len(integer.lstrip("0")) > self.precision - self.scale:
            raise ValueError("decimal exceeds declared precision")
        return self


class Float64Scalar(_Scalar):
    kind: Literal["float64"]
    value: float

    @field_validator("value", mode="before")
    @classmethod
    def validate_float(cls, value: object) -> float:
        if type(value) is not float or not math.isfinite(value):
            raise ValueError("expected a finite float")
        return value


class StringScalar(_Scalar):
    kind: Literal["string"]
    value: UnicodeString


_DATE = r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
_TIME = r"[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?"


def _temporal(value: str, pattern: str, parse: Callable[[str], object]) -> str:
    if not re.fullmatch(pattern, value):
        raise ValueError("expected ISO temporal value with at most microsecond precision")
    parse(value)
    return value


class DateScalar(_Scalar):
    kind: Literal["date"]
    value: str

    @field_validator("value")
    @classmethod
    def validate_date(cls, value: str) -> str:
        return _temporal(value, _DATE, date.fromisoformat)


class TimeScalar(_Scalar):
    kind: Literal["time"]
    value: str

    @field_validator("value")
    @classmethod
    def validate_time(cls, value: str) -> str:
        return _temporal(value, _TIME, time.fromisoformat)


class TimestampScalar(_Scalar):
    kind: Literal["timestamp"]
    value: str

    @field_validator("value")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        return _temporal(value, _DATE + "T" + _TIME, datetime.fromisoformat)


class TimestamptzScalar(_Scalar):
    kind: Literal["timestamptz"]
    value: str

    @field_validator("value")
    @classmethod
    def validate_timestamp(cls, value: str) -> str:
        return _temporal(
            value,
            _DATE + "T" + _TIME + r"(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])",
            datetime.fromisoformat,
        )


TypedScalar = Annotated[
    NullScalar | BooleanScalar | Int64Scalar | Uint64Scalar | DecimalScalar
    | Float64Scalar | StringScalar | DateScalar | TimeScalar | TimestampScalar | TimestamptzScalar,
    Field(discriminator="kind"),
]
