"""Shared context types for specialists and wrappers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from pathlib import Path


@dataclass
class WrapperContext:
    """Context passed to wrapper functions."""
    run_state: Any  # RunState
    model_gateway: Any  # ModelGateway
    trace_recorder: Any  # TraceRecorder
    authority: Any  # Authority
    artifact_store: Any  # ArtifactStore