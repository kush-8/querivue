import json
from copy import deepcopy
from uuid import UUID

import pytest
from pydantic import TypeAdapter, ValidationError

from querivue_agent.contracts.actions import (
    Action, CandidateInterpretation, ClarificationAction, DirectAnswer,
)
from querivue_agent.contracts.content import QuestionContent, QuestionSpan, Suggestion
from querivue_agent.contracts.responses import (
    ClarificationBlocked, ClarificationFailed, ClarificationOutcome,
    ClarificationQuestionReady,
)


ACTION_ID = "123e4567-e89b-42d3-a456-426614174000"
V1_ID = "123e4567-e89b-12d3-a456-426614174000"
OTHER_ID = "d816d53d-eac8-4d98-978e-97c1bd81f127"
CELL = {"kind": "cell", "evidence_id": V1_ID, "row_locator": 0, "column_ordinal": 1}
CONTEXT = {"kind": "context", "context_ref": V1_ID}
TEXT = {"kind": "text", "text": "Choose a meaning"}
VALUE = {"kind": "value", "target": CELL, "format": "exact"}
BLOCK = {
    "block_id": "answer-1",
    "kind": "general_explanation",
    "spans": [TEXT],
    "supports": [CONTEXT],
}
CONSTRAINTS = {
    "metric_definitions": {}, "filters": [], "date_windows": [],
    "analysis_timezone": None, "grain": None, "units": {},
}
DIRECT = {
    "action_id": ACTION_ID,
    "type": "direct_answer",
    "basis": "knowledge",
    "evidence_ids": [],
    "chart_artifact_ids": [],
    "context_refs": [V1_ID],
    "blocks": [BLOCK],
}
CANDIDATE = {
    "candidate_id": "candidate-1",
    "interpretation": "Use booked revenue",
    "basis_refs": [CELL, CONTEXT],
}
CLARIFY = {
    "action_id": ACTION_ID,
    "type": "clarify",
    "issue": "Revenue is ambiguous",
    "candidate_interpretations": [CANDIDATE],
    "constraints": CONSTRAINTS,
    "input_evidence_ids": [V1_ID],
    "context_refs": [OTHER_ID],
}
QUESTION = {"spans": [TEXT, VALUE], "supports": [CELL, CONTEXT]}
SUGGESTION = {
    "option_id": "option-1",
    "candidate_refs": ["candidate-1"],
    "content": {"spans": [TEXT], "supports": []},
}
READY = {
    "status": "question_ready",
    "question": QUESTION,
    "suggestions": [SUGGESTION, {**SUGGESTION, "option_id": "option-2"}],
}


@pytest.mark.parametrize(
    "payload,model", [(DIRECT, DirectAnswer), (CLARIFY, ClarificationAction)],
)
def test_new_actions_round_trip_through_discriminated_union(payload, model):
    adapter = TypeAdapter(Action)
    result = adapter.validate_python(payload)
    assert isinstance(result, model)
    assert result.model_dump() == payload
    assert adapter.validate_json(json.dumps(payload)) == result


def test_direct_answer_basis_and_reference_rules():
    for basis in ("knowledge", "evidence"):
        assert DirectAnswer.model_validate({**DIRECT, "basis": basis}).basis == basis
    with pytest.raises(ValidationError):
        DirectAnswer.model_validate({**DIRECT, "basis": "guess"})
    for field in ("evidence_ids", "chart_artifact_ids", "context_refs"):
        assert getattr(DirectAnswer.model_validate({**DIRECT, field: [V1_ID]}), field) == [V1_ID]
        with pytest.raises(ValidationError, match="unique"):
            DirectAnswer.model_validate({**DIRECT, field: [V1_ID, V1_ID]})
    with pytest.raises(ValidationError):
        DirectAnswer.model_validate({**DIRECT, "action_id": V1_ID})


def test_direct_answer_reuses_draft_block_and_aggregate_ceilings():
    blocks = [{**BLOCK, "block_id": f"b{i}", "spans": [TEXT] * 8} for i in range(16)]
    assert DirectAnswer.model_validate({**DIRECT, "blocks": blocks})
    with pytest.raises(ValidationError, match="128 spans"):
        DirectAnswer.model_validate({**DIRECT, "blocks": [{**blocks[0], "spans": [TEXT] * 9}, *blocks[1:]]})
    with pytest.raises(ValidationError, match="unique"):
        DirectAnswer.model_validate({**DIRECT, "blocks": [BLOCK, BLOCK]})
    supports = [{"kind": "context", "context_ref": str(UUID(int=i))} for i in range(1, 129)]
    assert DirectAnswer.model_validate({**DIRECT, "blocks": [{**BLOCK, "supports": supports}]})
    supports.append({"kind": "context", "context_ref": str(UUID(int=129))})
    with pytest.raises(ValidationError, match="128 distinct targets"):
        DirectAnswer.model_validate({**DIRECT, "blocks": [{**BLOCK, "supports": supports}]})


def test_clarification_action_allows_empty_candidates_and_references():
    result = ClarificationAction.model_validate({
        **CLARIFY, "candidate_interpretations": [], "input_evidence_ids": [], "context_refs": [],
    })
    assert result.candidate_interpretations == []
    assert result.input_evidence_ids == result.context_refs == []


def test_candidate_shape_ids_and_allowed_basis_targets():
    assert CandidateInterpretation.model_validate(CANDIDATE).model_dump() == CANDIDATE
    assert CandidateInterpretation.model_validate({**CANDIDATE, "basis_refs": []})
    for target in (
        {"kind": "chart", "chart_artifact_id": V1_ID},
        {"kind": "coverage", "evidence_id": V1_ID},
    ):
        with pytest.raises(ValidationError):
            CandidateInterpretation.model_validate({**CANDIDATE, "basis_refs": [target]})
    with pytest.raises(ValidationError):
        CandidateInterpretation.model_validate({**CANDIDATE, "candidate_id": "é" * 33})
    with pytest.raises(ValidationError, match="unique"):
        ClarificationAction.model_validate({**CLARIFY, "candidate_interpretations": [CANDIDATE, CANDIDATE]})


def test_clarification_action_reference_lists_are_unique_and_accept_v1():
    for field in ("input_evidence_ids", "context_refs"):
        assert getattr(ClarificationAction.model_validate({**CLARIFY, field: [V1_ID]}), field) == [V1_ID]
        with pytest.raises(ValidationError, match="unique"):
            ClarificationAction.model_validate({**CLARIFY, field: [V1_ID, V1_ID]})


def test_question_content_and_suggestion_shape():
    assert QuestionContent.model_validate(QUESTION).model_dump() == QUESTION
    assert TypeAdapter(QuestionSpan).validate_python(VALUE)
    assert Suggestion.model_validate(SUGGESTION).model_dump() == SUGGESTION
    with pytest.raises(ValidationError):
        QuestionContent.model_validate({"spans": [], "supports": []})
    with pytest.raises(ValidationError, match="unique"):
        Suggestion.model_validate({**SUGGESTION, "candidate_refs": ["candidate-1"] * 2})
    assert Suggestion.model_validate({
        **SUGGESTION, "candidate_refs": ["runtime-checks-this-reference"],
    })
    for forbidden in (
        {"kind": "chart", "chart_artifact_id": V1_ID},
        {"kind": "coverage", "evidence_id": V1_ID},
    ):
        with pytest.raises(ValidationError):
            QuestionContent.model_validate({"spans": [TEXT], "supports": [forbidden]})
    with pytest.raises(ValidationError):
        QuestionContent.model_validate({"spans": [{"kind": "chart", "chart_artifact_id": V1_ID}], "supports": []})


@pytest.mark.parametrize(
    "payload,model",
    [
        (READY, ClarificationQuestionReady),
        ({"status": "blocked", "explanation": "No source", "required_input": "Select one"}, ClarificationBlocked),
        ({"status": "failed", "error_ref": V1_ID}, ClarificationFailed),
    ],
)
def test_clarification_outcomes_round_trip_every_discriminator(payload, model):
    adapter = TypeAdapter(ClarificationOutcome)
    result = adapter.validate_python(payload)
    assert isinstance(result, model)
    assert adapter.validate_json(json.dumps(payload)) == result


def test_ready_suggestions_default_empty_or_require_two_to_four_unique_options():
    result = ClarificationQuestionReady.model_validate({"status": "question_ready", "question": QUESTION})
    assert result.suggestions == []
    with pytest.raises(ValidationError, match="2 to 4"):
        ClarificationQuestionReady.model_validate({**READY, "suggestions": [SUGGESTION]})
    four = [
        {**SUGGESTION, "option_id": f"option-{i}"}
        for i in range(4)
    ]
    assert ClarificationQuestionReady.model_validate({**READY, "suggestions": four})
    with pytest.raises(ValidationError):
        ClarificationQuestionReady.model_validate({
            **READY,
            "suggestions": [*four, {**SUGGESTION, "option_id": "option-5"}],
        })
    with pytest.raises(ValidationError, match="unique"):
        ClarificationQuestionReady.model_validate({**READY, "suggestions": [SUGGESTION, SUGGESTION]})


def test_ready_aggregate_span_boundary():
    suggestions = READY["suggestions"]
    assert ClarificationQuestionReady.model_validate({
        **READY, "question": {"spans": [TEXT] * 30, "supports": []}, "suggestions": suggestions,
    })
    with pytest.raises(ValidationError, match="32 spans"):
        ClarificationQuestionReady.model_validate({
            **READY, "question": {"spans": [TEXT] * 31, "supports": []}, "suggestions": suggestions,
        })


def test_ready_aggregate_support_reference_occurrence_boundary():
    supports = [CONTEXT] * 30
    suggestions = [
        {**SUGGESTION, "option_id": f"o{i}", "content": {"spans": [TEXT], "supports": [CONTEXT]}}
        for i in range(2)
    ]
    assert ClarificationQuestionReady.model_validate({
        **READY, "question": {"spans": [TEXT], "supports": supports}, "suggestions": suggestions,
    })
    with pytest.raises(ValidationError, match="32 support-reference"):
        ClarificationQuestionReady.model_validate({
            **READY, "question": {"spans": [VALUE], "supports": supports}, "suggestions": suggestions,
        })
