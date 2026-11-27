import json
import pytest
from pydantic import ValidationError

from querivue_agent.contracts.manifests import (
    CapabilityProof,
    CostRate,
    EnvironmentManifest,
    InferenceSettings,
    PackageBuild,
    ProviderIdentity,
    ResourceProfile,
    SchemaDescriptor,
    ToolDeclaration,
)


def uid(number: int) -> str:
    return f"00000000-0000-4000-8000-{number:012d}"


HASH_A = "a" * 64
HASH_B = "b" * 64


def artifact(*, sha256: str = HASH_A, media_type: str = "application/json") -> dict:
    return {
        "artifact_id": uid(1),
        "storage_ref": uid(2),
        "media_type": media_type,
        "size_bytes": 12,
        "sha256": sha256,
        "environment_manifest_id": uid(3),
    }


def resource_profile(**changes) -> dict:
    value = {
        "cpu_millis": 1000,
        "memory_bytes": 1024,
        "filesystem_bytes": 4096,
        "scratch_bytes": 1024,
        "output_bytes": 2048,
        "output_files": 2,
        "network_disabled": True,
        "process_tree_limits_enforced": True,
        "isolation_profile_version": "isolation-v1",
    }
    value.update(changes)
    return value


def provider_identity(**changes) -> dict:
    value = {
        "provider": "openrouter",
        "model_id": "gemini-test",
        "endpoint": "https://models.example.test/v1",
        "route": "primary",
        "account_tier": "free",
        "region": "global",
        "quota_identity": "quota-v1",
        "sdk_name": "provider-sdk",
        "sdk_version": "1.2.3",
        "protocol_version": "v1",
        "tokenizer_version": "tok-v2",
        "tokenizer_build_hash": HASH_A,
        "rate_manifest_hash": HASH_B,
        "observed_revision": None,
        "max_context_tokens": 4096,
        "rates": [{"meter": "request", "unit_size": 1, "usd_per_unit": "0"}],
        "free_tier_enforced": True,
        "accounting_verified": True,
        "privacy_verified": True,
    }
    value.update(changes)
    return value


def environment_manifest(**changes) -> dict:
    value = {
        "manifest_id": uid(10),
        "manifest_version": "manifest-v1",
        "schema_version": "schema-v1",
        "image_digest": HASH_A,
        "provider_identity": "sandbox-provider",
        "provider_template_revision": "template-r7",
        "os": "linux",
        "kernel": "6.12",
        "architecture": "x86_64",
        "python_version": "3.12.12",
        "packages": [{"name": "duckdb", "version": "1.4.2", "wheel_hash": HASH_A}],
        "lock_hash": HASH_A,
        "duckdb_build": HASH_A,
        "arrow_build": HASH_A,
        "sql_policy_version": "sql-v1",
        "importer_version": "import-v1",
        "profile_version": "profile-v1",
        "validator_version": "validator-v1",
        "locale": "C.UTF-8",
        "tzdata_version": "2026b",
        "requested_controls": resource_profile(),
        "observed_controls": resource_profile(),
        "gate_results": [{
            "gate_id": "network",
            "status": "passed",
            "evidence_ref": uid(11),
            "build_hash": HASH_B,
        }],
        "created_at": "2026-11-24T10:00:00+05:30",
    }
    value.update(changes)
    return value


@pytest.mark.parametrize(
    "model,payload",
    [
        (PackageBuild, {"name": "duckdb", "version": "1.4", "wheel_hash": HASH_A}),
        (ResourceProfile, resource_profile()),
        (CapabilityProof, {"gate_id": "gate", "status": "passed", "evidence_ref": uid(4), "build_hash": HASH_A}),
        (EnvironmentManifest, environment_manifest()),
        (CostRate, {"meter": "input_token", "unit_size": 1000, "usd_per_unit": "0.0001"}),
        (ProviderIdentity, provider_identity()),
        (InferenceSettings, {"reasoning": None, "temperature": None, "seed": None, "max_generated_tokens": 512, "sampling_overrides_verified": False, "reasoning_in_output_budget": True}),
        (SchemaDescriptor, {"name": "terminal", "version": "v1", "sha256": HASH_A, "artifact": artifact()}),
        (ToolDeclaration, {"name": "execute_query", "schema": {"name": "query", "version": "v1", "sha256": HASH_A, "artifact": artifact()}}),
    ],
)
def test_manifest_families_round_trip_native_and_json(model, payload):
    result = model.model_validate(payload)
    assert result.model_dump() == payload
    assert model.model_validate_json(result.model_dump_json()) == result
    assert model.model_validate_json(json.dumps(payload)) == result


@pytest.mark.parametrize("field", ["scratch_bytes", "output_bytes"])
def test_resource_suballocations_cannot_exceed_filesystem(field):
    with pytest.raises(ValidationError):
        ResourceProfile.model_validate(resource_profile(**{field: 4097}))


def test_environment_packages_and_gates_are_unique():
    payload = environment_manifest()
    payload["packages"].append({"name": "duckdb", "version": "other", "wheel_hash": HASH_B})
    with pytest.raises(ValidationError, match="package names must be unique"):
        EnvironmentManifest.model_validate(payload)
    payload = environment_manifest()
    payload["gate_results"].append({**payload["gate_results"][0], "status": "failed", "evidence_ref": None})
    with pytest.raises(ValidationError, match="gate IDs must be unique"):
        EnvironmentManifest.model_validate(payload)


def test_passed_capability_requires_observed_evidence():
    with pytest.raises(ValidationError, match="passed gate requires evidence_ref"):
        CapabilityProof.model_validate({"gate_id": "gate", "status": "passed", "evidence_ref": None, "build_hash": HASH_A})
    blocked = CapabilityProof.model_validate({"gate_id": "gate", "status": "blocked", "evidence_ref": None, "build_hash": HASH_A})
    assert blocked.evidence_ref is None


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://models.example.test/v1",
        "https://user@models.example.test/v1",
        "https://models.example.test/v1?token=secret",
        "https://models.example.test/v1#fragment",
        "not-a-url",
    ],
)
def test_provider_endpoint_is_secret_safe_https(endpoint):
    with pytest.raises(ValidationError):
        ProviderIdentity.model_validate(provider_identity(endpoint=endpoint))


def test_provider_rates_have_unique_meters_and_revision_may_stay_unknown():
    assert ProviderIdentity.model_validate(provider_identity()).observed_revision is None
    rates = [
        {"meter": "request", "unit_size": 1, "usd_per_unit": "0"},
        {"meter": "request", "unit_size": 2, "usd_per_unit": "0.1"},
    ]
    with pytest.raises(ValidationError, match="rate meters must be unique"):
        ProviderIdentity.model_validate(provider_identity(rates=rates))


def test_inference_sampling_overrides_require_verified_provider_support():
    base = {"reasoning": "low", "temperature": None, "seed": None, "max_generated_tokens": 512, "sampling_overrides_verified": False, "reasoning_in_output_budget": True}
    for field, value in (("temperature", 0.5), ("seed", 7)):
        with pytest.raises(ValidationError, match="sampling overrides"):
            InferenceSettings.model_validate({**base, field: value})
    accepted = InferenceSettings.model_validate({**base, "temperature": 0.5, "seed": 7, "sampling_overrides_verified": True})
    assert accepted.temperature == 0.5 and accepted.seed == 7


@pytest.mark.parametrize("media_type", ["text/plain", "application/octet-stream"])
def test_schema_descriptor_binds_json_artifact_bytes_and_hash(media_type):
    with pytest.raises(ValidationError):
        SchemaDescriptor.model_validate({"name": "terminal", "version": "v1", "sha256": HASH_A, "artifact": artifact(media_type=media_type)})
    with pytest.raises(ValidationError, match="artifact SHA"):
        SchemaDescriptor.model_validate({"name": "terminal", "version": "v1", "sha256": HASH_B, "artifact": artifact()})


def test_tool_declaration_uses_finite_public_tool_vocabulary():
    payload = {"name": "unknown_tool", "schema": {"name": "x", "version": "v1", "sha256": HASH_A, "artifact": artifact()}}
    with pytest.raises(ValidationError, match="literal_error"):
        ToolDeclaration.model_validate(payload)
