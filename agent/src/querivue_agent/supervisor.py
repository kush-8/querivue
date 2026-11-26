"""Supervisor decision logic."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from querivue_agent.contracts.control import (
    SupervisorDecision,
    ProposeQueue,
    StopDecision,
    InterpretationUpdate,
    ObligationUpdate,
    ObligationCheck,
    ObligationCheckItem,
    PartialAuthorization,
    BasisReference,
    UserMessageBasis,
    SupportTarget,
)
from querivue_agent.contracts.inputs import SupervisorInput
from querivue_agent.contracts.actions import Task, SQLAction, PythonAction, AnswerAction, ClarificationAction, DirectAnswer
from querivue_agent.contracts.common import SafeCount
from querivue_agent.contracts.content import BlockID
from querivue_agent.contracts.records import QueueReceipt
from querivue_agent.runtime.wrappers import WrapperContext, run_specialist
from querivue_agent.runtime.graph_state import RunState


async def decide(request: SupervisorInput, *, model) -> SupervisorDecision:
    """Make supervisor decision based on current state."""
    # For T13, implement a basic supervisor that proposes queue
    # In reality, this would call the model gateway

    # Check if we have evidence to answer directly
    if request.evidence and request.pending_tasks:
        # Propose analysis tasks
        return _propose_analysis_tasks(request)

    if request.outcomes and not request.pending_tasks:
        # Propose answer task
        return _propose_answer_task(request)

    # Default: stop with insufficient evidence
    return StopDecision(
        type="stop",
        expected_queue_revision=request.queue_revision,
        reason_code="insufficient_evidence",
        gap_refs=[],
        interpretation_updates=[],
        obligation_updates=[],
        obligation_check=None,
        partial_authorization=None,
    )


def _propose_analysis_tasks(request: SupervisorInput) -> ProposeQueue:
    """Propose analysis tasks (SQL/Python)."""
    pending_tasks = []

    for i, task in enumerate(request.pending_tasks):
        if isinstance(task, dict):
            task = Task(**task)
        pending_tasks.append({
            "kind": "existing_task",
            "task_id": task.task_id,
        })

    return ProposeQueue(
        type="propose_queue",
        expected_queue_revision=request.queue_revision,
        pending_tasks=pending_tasks,
        interpretation_updates=[],
        obligation_updates=[],
        obligation_check=None,
        partial_authorization=None,
    )


def _propose_answer_task(request: SupervisorInput) -> ProposeQueue:
    """Propose answer task."""
    # Create a new answer task
    task_key = BlockID("answer-1")
    action_key = BlockID("action-1")
    task_id = uuid4()
    action_id = uuid4()

    answer_action = AnswerAction(
        action_id=action_id,
        type="answer",
        objective="Create evidence-grounded answer",
        constraints={
            "metric_definitions": {},
            "filters": [],
            "date_windows": [],
            "analysis_timezone": None,
            "grain": None,
            "units": {},
        },
        evidence_ids=[eid for eid in request.evidence],
        chart_artifact_ids=[],
    )

    new_action = {
        "kind": "new_action",
        "action_key": action_key,
        "request": {
            "type": "answer",
            "objective": "Create evidence-grounded answer",
            "constraints": {
                "metric_definitions": {},
                "filters": [],
                "date_windows": [],
                "analysis_timezone": None,
                "grain": None,
                "units": {},
            },
            "evidence_ids": [str(eid) for eid in request.evidence],
            "chart_artifact_ids": [],
        },
    }

    new_task = {
        "kind": "new_task",
        "task_key": task_key,
        "type": "answer",
        "requires": [],
        "actions": [new_action],
    }

    return ProposeQueue(
        type="propose_queue",
        expected_queue_revision=request.queue_revision,
        pending_tasks=[new_task],
        interpretation_updates=[],
        obligation_updates=[],
        obligation_check=None,
        partial_authorization=None,
    )


async def run_supervisor_step(
    run_state: RunState,
    context: WrapperContext,
) -> RunState:
    """Run a supervisor step and update run state."""
    # Build supervisor input
    from querivue_agent.context import build_supervisor_input

    supervisor_input = build_supervisor_input(
        run_state=run_state,
        pending_tasks=run_state.pending_tasks,
        current_task=run_state.current_task,
        environment_manifest_id=UUID(context.artifacts if hasattr(context, 'artifacts') else "00000000-0000-0000-0000-000000000000"),
        policy_version="1.0",
        configuration_hash="config-v1",
        queue_revision=run_state.execution_status.get("queue_revision", 0),
        analysis_started=run_state.execution_status.get("analysis_started", False),
    )

    # Call model gateway (placeholder for T13)
    decision = await decide(supervisor_input, model=context.model_gateway)

    # Commit decision via authority
    from querivue_agent.runtime.authority import Authority
    from querivue_agent.contracts.records import QueueReceipt

    # In reality, this would be committed through authority
    # For now, update run state directly
    if decision.type == "propose_queue":
        run_state.pending_tasks = decision.pending_tasks
        run_state.execution_status["queue_revision"] = run_state.execution_status.get("queue_revision", 0) + 1
        run_state.phase = "planning"

    return run_state
