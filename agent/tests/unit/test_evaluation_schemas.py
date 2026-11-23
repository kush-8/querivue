"""Synthetic shape checks only; these records are not provider, build, or oracle proof."""

from copy import deepcopy
from decimal import Decimal

import pytest
from pydantic import ValidationError

from querivue_agent.contracts.evaluation import (
    CaseEvaluation, CostBreakdown, CostForecast, EvaluationReport, FixtureCase, GateResult,
    GoldTable, MetricCount, OracleResult, PrecisionPolicy,
)


U1 = "123e4567-e89b-42d3-a456-426614174001"
U2 = "123e4567-e89b-42d3-a456-426614174002"
U3 = "123e4567-e89b-42d3-a456-426614174003"
U4 = "123e4567-e89b-42d3-a456-426614174004"
U5 = "123e4567-e89b-42d3-a456-426614174005"
C1 = "123e4567-e89b-12d3-a456-426614174011"
C2 = "123e4567-e89b-12d3-a456-426614174012"
H1 = "a" * 64
H2 = "b" * 64
H3 = "c" * 64


def artifact(sha256: str = H1) -> dict[str, object]:
    return {
        "artifact_id": C1,
        "storage_ref": C2,
        "media_type": "application/octet-stream",
        "size_bytes": 12,
        "sha256": sha256,
        "environment_manifest_id": U5,
    }


def constraints() -> dict[str, object]:
    return {
        "metric_definitions": {},
        "filters": [],
        "date_windows": [],
        "analysis_timezone": None,
        "grain": None,
        "units": {},
    }


def import_settings() -> dict[str, object]:
    return {
        "settings_version": "1",
        "source_format": "csv",
        "selections": [{
            "source": {"kind": "file", "format": "csv"},
            "header_present": True,
            "header_row": 1,
            "columns": [{
                "source_position": 0,
                "original_label": "amount",
                "requested_type": {"tag": "decimal", "precision": 8, "scale": 2},
                "missing_markers": [],
                "decimal_separator": ".",
                "thousands_separator": None,
                "datetime_format": None,
                "source_timezone": None,
                "conversion_choice": None,
            }],
        }],
        "dialect": {
            "encoding": "utf-8", "delimiter": ",", "quote": "\"", "escape": None,
            "strip_bom": True,
        },
        "confirmation_id": C1,
    }


def oracle_spec() -> dict[str, object]:
    return {
        "method": "integer_decimal",
        "implementation_ref": artifact(H2),
        "gold_values": [{
            "key": "total", "value": {"kind": "decimal", "value": "12.50", "precision": 8,
            "scale": 2}, "unit": "USD",
        }],
        "gold_table": {
            "columns": [{
                "name": "amount", "type": {"tag": "decimal", "precision": 8, "scale": 2},
                "nullable": True,
            }],
            "rows": [
                [{"kind": "decimal", "value": "12.50", "precision": 8, "scale": 2}],
                [{"kind": "null", "value": None}],
            ],
        },
        "precision": {
            "mode": "exact", "decimal_places": None, "absolute_tolerance": None,
            "relative_tolerance": None, "rounding_mode": "half_even",
        },
        "coverage": "all declared obligations",
        "rubric": [],
    }


def fixture_case() -> dict[str, object]:
    return {
        "manifest_version": "querivue-eval-v1",
        "case_id": "D01",
        "split": "development",
        "family": "exact_numeric",
        "template_family": "sum",
        "generator_hash": H1,
        "original_question": "What is the total?",
        "obligations": [{
            "key": "answer", "description": "Report the total", "deliverable": "numerical",
            "constraints": constraints(),
        }],
        "sources": [{
            "dataset_id": U1,
            "source_format": "csv",
            "filename": "untrusted.csv",
            "source_bytes": artifact(H1),
            "upload_hash": H1,
            "settings": import_settings(),
            "expected_table_count": 1,
        }],
        "expected_entry": "accept",
        "expected_route": "analysis",
        "expected_outcome": "complete",
        "complete_answer_eligible": True,
        "required_events": ["oracle_checked"],
        "forbidden_events": ["published_before_review"],
        "oracle": oracle_spec(),
        "scripted_replies": ["Use net amount"],
        "fault": None,
        "applicable_gates": ["G01", "G10"],
        "dependencies": [{"dataset_id": C1, "snapshot_id": C2}],
        "fixture_hash": H1,
        "oracle_hash": H2,
        "rubric_hash": H3,
    }


def oracle_result(
    case_id: str = "D01", verdict: str = "passed", complete: bool = True,
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "verdict": verdict,
        "checked_obligations": ["answer"] if complete else [],
        "missing_obligations": [],
        "findings": [],
        "actual_values": [],
        "expected_values": [],
        "checked_events": ["reviewed"] if complete else [],
        "complete": complete,
        "oracle_hash": H2,
        "diagnostic_ref": None,
    }


def known_cost(value: str = "0") -> dict[str, object]:
    return {
        "model": value, "judge": "0", "sandbox": "0", "storage": "0", "validator": "0",
        "total": value,
    }


def unknown_cost() -> dict[str, object]:
    return {
        "model": None, "judge": None, "sandbox": None, "storage": None, "validator": None,
        "total": None,
    }


def forecast() -> dict[str, object]:
    return {
        "roles": [{
            "role": "answer", "logical_calls": 1, "physical_calls": 1, "input_tokens": 10,
            "output_tokens": 5, "maximum_usd": "1.25",
        }],
        "non_model": known_cost("0.75"),
        "maximum_usd": "2.00",
        "caps": {
            "operator": "0", "project": "10", "intake": "1", "action": "2", "run": "4",
            "suite": "10",
        },
        "cache_assumption": "none",
        "cache_evidence_ref": None,
        "repetitions": 1,
        "reason": "upper bound",
    }


def case_evaluation(
    status: str = "completed", case_id: str = "D01",
) -> dict[str, object]:
    if status == "completed":
        return {
            "case_id": case_id, "repetition": 1, "status": status, "run_id": C1,
            "terminal_class": "correct_complete", "oracle": oracle_result(case_id),
            "route": "analysis", "review": None, "input_tokens": 10, "output_tokens": 5,
            "active_milliseconds": 8, "wall_milliseconds": 10, "costs": known_cost("1.00"),
            "events": ["completed"],
        }
    verdict = "blocked" if status == "preflight_failed" else "not_run"
    return {
        "case_id": case_id, "repetition": 1, "status": status, "run_id": None,
        "terminal_class": "operational_stop" if status == "preflight_failed" else None,
        "oracle": oracle_result(case_id, verdict, False), "route": "withhold", "review": None,
        "input_tokens": None, "output_tokens": None, "active_milliseconds": None,
        "wall_milliseconds": None, "costs": unknown_cost(), "events": [status],
    }


def approved_review() -> dict[str, object]:
    return {
        "status": "reviewed", "verdict": "approved", "findings": [], "review_id": C1,
        "draft_id": C2, "draft_content_hash": H1, "draft_input_packet_hash": H2,
        "review_input_packet_hash": H3, "rendering_policy_version": "1", "review_pass": 1,
    }


def rejected_review() -> dict[str, object]:
    value = approved_review()
    value["verdict"] = "rejected"
    value["findings"] = [{
        "finding_id": "false-rejection", "category": "draft", "block_ids": [],
        "explanation": "incorrectly rejected", "support_refs": [],
        "required_change": "No change was actually required",
    }]
    return value


def failed_review() -> dict[str, object]:
    value = approved_review()
    value.pop("verdict")
    value.pop("findings")
    value["status"] = "failed"
    value["error_ref"] = U3
    return value


def report() -> dict[str, object]:
    return {
        "report_id": U4,
        "manifest_hash": H1,
        "configuration_hash": H2,
        "commit": "abc123",
        "dirty_patch_hash": None,
        "split": "development",
        "mode": "scripted",
        "scheduled_count": 1,
        "completed_count": 1,
        "case_results": [case_evaluation()],
        "safety_gates": [{
            "gate_id": "G01", "status": "passed", "evidence_kind": "scripted",
            "evidence_ref": artifact(H3), "explanation": "synthetic schema evidence",
        }],
        "metrics": [{
            "name": "correct", "numerator": 1, "denominator": 1,
            "family": "exact_numeric", "route": "analysis",
        }],
        "costs": known_cost("1.00"),
        "forecast": forecast(),
        "actual_build_manifest_ids": [C1],
        "generated_at": "2026-11-24T01:00:00Z",
    }


def test_fixture_case_native_and_json_round_trip() -> None:
    case = FixtureCase.model_validate(fixture_case())
    assert FixtureCase.model_validate_json(case.model_dump_json()) == case


def test_fixture_records_rubric_fault_and_invalidation_without_completeness_claim() -> None:
    payload = fixture_case()
    payload["oracle"]["method"] = "rubric"
    payload["oracle"]["implementation_ref"] = None
    payload["oracle"]["rubric"] = ["Explains the limitation"]
    payload["fault"] = {
        "point": "after provider request", "kind": "unknown_completion",
        "payload_ref": artifact(H3),
    }
    payload["expected_outcome"] = "invalidated"
    payload["complete_answer_eligible"] = False
    case = FixtureCase.model_validate(payload)
    assert case.fault is not None and case.oracle.method == "rubric"


def test_oracle_result_native_and_json_round_trip() -> None:
    result = OracleResult.model_validate(oracle_result())
    assert OracleResult.model_validate_json(result.model_dump_json()) == result


def test_evaluation_report_native_and_json_round_trip() -> None:
    value = EvaluationReport.model_validate(report())
    assert EvaluationReport.model_validate_json(value.model_dump_json()) == value


@pytest.mark.parametrize("field", ["case_id", "split", "family", "manifest_version"])
def test_fixture_rejects_invalid_frozen_vocabulary(field: str) -> None:
    payload = fixture_case()
    payload[field] = {"case_id": "D25", "split": "held_out", "family": "other",
                      "manifest_version": "v2"}[field]
    with pytest.raises(ValidationError):
        FixtureCase.model_validate(payload)


@pytest.mark.parametrize("mutation", ["missing", "extra", "bool"])
def test_fixture_is_strict_for_required_fields_extras_and_bools(mutation: str) -> None:
    payload = fixture_case()
    if mutation == "missing":
        del payload["oracle_hash"]
    elif mutation == "extra":
        payload["proof"] = True
    else:
        payload["complete_answer_eligible"] = 1
    with pytest.raises(ValidationError):
        FixtureCase.model_validate(payload)


def test_fixture_rejects_source_hash_format_and_duplicate_ids() -> None:
    payload = fixture_case()
    payload["sources"][0]["upload_hash"] = H2
    with pytest.raises(ValidationError):
        FixtureCase.model_validate(payload)
    payload = fixture_case()
    payload["sources"][0]["settings"]["source_format"] = "json"
    with pytest.raises(ValidationError):
        FixtureCase.model_validate(payload)
    payload = fixture_case()
    payload["sources"].append(deepcopy(payload["sources"][0]))
    with pytest.raises(ValidationError):
        FixtureCase.model_validate(payload)


def test_fixture_rejects_event_overlap_and_ineligible_outcome_claim() -> None:
    payload = fixture_case()
    payload["forbidden_events"] = ["oracle_checked"]
    with pytest.raises(ValidationError):
        FixtureCase.model_validate(payload)
    payload = fixture_case()
    payload["expected_outcome"] = "partial"
    with pytest.raises(ValidationError):
        FixtureCase.model_validate(payload)


def test_fixture_rejects_malformed_hash_and_non_runtime_dataset_id() -> None:
    payload = fixture_case()
    payload["fixture_hash"] = "A" * 64
    with pytest.raises(ValidationError):
        FixtureCase.model_validate(payload)
    payload = fixture_case()
    payload["sources"][0]["dataset_id"] = C1
    with pytest.raises(ValidationError):
        FixtureCase.model_validate(payload)


@pytest.mark.parametrize(
    ("mode", "places", "absolute", "relative"),
    [
        ("exact", None, None, None),
        ("decimal_places", 2, None, None),
        ("tolerance", None, {"kind": "decimal", "value": "0.01", "precision": 2, "scale": 2}, None),
        ("tolerance", None, None, {"kind": "float64", "value": 0.1}),
    ],
)
def test_precision_policy_variants(
    mode: str, places: int | None, absolute: dict[str, object] | None,
    relative: dict[str, object] | None,
) -> None:
    PrecisionPolicy.model_validate({
        "mode": mode, "decimal_places": places, "absolute_tolerance": absolute,
        "relative_tolerance": relative, "rounding_mode": "half_even",
    })


@pytest.mark.parametrize(
    "payload",
    [
        {"mode": "exact", "decimal_places": 2, "absolute_tolerance": None,
         "relative_tolerance": None, "rounding_mode": "half_even"},
        {"mode": "decimal_places", "decimal_places": None, "absolute_tolerance": None,
         "relative_tolerance": None, "rounding_mode": "half_even"},
        {"mode": "tolerance", "decimal_places": None,
         "absolute_tolerance": {"kind": "string", "value": "0.1"},
         "relative_tolerance": None, "rounding_mode": "half_even"},
        {"mode": "tolerance", "decimal_places": None,
         "absolute_tolerance": {"kind": "int64", "value": "-1"},
         "relative_tolerance": None, "rounding_mode": "half_even"},
    ],
)
def test_precision_policy_rejects_malformed_combinations(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        PrecisionPolicy.model_validate(payload)


def test_gold_table_rejects_width_kind_decimal_and_nullability_mismatches() -> None:
    column = {"name": "x", "type": {"tag": "decimal", "precision": 8, "scale": 2},
              "nullable": False}
    invalid_rows = [
        [],
        [{"kind": "string", "value": "12.50"}],
        [{"kind": "decimal", "value": "12.50", "precision": 9, "scale": 2}],
        [{"kind": "null", "value": None}],
    ]
    for row in invalid_rows:
        with pytest.raises(ValidationError):
            GoldTable.model_validate({"columns": [column], "rows": [row]})


@pytest.mark.parametrize("verdict", ["failed", "not_run", "blocked"])
def test_oracle_failure_variants_remain_explicit(verdict: str) -> None:
    result = OracleResult.model_validate(oracle_result(verdict=verdict, complete=False))
    assert result.verdict == verdict
    assert not result.complete


def test_passed_oracle_cannot_hide_missing_or_blocking_findings() -> None:
    payload = oracle_result()
    payload["findings"] = ["wrong value"]
    with pytest.raises(ValidationError):
        OracleResult.model_validate(payload)


def test_costs_distinguish_unknown_from_known_zero_and_sum_large_decimals_exactly() -> None:
    assert CostBreakdown.model_validate(unknown_cost()).total is None
    assert CostBreakdown.model_validate(known_cost()).total == "0"
    huge = "9" * 100
    payload = {"model": huge, "judge": "1", "sandbox": "0", "storage": "0",
               "validator": "0", "total": "1" + "0" * 100}
    assert CostBreakdown.model_validate(payload).total == payload["total"]
    payload["total"] = huge
    with pytest.raises(ValidationError):
        CostBreakdown.model_validate(payload)


def test_forecast_requires_known_exact_maximum_and_cache_evidence_pairing() -> None:
    CostForecast.model_validate(forecast())
    payload = forecast()
    payload["non_model"] = unknown_cost()
    with pytest.raises(ValidationError):
        CostForecast.model_validate(payload)
    payload = forecast()
    payload["cache_assumption"] = "explicit_verified"
    with pytest.raises(ValidationError):
        CostForecast.model_validate(payload)
    payload = forecast()
    payload["maximum_usd"] = "1.99"
    with pytest.raises(ValidationError):
        CostForecast.model_validate(payload)
    payload = forecast()
    payload["roles"][0]["physical_calls"] = 0
    with pytest.raises(ValidationError):
        CostForecast.model_validate(payload)


def test_metric_rate_is_read_only_nonserialized_and_zero_denominator_is_na() -> None:
    metric = MetricCount.model_validate({
        "name": "none", "numerator": 0, "denominator": 0, "family": None, "route": None,
    })
    assert metric.rate is None
    assert "rate" not in metric.model_dump()
    repeated = MetricCount.model_validate({
        "name": "passes", "numerator": 2, "denominator": 3, "family": None, "route": None,
    })
    assert repeated.rate == Decimal(2) / Decimal(3)
    with pytest.raises(ValidationError):
        MetricCount.model_validate({
            "name": "bad", "numerator": 1, "denominator": 0, "family": None, "route": None,
        })


@pytest.mark.parametrize("status", ["completed", "preflight_failed", "not_run"])
def test_case_evaluation_retains_terminal_status_variants(status: str) -> None:
    value = CaseEvaluation.model_validate(case_evaluation(status))
    assert value.status == status


def test_not_run_rejects_invented_usage_and_preflight_requires_operational_stop() -> None:
    payload = case_evaluation("not_run")
    payload["input_tokens"] = 0
    with pytest.raises(ValidationError):
        CaseEvaluation.model_validate(payload)
    payload = case_evaluation("preflight_failed")
    payload["terminal_class"] = "correct_complete"
    with pytest.raises(ValidationError):
        CaseEvaluation.model_validate(payload)


def test_false_approval_is_preserved_as_incorrect_publication() -> None:
    payload = case_evaluation()
    payload["oracle"] = oracle_result(verdict="failed", complete=False)
    payload["review"] = approved_review()
    payload["terminal_class"] = "incorrect_publication"
    value = CaseEvaluation.model_validate(payload)
    assert value.review is not None and value.review.status == "reviewed"
    assert value.review.verdict == "approved"


def test_false_rejection_is_preserved_as_incorrect_withholding() -> None:
    payload = case_evaluation()
    payload["review"] = rejected_review()
    payload["terminal_class"] = "incorrect_withholding"
    value = CaseEvaluation.model_validate(payload)
    assert value.review is not None and value.review.status == "reviewed"
    assert value.review.verdict == "rejected"


def test_failed_oracle_may_preserve_cannot_complete_review() -> None:
    payload = case_evaluation()
    payload["oracle"] = oracle_result(verdict="failed", complete=False)
    payload["review"] = {"status": "cannot_complete", "explanation": "oracle did not pass"}
    value = CaseEvaluation.model_validate(payload)
    assert value.review is not None and value.review.status == "cannot_complete"


@pytest.mark.parametrize(
    "review",
    [
        failed_review(),
        {"status": "cannot_complete", "explanation": "review produced no verdict"},
    ],
)
def test_review_failure_and_no_verdict_round_trip_without_becoming_approval(
    review: dict[str, object],
) -> None:
    payload = case_evaluation()
    payload["review"] = review
    value = CaseEvaluation.model_validate(payload)
    restored = CaseEvaluation.model_validate_json(value.model_dump_json())
    assert restored.review is not None
    assert restored.review.status in {"failed", "cannot_complete"}
    assert not hasattr(restored.review, "verdict")
    if restored.review.status == "failed":
        assert restored.review.error_ref == U3


def test_not_run_requires_not_run_oracle_result() -> None:
    payload = case_evaluation("not_run")
    payload["oracle"] = oracle_result(verdict="blocked", complete=False)
    with pytest.raises(ValidationError):
        CaseEvaluation.model_validate(payload)


def test_gate_pass_requires_evidence_and_all_statuses_are_recordable() -> None:
    with pytest.raises(ValidationError):
        GateResult.model_validate({
            "gate_id": "G01", "status": "passed", "evidence_kind": "scripted",
            "evidence_ref": None, "explanation": "missing",
        })
    for status in ("failed", "not_run", "blocked"):
        assert GateResult.model_validate({
            "gate_id": "G10", "status": status, "evidence_kind": "not_applicable",
            "evidence_ref": None, "explanation": status,
        }).status == status


def test_report_keeps_not_run_and_preflight_cases_in_scheduled_count() -> None:
    payload = report()
    payload["case_results"] = [
        case_evaluation("completed", "D01"), case_evaluation("preflight_failed", "D02"),
        case_evaluation("not_run", "D03"),
    ]
    payload["scheduled_count"] = 3
    payload["completed_count"] = 1
    payload["costs"] = unknown_cost()
    value = EvaluationReport.model_validate(payload)
    assert [item.status for item in value.case_results] == [
        "completed", "preflight_failed", "not_run",
    ]


def test_report_rejects_dropped_counts_duplicates_split_and_cost_mismatch() -> None:
    payload = report()
    payload["scheduled_count"] = 0
    with pytest.raises(ValidationError):
        EvaluationReport.model_validate(payload)
    payload = report()
    payload["case_results"].append(deepcopy(payload["case_results"][0]))
    payload["scheduled_count"] = 2
    payload["completed_count"] = 2
    payload["costs"] = known_cost("2.00")
    with pytest.raises(ValidationError):
        EvaluationReport.model_validate(payload)
    payload = report()
    payload["split"] = "held_out"
    with pytest.raises(ValidationError):
        EvaluationReport.model_validate(payload)
    payload = report()
    payload["costs"] = known_cost("0.99")
    with pytest.raises(ValidationError):
        EvaluationReport.model_validate(payload)
