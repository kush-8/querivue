"""Python Specialist implementation."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from uuid import UUID

from querivue_agent.contracts.tools import ExecutePythonRequest, OutputDeclaration
from querivue_agent.contracts.evidence import TabularEvidence, ChartArtifact
from pathlib import Path
from querivue_agent.runtime.execution.python_runner import PythonRunner, PythonRunnerConfig
from querivue_agent.runtime.sandbox import SandboxController, create_sandbox_controller
from querivue_agent.runtime.wrappers import WrapperContext


async def run_python(
    request: dict[str, Any],
    *,
    model: Any,
    tools: Any,
) -> dict[str, Any]:
    """Run Python specialist action."""
    # For T14, we return a scripted result
    # Real implementation would use PythonRunner
    return {
        "type": "python_succeeded",
        "evidence_ids": [],
        "chart_artifact_ids": [],
        "message": "Python specialist - T14 implementation in progress",
    }


class PythonSpecialist:
    """Python specialist with fresh process execution."""

    def __init__(self, context: WrapperContext) -> None:
        self._context = context
        self._sandbox = None
        self._runner = None

    async def start(self) -> None:
        """Initialize sandbox and runner."""
        self._sandbox = await create_sandbox_controller()
        config = PythonRunnerConfig(
            action_id=UUID("00000000-0000-0000-0000-000000000000"),
            run_id=self._context.run_state.run_id,
            attempt=1,
            runner_nonce="python-runner-1",
            sandbox_id=UUID("00000000-0000-0000-0000-000000000000"),
            pid=0,
            authorized_evidence={},
            analysis_timezone="UTC",
            artifact_dir=Path("artifacts"),
            resource_limits={"python_memory_gib": 2.0},
        )
        self._runner = await create_python_runner(config, self._sandbox)

    async def execute(
        self,
        request: ExecutePythonRequest,
        operation_id: UUID,
    ) -> dict[str, Any]:
        """Execute Python code."""
        if not self._runner:
            await self.start()
        return await self._runner.execute_python(request, operation_id)

    async def shutdown(self) -> None:
        """Shutdown sandbox."""
        if self._sandbox and self._runner and self._runner._ticket:
            await self._sandbox.retire(self._runner._ticket)