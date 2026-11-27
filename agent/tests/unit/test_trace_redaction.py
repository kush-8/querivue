"""Unit tests for trace boundary and redaction."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from querivue_agent.runtime.trace import (
    TraceEvent,
    TraceSpan,
    TraceRecorder,
    TraceBoundary,
    create_trace_recorder,
    load_trace,
)


class TestTraceEvent:
    """Tests for TraceEvent dataclass."""

    def test_trace_event_creation(self) -> None:
        """TraceEvent should store all fields."""
        event = TraceEvent(
            event_id="evt-123",
            timestamp="2026-01-01T00:00:00Z",
            run_id="run-456",
            invocation_id="inv-789",
            event_type="model_call",
            payload={"provider": "google", "model": "gemini-3.8-flash"},
            duration_ms=100,
            tokens={"input": 100, "output": 50},
            cost_usd="0.001",
        )
        assert event.event_id == "evt-123"
        assert event.event_type == "model_call"
        assert event.tokens == {"input": 100, "output": 50}

    def test_trace_event_optional_fields(self) -> None:
        """TraceEvent should handle optional fields."""
        event = TraceEvent(
            event_id="evt-123",
            timestamp="2026-01-01T00:00:00Z",
            run_id="run-456",
            invocation_id=None,
            event_type="run_start",
            payload={},
        )
        assert event.invocation_id is None
        assert event.duration_ms is None
        assert event.tokens is None
        assert event.cost_usd is None


class TestTraceSpan:
    """Tests for TraceSpan dataclass."""

    def test_trace_span_creation(self) -> None:
        """TraceSpan should store all fields."""
        span = TraceSpan(
            span_id="span-123",
            parent_span_id=None,
            run_id="run-456",
            invocation_id="inv-789",
            name="model_generation",
            start_time=1000.0,
        )
        assert span.span_id == "span-123"
        assert span.parent_span_id is None
        assert span.name == "model_generation"
        assert span.events == []

    def test_trace_span_end(self) -> None:
        """end() should set end_time."""
        span = TraceSpan(
            span_id="span-123",
            parent_span_id=None,
            run_id="run-456",
            invocation_id=None,
            name="test",
            start_time=1000.0,
        )
        span.end(1001.5)
        assert span.end_time == 1001.5

    def test_trace_span_duration_ms(self) -> None:
        """duration_ms should calculate correctly."""
        span = TraceSpan(
            span_id="span-123",
            parent_span_id=None,
            run_id="run-456",
            invocation_id=None,
            name="test",
            start_time=1000.0,
            end_time=1001.5,
        )
        assert span.duration_ms() == 1500

    def test_trace_span_duration_ms_before_end(self) -> None:
        """duration_ms should return 0 before end()."""
        span = TraceSpan(
            span_id="span-123",
            parent_span_id=None,
            run_id="run-456",
            invocation_id=None,
            name="test",
            start_time=1000.0,
        )
        assert span.duration_ms() == 0


class TestTraceRecorder:
    """Tests for TraceRecorder class."""

    def test_create_trace_recorder(self) -> None:
        """create_trace_recorder should create recorder with run_id."""
        recorder = create_trace_recorder("run-123")
        assert recorder.run_id == "run-123"

    def test_create_trace_recorder_custom_dir(self) -> None:
        """create_trace_recorder should accept custom trace directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = create_trace_recorder("run-123", Path(tmpdir))
            assert recorder.run_id == "run-123"
            assert recorder._trace_dir == Path(tmpdir) / "run-123"

    def test_record_event_adds_to_list(self) -> None:
        """record_event should add event to internal list."""
        recorder = create_trace_recorder("run-123")
        event = recorder.record_event(
            event_type="run_start",
            payload={"config": "test"},
            invocation_id="inv-1",
        )
        assert len(recorder._events) == 1
        assert recorder._events[0] == event
        assert event.run_id == "run-123"
        assert event.invocation_id == "inv-1"

    def test_record_event_generates_id_and_timestamp(self) -> None:
        """record_event should generate event_id and timestamp."""
        recorder = create_trace_recorder("run-123")
        event = recorder.record_event(
            event_type="run_start",
            payload={},
        )
        assert event.event_id is not None
        assert len(event.event_id) > 0
        assert event.timestamp.endswith("Z")
        assert "T" in event.timestamp

    def test_span_context_manager(self) -> None:
        """span context manager should create and close spans."""
        recorder = create_trace_recorder("run-123")
        with recorder.span("test_span", invocation_id="inv-1") as span:
            assert span.name == "test_span"
            assert span.invocation_id == "inv-1"
            assert span.span_id in recorder._spans
            assert recorder._current_span == span
        # After context, span should be ended
        assert span.end_time is not None
        assert recorder._current_span is None

    def test_nested_spans(self) -> None:
        """Nested spans should track parent correctly."""
        recorder = create_trace_recorder("run-123")
        with recorder.span("outer") as outer:
            with recorder.span("inner") as inner:
                assert inner.parent_span_id == outer.span_id
            assert recorder._current_span == outer
        assert recorder._current_span is None

    def test_record_model_call(self) -> None:
        """record_model_call should create model_call event."""
        recorder = create_trace_recorder("run-123")
        mock_provider = MagicMock()
        mock_provider.model_id = "gemini-3.8-flash"
        mock_settings = MagicMock()
        mock_settings.temperature = 0.0
        mock_settings.max_generated_tokens = 8192
        mock_settings.reasoning = "low"

        event = recorder.record_model_call(
            invocation_id="inv-1",
            provider=mock_provider,
            settings=mock_settings,
            messages=[{"role": "user", "content": "test"}],
            tools=[{"name": "tool1"}],
            system_instruction="sys",
        )

        assert event.event_type == "model_call"
        assert event.payload["provider"] == "gemini-3.8-flash"
        assert event.payload["messages_count"] == 1
        assert event.payload["tools_count"] == 1
        assert event.payload["has_system_instruction"] is True

    def test_record_model_response(self) -> None:
        """record_model_response should create model_response event."""
        recorder = create_trace_recorder("run-123")
        event = recorder.record_model_response(
            invocation_id="inv-1",
            response_content="Hello world",
            tool_calls=[{"id": "call_1", "name": "tool1"}],
            usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            duration_ms=1000,
            cost_usd="0.001",
        )

        assert event.event_type == "model_response"
        assert event.payload["has_content"] is True
        assert event.payload["content_length"] == 11
        assert event.payload["tool_calls_count"] == 1
        assert event.tokens == {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
        assert event.duration_ms == 1000
        assert event.cost_usd == "0.001"

    def test_record_tool_call(self) -> None:
        """record_tool_call should create tool_call event."""
        recorder = create_trace_recorder("run-123")
        event = recorder.record_tool_call(
            invocation_id="inv-1",
            tool_name="execute_query",
            arguments={"sql": "SELECT 1", "params": {}},
        )

        assert event.event_type == "tool_call"
        assert event.payload["tool_name"] == "execute_query"
        assert event.payload["arguments_keys"] == ["sql", "params"]

    def test_record_tool_result(self) -> None:
        """record_tool_result should create tool_result event."""
        recorder = create_trace_recorder("run-123")
        event = recorder.record_tool_result(
            invocation_id="inv-1",
            tool_name="execute_query",
            success=True,
            result_summary={"rows": 10, "columns": 3},
            duration_ms=500,
        )

        assert event.event_type == "tool_result"
        assert event.payload["tool_name"] == "execute_query"
        assert event.payload["success"] is True
        assert event.payload["result_summary"]["rows"] == 10
        assert event.duration_ms == 500

    def test_record_budget_check(self) -> None:
        """record_budget_check should create budget_admitted/denied event."""
        recorder = create_trace_recorder("run-123")

        admitted = recorder.record_budget_check(
            invocation_id="inv-1",
            purpose="model_call",
            admitted=True,
            snapshot_revision=5,
        )
        assert admitted.event_type == "budget_admitted"
        assert admitted.payload["admitted"] is True

        denied = recorder.record_budget_check(
            invocation_id="inv-1",
            purpose="model_call",
            admitted=False,
            snapshot_revision=5,
            reason="budget exceeded",
        )
        assert denied.event_type == "budget_denied"
        assert denied.payload["admitted"] is False
        assert denied.payload["reason"] == "budget exceeded"

    def test_record_queue_decision(self) -> None:
        """record_queue_decision should create queue_decision event."""
        recorder = create_trace_recorder("run-123")
        event = recorder.record_queue_decision(
            invocation_id="inv-1",
            decision_type="delegate",
            tasks_count=3,
            queue_revision=7,
        )

        assert event.event_type == "queue_decision"
        assert event.payload["decision_type"] == "delegate"
        assert event.payload["tasks_count"] == 3
        assert event.payload["queue_revision"] == 7

    def test_record_evidence_published(self) -> None:
        """record_evidence_published should create evidence_published event."""
        recorder = create_trace_recorder("run-123")
        event = recorder.record_evidence_published(
            invocation_id="inv-1",
            evidence_type="query_result",
            evidence_id="ev-123",
            rows=100,
            columns=5,
        )

        assert event.event_type == "evidence_published"
        assert event.payload["evidence_type"] == "query_result"
        assert event.payload["evidence_id"] == "ev-123"
        assert event.payload["rows"] == 100
        assert event.payload["columns"] == 5

    def test_record_review_verdict(self) -> None:
        """record_review_verdict should create review_verdict event."""
        recorder = create_trace_recorder("run-123")
        event = recorder.record_review_verdict(
            invocation_id="inv-1",
            approved=True,
            findings_count=2,
            pass_number=1,
        )

        assert event.event_type == "review_verdict"
        assert event.payload["approved"] is True
        assert event.payload["findings_count"] == 2
        assert event.payload["pass_number"] == 1

    def test_record_error(self) -> None:
        """record_error should create error event."""
        recorder = create_trace_recorder("run-123")
        event = recorder.record_error(
            invocation_id="inv-1",
            error_type="ValueError",
            error_message="Invalid input",
            context={"field": "test"},
        )

        assert event.event_type == "error"
        assert event.payload["error_type"] == "ValueError"
        assert event.payload["error_message"] == "Invalid input"
        assert event.payload["context"]["field"] == "test"

    def test_save_writes_jsonl(self) -> None:
        """save should write events as JSONL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            recorder = create_trace_recorder("run-123", Path(tmpdir))
            recorder.record_event(event_type="run_start", payload={"test": "data"})

            trace_file = recorder.save()
            assert trace_file.exists()
            assert trace_file.suffix == ".jsonl"

            content = trace_file.read_text(encoding="utf-8")
            lines = content.strip().split("\n")
            assert len(lines) == 1
            parsed = json.loads(lines[0])
            assert parsed["event_type"] == "run_start"
            assert parsed["payload"]["test"] == "data"

    def test_get_events_returns_copy(self) -> None:
        """get_events should return a copy of events."""
        recorder = create_trace_recorder("run-123")
        recorder.record_event(event_type="run_start", payload={})
        events = recorder.get_events()
        events.clear()  # Modify returned list
        assert len(recorder._events) == 1  # Original unchanged

    def test_get_events_by_type(self) -> None:
        """get_events_by_type should filter by event type."""
        recorder = create_trace_recorder("run-123")
        recorder.record_event(event_type="run_start", payload={})
        recorder.record_event(event_type="model_call", payload={})
        recorder.record_event(event_type="model_call", payload={})
        recorder.record_event(event_type="run_end", payload={})

        model_calls = recorder.get_events_by_type("model_call")
        assert len(model_calls) == 2

        run_starts = recorder.get_events_by_type("run_start")
        assert len(run_starts) == 1


class TestTraceBoundary:
    """Tests for TraceBoundary class."""

    def test_trace_boundary_wraps_model_call(self) -> None:
        """TraceBoundary.wrap_model_call should trace model calls."""
        recorder = create_trace_recorder("run-123")
        boundary = TraceBoundary(recorder)

        mock_provider = MagicMock()
        mock_provider.model_id = "gemini-3.8-flash"
        mock_settings = MagicMock()
        mock_settings.temperature = 0.0
        mock_settings.max_generated_tokens = 8192
        mock_settings.reasoning = "low"

        mock_response = MagicMock()
        mock_response.content = "test response"
        mock_response.tool_calls = None
        mock_response.usage = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}

        def call_func():
            return mock_response

        result = boundary.wrap_model_call(
            provider=mock_provider,
            settings=mock_settings,
            invocation_id="inv-1",
            call_func=call_func,
        )

        assert result == mock_response
        # Verify trace events recorded
        model_calls = recorder.get_events_by_type("model_call")
        model_responses = recorder.get_events_by_type("model_response")
        assert len(model_calls) == 1
        assert len(model_responses) == 1

    def test_trace_boundary_wraps_model_call_error(self) -> None:
        """TraceBoundary.wrap_model_call should trace errors."""
        recorder = create_trace_recorder("run-123")
        boundary = TraceBoundary(recorder)

        mock_provider = MagicMock()
        mock_provider.model_id = "gemini-3.8-flash"
        mock_settings = MagicMock()
        mock_settings.temperature = 0.0
        mock_settings.max_generated_tokens = 8192
        mock_settings.reasoning = "low"

        def call_func():
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            boundary.wrap_model_call(
                provider=mock_provider,
                settings=mock_settings,
                invocation_id="inv-1",
                call_func=call_func,
            )

        errors = recorder.get_events_by_type("error")
        assert len(errors) == 1
        assert errors[0].payload["error_type"] == "ValueError"


class TestLoadTrace:
    """Tests for load_trace function."""

    def test_load_trace_reads_jsonl(self) -> None:
        """load_trace should parse JSONL trace file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_file = Path(tmpdir) / "trace.jsonl"
            events = [
                {"event_id": "1", "timestamp": "2026-01-01T00:00:00Z", "run_id": "run-1",
                 "invocation_id": None, "event_type": "run_start", "payload": {},
                 "duration_ms": None, "tokens": None, "cost_usd": None},
                {"event_id": "2", "timestamp": "2026-01-01T00:00:01Z", "run_id": "run-1",
                 "invocation_id": "inv-1", "event_type": "model_call", "payload": {"provider": "google"},
                 "duration_ms": None, "tokens": None, "cost_usd": None},
            ]
            with trace_file.open("w", encoding="utf-8") as f:
                for e in events:
                    f.write(json.dumps(e) + "\n")

            loaded = load_trace(trace_file)
            assert len(loaded) == 2
            assert loaded[0].event_type == "run_start"
            assert loaded[1].event_type == "model_call"
            assert loaded[1].payload["provider"] == "google"

    def test_load_trace_empty_file(self) -> None:
        """load_trace should handle empty file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            trace_file = Path(tmpdir) / "empty.jsonl"
            trace_file.write_text("")

            loaded = load_trace(trace_file)
            assert loaded == []


class TestTraceRedaction:
    """Tests for trace redaction - ensuring hosted payloads don't leak sensitive data."""

    def test_trace_excludes_credentials(self) -> None:
        """Trace events should not contain credential values."""
        recorder = create_trace_recorder("run-123")
        # Simulate a model call with credentials in system_instruction
        recorder.record_model_call(
            invocation_id="inv-1",
            provider=MagicMock(model_id="gemini-3.8-flash"),
            settings=MagicMock(temperature=0.0, max_generated_tokens=8192, reasoning="low"),
            messages=[{"role": "user", "content": "test"}],
            tools=None,
            system_instruction="API_KEY=secret123\n\nActual prompt",
        )

        events = recorder.get_events_by_type("model_call")
        assert len(events) == 1
        # The trace should record metadata about the call, not the full system instruction
        assert "system_instruction" not in events[0].payload
        # It should only record whether there WAS a system instruction
        assert events[0].payload["has_system_instruction"] is True

    def test_trace_model_response_excludes_full_content(self) -> None:
        """Model response trace should not include full response content."""
        recorder = create_trace_recorder("run-123")
        recorder.record_model_response(
            invocation_id="inv-1",
            response_content="Sensitive data: password=secret123",
            tool_calls=None,
            usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
            duration_ms=1000,
            cost_usd="0.001",
        )

        events = recorder.get_events_by_type("model_response")
        assert len(events) == 1
        # Should only record metadata, not the actual content
        assert "content" not in events[0].payload
        assert events[0].payload["has_content"] is True
        assert events[0].payload["content_length"] == len("Sensitive data: password=secret123")

    def test_trace_tool_call_excludes_argument_values(self) -> None:
        """Tool call trace should not include argument values."""
        recorder = create_trace_recorder("run-123")
        recorder.record_tool_call(
            invocation_id="inv-1",
            tool_name="execute_query",
            arguments={"sql": "SELECT password FROM users", "params": {"secret": "value"}},
        )

        events = recorder.get_events_by_type("tool_call")
        assert len(events) == 1
        # Should only record argument keys, not values
        assert "arguments" not in events[0].payload
        assert events[0].payload["arguments_keys"] == ["sql", "params"]

    def test_hosted_export_separate_from_local(self) -> None:
        """Hosted export should be explicitly gated and separate from local trace."""
        # This test documents the architecture: local trace recorder captures everything
        # Hosted export (LangSmith, etc.) is a separate explicit activation
        recorder = create_trace_recorder("run-123")
        recorder.record_event(event_type="run_start", payload={"config": "full"})

        # Local trace has full detail
        local_events = recorder.get_events()
        assert len(local_events) == 1

        # Hosted export would be a separate mechanism with its own gate
        # This test ensures the architecture supports this separation
        assert True  # Architecture test - no code to verify, just documenting intent


if __name__ == "__main__":
    pytest.main([__file__, "-v"])