"""Redis checkpoint saver for LangGraph integration."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator
from uuid import UUID

from langchain_core.runnables.config import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    ChannelVersions,
)
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from querivue_agent.runtime.graph_state import RunState
from querivue_agent.runtime.redis_projection import RedisProjection, CheckpointRecord


class RedisCheckpointSaver(BaseCheckpointSaver):
    """LangGraph checkpoint saver backed by RedisProjection."""

    def __init__(
        self,
        redis_projection: RedisProjection,
        serde: JsonPlusSerializer | None = None,
    ) -> None:
        super().__init__(serde=serde or JsonPlusSerializer())
        self._redis_projection = redis_projection

    def _config_to_run_id(self, config: RunnableConfig) -> UUID | None:
        """Extract run_id from config."""
        configurable = config.get("configurable", {})
        thread_id = configurable.get("thread_id")
        if thread_id:
            try:
                return UUID(thread_id)
            except ValueError:
                return None
        return None

    def _run_id_to_config(self, run_id: UUID) -> RunnableConfig:
        """Convert run_id to config."""
        return {"configurable": {"thread_id": str(run_id)}}

    def _checkpoint_record_to_tuple(
        self,
        record: CheckpointRecord,
        parent_config: RunnableConfig | None = None,
    ) -> CheckpointTuple:
        """Convert a CheckpointRecord to a CheckpointTuple."""
        # Deserialize the run state
        run_state = self._redis_projection._deserialize_run_state(record.run_state_json)

        # Convert RunState to LangGraph checkpoint format
        checkpoint: Checkpoint = {
            "v": 1,
            "id": record.checkpoint_id,
            "ts": record.created_at,
            "channel_values": {"run_state": run_state},
            "channel_versions": {"run_state": record.checkpoint_id},
            "versions_seen": {"run_state": {record.checkpoint_id: record.checkpoint_id}},
            "updated_channels": ["run_state"],
        }

        metadata: CheckpointMetadata = {
            "source": "update",
            "step": 0,
            "parents": {},
            "run_id": record.run_id,
            "counters_since_delta_snapshot": {},
        }

        if record.parent_checkpoint_id:
            metadata["parents"]["run_state"] = record.parent_checkpoint_id

        return CheckpointTuple(
            config=self._run_id_to_config(UUID(record.run_id)),
            checkpoint=checkpoint,
            metadata=metadata,
            parent_config=parent_config,
            pending_writes=None,
        )

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        """Get a checkpoint tuple for the given config."""
        run_id = self._config_to_run_id(config)
        if not run_id:
            return None

        # Try to get the latest checkpoint
        record = await self._redis_projection.load_latest_checkpoint(run_id)
        if not record:
            return None

        # We need to find the checkpoint record by ID
        # Load the actual checkpoint record
        # The load_latest_checkpoint returns RunState, we need the record
        # Let's use list_checkpoints to get the latest record
        checkpoints = await self._redis_projection.list_checkpoints(run_id)
        if not checkpoints:
            return None

        latest_record = checkpoints[0]
        return self._checkpoint_record_to_tuple(latest_record)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """List checkpoints matching the given criteria."""
        if config is None:
            return

        run_id = self._config_to_run_id(config)
        if not run_id:
            return

        checkpoints = await self._redis_projection.list_checkpoints(run_id)

        for record in checkpoints:
            if limit is not None and limit <= 0:
                break
            yield self._checkpoint_record_to_tuple(record)
            if limit is not None:
                limit -= 1

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        """Save a checkpoint."""
        run_id = self._config_to_run_id(config)
        if not run_id:
            raise ValueError("No thread_id in config")

        # Extract run_state from checkpoint
        run_state = checkpoint.get("channel_values", {}).get("run_state")
        if not isinstance(run_state, RunState):
            raise ValueError("Checkpoint missing run_state in channel_values")

        # Determine parent checkpoint ID
        parent_checkpoint_id = None
        parents = metadata.get("parents", {})
        if parents:
            parent_checkpoint_id = parents.get("run_state")

        # Save checkpoint
        checkpoint_id = await self._redis_projection.save_checkpoint(
            run_state=run_state,
            checkpoint_id=checkpoint["id"],
            parent_checkpoint_id=parent_checkpoint_id,
        )

        # Return updated config with new checkpoint ID
        return self._run_id_to_config(run_id)

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: list[tuple[str, str, Any]],
        task_id: str,
    ) -> None:
        """Save intermediate writes (for channel updates)."""
        # For now, we don't use intermediate writes
        # The full state is saved via aput
        pass

    async def adelete_thread(self, config: RunnableConfig) -> None:
        """Delete all checkpoints for a thread."""
        run_id = self._config_to_run_id(config)
        if run_id:
            await self._redis_projection.delete_run_checkpoints(run_id)

    async def adelete_for_runs(self, run_ids: list[str]) -> None:
        """Delete checkpoints for multiple runs."""
        for run_id_str in run_ids:
            try:
                run_id = UUID(run_id_str)
                await self._redis_projection.delete_run_checkpoints(run_id)
            except ValueError:
                continue

    # Synchronous versions (required by base class but can raise NotImplementedError)
    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        raise NotImplementedError("Use async version")

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> list[CheckpointTuple]:
        raise NotImplementedError("Use async version")

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        raise NotImplementedError("Use async version")

    def put_writes(
        self,
        config: RunnableConfig,
        writes: list[tuple[str, str, Any]],
        task_id: str,
    ) -> None:
        raise NotImplementedError("Use async version")

    def delete_thread(self, config: RunnableConfig) -> None:
        raise NotImplementedError("Use async version")

    def delete_for_runs(self, run_ids: list[str]) -> None:
        raise NotImplementedError("Use async version")


def create_checkpoint_saver(redis_projection: RedisProjection) -> RedisCheckpointSaver:
    """Create a Redis checkpoint saver."""
    return RedisCheckpointSaver(redis_projection)