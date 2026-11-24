import json
import pytest
from pydantic import TypeAdapter, ValidationError

from querivue_agent.contracts.responses import (
    AnswerBlocked, AnswerDraftReady, AnswerFailed, AnswerOutcome, CannotCompleteAssessment,
    ReviewAssessment, ReviewedAssessment, ReviewFailed, ReviewFinding, ReviewOutcome,
)


ID = "123e4567-e89b-12d3-a456-426614174000"
OTHER_ID = "d816d53d-eac8-4d98-978e-97c1bd81f127"
HASH = "a" * 64
DRAFT = {
    "blocks": [{
        "block_id": "claim-1", "kind": "data_claim",
        "spans": [{"kind": "text", "text": "Revenue rose."}],
        "supports": [],
    }],
    "unmet_deliverables": [],
}
ANSWER_DRAFT = {"status": "draft_ready", "draft": DRAFT, "completeness": "complete"}
ANSWER_BLOCKED = {
    "status": "blocked", "explanation": "Need a definition",
    "requirements": [{"kind": "definition", "description": "Define revenue"}],
}
ANSWER_FAILED = {"status": "failed", "error_ref": ID}
BINDING = {
    "review_id": ID,
    "draft_id": OTHER_ID,
    "draft_content_hash": HASH,
    "draft_input_packet_hash": "b" * 64,
    "review_input_packet_hash": "0" * 64,
    "rendering_policy_version": "v1",
    "review_pass": 1,
}
FINDING = {
    "finding_id": "finding-1", "category": "evidence", "block_ids": ["claim-1"],
    "explanation": "No supporting cell", "support_refs": [],
    "required_change": "Add a value span",
}
APPROVED = {**BINDING, "status": "reviewed", "verdict": "approved", "findings": []}
REJECTED = {**BINDING, "status": "reviewed", "verdict": "rejected", "findings": [FINDING]}
CANNOT = {"status": "cannot_complete", "explanation": "Review input is unavailable"}
REVIEW_FAILED = {**BINDING, "status": "failed", "error_ref": ID}


@pytest.mark.parametrize("payload,model", [
    (ANSWER_DRAFT, AnswerDraftReady), (ANSWER_BLOCKED, AnswerBlocked), (ANSWER_FAILED, AnswerFailed),
])
def test_answer_variants_round_trip(payload, model):
    adapter = TypeAdapter(AnswerOutcome)
    result = adapter.validate_python(payload)
    assert isinstance(result, model)
    assert adapter.validate_json(json.dumps(payload)) == result
    assert model.model_validate(payload) == result


def test_answer_completeness_requirements_and_failure_reference_rules():
    assert AnswerDraftReady.model_validate({**ANSWER_DRAFT, "completeness": "partial"})
    with pytest.raises(ValidationError):
        AnswerDraftReady.model_validate({**ANSWER_DRAFT, "completeness": "unknown"})
    with pytest.raises(ValidationError):
        AnswerBlocked.model_validate({**ANSWER_BLOCKED, "requirements": []})
    for requirement in [
        {"kind": "evidence", "description": "Need rows"},
        {"kind": "definition", "description": "Need terms"},
        {"kind": "conflict", "description": "Resolve mismatch"},
    ]:
        assert AnswerBlocked.model_validate({**ANSWER_BLOCKED, "requirements": [requirement]})
    with pytest.raises(ValidationError):
        AnswerFailed.model_validate({**ANSWER_FAILED, "error_ref": ID.upper()})


@pytest.mark.parametrize("payload,model", [
    (APPROVED, ReviewedAssessment), (REJECTED, ReviewedAssessment),
    (CANNOT, CannotCompleteAssessment),
])
def test_review_assessment_variants_round_trip(payload, model):
    adapter = TypeAdapter(ReviewAssessment)
    result = adapter.validate_python(payload)
    assert isinstance(result, model)
    assert adapter.validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("payload,model", [(APPROVED, ReviewedAssessment), (REJECTED, ReviewedAssessment), (REVIEW_FAILED, ReviewFailed)])
def test_review_outcome_variants_round_trip(payload, model):
    adapter = TypeAdapter(ReviewOutcome)
    result = adapter.validate_python(payload)
    assert isinstance(result, model)
    assert adapter.validate_json(json.dumps(payload)) == result


def test_cannot_complete_is_assessment_but_not_review_outcome():
    assert isinstance(TypeAdapter(ReviewAssessment).validate_python(CANNOT), CannotCompleteAssessment)
    with pytest.raises(ValidationError):
        TypeAdapter(ReviewOutcome).validate_python(CANNOT)


def test_review_binding_pass_bound_and_runtime_authority_boundary():
    assert ReviewedAssessment.model_validate({**APPROVED, "review_pass": 2}).review_pass == 2
    with pytest.raises(ValidationError):
        ReviewedAssessment.model_validate({**APPROVED, "review_pass": 3})
    with pytest.raises(ValidationError, match="extra_forbidden"):
        TypeAdapter(ReviewOutcome).validate_python({**APPROVED, "execute": True})


def test_finding_rules_and_support_target_validation():
    assert ReviewFinding.model_validate({**FINDING, "block_ids": []})
    assert ReviewFinding.model_validate({
        **FINDING,
        "support_refs": [{"kind": "coverage", "evidence_id": ID}],
    })
    for change in [
        {"finding_id": ""}, {"finding_id": "é" * 33}, {"block_ids": ["claim-1", "claim-1"]},
        {"block_ids": ["é" * 33]}, {"explanation": " "}, {"required_change": ""},
        {"support_refs": [{"kind": "value", "evidence_id": ID}]},
    ]:
        with pytest.raises(ValidationError):
            ReviewFinding.model_validate({**FINDING, **change})


def test_verdict_findings_consistency_and_unique_finding_ids():
    with pytest.raises(ValidationError, match="approved requires"):
        ReviewedAssessment.model_validate({**APPROVED, "findings": [FINDING]})
    with pytest.raises(ValidationError, match="rejected requires"):
        ReviewedAssessment.model_validate({**REJECTED, "findings": []})
    with pytest.raises(ValidationError, match="finding_id"):
        ReviewedAssessment.model_validate({**REJECTED, "findings": [FINDING, FINDING]})


def test_reviewer_finding_shape_bounds_are_utf8_aware():
    assert len(ReviewFinding.model_validate({
        **FINDING,
        "block_ids": [f"b-{index}" for index in range(16)],
        "support_refs": [{"kind": "coverage", "evidence_id": ID} for _ in range(16)],
        "explanation": "界" * 341 + "a",
        "required_change": "界" * 341 + "a",
    }).explanation.encode("utf-8")) == 1024
    for change in (
        {"block_ids": [f"b-{index}" for index in range(17)]},
        {"support_refs": [{"kind": "coverage", "evidence_id": ID} for _ in range(17)]},
        {"explanation": "界" * 342},
        {"required_change": "界" * 342},
    ):
        with pytest.raises(ValidationError):
            ReviewFinding.model_validate({**FINDING, **change})


def test_reviewer_finding_count_and_support_occurrence_bounds_reject_whole_shape():
    findings = [{**FINDING, "finding_id": f"finding-{index}"} for index in range(8)]
    assert len(ReviewedAssessment.model_validate({**REJECTED, "findings": findings}).findings) == 8
    with pytest.raises(ValidationError):
        ReviewedAssessment.model_validate({
            **REJECTED,
            "findings": findings + [{**FINDING, "finding_id": "finding-9"}],
        })
    too_many_supports = [
        {
            **FINDING,
            "finding_id": f"finding-{index}",
            "support_refs": [{"kind": "coverage", "evidence_id": ID} for _ in range(9)],
        }
        for index in range(8)
    ]
    with pytest.raises(ValidationError, match="64"):
        ReviewedAssessment.model_validate({**REJECTED, "findings": too_many_supports})


def test_cannot_complete_explanation_has_1024_utf8_byte_bound():
    accepted = CannotCompleteAssessment.model_validate({
        **CANNOT,
        "explanation": "界" * 341 + "a",
    })
    assert len(accepted.explanation.encode("utf-8")) == 1024
    with pytest.raises(ValidationError):
        CannotCompleteAssessment.model_validate({**CANNOT, "explanation": "界" * 342})
