"""Task dispatch and action execution."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

from querivue_agent.contracts.records import QueueReceipt, Task
from querivue_agent.contracts.control import SupervisorDecision, ProposeQueue
from querivue_agent.runtime.graph_state import RunState, Task as GraphTask
from querivue_agent.runtime.wrappers import (
    WrapperContext,
    run_specialist,
    get_specialist_wrapper,
    get_input_builder,
)
from querivue_agent.context import (
    build_supervisor_input,
    build_sql_input,
    build_python_input,
    build_answer_input,
    build_review_input,
    build_clarification_input,
)
async def dispatch_queue(
    run_state: RunState,
    decision: SupervisorDecision,
    context: WrapperContext,
) -> RunState:
    """Dispatch tasks from a supervisor decision."""
    if decision.type == "propose_queue":
        # Convert pending task proposals to committed tasks
        for task_proposal in decision.pending_tasks:
            if task_proposal.get("kind") == "existing_task":
                # Existing task reference
                task_id = UUID(task_proposal["task_id"])
                # Find in pending_tasks
                for t in run_state.pending_tasks:
                    if isinstance(t, dict) and t.get("task_id") == task_id:
                        run_state.current_task = t
                        break
            elif task_proposal.get("kind") == "new_task":
                # New task proposal - create task
                new_task = _create_task_from_proposal(task_proposal, run_state)
                run_state.pending_tasks.append(new_task)
                if run_state.current_task is None:
                    run_state.current_task = new_task

    run_state.phase = "analysis"
    return run_state


def _create_task_from_proposal(proposal: dict, run_state: RunState) -> dict:
    """Create a committed Task from a TaskProposal."""
    task_key = proposal["task_key"]
    task_type = proposal["type"]
    requires = proposal.get("requires", [])
    actions = []

    for action_proposal in proposal.get("actions", []):
        if action_proposal.get("kind") == "new_action":
            action_key = action_proposal["action_key"]
            request = action_proposal["request"]
            action_id = uuid4()

            if task_type == "analysis":
                if request["type"] == "sql":
                    action = {
                        "action_id": str(action_id),
                        "type": "sql",
                        "objective": request["objective"],
                        "constraints": request["constraints"],
                        "table_ids": request["table_ids"],
                        "input_evidence_ids": request["input_evidence_ids"],
                    }
                elif request["type"] == "python":
                    action = {
                        "action_id": str(action_id),
                        "type": "python",
                        "objective": request["objective"],
                        "constraints": request["constraints"],
                        "input_evidence_ids": request["input_evidence_ids"],
                        "required_outputs": request["required_outputs"],
                    }
                actions.append(action)
        elif action_proposal.get("kind") == "retry_action":
            # Retry existing action
            action_id = action_proposal["action_id"]
            actions.append({
                "action_id": action_id,
                "type": "retry",
                "failed_attempt": action_proposal["failed_attempt"],
                "result_ref": action_proposal["result_ref"],
            })

    return {
        "task_id": str(uuid4()),
        "type": task_type,
        "requires": requires,
        "actions": actions,
    }


async def execute_current_task(
    run_state: RunState,
    context: WrapperContext,
) -> RunState:
    """Execute the current task's actions."""
    if run_state.current_task is None:
        run_state.phase = "answer"
        return run_state

    task = run_state.current_task
    if isinstance(task, dict):
        task_type = task.get("type")
        actions = task.get("actions", [])
    else:
        task_type = task.type
        actions = task.actions

    for action in actions:
        if isinstance(action, dict):
            action_type = action.get("type")
            action_id = UUID(action["action_id"])
        else:
            action_type = action.type
            action_id = action.action_id

        if action_type in ("sql", "python"):
            # Execute specialist action
            run_state = await _execute_action(run_state, action, task_type, context)
        elif action_type == "retry":
            # Handle retry
            run_state = await _execute_action(run_state, action, action.get("original_type", "sql"), context)

    # After all actions complete, move to answer phase
    run_state.phase = "answer"
    run_state.current_task = None

    return run_state


async def _execute_action(
    run_state: RunState,
    action: dict,
    action_type: str,
    context: WrapperContext,
) -> RunState:
    """Execute a single action via specialist wrapper."""
    from querivue_agent.runtime.wrappers import run_specialist, get_input_builder, get_specialist_wrapper

    # Build specialist input
    if action_type == "sql":
        specialist_input = build_sql_input(
            run_state=run_state,
            task=run_state.current_task,
            action=action,
            attempt=run_state.execution_status.get("expected_attempt", 1),
            environment_manifest_id=UUID("00000000-0000-0000-0000-000000000000"),
            policy_version="1.0",
            configuration_hash="config-v1",
            tables=[],
            table_profiles=[],
        )
        role = "sql_specialist"
    elif action_type == "python":
        specialist_input = build_python_input(
            run_state=run_state,
            task=run_state.current_task,
            action=action,
            attempt=run_state.execution_status.get("expected_attempt", 1),
            environment_manifest_id=UUID("00000000-0000-0000-0000-000000000000"),
            policy_version="1.0",
            configuration_hash="config-v1",
        )
        role = "python_specialist"
    else:
        return run_state

    # Run specialist
    output = await run_specialist(
        run_state=run_state,
        role=role,
        task=run_state.current_task,
        action=action,
        context=context,
        attempt=run_state.execution_status.get("expected_attempt", 1),
    )

    # Record outcome
    from querivue_agent.runtime.graph_state import ActionOutcome
    outcome = ActionOutcome(
        task_id=run_state.current_task["task_id"] if isinstance(run_state.current_task, dict) else run_state.current_task.task_id,
        action_id=action["action_id"] if isinstance(action, dict) else action.action_id,
        attempt=run_state.execution_status.get("expected_attempt", 1),
        result_ref=str(uuid4()),
        result=output.result or {},
        evidence_ids=output.evidence_ids,
        chart_artifact_ids=output.chart_artifact_ids,
        status=output.status,
        error=output.error,
    )
    run_state.commit_outcome(outcome)

    return run_state


async def run_review(
    run_state: RunState,
    draft_id: UUID,
    context: WrapperContext,
) -> RunState:
    """Run review on a draft."""
    from querivue_agent.runtime.wrappers import run_specialist
    from querivue_agent.context import build_review_input

    # Find the draft
    draft = None
    for outcome in run_state.outcomes.values():
        if outcome.result and outcome.result.get("draft_id") == str(draft_id):
            draft = outcome.result
            break

    if draft is None:
        return run_state

    # Build review input
    # In reality, this would use the actual draft and draft_input
    # For now, skip review in T13

    run_state.phase = "review"
    return run_state


async def run_answer(
    run_state: RunState,
    context: WrapperContext,
) -> RunState:
    """Run answer specialist."""
    from querivue_agent.runtime.wrappers import run_specialist
    from querivue_agent.context import build_answer_input

    # Build answer input
    # In reality, this would use the actual action and evidence
    run_state.phase = "finalization"
    return run_state
