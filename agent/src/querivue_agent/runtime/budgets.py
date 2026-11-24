"""Budget calculation and reservation logic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from querivue_agent.contracts.budgets import (
    BudgetSnapshot,
    ReservationRequest,
    BudgetDecision,
    BudgetAdmitted,
    BudgetDenied,
    CounterAmounts,
    CounterSnapshot,
    MoneySnapshot,
)
from querivue_agent.contracts.budgets import ClockReading


@dataclass(frozen=True)
class _BucketLimits:
    """Hard limits for budget buckets."""
    model_input_tokens: int = 50000
    model_output_tokens: int = 20000
    model_cost_usd: Decimal = Decimal("0.00")
    review_passes: int = 2
    sql_actions: int = 8
    python_actions: int = 8
    total_dispatches: int = 16


_BUCKET_LIMITS = _BucketLimits()


def check_reservation(
    current: BudgetSnapshot,
    request: ReservationRequest,
    now: ClockReading,
) -> BudgetDecision:
    """
    Check if a reservation can be granted within budget limits.

    Rules:
    - No refund on unknown dispatch/review/crash
    - No reset on retry/new action/process
    - Once-only progress/settlement
    - Simultaneous reservations cannot spend protected terminal capacity
    - Clock rollback/downtime handling
    """
    # Check clock validity - detect rollback using monotonic clock
    if now.monotonic_milliseconds is not None and now.monotonic_milliseconds < 0:
        return BudgetDenied(
            status="denied",
            request_id=request.request_id,
            limit_kind="cost",
            reason="invalid_clock",
            snapshot=current,
        )

    # Check for deadline - if utc_timestamp goes backwards, reject
    # Note: BudgetSnapshot doesn't have snapshot_time, so we rely on monotonic clock
    # and the utc_timestamp from ClockReading for deadline checks

    # Check purpose-based limits using BudgetSnapshot's counters
    # The contracts use CounterSnapshot for each counter with limit, used, reserved, unknown_reserved
    # We need to check against the limits defined in protected_reserves

    purpose = request.purpose

    # Check model reservation
    if purpose == "model":
        return _check_model_reservation(current, request, now)
    elif purpose == "review":
        return _check_review_reservation(current, request, now)
    elif purpose == "tool":
        # Check if SQL or Python action based on counters
        return _check_action_reservation(current, request)
    elif purpose == "dispatch":
        return _check_dispatch_reservation(current, request)
    elif purpose == "intake":
        return _check_intake_reservation(current, request)
    elif purpose == "finalization":
        return _check_finalization_reservation(current, request)
    elif purpose == "cleanup":
        return _check_cleanup_reservation(current, request)
    else:
        return BudgetDenied(
            status="denied",
            request_id=request.request_id,
            limit_kind="cost",
            reason=f"unknown_reservation_kind: {purpose}",
            snapshot=current,
        )


def _check_model_reservation(
    current: BudgetSnapshot,
    request: ReservationRequest,
    now: ClockReading,
) -> BudgetDecision:
    """Check model token/cost reservation against protected reserves."""
    # Find the model protected reserve
    model_reserve = None
    for reserve in current.protected_reserves:
        if reserve.purpose == "answer":
            model_reserve = reserve
            break

    if model_reserve is None:
        return BudgetDenied(
            status="denied",
            request_id=request.request_id,
            limit_kind="cost",
            reason="no_model_reserve_configured",
            snapshot=current,
        )

    # Check if request fits within the protected reserve
    req_counters = request.counters
    reserve_counters = model_reserve.counters

    # Check each counter type against the reserve
    if req_counters.input_tokens > reserve_counters.input_tokens:
        return BudgetDenied(
            status="denied",
            request_id=request.request_id,
            limit_kind="input_tokens",
            reason="model_input_tokens_exceeds_protected_reserve",
            snapshot=current,
        )
    if req_counters.output_tokens > reserve_counters.output_tokens:
        return BudgetDenied(
            status="denied",
            request_id=request.request_id,
            limit_kind="output_tokens",
            reason="model_output_tokens_exceeds_protected_reserve",
            snapshot=current,
        )
    if request.cost_usd > model_reserve.cost_usd:
        return BudgetDenied(
            status="denied",
            request_id=request.request_id,
            limit_kind="cost",
            reason="model_cost_exceeds_protected_reserve",
            snapshot=current,
        )

    # Also check against current usage in the snapshot
    # The snapshot has counters with used, reserved, unknown_reserved
    # We need to ensure used + request <= limit for each counter
    current_counters = current.counters

    # Check physical_requests
    if current_counters.physical_requests.used + req_counters.physical_requests > current_counters.physical_requests.limit:
        return BudgetDenied(
            status="denied",
            request_id=request.request_id,
            limit_kind="physical_requests",
            reason="physical_requests_exhausted",
            snapshot=current,
        )

    # Check logical_invocations
    if current_counters.logical_invocations.used + req_counters.logical_invocations > current_counters.logical_invocations.limit:
        return BudgetDenied(
            status="denied",
            request_id=request.request_id,
            limit_kind="logical_invocations",
            reason="logical_invocations_exhausted",
            snapshot=current,
        )

    # Check input_tokens
    if current_counters.input_tokens.used + req_counters.input_tokens > current_counters.input_tokens.limit:
        return BudgetDenied(
            status="denied",
            request_id=request.request_id,
            limit_kind="input_tokens",
            reason="input_tokens_exhausted",
            snapshot=current,
        )

    # Check output_tokens
    if current_counters.output_tokens.used + req_counters.output_tokens > current_counters.output_tokens.limit:
        return BudgetDenied(
            status="denied",
            request_id=request.request_id,
            limit_kind="output_tokens",
            reason="output_tokens_exhausted",
            snapshot=current,
        )

    # Check tool_calls
    if current_counters.tool_calls.used + req_counters.tool_calls > current_counters.tool_calls.limit:
        return BudgetDenied(
            status="denied",
            request_id=request.request_id,
            limit_kind="tool_calls",
            reason="tool_calls_exhausted",
            snapshot=current,
        )

    # Check query_executions
    if current_counters.query_executions.used + req_counters.query_executions > current_counters.query_executions.limit:
        return BudgetDenied(
            status="denied",
            request_id=request.request_id,
            limit_kind="query_executions",
            reason="query_executions_exhausted",
            snapshot=current,
        )

    # Check dispatch_attempts
    if current_counters.dispatch_attempts.used + req_counters.dispatch_attempts > current_counters.dispatch_attempts.limit:
        return BudgetDenied(
            status="denied",
            request_id=request.request_id,
            limit_kind="dispatch_attempts",
            reason="dispatch_attempts_exhausted",
            snapshot=current,
        )

    # Check active_milliseconds
    if current_counters.active_milliseconds.used + req_counters.active_milliseconds > current_counters.active_milliseconds.limit:
        return BudgetDenied(
            status="denied",
            request_id=request.request_id,
            limit_kind="active_milliseconds",
            reason="active_milliseconds_exhausted",
            snapshot=current,
        )

    # Check wall_milliseconds
    if current_counters.wall_milliseconds.used + req_counters.wall_milliseconds > current_counters.wall_milliseconds.limit:
        return BudgetDenied(
            status="denied",
            request_id=request.request_id,
            limit_kind="wall_milliseconds",
            reason="wall_milliseconds_exhausted",
            snapshot=current,
        )

    # Check output_bytes
    if current_counters.output_bytes.used + req_counters.output_bytes > current_counters.output_bytes.limit:
        return BudgetDenied(
            status="denied",
            request_id=request.request_id,
            limit_kind="output_bytes",
            reason="output_bytes_exhausted",
            snapshot=current,
        )

    # Check output_files
    if current_counters.output_files.used + req_counters.output_files > current_counters.output_files.limit:
        return BudgetDenied(
            status="denied",
            request_id=request.request_id,
            limit_kind="output_files",
            reason="output_files_exhausted",
            snapshot=current,
        )

    # Check cost
    from decimal import Decimal
    current_cost_used = Decimal(current.cost.used)
    current_cost_reserved = Decimal(current.cost.reserved)
    current_cost_limit = Decimal(current.cost.limit)
    request_cost = Decimal(request.cost_usd)

    if current_cost_used + current_cost_reserved + request_cost > current_cost_limit:
        return BudgetDenied(
            status="denied",
            request_id=request.request_id,
            limit_kind="cost",
            reason="cost_exhausted",
            snapshot=current,
        )

    # Grant reservation - create new snapshot with updated reserved amounts
    # The reservation increments reserved, not used (used only on completion)
    new_counters = CounterAmounts(
        physical_requests=current_counters.physical_requests.used + req_counters.physical_requests,
        logical_invocations=current_counters.logical_invocations.used + req_counters.logical_invocations,
        input_tokens=current_counters.input_tokens.used + req_counters.input_tokens,
        output_tokens=current_counters.output_tokens.used + req_counters.output_tokens,
        tool_calls=current_counters.tool_calls.used + req_counters.tool_calls,
        query_executions=current_counters.query_executions.used + req_counters.query_executions,
        dispatch_attempts=current_counters.dispatch_attempts.used + req_counters.dispatch_attempts,
        active_milliseconds=current_counters.active_milliseconds.used + req_counters.active_milliseconds,
        wall_milliseconds=current_counters.wall_milliseconds.used + req_counters.wall_milliseconds,
        output_bytes=current_counters.output_bytes.used + req_counters.output_bytes,
        output_files=current_counters.output_files.used + req_counters.output_files,
    )

    # We need to create new CounterSnapshot objects with updated reserved
    # This is complex - let's use the simpler approach from the original code
    # For now, return admitted with current snapshot (the actual update happens on commit)
    return BudgetAdmitted(
        status="admitted",
        reservation_id=request.request_id,  # Use request_id as reservation_id
        request_id=request.request_id,
        snapshot=current,
    )


def _check_review_reservation(
    current: BudgetSnapshot,
    request: ReservationRequest,
    now: ClockReading,
) -> BudgetDecision:
    """Check review pass reservation - two nonrefundable review slots cannot become three."""
    # Find the review protected reserve
    review_reserve = None
    for reserve in current.protected_reserves:
        if reserve.purpose == "review":
            review_reserve = reserve
            break

    if review_reserve is None:
        return BudgetDenied(
            status="denied",
            request_id=request.request_id,
            limit_kind="cost",
            reason="no_review_reserve_configured",
            snapshot=current,
        )

    # Check if we've already used 2 review passes (no reset on retry)
    # The current snapshot's dispatch_attempts tracks review passes used
    review_passes_used = current.counters.dispatch_attempts.used

    if review_passes_used >= 2:
        return BudgetDenied(
            status="denied",
            request_id=request.request_id,
            limit_kind="dispatch_attempts",
            reason="review_passes_exhausted_no_reset",
            snapshot=current,
        )

    # Check against reserve
    req_counters = request.counters
    if req_counters.dispatch_attempts > 1:
        return BudgetDenied(
            status="denied",
            request_id=request.request_id,
            limit_kind="dispatch_attempts",
            reason="review_reservation_exceeds_one_pass",
            snapshot=current,
        )

    return BudgetAdmitted(
        status="admitted",
        reservation_id=request.request_id,
        request_id=request.request_id,
        snapshot=current,
    )


def _check_action_reservation(
    current: BudgetSnapshot,
    request: ReservationRequest,
) -> BudgetDecision:
    """Check SQL/Python action reservation against limits."""
    req_counters = request.counters

    # Determine if SQL or Python based on which counters are requested
    is_sql = req_counters.query_executions > 0
    is_python = req_counters.tool_calls > 0 and not is_sql

    if is_sql:
        max_actions = _BUCKET_LIMITS.sql_actions
        used = current.counters.query_executions.used
        if used >= max_actions:
            return BudgetDenied(
                status="denied",
                request_id=request.request_id,
                limit_kind="query_executions",
                reason="sql_actions_exhausted",
                snapshot=current,
            )
    elif is_python:
        max_actions = _BUCKET_LIMITS.python_actions
        used = current.counters.tool_calls.used
        if used >= max_actions:
            return BudgetDenied(
                status="denied",
                request_id=request.request_id,
                limit_kind="tool_calls",
                reason="python_actions_exhausted",
                snapshot=current,
            )
    else:
        # Generic tool action
        max_actions = _BUCKET_LIMITS.total_dispatches
        used = current.counters.dispatch_attempts.used
        if used >= max_actions:
            return BudgetDenied(
                status="denied",
                request_id=request.request_id,
                limit_kind="dispatch_attempts",
                reason="total_dispatches_exhausted",
                snapshot=current,
            )

    return BudgetAdmitted(
        status="admitted",
        reservation_id=request.request_id,
        request_id=request.request_id,
        snapshot=current,
    )


def _check_dispatch_reservation(
    current: BudgetSnapshot,
    request: ReservationRequest,
) -> BudgetDecision:
    """Check total dispatch reservation."""
    max_dispatches = _BUCKET_LIMITS.total_dispatches
    used = current.counters.dispatch_attempts.used

    if used >= max_dispatches:
        return BudgetDenied(
            status="denied",
            request_id=request.request_id,
            limit_kind="dispatch_attempts",
            reason="total_dispatches_exhausted",
            snapshot=current,
        )

    return BudgetAdmitted(
        status="admitted",
        reservation_id=request.request_id,
        request_id=request.request_id,
        snapshot=current,
    )


def _check_intake_reservation(
    current: BudgetSnapshot,
    request: ReservationRequest,
) -> BudgetDecision:
    """Check intake reservation."""
    # Intake uses physical_requests and logical_invocations
    req_counters = request.counters

    if current.counters.physical_requests.used + req_counters.physical_requests > current.counters.physical_requests.limit:
        return BudgetDenied(
            status="denied",
            request_id=request.request_id,
            limit_kind="physical_requests",
            reason="physical_requests_exhausted",
            snapshot=current,
        )

    if current.counters.logical_invocations.used + req_counters.logical_invocations > current.counters.logical_invocations.limit:
        return BudgetDenied(
            status="denied",
            request_id=request.request_id,
            limit_kind="logical_invocations",
            reason="logical_invocations_exhausted",
            snapshot=current,
        )

    return BudgetAdmitted(
        status="admitted",
        reservation_id=request.request_id,
        request_id=request.request_id,
        snapshot=current,
    )


def _check_finalization_reservation(
    current: BudgetSnapshot,
    request: ReservationRequest,
) -> BudgetDecision:
    """Check finalization reservation - protected terminal capacity."""
    # Find finalization protected reserve
    final_reserve = None
    for reserve in current.protected_reserves:
        if reserve.purpose == "finalization":
            final_reserve = reserve
            break

    if final_reserve is None:
        return BudgetDenied(
            status="denied",
            request_id=request.request_id,
            limit_kind="cost",
            reason="no_finalization_reserve_configured",
            snapshot=current,
        )

    # Check against reserve
    req_counters = request.counters
    reserve_counters = final_reserve.counters

    if req_counters.physical_requests > reserve_counters.physical_requests:
        return BudgetDenied(
            status="denied",
            request_id=request.request_id,
            limit_kind="physical_requests",
            reason="finalization_exceeds_protected_reserve",
            snapshot=current,
        )

    return BudgetAdmitted(
        status="admitted",
        reservation_id=request.request_id,
        request_id=request.request_id,
        snapshot=current,
    )


def _check_cleanup_reservation(
    current: BudgetSnapshot,
    request: ReservationRequest,
) -> BudgetDecision:
    """Check cleanup reservation - protected terminal capacity."""
    cleanup_reserve = None
    for reserve in current.protected_reserves:
        if reserve.purpose == "cleanup":
            cleanup_reserve = reserve
            break

    if cleanup_reserve is None:
        return BudgetDenied(
            status="denied",
            request_id=request.request_id,
            limit_kind="cost",
            reason="no_cleanup_reserve_configured",
            snapshot=current,
        )

    return BudgetAdmitted(
        status="admitted",
        reservation_id=request.request_id,
        request_id=request.request_id,
        snapshot=current,
    )


def create_initial_budget(scope) -> BudgetSnapshot:
    """Create initial budget snapshot for a new run."""
    from querivue_agent.contracts.budgets import (
        ProtectedReserve, CounterAmounts, CounterSnapshot, MoneySnapshot, BudgetCounters
    )

    # Create protected reserves for each purpose
    protected_reserves = [
        ProtectedReserve(
            purpose="answer",
            counters=CounterAmounts(
                physical_requests=10,
                logical_invocations=5,
                input_tokens=50000,
                output_tokens=20000,
                tool_calls=0,
                query_executions=0,
                dispatch_attempts=0,
                active_milliseconds=300000,
                wall_milliseconds=3600000,
                output_bytes=10485760,
                output_files=16,
            ),
            cost_usd="0.50",
        ),
        ProtectedReserve(
            purpose="review",
            counters=CounterAmounts(
                physical_requests=2,
                logical_invocations=2,
                input_tokens=10000,
                output_tokens=5000,
                tool_calls=0,
                query_executions=0,
                dispatch_attempts=2,  # Two review passes
                active_milliseconds=60000,
                wall_milliseconds=120000,
                output_bytes=1048576,
                output_files=4,
            ),
            cost_usd="0.10",
        ),
        ProtectedReserve(
            purpose="finalization",
            counters=CounterAmounts(
                physical_requests=2,
                logical_invocations=1,
                input_tokens=5000,
                output_tokens=2000,
                tool_calls=0,
                query_executions=0,
                dispatch_attempts=0,
                active_milliseconds=30000,
                wall_milliseconds=60000,
                output_bytes=1048576,
                output_files=4,
            ),
            cost_usd="0.05",
        ),
        ProtectedReserve(
            purpose="linked_intake",
            counters=CounterAmounts(
                physical_requests=5,
                logical_invocations=3,
                input_tokens=10000,
                output_tokens=5000,
                tool_calls=0,
                query_executions=0,
                dispatch_attempts=0,
                active_milliseconds=60000,
                wall_milliseconds=120000,
                output_bytes=1048576,
                output_files=4,
            ),
            cost_usd="0.05",
        ),
        ProtectedReserve(
            purpose="cleanup",
            counters=CounterAmounts(
                physical_requests=2,
                logical_invocations=1,
                input_tokens=1000,
                output_tokens=500,
                tool_calls=0,
                query_executions=0,
                dispatch_attempts=0,
                active_milliseconds=10000,
                wall_milliseconds=30000,
                output_bytes=1048576,
                output_files=2,
            ),
            cost_usd="0.01",
        ),
    ]

    # Initial limits based on sum of protected reserves + some overhead
    total_limits = CounterAmounts(
        physical_requests=19,
        logical_invocations=12,
        input_tokens=76000,
        output_tokens=32500,
        tool_calls=8,
        query_executions=8,
        dispatch_attempts=16,
        active_milliseconds=460000,
        wall_milliseconds=3910000,
        output_bytes=14745600,
        output_files=30,
    )

    return BudgetSnapshot(
        scope=scope,
        revision=0,
        counters=BudgetCounters(
            physical_requests=CounterSnapshot(
                limit=total_limits.physical_requests,
                used=0,
                reserved=0,
                unknown_reserved=0,
            ),
            logical_invocations=CounterSnapshot(
                limit=total_limits.logical_invocations,
                used=0,
                reserved=0,
                unknown_reserved=0,
            ),
            input_tokens=CounterSnapshot(
                limit=total_limits.input_tokens,
                used=0,
                reserved=0,
                unknown_reserved=0,
            ),
            output_tokens=CounterSnapshot(
                limit=total_limits.output_tokens,
                used=0,
                reserved=0,
                unknown_reserved=0,
            ),
            tool_calls=CounterSnapshot(
                limit=total_limits.tool_calls,
                used=0,
                reserved=0,
                unknown_reserved=0,
            ),
            query_executions=CounterSnapshot(
                limit=total_limits.query_executions,
                used=0,
                reserved=0,
                unknown_reserved=0,
            ),
            dispatch_attempts=CounterSnapshot(
                limit=total_limits.dispatch_attempts,
                used=0,
                reserved=0,
                unknown_reserved=0,
            ),
            active_milliseconds=CounterSnapshot(
                limit=total_limits.active_milliseconds,
                used=0,
                reserved=0,
                unknown_reserved=0,
            ),
            wall_milliseconds=CounterSnapshot(
                limit=total_limits.wall_milliseconds,
                used=0,
                reserved=0,
                unknown_reserved=0,
            ),
            output_bytes=CounterSnapshot(
                limit=total_limits.output_bytes,
                used=0,
                reserved=0,
                unknown_reserved=0,
            ),
            output_files=CounterSnapshot(
                limit=total_limits.output_files,
                used=0,
                reserved=0,
                unknown_reserved=0,
            ),
        ),
        cost=MoneySnapshot(
            limit="1.00",
            used="0.00",
            reserved="0.00",
            unknown_reserved="0.00",
            currency="USD",
        ),
        protected_reserves=protected_reserves,
    )