"""Trace boundary and observability for agent runs."""

from __future__ import annotations

import contextlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Literal

from querivue_agent.contracts.budgets import BudgetSnapshot
from querivue_agent.contracts.common import Scope
from querivue_agent.contracts.manifests import ProviderIdentity, InferenceSettings


@dataclass(frozen=True)
class TraceEvent:
    """Single trace event."""
    event_id: str
    timestamp: str
    run_id: str
    invocation_id: str | None
    event_type: Literal[
        "run_start", "run_end", "invocation_start", "invocation_end",
        "model_call", "model_response", "tool_call", "tool_result",
        "budget_check", "budget_admitted", "budget_denied",
        "queue_decision", "evidence_published", "review_verdict",
        "clarification_request", "clarification_reply",
        "checkpoint_save", "checkpoint_restore", "error",
    ]
    payload: dict[str, Any]
    duration_ms: int | None = None
    tokens: dict[str, int] | None = None
    cost_usd: str | None = None


@dataclass
class TraceSpan:
    """A trace span with start/end."""
    span_id: str
    parent_span_id: str | None
    run_id: str
    invocation_id: str | None
    name: str
    start_time: float
    end_time: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    events: list[TraceEvent] = field(default_factory=list)

    def end(self, end_time: float | None = None) -> None:
        self.end_time = end_time or time.time()

    def duration_ms(self) -> int:
        if self.end_time is None:
            return 0
        return int((self.end_time - self.start_time) * 1000)


class TraceRecorder:
    """Records trace events for a run."""

    def __init__(self, run_id: str, trace_dir: Path | None = None) -> None:
        self._run_id = run_id
        self._trace_dir = trace_dir or Path.cwd() / "traces" / run_id
        self._trace_dir.mkdir(parents=True, exist_ok=True)
        self._events: list[TraceEvent] = []
        self._spans: dict[str, TraceSpan] = {}
        self._current_span: TraceSpan | None = None

    @property
    def run_id(self) -> str:
        return self._run_id

    def record_event(
        self,
        event_type: TraceEvent["event_type"],
        payload: dict[str, Any],
        invocation_id: str | None = None,
        duration_ms: int | None = None,
        tokens: dict[str, int] | None = None,
        cost_usd: str | None = None,
    ) -> TraceEvent:
        """Record a trace event."""
        event = TraceEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            run_id=self._run_id,
            invocation_id=invocation_id,
            event_type=event_type,
            payload=payload,
            duration_ms=duration_ms,
            tokens=tokens,
            cost_usd=cost_usd,
        )
        self._events.append(event)

        # Add to current span if exists
        if self._current_span:
            self._current_span.events.append(event)

        return event

    @contextlib.contextmanager
    def span(
        self,
        name: str,
        invocation_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """Create a new span."""
        span_id = str(uuid.uuid4())
        parent_span_id = self._current_span.span_id if self._current_span else None
        span = TraceSpan(
            span_id=span_id,
            parent_span_id=parent_span_id,
            run_id=self._run_id,
            invocation_id=invocation_id,
            name=name,
            start_time=time.time(),
            metadata=metadata or {},
        )
        self._spans[span_id] = span
        old_span = self._current_span
        self._current_span = span
        try:
            yield span
        finally:
            span.end()
            self._current_span = old_span

    def record_model_call(
        self,
        invocation_id: str,
        provider: ProviderIdentity,
        settings: InferenceSettings,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        system_instruction: str | None,
    ) -> TraceEvent:
        """Record a model call."""
        return self.record_event(
            event_type="model_call",
            invocation_id=invocation_id,
            payload={
                "provider": provider.model_id,
                "model": provider.model_id,
                "settings": {
                    "temperature": settings.temperature,
                    "max_tokens": settings.max_generated_tokens,
                    "reasoning": settings.reasoning,
                },
                "messages_count": len(messages),
                "tools_count": len(tools) if tools else 0,
                "has_system_instruction": system_instruction is not None,
            },
        )

    def record_model_response(
        self,
        invocation_id: str,
        response_content: str | None,
        tool_calls: list[dict[str, Any]] | None,
        usage: dict[str, int] | None,
        duration_ms: int,
        cost_usd: str,
    ) -> TraceEvent:
        """Record a model response."""
        return self.record_event(
            event_type="model_response",
            invocation_id=invocation_id,
            payload={
                "has_content": response_content is not None,
                "content_length": len(response_content) if response_content else 0,
                "tool_calls_count": len(tool_calls) if tool_calls else 0,
                "finish_reason": "stop",  # Would be from response
            },
            duration_ms=duration_ms,
            tokens=usage,
            cost_usd=cost_usd,
        )

    def record_tool_call(
        self,
        invocation_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> TraceEvent:
        """Record a tool call."""
        return self.record_event(
            event_type="tool_call",
            invocation_id=invocation_id,
            payload={
                "tool_name": tool_name,
                "arguments_keys": list(arguments.keys()),
            },
        )

    def record_tool_result(
        self,
        invocation_id: str,
        tool_name: str,
        success: bool,
        result_summary: dict[str, Any],
        duration_ms: int,
    ) -> TraceEvent:
        """Record a tool result."""
        return self.record_event(
            event_type="tool_result",
            invocation_id=invocation_id,
            payload={
                "tool_name": tool_name,
                "success": success,
                "result_summary": result_summary,
            },
            duration_ms=duration_ms,
        )

    def record_budget_check(
        self,
        invocation_id: str | None,
        purpose: str,
        admitted: bool,
        snapshot_revision: int,
        reason: str | None = None,
    ) -> TraceEvent:
        """Record a budget check."""
        return self.record_event(
            event_type="budget_admitted" if admitted else "budget_denied",
            invocation_id=invocation_id,
            payload={
                "purpose": purpose,
                "admitted": admitted,
                "snapshot_revision": snapshot_revision,
                "reason": reason,
            },
        )

    def record_queue_decision(
        self,
        invocation_id: str,
        decision_type: str,
        tasks_count: int,
        queue_revision: int,
    ) -> TraceEvent:
        """Record a supervisor queue decision."""
        return self.record_event(
            event_type="queue_decision",
            invocation_id=invocation_id,
            payload={
                "decision_type": decision_type,
                "tasks_count": tasks_count,
                "queue_revision": queue_revision,
            },
        )

    def record_evidence_published(
        self,
        invocation_id: str,
        evidence_type: str,
        evidence_id: str,
        rows: int,
        columns: int,
    ) -> TraceEvent:
        """Record evidence publication."""
        return self.record_event(
            event_type="evidence_published",
            invocation_id=invocation_id,
            payload={
                "evidence_type": evidence_type,
                "evidence_id": evidence_id,
                "rows": rows,
                "columns": columns,
            },
        )

    def record_review_verdict(
        self,
        invocation_id: str,
        approved: bool,
        findings_count: int,
        pass_number: int,
    ) -> TraceEvent:
        """Record review verdict."""
        return self.record_event(
            event_type="review_verdict",
            invocation_id=invocation_id,
            payload={
                "approved": approved,
                "findings_count": findings_count,
                "pass_number": pass_number,
            },
        )

    def record_error(
        self,
        invocation_id: str | None,
        error_type: str,
        error_message: str,
        context: dict[str, Any] | None = None,
    ) -> TraceEvent:
        """Record an error."""
        return self.record_event(
            event_type="error",
            invocation_id=invocation_id,
            payload={
                "error_type": error_type,
                "error_message": error_message,
                "context": context or {},
            },
        )

    def save(self) -> Path:
        """Save trace to disk."""
        trace_file = self._trace_dir / f"trace_{self._run_id}.jsonl"
        with trace_file.open("w", encoding="utf-8") as f:
            for event in self._events:
                f.write(json.dumps(event.__dict__, separators=(",", ":")) + "\n")
        return trace_file

    def get_events(self) -> list[TraceEvent]:
        """Get all recorded events."""
        return list(self._events)

    def get_events_by_type(
        self,
        event_type: TraceEvent["event_type"],
    ) -> list[TraceEvent]:
        """Get events filtered by type."""
        return [e for e in self._events if e.event_type == event_type]


class TraceBoundary:
    """Trace boundary for separating trusted runtime from model interactions."""

    def __init__(self, recorder: TraceRecorder) -> None:
        self._recorder = recorder

    @property
    def recorder(self) -> TraceRecorder:
        return self._recorder

    def wrap_model_call(
        self,
        provider: ProviderIdentity,
        settings: InferenceSettings,
        invocation_id: str,
        call_func,
    ):
        """Wrap a model call with tracing."""
        start = time.time()
        self._recorder.record_model_call(
            invocation_id=invocation_id,
            provider=provider,
            settings=settings,
            messages=[],  # Would be passed in
            tools=None,
            system_instruction=None,
        )

        try:
            result = call_func()
            duration_ms = int((time.time() - start) * 1000)
            self._recorder.record_model_response(
                invocation_id=invocation_id,
                response_content=result.content if hasattr(result, 'content') else str(result),
                tool_calls=result.tool_calls if hasattr(result, 'tool_calls') else None,
                usage=result.usage if hasattr(result, 'usage') else None,
                duration_ms=duration_ms,
                cost_usd="0.00",  # Would be calculated
            )
            return result
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            self._recorder.record_error(
                invocation_id=invocation_id,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            raise


def create_trace_recorder(run_id: str, trace_dir: Path | None = None) -> TraceRecorder:
    """Create a new trace recorder for a run."""
    return TraceRecorder(run_id, trace_dir)


def load_trace(trace_file: Path) -> list[TraceEvent]:
    """Load trace events from a file."""
    events = []
    with trace_file.open("r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            events.append(TraceEvent(**data))
    return events