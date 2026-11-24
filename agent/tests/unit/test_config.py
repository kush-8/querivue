from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from querivue_agent.config import (
    ConfigError,
    ContextLimits,
    ExecutionLimits,
    LocalBuildIdentity,
    OperationalSettings,
    ReviewLimits,
    RoleLimits,
    RoleModelConfig,
    RunConfig,
    RunLimits,
    load_config,
)


SAMPLE = Path(__file__).parents[2] / "config" / "development.toml"
ROLES = {"entry", "supervisor", "sql", "python", "answer", "reviewer", "clarification"}
SECRET = "credential-sentinel-do-not-serialize"


def load_sample() -> RunConfig:
    return load_config(SAMPLE, {})


def run_payload() -> dict[str, object]:
    return load_sample().model_dump(mode="json")


def write_toml(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def model_config_payload() -> dict[str, object]:
    return {
        "identity": None,
        "inference": None,
        "prompt_hash": None,
        "schema_hash": None,
        "credential_env": "PROVIDER_TOKEN",
    }


def test_canonical_offline_sample_loads_without_inventing_live_settings() -> None:
    config = load_sample()
    assert config.schema_version == 1
    assert config.profile == "offline"
    assert config.live_enabled is False
    assert config.hosted_tracing_enabled is False
    assert set(config.role_limits) == ROLES
    assert config.role_limits["python"].request_timeout_seconds is None
    assert config.operational is None
    assert config.build is None
    assert config.environment is None
    assert config.models == {}
    assert config.spend_caps is not None
    assert set(config.spend_caps.model_dump().values()) == {"0.00"}


def test_public_payload_round_trips_in_native_and_json_modes() -> None:
    config = load_sample()
    native = config.public_payload()
    assert RunConfig.model_validate(native).public_payload() == native
    assert RunConfig.model_validate_json(config.model_dump_json()).public_payload() == native


@pytest.mark.parametrize(
    ("field", "value"),
    [("schema_version", True), ("schema_version", 1.0), ("live_enabled", 1),
     ("hosted_tracing_enabled", "false")],
)
def test_top_level_literals_and_booleans_are_strict(field: str, value: object) -> None:
    payload = run_payload()
    payload[field] = value
    with pytest.raises(ValidationError):
        RunConfig.model_validate(payload)


def test_required_sections_unknown_keys_and_full_role_map_are_enforced() -> None:
    payload = run_payload()
    del payload["run_limits"]
    with pytest.raises(ValidationError):
        RunConfig.model_validate(payload)
    payload = run_payload()
    payload["unknown"] = 1
    with pytest.raises(ValidationError):
        RunConfig.model_validate(payload)
    payload = run_payload()
    del payload["role_limits"]["reviewer"]
    with pytest.raises(ValidationError, match="all seven roles"):
        RunConfig.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [("active_seconds", 3601), ("concurrent_actions", 3), ("pending_tasks", 5),
     ("review_passes", 3), ("clarification_slots", 3)],
)
def test_run_limits_reject_inconsistent_or_out_of_contract_caps(field: str, value: int) -> None:
    payload = run_payload()["run_limits"]
    payload[field] = value
    with pytest.raises(ValidationError):
        RunLimits.model_validate(payload)


def test_role_limits_enforce_scope_request_and_timeout_intersections() -> None:
    config = run_payload()
    config["role_limits"]["sql"]["limit_scope"] = "run"
    with pytest.raises(ValidationError, match="limit_scope"):
        RunConfig.model_validate(config)
    payload = run_payload()["role_limits"]["sql"]
    for field, value in (("request_input_tokens", 64001), ("logical_invocations", 9),
                         ("request_timeout_seconds", 121)):
        with pytest.raises(ValidationError):
            RoleLimits.model_validate({**payload, field: value})


def test_context_execution_and_review_limits_enforce_fixed_ceilings() -> None:
    payload = run_payload()
    context = payload["context_limits"]
    for field, value in (("evidence_views", 9), ("preview_columns", 33), ("charts", 5),
                         ("cell_utf8_bytes", 2049), ("default_preview_rows", 33),
                         ("compaction_trigger_percent", 101)):
        with pytest.raises(ValidationError):
            ContextLimits.model_validate({**context, field: value})
    with pytest.raises(ValidationError):
        ExecutionLimits.model_validate({**payload["sql_limits"], "execution_seconds": 121})
    for field, value in (("logical_passes", 3), ("logical_per_pass", 3),
                         ("max_findings", 9), ("json_bytes", 32769), ("total_seconds", 29)):
        with pytest.raises(ValidationError):
            ReviewLimits.model_validate({**payload["review_limits"], field: value})


def test_optional_context_capacities_accept_explicit_strict_zero() -> None:
    payload = run_payload()["context_limits"]
    optional = (
        "unanchored_candidates", "optional_exchanges", "entry_optional_tokens",
        "clarification_optional_tokens", "other_optional_tokens", "charts",
        "overflow_replans", "compaction_rebuilds",
    )
    for field in optional:
        assert ContextLimits.model_validate({**payload, field: 0}).model_dump()[field] == 0
        with pytest.raises(ValidationError):
            ContextLimits.model_validate({**payload, field: False})


def test_optional_operational_and_build_shapes_have_no_silent_defaults() -> None:
    with pytest.raises(ValidationError):
        OperationalSettings.model_validate({})
    operational = {
        "coordinator_lease_seconds": 20, "heartbeat_seconds": 5, "db_busy_timeout_ms": 1000,
        "operator_concurrent_runs": 2, "project_concurrent_runs": 1,
        "operator_intakes_per_hour": 10, "project_intakes_per_hour": 5,
        "concurrent_assessments": 1, "entry_wait_seconds": 10,
        "analytical_wait_seconds": 20, "unadmitted_upload_retention_seconds": 60,
    }
    assert OperationalSettings.model_validate(operational).heartbeat_seconds == 5
    with pytest.raises(ValidationError):
        OperationalSettings.model_validate({**operational, "heartbeat_seconds": 20})
    with pytest.raises(ValidationError):
        LocalBuildIdentity.model_validate({})


def test_absent_spend_caps_stays_unknown_and_zero_is_explicit() -> None:
    payload = run_payload()
    payload["spend_caps"] = None
    assert RunConfig.model_validate(payload).spend_caps is None
    payload = run_payload()
    payload["spend_caps"]["run"] = 0.0
    with pytest.raises(ValidationError):
        RunConfig.model_validate(payload)


def test_model_config_does_not_auto_select_identity_or_inference() -> None:
    model = RoleModelConfig.model_validate(model_config_payload())
    assert model.identity is None and model.inference is None
    assert model.credential_env == "PROVIDER_TOKEN"


def test_credentials_are_private_and_rotation_does_not_change_public_payload() -> None:
    payload = run_payload()
    payload["models"] = {"entry": model_config_payload()}
    first = RunConfig.model_validate(payload)
    first._set_credentials({"entry": SECRET})
    second = RunConfig.model_validate(payload)
    second._set_credentials({"entry": "rotated-secret"})
    assert first.credential("entry") is not None
    assert first.credential("entry").get_secret_value() == SECRET
    assert first.public_payload() == second.public_payload()
    representations = [repr(first), str(first), first.model_dump(), first.model_dump_json(), first.public_payload()]
    assert all(SECRET not in str(value) for value in representations)


def test_live_profile_may_be_an_inactive_plan_but_enabled_live_is_fail_closed() -> None:
    payload = run_payload()
    payload["profile"] = "live"
    assert RunConfig.model_validate(payload).profile == "live"
    payload["live_enabled"] = True
    config = RunConfig.model_validate(payload)
    missing = config.missing_live_settings()
    assert {"operational", "build", "environment", "live_authorization_ref"} <= set(missing)
    with pytest.raises(ConfigError, match="operational"):
        config.require_live_ready()


def test_live_enabled_requires_live_profile() -> None:
    payload = run_payload()
    payload["live_enabled"] = True
    with pytest.raises(ValidationError, match="profile='live'"):
        RunConfig.model_validate(payload)


def test_loader_sanitizes_toml_validation_and_secret_errors(tmp_path: Path) -> None:
    malformed = write_toml(tmp_path, "credential = '" + SECRET + "'\nnot = [valid")
    with pytest.raises(ConfigError) as error:
        load_config(malformed, {})
    assert SECRET not in str(error.value)
    unknown = write_toml(tmp_path, "schema_version = 1\ncredential = '" + SECRET + "'\n")
    with pytest.raises(ConfigError) as error:
        load_config(unknown, {})
    assert SECRET not in str(error.value)
    assert "credential" in str(error.value)


def test_loader_sanitizes_unsafe_provider_endpoint_errors(tmp_path: Path) -> None:
    identity = f"""
[models.entry]
credential_env = "PROVIDER_TOKEN"

[models.entry.identity]
provider = "google"
model_id = "test-model"
endpoint = "https://models.example.test/v1?token={SECRET}"
route = "primary"
account_tier = "free"
region = "global"
quota_identity = "quota"
sdk_name = "sdk"
sdk_version = "1"
protocol_version = "1"
tokenizer_version = "1"
tokenizer_build_hash = "{'a' * 64}"
rate_manifest_hash = "{'b' * 64}"
max_context_tokens = 4096
free_tier_enforced = true
accounting_verified = true
privacy_verified = true

[[models.entry.identity.rates]]
meter = "request"
unit_size = 1
usd_per_unit = "0.00"
"""
    path = write_toml(tmp_path, SAMPLE.read_text(encoding="utf-8") + identity)
    with pytest.raises(ConfigError) as error:
        load_config(path, {"PROVIDER_TOKEN": SECRET})
    assert SECRET not in str(error.value)
    assert "models.entry.identity.endpoint" in str(error.value)


def test_loader_ignores_unrelated_env_and_rejects_enabled_ambient_tracing() -> None:
    assert load_config(SAMPLE, {"UNRELATED_SECRET": SECRET}).public_payload() == load_sample().public_payload()
    for name in ("LANGCHAIN_TRACING_V2", "LANGSMITH_TRACING"):
        with pytest.raises(ConfigError, match=name):
            load_config(SAMPLE, {name: "true-" + SECRET})
    assert load_config(SAMPLE, {"LANGCHAIN_TRACING_V2": "off"}).hosted_tracing_enabled is False


def test_loader_reads_only_named_credentials_and_never_echoes_them(tmp_path: Path) -> None:
    text = SAMPLE.read_text(encoding="utf-8") + "\n[models.entry]\ncredential_env = 'PROVIDER_TOKEN'\n"
    config = load_config(write_toml(tmp_path, text), {"PROVIDER_TOKEN": SECRET, "OTHER_TOKEN": "ignored"})
    assert config.credential("entry").get_secret_value() == SECRET
    assert SECRET not in str(config.public_payload())
    assert "OTHER_TOKEN" not in str(config)


def test_partial_model_configuration_is_reported_incomplete() -> None:
    payload = run_payload()
    payload["profile"] = "live"
    payload["models"] = {"entry": model_config_payload()}
    config = RunConfig.model_validate(payload)
    missing = config.missing_live_settings()
    assert "models.entry.identity" in missing
    assert "models.entry.inference" in missing
    assert "models.entry.credential" in missing
    assert "models.supervisor" in missing


def test_loader_rejects_hosted_tracing_and_invokes_live_readiness(tmp_path: Path) -> None:
    hosted = SAMPLE.read_text(encoding="utf-8").replace(
        "hosted_tracing_enabled = false", "hosted_tracing_enabled = true")
    with pytest.raises(ConfigError, match="hosted_tracing_enabled"):
        load_config(write_toml(tmp_path, hosted), {})
    live = SAMPLE.read_text(encoding="utf-8").replace('profile = "offline"', 'profile = "live"')
    live = live.replace("live_enabled = false", "live_enabled = true")
    with pytest.raises(ConfigError, match="operational"):
        load_config(write_toml(tmp_path, live), {})
