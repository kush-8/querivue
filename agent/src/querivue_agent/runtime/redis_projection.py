"""Redis projection for persistent graph checkpoints."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import redis.asyncio as redis
from redis.asyncio import Redis

from querivue_agent.runtime.graph_state import RunState, EvidenceRegistryEntry, ActionOutcome
from querivue_agent.contracts.budgets import BudgetSnapshot
from querivue_agent.contracts.records import AdmissionReceipt, Task, OwnerFence


@dataclass(frozen=True)
class CheckpointRecord:
    """A checkpoint record for a run."""
    run_id: str
    checkpoint_id: str
    created_at: str
    run_state_json: str
    parent_checkpoint_id: str | None = None


class RedisProjection:
    """Manages Redis-backed checkpoints for graph runs."""

    def __init__(
        self,
        redis_client: Redis,
        key_prefix: str = "querivue:checkpoints",
        ttl_seconds: int = 86400 * 7,  # 7 days
    ) -> None:
        self._redis = redis_client
        self._key_prefix = key_prefix
        self._ttl = ttl_seconds

    @classmethod
    async def create(
        cls,
        redis_url: str | None = None,
        key_prefix: str = "querivue:checkpoints",
        ttl_seconds: int = 86400 * 7,
    ) -> "RedisProjection":
        """Create a Redis projection with connection."""
        url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        client = redis.from_url(url, encoding="utf-8", decode_responses=True)
        await client.ping()
        return cls(client, key_prefix, ttl_seconds)

    def _run_key(self, run_id: str) -> str:
        return f"{self._key_prefix}:run:{run_id}"

    def _checkpoint_key(self, run_id: str, checkpoint_id: str) -> str:
        return f"{self._key_prefix}:run:{run_id}:checkpoint:{checkpoint_id}"

    def _latest_key(self, run_id: str) -> str:
        return f"{self._key_prefix}:run:{run_id}:latest"

    def _index_key(self, run_id: str) -> str:
        return f"{self._key_prefix}:run:{run_id}:index"

    async def save_checkpoint(
        self,
        run_state: RunState,
        checkpoint_id: str | None = None,
        parent_checkpoint_id: str | None = None,
    ) -> str:
        """Save a run state checkpoint."""
        if checkpoint_id is None:
            checkpoint_id = f"cp_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S_%f')}"

        # Serialize run state
        state_json = self._serialize_run_state(run_state)

        # Create checkpoint record
        record = CheckpointRecord(
            run_id=str(run_state.run_id),
            checkpoint_id=checkpoint_id,
            created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            run_state_json=state_json,
            parent_checkpoint_id=parent_checkpoint_id,
        )

        # Store checkpoint
        checkpoint_key = self._checkpoint_key(str(run_state.run_id), checkpoint_id)
        await self._redis.set(checkpoint_key, json.dumps(record.__dict__), ex=self._ttl)

        # Update latest pointer
        latest_key = self._latest_key(str(run_state.run_id))
        await self._redis.set(latest_key, checkpoint_id, ex=self._ttl)

        # Add to index (sorted set by timestamp)
        index_key = self._index_key(str(run_state.run_id))
        timestamp = datetime.now(UTC).timestamp()
        await self._redis.zadd(index_key, {checkpoint_id: timestamp})
        await self._redis.expire(index_key, self._ttl)

        return checkpoint_id

    async def load_latest_checkpoint(self, run_id: UUID) -> RunState | None:
        """Load the latest checkpoint for a run."""
        latest_key = self._latest_key(str(run_id))
        checkpoint_id = await self._redis.get(latest_key)
        if not checkpoint_id:
            return None

        return await self.load_checkpoint(run_id, checkpoint_id)

    async def load_checkpoint(self, run_id: UUID, checkpoint_id: str) -> RunState | None:
        """Load a specific checkpoint."""
        checkpoint_key = self._checkpoint_key(str(run_id), checkpoint_id)
        data = await self._redis.get(checkpoint_key)
        if not data:
            return None

        record = json.loads(data)
        return self._deserialize_run_state(record["run_state_json"])

    async def list_checkpoints(self, run_id: UUID) -> list[CheckpointRecord]:
        """List all checkpoints for a run, newest first."""
        index_key = self._index_key(str(run_id))
        checkpoint_ids = await self._redis.zrevrange(index_key, 0, -1)

        checkpoints = []
        for cp_id in checkpoint_ids:
            cp_id_str = cp_id if isinstance(cp_id, str) else cp_id.decode()
            checkpoint_key = self._checkpoint_key(str(run_id), cp_id_str)
            data = await self._redis.get(checkpoint_key)
            if data:
                record_data = json.loads(data)
                checkpoints.append(CheckpointRecord(**record_data))

        return checkpoints

    async def delete_run_checkpoints(self, run_id: UUID) -> int:
        """Delete all checkpoints for a run."""
        index_key = self._index_key(str(run_id))
        checkpoint_ids = await self._redis.zrange(index_key, 0, -1)

        keys_to_delete = [index_key, self._latest_key(str(run_id))]
        for cp_id in checkpoint_ids:
            cp_id_str = cp_id if isinstance(cp_id, str) else cp_id.decode()
            keys_to_delete.append(self._checkpoint_key(str(run_id), cp_id_str))

        if keys_to_delete:
            return await self._redis.delete(*keys_to_delete)
        return 0

    def _serialize_run_state(self, run_state: RunState) -> str:
        """Serialize RunState to JSON."""
        # Convert UUIDs to strings for JSON serialization
        def convert(obj: Any) -> Any:
            if isinstance(obj, UUID):
                return str(obj)
            if isinstance(obj, dict):
                return {k: convert(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [convert(v) for v in obj]
            if hasattr(obj, 'model_dump'):
                return convert(obj.model_dump())
            if hasattr(obj, '__dict__'):
                return convert(obj.__dict__)
            return obj

        state_dict = {
            "run_id": str(run_state.run_id),
            "project_id": str(run_state.project_id),
            "chat_id": str(run_state.chat_id),
            "question": run_state.question,
            "eligible_dataset_ids": [str(d) for d in run_state.eligible_dataset_ids],
            "admission_receipt": convert(run_state.admission_receipt) if run_state.admission_receipt else None,
            "fence": convert(run_state.fence) if run_state.fence else None,
            "context": convert(run_state.context),
            "evidence": {k: convert(v) for k, v in run_state.evidence.items()},
            "messages": convert(run_state.messages),
            "pending_tasks": [convert(t) for t in run_state.pending_tasks],
            "current_task": convert(run_state.current_task) if run_state.current_task else None,
            "outcomes": {k: convert(v) for k, v in run_state.outcomes.items()},
            "execution_status": convert(run_state.execution_status),
            "output": convert(run_state.output) if run_state.output else None,
            "budget": convert(run_state.budget) if run_state.budget else None,
            "deadline": run_state.deadline,
            "phase": run_state.phase,
            "active_review_id": str(run_state.active_review_id) if run_state.active_review_id else None,
            "active_review_pass": run_state.active_review_pass,
            "active_clarification_id": str(run_state.active_clarification_id) if run_state.active_clarification_id else None,
            "active_draft_id": str(run_state.active_draft_id) if run_state.active_draft_id else None,
            "active_draft_predecessor": str(run_state.active_draft_predecessor) if run_state.active_draft_predecessor else None,
        }

        return json.dumps(state_dict, separators=(",", ":"))

    def _deserialize_run_state(self, json_str: str) -> RunState:
        """Deserialize JSON to RunState."""
        data = json.loads(json_str)

        def convert_uuid(val: Any) -> Any:
            if isinstance(val, str) and len(val) == 36 and val.count('-') == 4:
                try:
                    return UUID(val)
                except ValueError:
                    return val
            return val

        def convert_dict(d: dict[str, Any]) -> dict[str, Any]:
            return {k: convert_uuid(v) for k, v in d.items()}

        def convert_list(lst: list[Any]) -> list[Any]:
            return [convert_uuid(v) for v in lst]

        # Reconstruct RunState
        return RunState(
            run_id=convert_uuid(data["run_id"]),
            project_id=convert_uuid(data["project_id"]),
            chat_id=convert_uuid(data["chat_id"]),
            question=data["question"],
            eligible_dataset_ids=convert_list(data["eligible_dataset_ids"]),
            admission_receipt=data.get("admission_receipt"),
            fence=data.get("fence"),
            context=data.get("context", {}),
            evidence=data.get("evidence", {}),
            messages=data.get("messages", []),
            pending_tasks=data.get("pending_tasks", []),
            current_task=data.get("current_task"),
            outcomes=data.get("outcomes", {}),
            execution_status=data.get("execution_status", {}),
            output=data.get("output"),
            budget=data.get("budget"),
            deadline=data.get("deadline"),
            phase=data.get("phase", "admitted"),
            active_review_id=convert_uuid(data["active_review_id"]) if data.get("active_review_id") else None,
            active_review_pass=data.get("active_review_pass", 0),
            active_clarification_id=convert_uuid(data["active_clarification_id"]) if data.get("active_clarification_id") else None,
            active_draft_id=convert_uuid(data["active_draft_id"]) if data.get("active_draft_id") else None,
            active_draft_predecessor=convert_uuid(data["active_draft_predecessor"]) if data.get("active_draft_predecessor") else None,
        )

    async def close(self) -> None:
        """Close Redis connection."""
        await self._redis.aclose()


async def create_redis_projection(
    redis_url: str | None = None,
) -> RedisProjection:
    """Create a Redis projection instance."""
    return await RedisProjection.create(redis_url=redis_url)