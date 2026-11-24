"""Strict immutable environment, provider, inference, and schema manifests."""

import math
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BeforeValidator, Field, field_validator, model_validator

from .artifacts import ArtifactRef
from .common import (
    Hash64,
    MoneyText,
    NonblankString,
    PositiveCount,
    SafeCount,
    StrictRecord,
    TimestampText,
)
from .values import CanonicalUUID, RuntimeUUID


def _strict_finite_float(value: object) -> object:
    if type(value) is not float or not math.isfinite(value):
        raise ValueError("expected a finite float")
    return value


StrictFiniteFloat = Annotated[float, BeforeValidator(_strict_finite_float)]


class PackageBuild(StrictRecord):
    name: NonblankString
    version: NonblankString
    wheel_hash: Hash64


class ResourceProfile(StrictRecord):
    cpu_millis: PositiveCount
    memory_bytes: PositiveCount
    filesystem_bytes: PositiveCount
    scratch_bytes: PositiveCount
    output_bytes: PositiveCount
    output_files: PositiveCount
    network_disabled: bool
    process_tree_limits_enforced: bool
    isolation_profile_version: NonblankString

    @model_validator(mode="after")
    def validate_filesystem_allocations(self) -> "ResourceProfile":
        if self.scratch_bytes > self.filesystem_bytes:
            raise ValueError("scratch_bytes cannot exceed filesystem_bytes")
        if self.output_bytes > self.filesystem_bytes:
            raise ValueError("output_bytes cannot exceed filesystem_bytes")
        return self


class CapabilityProof(StrictRecord):
    gate_id: NonblankString
    status: Literal["passed", "failed", "not_run", "blocked"]
    evidence_ref: CanonicalUUID | None
    build_hash: Hash64

    @model_validator(mode="after")
    def validate_passed_evidence(self) -> "CapabilityProof":
        if self.status == "passed" and self.evidence_ref is None:
            raise ValueError("passed gate requires evidence_ref")
        return self


class EnvironmentManifest(StrictRecord):
    manifest_id: RuntimeUUID
    manifest_version: NonblankString
    schema_version: NonblankString
    image_digest: Hash64
    provider_identity: NonblankString
    provider_template_revision: NonblankString
    os: NonblankString
    kernel: NonblankString
    architecture: NonblankString
    python_version: NonblankString
    packages: list[PackageBuild] = Field(min_length=1)
    lock_hash: Hash64
    duckdb_build: Hash64
    arrow_build: Hash64
    sql_policy_version: NonblankString
    importer_version: NonblankString
    profile_version: NonblankString
    validator_version: NonblankString
    locale: NonblankString
    tzdata_version: NonblankString
    requested_controls: ResourceProfile
    observed_controls: ResourceProfile
    gate_results: list[CapabilityProof]
    created_at: TimestampText

    @field_validator("packages")
    @classmethod
    def unique_package_names(cls, value: list[PackageBuild]) -> list[PackageBuild]:
        names = [package.name for package in value]
        if len(names) != len(set(names)):
            raise ValueError("package names must be unique")
        return value

    @field_validator("gate_results")
    @classmethod
    def unique_gate_ids(cls, value: list[CapabilityProof]) -> list[CapabilityProof]:
        gate_ids = [result.gate_id for result in value]
        if len(gate_ids) != len(set(gate_ids)):
            raise ValueError("gate IDs must be unique")
        return value


class CostRate(StrictRecord):
    meter: Literal["input_token", "output_token", "neuron", "second", "byte", "request"]
    unit_size: PositiveCount
    usd_per_unit: MoneyText


class ProviderIdentity(StrictRecord):
    provider: Literal["google", "nvidia", "cloudflare", "openrouter"]
    model_id: NonblankString
    endpoint: NonblankString
    route: NonblankString
    account_tier: NonblankString
    region: NonblankString
    quota_identity: NonblankString
    sdk_name: NonblankString
    sdk_version: NonblankString
    protocol_version: NonblankString
    tokenizer_version: NonblankString
    tokenizer_build_hash: Hash64
    rate_manifest_hash: Hash64
    observed_revision: NonblankString | None
    max_context_tokens: PositiveCount
    rates: list[CostRate] = Field(min_length=1)
    free_tier_enforced: bool
    accounting_verified: bool
    privacy_verified: bool

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        endpoint = urlsplit(value)
        if (
            endpoint.scheme != "https"
            or not endpoint.netloc
            or endpoint.username is not None
            or endpoint.password is not None
            or endpoint.query
            or endpoint.fragment
        ):
            raise ValueError("endpoint must be HTTPS without userinfo, query, or fragment")
        return value

    @field_validator("rates")
    @classmethod
    def unique_rate_meters(cls, value: list[CostRate]) -> list[CostRate]:
        meters = [rate.meter for rate in value]
        if len(meters) != len(set(meters)):
            raise ValueError("rate meters must be unique")
        return value


class InferenceSettings(StrictRecord):
    reasoning: Literal["minimal", "low", "medium", "high"] | None
    temperature: StrictFiniteFloat | None
    seed: SafeCount | None
    max_generated_tokens: PositiveCount
    sampling_overrides_verified: bool
    reasoning_in_output_budget: bool

    @model_validator(mode="after")
    def validate_sampling_overrides(self) -> "InferenceSettings":
        if (self.temperature is not None or self.seed is not None) and not self.sampling_overrides_verified:
            raise ValueError("sampling overrides require verified provider support")
        return self


class SchemaDescriptor(StrictRecord):
    name: NonblankString
    version: NonblankString
    sha256: Hash64
    artifact: ArtifactRef

    @model_validator(mode="after")
    def validate_artifact(self) -> "SchemaDescriptor":
        if self.artifact.sha256 != self.sha256:
            raise ValueError("artifact SHA must match schema sha256")
        if self.artifact.media_type not in ("application/json", "application/schema+json"):
            raise ValueError("schema artifact must use a JSON schema media type")
        return self


class ToolDeclaration(StrictRecord):
    name: Literal[
        "inspect_table",
        "preview_rows",
        "inspect_evidence",
        "execute_query",
        "execute_python",
    ]
    schema: SchemaDescriptor
