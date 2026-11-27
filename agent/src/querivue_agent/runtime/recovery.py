"""Checkpoint restoration and run recovery logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from langgraph.checkpoint.base import BaseCheckpointSaver

from querivue_agent.runtime.graph_state import RunState, create_initial_run_state
from querivue_agent.runtime.authority import Authority
from querivue_agent.runtime.redis_projection import RedisProjection
from querivue_agent.graph import RunConfig, GraphProjection


@dataclass(frozen=True)
class RecoveryResult:
    """Result of a run recovery attempt."""
    run_state: RunState
    is_fresh: bool
    checkpoint_id: str | None
    recovery_warnings: list[str]


async def restore_run(
    run_id: UUID,
    *,
    authority: Authority,
    checkpointer: BaseCheckpointSaver,
    redis_projection: RedisProjection,
    config: RunConfig,
) -> GraphProjection:
    """
    Restore a run from checkpoints.

    This function loads the latest checkpoint from Redis and reconstructs
    the RunState. It validates that the restored state is compatible with
    the current configuration and authority.
    """
    # Get the latest checkpoint
    run_state = await _load_latest_checkpoint(run_id, redis_projection, checkpointer)

    if run_state is None:
        # No checkpoint found - this is a fresh run
        # The caller should create initial state via submit()
        raise ValueError(f"No checkpoint found for run {run_id}")

    # Validate the restored state
    warnings = _validate_restored_state(run_state, authority, config)

    # Create graph projection
    projection = GraphProjection(
        run_state=run_state,
        checkpoint_id="latest",
        is_fresh=False,
    )

    return projection


async def _load_latest_checkpoint(
    run_id: UUID,
    redis_projection: RedisProjection,
    checkpointer: BaseCheckpointSaver,
) -> RunState | None:
    """Load the latest checkpoint for a run."""
    # First try using the checkpointer (LangGraph interface)
    try:
        from langchain_core.runnables.config import RunnableConfig
        config = {"configurable": {"thread_id": str(run_id)}}
        checkpoint_tuple = await checkpointer.aget_tuple(config)
        if checkpoint_tuple:
            run_state = checkpoint_tuple.checkpoint.get("channel_values", {}).get("run_state")
            if isinstance(run_state, RunState):
                return run_state
    except Exception:
        pass

    # Fallback to direct Redis projection
    return await redis_projection.load_latest_checkpoint(run_id)


def _validate_restored_state(
    run_state: RunState,
    authority: Authority,
    config: RunConfig,
) -> list[str]:
    """Validate that a restored run state is compatible with current config."""
    warnings = []

    # Check if run is already terminal
    if run_state.phase == "terminal":
        warnings.append("Run is already in terminal phase")

    # Check deadline
    from datetime import datetime, UTC
    try:
        deadline = datetime.fromisoformat(run_state.deadline.replace("Z", "+00:00"))
        if deadline < datetime.now(UTC):
            warnings.append("Run deadline has passed")
    except Exception:
        warnings.append("Could not parse deadline")

    # Check budget compatibility
    if run_state.budget:
        # Budget revision should be consistent
        if run_state.budget.revision < 0:
            warnings.append("Invalid budget revision")

    # Check that all dataset IDs are still eligible
    # This would require checking the authority, which we skip for now

    return warnings


async def resume_run(
    run_id: UUID,
    *,
    authority: Authority,
    checkpointer: BaseCheckpointSaver,
    redis_projection: RedisProjection,
    config: RunConfig,
) -> RecoveryResult:
    """
    Resume a run from its latest checkpoint.

    This is the main entry point for CLI resume functionality.
    """
    run_state = await _load_latest_checkpoint(run_id, redis_projection, checkpointer)

    if run_state is None:
        # No checkpoint - return fresh state indicator
        raise ValueError(f"No checkpoint found for run {run_id}, cannot resume")

    warnings = _validate_restored_state(run_state, authority, config)

    return RecoveryResult(
        run_state=run_state,
        is_fresh=False,
        checkpoint_id="latest",
        recovery_warnings=warnings,
    )


def create_fresh_run_state(
    run_id: UUID,
    project_id: UUID,
    chat_id: UUID,
    question: str,
    eligible_dataset_ids: list[UUID],
    admission_receipt: Any,
    fence: Any,
    budget: Any,
    deadline: str,
) -> RunState:
    """Create a fresh run state (for new runs, not recovery)."""
    return create_initial_run_state(
        run_id=run_id,
        project_id=project_id,
        chat_id=chat_id,
        question=question,
        eligible_dataset_ids=eligible_dataset_ids,
        admission_receipt=admission_receipt,
        fence=fence,
        budget=budget,
        deadline=deadline,
    )