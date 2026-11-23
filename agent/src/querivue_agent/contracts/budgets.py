"""Strict budget snapshots, reservation decisions, and clock readings."""

from decimal import Decimal, localcontext
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from .common import (
    MoneyText, NonblankString, SafeCount, Scope, StrictRecord, TimestampText,
)
from .values import CanonicalUUID, RuntimeUUID


def _add_money(left: str, right: str) -> Decimal:
    with localcontext() as context:
        context.prec = 512
        return Decimal(left) + Decimal(right)


class CounterSnapshot(StrictRecord):
    limit: SafeCount
    used: SafeCount
    reserved: SafeCount
    unknown_reserved: SafeCount

    @model_validator(mode="after")
    def validate_totals(self) -> "CounterSnapshot":
        if self.unknown_reserved > self.reserved:
            raise ValueError("unknown_reserved cannot exceed reserved")
        if self.used + self.reserved > self.limit:
            raise ValueError("used plus reserved cannot exceed limit")
        return self


class MoneySnapshot(StrictRecord):
    limit: MoneyText
    used: MoneyText
    reserved: MoneyText
    unknown_reserved: MoneyText
    currency: Literal["USD"]

    @model_validator(mode="after")
    def validate_totals(self) -> "MoneySnapshot":
        if _add_money(self.unknown_reserved, "0") > _add_money(self.reserved, "0"):
            raise ValueError("unknown_reserved cannot exceed reserved")
        if _add_money(self.used, self.reserved) > _add_money(self.limit, "0"):
            raise ValueError("used plus reserved cannot exceed limit")
        return self


class CounterAmounts(StrictRecord):
    physical_requests: SafeCount
    logical_invocations: SafeCount
    input_tokens: SafeCount
    output_tokens: SafeCount
    tool_calls: SafeCount
    query_executions: SafeCount
    dispatch_attempts: SafeCount
    active_milliseconds: SafeCount
    wall_milliseconds: SafeCount
    output_bytes: SafeCount
    output_files: SafeCount


class BudgetCounters(StrictRecord):
    physical_requests: CounterSnapshot
    logical_invocations: CounterSnapshot
    input_tokens: CounterSnapshot
    output_tokens: CounterSnapshot
    tool_calls: CounterSnapshot
    query_executions: CounterSnapshot
    dispatch_attempts: CounterSnapshot
    active_milliseconds: CounterSnapshot
    wall_milliseconds: CounterSnapshot
    output_bytes: CounterSnapshot
    output_files: CounterSnapshot


class ProtectedReserve(StrictRecord):
    purpose: Literal["answer", "review", "finalization", "linked_intake", "cleanup"]
    counters: CounterAmounts
    cost_usd: MoneyText


class BudgetSnapshot(StrictRecord):
    scope: Scope
    revision: SafeCount
    counters: BudgetCounters
    cost: MoneySnapshot
    protected_reserves: list[ProtectedReserve]

    @field_validator("protected_reserves")
    @classmethod
    def unique_purposes(cls, value: list[ProtectedReserve]) -> list[ProtectedReserve]:
        purposes = [reserve.purpose for reserve in value]
        if len(purposes) != len(set(purposes)):
            raise ValueError("protected reserve purposes must be unique")
        return value


class ReservationRequest(StrictRecord):
    request_id: RuntimeUUID
    scope: Scope
    purpose: Literal["intake", "model", "tool", "dispatch", "review", "finalization", "cleanup"]
    counters: CounterAmounts
    cost_usd: MoneyText
    expected_revision: SafeCount
    idempotency_key: NonblankString


class BudgetAdmitted(StrictRecord):
    status: Literal["admitted"]
    reservation_id: RuntimeUUID
    request_id: CanonicalUUID
    snapshot: BudgetSnapshot


class BudgetDenied(StrictRecord):
    status: Literal["denied"]
    request_id: CanonicalUUID
    limit_kind: Literal[
        "physical_requests", "logical_invocations", "input_tokens", "output_tokens",
        "tool_calls", "query_executions", "dispatch_attempts", "active_milliseconds",
        "wall_milliseconds", "output_bytes", "output_files", "cost",
    ]
    reason: NonblankString
    snapshot: BudgetSnapshot


BudgetDecision = Annotated[BudgetAdmitted | BudgetDenied, Field(discriminator="status")]


class ClockReading(StrictRecord):
    utc_timestamp: TimestampText
    monotonic_milliseconds: SafeCount
    process_id: RuntimeUUID
    trusted: bool
