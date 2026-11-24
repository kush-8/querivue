"""Strict, nonsecret, fail-closed runtime configuration."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    BeforeValidator,
    Field,
    PrivateAttr,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)

from .contracts.common import (
    Hash64,
    NonblankString,
    PositiveCount,
    Role,
    SafeCount,
    StrictRecord,
)
from .contracts.evaluation import SpendCaps
from .contracts.manifests import EnvironmentManifest, InferenceSettings, ProviderIdentity
from .contracts.values import CanonicalUUID


ALL_ROLES: tuple[Role, ...] = (
    "entry", "supervisor", "sql", "python", "answer", "reviewer", "clarification",
)
ROLE_SCOPES: dict[Role, Literal["intake_chain", "run", "action"]] = {
    "entry": "intake_chain",
    "supervisor": "run",
    "sql": "action",
    "python": "action",
    "answer": "run",
    "reviewer": "run",
    "clarification": "run",
}
_FALSE_ENV_VALUES = {"", "0", "false", "off", "no"}
_TRACING_ENV_NAMES = ("LANGCHAIN_TRACING_V2", "LANGSMITH_TRACING")


class ConfigError(ValueError):
    """Sanitized configuration failure safe for operator-facing errors."""


def _schema_version(value: object) -> object:
    if type(value) is not int or value != 1:
        raise ValueError("schema_version must be the integer 1")
    return value


SchemaVersion = Annotated[Literal[1], BeforeValidator(_schema_version)]


class RunLimits(StrictRecord):
    active_seconds: PositiveCount
    hard_wall_seconds: PositiveCount
    input_tokens: PositiveCount
    output_tokens: PositiveCount
    pending_tasks: PositiveCount
    actions_per_task: PositiveCount
    concurrent_actions: PositiveCount
    dispatch_attempts: PositiveCount
    review_passes: PositiveCount
    clarification_slots: PositiveCount
    deliberate_retries_per_action: SafeCount

    @model_validator(mode="after")
    def validate_intersections(self) -> "RunLimits":
        if self.active_seconds > self.hard_wall_seconds:
            raise ValueError("active_seconds cannot exceed hard_wall_seconds")
        if self.concurrent_actions > self.actions_per_task or self.actions_per_task > 2:
            raise ValueError("concurrent_actions <= actions_per_task <= 2 is required")
        if self.pending_tasks > 4:
            raise ValueError("pending_tasks cannot exceed 4")
        if self.review_passes > 2:
            raise ValueError("review_passes cannot exceed 2")
        if self.clarification_slots > 2:
            raise ValueError("clarification_slots cannot exceed 2")
        return self


class RoleLimits(StrictRecord):
    limit_scope: Literal["intake_chain", "run", "action"]
    request_input_tokens: PositiveCount
    request_output_tokens: PositiveCount
    cumulative_input_tokens: PositiveCount
    cumulative_output_tokens: PositiveCount
    logical_invocations: PositiveCount
    physical_requests: PositiveCount
    active_seconds: PositiveCount
    request_timeout_seconds: PositiveCount | None = None

    @model_validator(mode="after")
    def validate_intersections(self) -> "RoleLimits":
        if self.request_input_tokens > self.cumulative_input_tokens:
            raise ValueError("request input cap cannot exceed cumulative input cap")
        if self.request_output_tokens > self.cumulative_output_tokens:
            raise ValueError("request output cap cannot exceed cumulative output cap")
        if self.logical_invocations > self.physical_requests:
            raise ValueError("logical invocations cannot exceed physical requests")
        if self.request_timeout_seconds is not None and self.request_timeout_seconds > self.active_seconds:
            raise ValueError("request timeout cannot exceed active time")
        return self


class ContextLimits(StrictRecord):
    thread_candidates: PositiveCount
    label_utf8_bytes: PositiveCount
    unanchored_candidates: SafeCount
    optional_exchanges: SafeCount
    entry_optional_tokens: SafeCount
    clarification_optional_tokens: SafeCount
    other_optional_tokens: SafeCount
    evidence_views: PositiveCount
    analysis_preview_rows: PositiveCount
    answer_preview_rows: PositiveCount
    preview_columns: PositiveCount
    charts: SafeCount
    cell_utf8_bytes: PositiveCount
    default_preview_rows: PositiveCount
    overflow_replans: SafeCount
    compaction_trigger_percent: PositiveCount
    compaction_rebuilds: SafeCount

    @model_validator(mode="after")
    def validate_ceilings(self) -> "ContextLimits":
        ceilings = {
            "evidence_views": 8,
            "analysis_preview_rows": 32,
            "answer_preview_rows": 128,
            "preview_columns": 32,
            "charts": 4,
            "cell_utf8_bytes": 2048,
        }
        for field, ceiling in ceilings.items():
            if getattr(self, field) > ceiling:
                raise ValueError(f"{field} cannot exceed {ceiling}")
        if not self.default_preview_rows <= self.analysis_preview_rows <= self.answer_preview_rows:
            raise ValueError("preview row caps must be nondecreasing")
        if self.compaction_trigger_percent > 100:
            raise ValueError("compaction_trigger_percent cannot exceed 100")
        return self


class ExecutionLimits(StrictRecord):
    max_model_requests: SafeCount
    max_tool_calls: SafeCount
    max_executions: SafeCount
    max_corrections: SafeCount
    max_terminal_corrections: SafeCount
    max_transient_retries: SafeCount
    no_progress_rounds: SafeCount
    active_seconds: PositiveCount
    execution_seconds: PositiveCount

    @model_validator(mode="after")
    def validate_times(self) -> "ExecutionLimits":
        if self.execution_seconds > self.active_seconds:
            raise ValueError("execution_seconds cannot exceed active_seconds")
        return self


class ReviewLimits(StrictRecord):
    logical_passes: PositiveCount
    logical_per_pass: PositiveCount
    physical_per_pass: PositiveCount
    total_physical: PositiveCount
    total_logical: PositiveCount
    per_pass_seconds: PositiveCount
    total_seconds: PositiveCount
    request_timeout_seconds: PositiveCount
    finalization_seconds: PositiveCount
    max_findings: PositiveCount
    supports_per_finding: PositiveCount
    support_occurrences: PositiveCount
    block_ids_per_finding: PositiveCount
    text_utf8_bytes: PositiveCount
    json_bytes: PositiveCount

    @model_validator(mode="after")
    def validate_intersections(self) -> "ReviewLimits":
        ceilings = {
            "logical_passes": 2,
            "logical_per_pass": 2,
            "physical_per_pass": 3,
            "total_physical": 5,
            "total_logical": 4,
            "per_pass_seconds": 30,
            "total_seconds": 60,
            "request_timeout_seconds": 20,
            "finalization_seconds": 5,
            "max_findings": 8,
            "supports_per_finding": 16,
            "support_occurrences": 64,
            "block_ids_per_finding": 16,
            "text_utf8_bytes": 1024,
            "json_bytes": 32768,
        }
        for field, ceiling in ceilings.items():
            if getattr(self, field) > ceiling:
                raise ValueError(f"{field} cannot exceed {ceiling}")
        if self.logical_per_pass > self.physical_per_pass:
            raise ValueError("logical_per_pass cannot exceed physical_per_pass")
        if self.total_logical > self.logical_passes * self.logical_per_pass:
            raise ValueError("total_logical exceeds per-pass capacity")
        if self.total_physical > self.logical_passes * self.physical_per_pass:
            raise ValueError("total_physical exceeds per-pass capacity")
        if self.total_logical > self.total_physical:
            raise ValueError("total_logical cannot exceed total_physical")
        if self.request_timeout_seconds > self.per_pass_seconds:
            raise ValueError("request timeout cannot exceed per-pass time")
        if self.per_pass_seconds > self.total_seconds:
            raise ValueError("per-pass time cannot exceed total time")
        if self.total_seconds > self.logical_passes * self.per_pass_seconds:
            raise ValueError("total time exceeds the pass-time envelope")
        if self.finalization_seconds > self.total_seconds:
            raise ValueError("finalization time cannot exceed total time")
        return self


class OperationalSettings(StrictRecord):
    coordinator_lease_seconds: PositiveCount
    heartbeat_seconds: PositiveCount
    db_busy_timeout_ms: PositiveCount
    operator_concurrent_runs: PositiveCount
    project_concurrent_runs: PositiveCount
    operator_intakes_per_hour: PositiveCount
    project_intakes_per_hour: PositiveCount
    concurrent_assessments: PositiveCount
    entry_wait_seconds: PositiveCount
    analytical_wait_seconds: PositiveCount
    unadmitted_upload_retention_seconds: PositiveCount

    @model_validator(mode="after")
    def validate_relationships(self) -> "OperationalSettings":
        if self.heartbeat_seconds >= self.coordinator_lease_seconds:
            raise ValueError("heartbeat must be shorter than coordinator lease")
        if self.db_busy_timeout_ms >= self.coordinator_lease_seconds * 1000:
            raise ValueError("database busy timeout must be shorter than coordinator lease")
        if self.project_concurrent_runs > self.operator_concurrent_runs:
            raise ValueError("project concurrency cannot exceed operator concurrency")
        if self.project_intakes_per_hour > self.operator_intakes_per_hour:
            raise ValueError("project intake rate cannot exceed operator intake rate")
        return self


class LocalBuildIdentity(StrictRecord):
    python_version: NonblankString
    platform: NonblankString
    schema_version: NonblankString
    codec_version: NonblankString
    renderer_version: NonblankString
    graph_version: NonblankString
    selector_version: NonblankString
    lock_sha256: Hash64
    tokenizer_build_hash: Hash64


class RoleModelConfig(StrictRecord):
    identity: ProviderIdentity | None = None
    inference: InferenceSettings | None = None
    prompt_hash: Hash64 | None = None
    schema_hash: Hash64 | None = None
    credential_env: NonblankString


class RunConfig(StrictRecord):
    schema_version: SchemaVersion
    profile: Literal["offline", "live"] = "offline"
    live_enabled: bool = False
    hosted_tracing_enabled: bool = False
    run_limits: RunLimits
    role_limits: dict[Role, RoleLimits]
    context_limits: ContextLimits
    sql_limits: ExecutionLimits
    python_limits: ExecutionLimits
    review_limits: ReviewLimits
    spend_caps: SpendCaps | None = None
    operational: OperationalSettings | None = None
    build: LocalBuildIdentity | None = None
    environment: EnvironmentManifest | None = None
    models: dict[Role, RoleModelConfig] = Field(default_factory=dict)
    live_authorization_ref: CanonicalUUID | None = None

    _credentials: dict[Role, SecretStr] = PrivateAttr(default_factory=dict)

    @field_validator("hosted_tracing_enabled")
    @classmethod
    def reject_hosted_tracing(cls, value: bool) -> bool:
        if value:
            raise ValueError("hosted tracing must remain disabled")
        return value

    @model_validator(mode="after")
    def validate_configuration(self) -> "RunConfig":
        if self.live_enabled and self.profile != "live":
            raise ValueError("live_enabled requires profile='live'")
        if set(self.role_limits) != set(ALL_ROLES):
            raise ValueError("role_limits must contain all seven roles exactly")
        for role, limits in self.role_limits.items():
            if limits.limit_scope != ROLE_SCOPES[role]:
                raise ValueError(f"role_limits.{role}.limit_scope is incorrect")
        if self.operational is not None:
            if self.operational.entry_wait_seconds > self.run_limits.hard_wall_seconds:
                raise ValueError("entry wait cannot exceed run hard wall")
            if self.operational.analytical_wait_seconds > self.run_limits.hard_wall_seconds:
                raise ValueError("analytical wait cannot exceed run hard wall")
        for role, model in self.models.items():
            limits = self.role_limits[role]
            if model.inference is not None and model.inference.max_generated_tokens > limits.request_output_tokens:
                raise ValueError(f"models.{role} output cap exceeds role request output cap")
            if model.identity is not None and model.inference is not None:
                requested = limits.request_input_tokens + model.inference.max_generated_tokens
                if requested > model.identity.max_context_tokens:
                    raise ValueError(f"models.{role} request exceeds provider context")
        return self

    def _set_credentials(self, values: Mapping[Role, str]) -> None:
        self._credentials = {role: SecretStr(value) for role, value in values.items() if value}

    def credential(self, role: Role) -> SecretStr | None:
        return self._credentials.get(role)

    def public_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json")

    def missing_live_settings(self) -> list[str]:
        missing: list[str] = []
        if self.profile != "live":
            missing.append("profile")
        for field in ("operational", "build", "environment", "spend_caps", "live_authorization_ref"):
            if getattr(self, field) is None:
                missing.append(field)
        for role in ALL_ROLES:
            model = self.models.get(role)
            if model is None:
                missing.append(f"models.{role}")
                continue
            if model.identity is None:
                missing.append(f"models.{role}.identity")
            if model.inference is None:
                missing.append(f"models.{role}.inference")
            if model.prompt_hash is None:
                missing.append(f"models.{role}.prompt_hash")
            if model.schema_hash is None:
                missing.append(f"models.{role}.schema_hash")
            if role not in self._credentials:
                missing.append(f"models.{role}.credential")
            if self.role_limits[role].request_timeout_seconds is None:
                missing.append(f"role_limits.{role}.request_timeout_seconds")
            if model.identity is not None:
                identity = model.identity
                if not identity.accounting_verified:
                    missing.append(f"models.{role}.accounting_verified")
                if not identity.privacy_verified:
                    missing.append(f"models.{role}.privacy_verified")
                zero_cap = self.spend_caps is not None and any(
                    set(value) <= {"0", "."} for value in self.spend_caps.model_dump().values()
                )
                if zero_cap and not identity.free_tier_enforced:
                    missing.append(f"models.{role}.free_tier_enforced")
        environment = self.environment
        if environment is not None:
            controls = environment.observed_controls
            if not controls.network_disabled:
                missing.append("environment.observed_controls.network_disabled")
            if not controls.process_tree_limits_enforced:
                missing.append("environment.observed_controls.process_tree_limits_enforced")
            if not environment.gate_results:
                missing.append("environment.gate_results")
            for gate in environment.gate_results:
                if gate.status != "passed" or gate.evidence_ref is None:
                    missing.append(f"environment.gate_results.{gate.gate_id}")
                if gate.build_hash != environment.image_digest:
                    missing.append(f"environment.gate_results.{gate.gate_id}.build_hash")
        return missing

    def require_live_ready(self) -> None:
        missing = self.missing_live_settings()
        if missing:
            raise ConfigError("live configuration is incomplete: " + ", ".join(missing))


def _validation_error(error: ValidationError) -> ConfigError:
    details: list[str] = []
    for item in error.errors(include_url=False, include_context=False, include_input=False):
        location = ".".join(str(part) for part in item["loc"]) or "configuration"
        details.append(f"{location} [{item['type']}]")
    return ConfigError("configuration validation failed: " + ", ".join(details))


def load_config(path: Path, env: Mapping[str, str]) -> RunConfig:
    """Load an explicit TOML file without consulting ambient process state."""
    for name in _TRACING_ENV_NAMES:
        if name in env and env[name].strip().casefold() not in _FALSE_ENV_VALUES:
            raise ConfigError(f"ambient tracing flag {name} must be disabled")
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise ConfigError("configuration file could not be read or parsed") from error
    try:
        config = RunConfig.model_validate(payload)
    except ValidationError as error:
        raise _validation_error(error) from None
    credentials: dict[Role, str] = {}
    for role, model in config.models.items():
        value = env.get(model.credential_env)
        if value:
            credentials[role] = value
    config._set_credentials(credentials)
    if config.live_enabled:
        config.require_live_ready()
    return config
