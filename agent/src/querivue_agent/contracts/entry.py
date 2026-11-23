"""Entry assessment wire contracts and runtime availability outcome."""

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, Field

from .common import NonblankString, StrictRecord
from .values import CanonicalUUID


def _policy_reason(value: str) -> str:
    if len(value.encode("ascii", errors="ignore")) != len(value) or not re.fullmatch(
        r"[a-z][a-z0-9_]*", value,
    ) or len(value) > 64:
        raise ValueError("expected an ASCII lowercase policy identifier of at most 64 bytes")
    return value


def _text_2048(value: str) -> str:
    if len(value.encode("utf-8")) > 2048:
        raise ValueError("expected at most 2048 UTF-8 bytes")
    return value


PolicyReason = Annotated[str, Field(strict=True), AfterValidator(_policy_reason)]
Explanation = Annotated[NonblankString, AfterValidator(_text_2048)]


class EntryAccept(StrictRecord):
    disposition: Literal["accept"]
    policy_reason: PolicyReason
    explanation: Explanation


class EntryReject(StrictRecord):
    disposition: Literal["reject"]
    policy_reason: PolicyReason
    explanation: Explanation


class EntryClarify(StrictRecord):
    disposition: Literal["clarify"]
    policy_reason: PolicyReason
    explanation: Explanation
    question: Explanation


EntryAssessment = Annotated[EntryAccept | EntryReject | EntryClarify, Field(discriminator="disposition")]


class EntryUnavailable(StrictRecord):
    disposition: Literal["unavailable"]
    error_ref: CanonicalUUID
    explanation: Explanation
    retryable: bool


EntryOutcome = Annotated[EntryAccept | EntryReject | EntryClarify | EntryUnavailable, Field(discriminator="disposition")]
