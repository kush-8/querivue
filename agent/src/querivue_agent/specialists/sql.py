"""SQL Specialist implementation."""

from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

from querivue_agent.contracts.tools import ExecuteQueryRequest, InspectTableRequest, PreviewRowsRequest, InspectEvidenceRequest
from querivue_agent.contracts.evidence import TabularEvidence
from querivue_agent.runtime.sql_runner import SQLRunner, SQLRunnerConfig
from querivue_agent.runtime.sql_tools import SQLToolContext, create_sql_tool_executor
from querivue_agent.runtime.context import WrapperContext


async def run_sql(
    request: dict[str, Any],
    *,
    model: Any,
    tools: Any,
) -> dict[str, Any]:
    """Run SQL specialist action."""
    # For T11, we return a scripted result
    # Real implementation would use SQLRunner/SQLToolExecutor
    return {
        "type": "sql_succeeded",
        "evidence_ids": [],
        "limitations": [],
    }


class SQLSpecialist:
    """SQL specialist with persistent DuckDB runner and mailbox protocol."""

    def __init__(self, context: WrapperContext) -> None:
        self._context = context
        self._runner: SQLRunner | None = None
        self._executor = None

    async def start(
        self,
        action_id: UUID,
        attempt: int,
        runner_nonce: str,
        authorized_tables: dict[Any, Any],
        authorized_evidence: dict[Any, Any],
        analysis_timezone: str | None,
        policy_version: str,
        artifact_dir: str,
        resource_limits: dict[str, Any],
    ) -> None:
        """Initialize SQL runner and tool executor."""
        config = SQLRunnerConfig(
            action_id=action_id,
            run_id=self._context.run_state.run_id,
            attempt=attempt,
            runner_nonce=runner_nonce,
            sandbox_id=UUID("00000000-0000-0000-0000-000000000000"),
            pid=0,
            authorized_tables=authorized_tables,
            authorized_evidence=authorized_evidence,
            analysis_timezone=analysis_timezone,
            policy_version=policy_version,
            mailbox_dir=__import__('tempfile').gettempdir() / f"sql_mailbox_{runner_nonce}",
            artifact_dir=__import__('pathlib').Path(artifact_dir),
            resource_limits=resource_limits,
        )
        self._runner = await create_sql_runner(config)

        tool_context = SQLToolContext(
            run_id=self._context.run_state.run_id,
            action_id=action_id,
            attempt=attempt,
            authorized_tables=authorized_tables,
            authorized_evidence=authorized_evidence,
            analysis_timezone=analysis_timezone,
            policy_version=policy_version,
            artifact_dir=__import__('pathlib').Path(artifact_dir),
            environment_manifest_id=UUID("00000000-0000-0000-0000-000000000000"),
            operation_id=UUID("00000000-0000-0000-0000-000000000000"),
            runner_nonce=runner_nonce,
            deadline=None,
        )
        self._executor = await create_sql_tool_executor(tool_context)

    async def inspect_table(self, request: InspectTableRequest) -> dict[str, Any]:
        """Execute inspect_table tool."""
        if not self._runner:
            raise RuntimeError("SQL specialist not started")
        operation_id = uuid.uuid4()
        return await self._runner.handle_request_from_data(
            __import__('querivue_agent.runtime.sql_runner', fromlist=['MailboxRequest']).MailboxRequest(
                mailbox_id=uuid.uuid4(),
                operation_id=operation_id,
                action_id=request.table_id,
                attempt=1,
                runner_nonce="",
                request_type="inspect_table",
                payload=request.model_dump(),
                request_digest="",
                deadline="",
            )
        )

    async def preview_rows(self, request: PreviewRowsRequest) -> dict[str, Any]:
        """Execute preview_rows tool."""
        if not self._runner:
            raise RuntimeError("SQL specialist not started")
        operation_id = uuid.uuid4()
        return await self._runner.handle_request_from_data(
            __import__('querivue_agent.runtime.sql_runner', fromlist=['MailboxRequest']).MailboxRequest(
                mailbox_id=uuid.uuid4(),
                operation_id=operation_id,
                action_id=request.table_id,
                attempt=1,
                runner_nonce="",
                request_type="preview_rows",
                payload=request.model_dump(),
                request_digest="",
                deadline="",
            )
        )

    async def inspect_evidence(self, request: InspectEvidenceRequest) -> dict[str, Any]:
        """Execute inspect_evidence tool."""
        if not self._runner:
            raise RuntimeError("SQL specialist not started")
        operation_id = uuid.uuid4()
        return await self._runner.handle_request_from_data(
            __import__('querivue_agent.runtime.sql_runner', fromlist=['MailboxRequest']).MailboxRequest(
                mailbox_id=uuid.uuid4(),
                operation_id=operation_id,
                action_id=request.evidence_id,
                attempt=1,
                runner_nonce="",
                request_type="inspect_evidence",
                payload=request.model_dump(),
                request_digest="",
                deadline="",
            )
        )

    async def execute_query(self, request: ExecuteQueryRequest) -> dict[str, Any]:
        """Execute execute_query tool."""
        if not self._runner:
            raise RuntimeError("SQL specialist not started")
        operation_id = uuid.uuid4()
        return await self._runner.handle_request_from_data(
            __import__('querivue_agent.runtime.sql_runner', fromlist=['MailboxRequest']).MailboxRequest(
                mailbox_id=uuid.uuid4(),
                operation_id=operation_id,
                action_id=UUID("00000000-0000-0000-0000-000000000000"),
                attempt=1,
                runner_nonce="",
                request_type="execute_query",
                payload=request.model_dump(),
                request_digest="",
                deadline="",
            )
        )

    async def shutdown(self) -> None:
        """Shutdown the specialist."""
        if self._runner:
            await self._runner.shutdown()
            self._runner = None
        if self._executor:
            await self._executor.shutdown()
            self._executor = None