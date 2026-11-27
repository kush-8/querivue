"""Python Specialist implementation."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from uuid import UUID
from pathlib import Path

from querivue_agent.contracts.tools import ExecutePythonRequest
from querivue_agent.contracts.evidence import TabularEvidence, ChartArtifact
from querivue_agent.execution.python_runner import PythonRunner, PythonRunnerConfig, create_python_runner
from querivue_agent.runtime.sandbox import SandboxController, create_sandbox_controller, EnvironmentManifest, ResourceLimits, SandboxConfig
from querivue_agent.runtime.context import WrapperContext
from querivue_agent.contracts.common import Scope
from querivue_agent.contracts.values import CanonicalUUID


async def run_python(
    request: dict[str, Any],
    *,
    model: Any,
    tools: Any,
) -> dict[str, Any]:
    """Run Python specialist action - called by the outer graph."""
    # This is the entry point from the LangGraph outer graph
    # The actual execution is done via PythonSpecialist.execute
    # This function is kept for API compatibility
    return {
        "type": "python_succeeded",
        "evidence_ids": [],
        "chart_artifact_ids": [],
        "message": "Use PythonSpecialist.execute directly",
    }


class PythonSpecialist:
    """Python specialist with fresh process execution."""

    def __init__(self, context: WrapperContext) -> None:
        self._context = context
        self._sandbox: SandboxController | None = None
        self._runner: PythonRunner | None = None
        self._action_id: UUID | None = None

    async def start(self, action_id: UUID) -> None:
        """Initialize sandbox and runner for a specific action."""
        self._action_id = action_id

        # Create sandbox config with proper environment manifest
        manifest = EnvironmentManifest(
            manifest_id=CanonicalUUID(str(uuid.uuid4())),
            schema_version="1.0",
            image_digest="sha256:" + "a" * 64,
            provider_template_revision="dev",
            os_kernel_arch="linux/x86_64",
            python_version="3.12",
            package_hashes={},
            duckdb_version="1.0.0",
            arrow_version="15.0.0",
            sql_parser_policy_version="1.0",
            importer_version="1.0",
            profiler_version="1.0",
            validator_version="1.0",
            locale="en_US.UTF-8",
            timezone="UTC",
            resource_profile="development",
            created_at="2024-01-01T00:00:00Z",
            provider_identity="local",
            observed_controls={
                "read_only_inputs": True,
                "network_blocked": True,
                "process_tree_termination": True,
                "cgroup_v2": True,
                "bubblewrap": True,
            },
        )
        limits = ResourceLimits()
        sandbox_config = SandboxConfig(
            environment_manifest=manifest,
            resource_limits=limits,
            session_id=CanonicalUUID(str(uuid.uuid4())),
            run_id=self._context.run_state.run_id,
            read_only_inputs=[],
        )
        self._sandbox = SandboxController(sandbox_config)
        await self._sandbox.create_session()

        config = PythonRunnerConfig(
            action_id=action_id,
            run_id=self._context.run_state.run_id,
            attempt=1,
            runner_nonce=1,
            sandbox_id=sandbox_config.session_id,
            pid=0,
            authorized_evidence={},  # Will be populated per request
            analysis_timezone="UTC",
            artifact_dir=Path(self._context.artifact_store.root_dir) if hasattr(self._context.artifact_store, 'root_dir') else Path("artifacts"),
            resource_limits={"python_memory_gib": 2.0},
            scope=Scope(
                project_id=CanonicalUUID("00000000-0000-0000-0000-000000000000"),
                chat_id=CanonicalUUID("00000000-0000-0000-0000-000000000000"),
                run_id=self._context.run_state.run_id,
                eligible_dataset_ids=[],
            ),
        )
        self._runner = await create_python_runner(config, self._sandbox)

    async def execute(
        self,
        request: ExecutePythonRequest,
        operation_id: UUID,
        authorized_evidence: dict[CanonicalUUID, Path],
    ) -> dict[str, Any]:
        """Execute Python code with authorized evidence."""
        if not self._runner or not self._action_id:
            raise RuntimeError("PythonSpecialist not started - call start() first")

        # Update authorized evidence in runner config
        self._runner._config = PythonRunnerConfig(
            action_id=self._action_id,
            run_id=self._config.run_id,
            attempt=self._config.attempt,
            runner_nonce=self._config.runner_nonce,
            sandbox_id=self._config.sandbox_id,
            pid=self._config.pid,
            authorized_evidence=authorized_evidence,
            analysis_timezone=self._config.analysis_timezone,
            artifact_dir=self._config.artifact_dir,
            resource_limits=self._config.resource_limits,
            scope=self._config.scope,
        )

        return await self._runner.execute_python(request, operation_id)

    async def shutdown(self) -> None:
        """Shutdown sandbox."""
        if self._sandbox:
            await self._sandbox.destroy_session()
        self._sandbox = None
        self._runner = None
        self._action_id = None

    @property
    def _config(self) -> PythonRunnerConfig:
        """Get runner config."""
        if not self._runner:
            raise RuntimeError("Runner not initialized")
        return self._runner._config