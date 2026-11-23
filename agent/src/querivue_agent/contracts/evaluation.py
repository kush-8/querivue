"""Strict frozen-fixture and failure-inclusive evaluation records."""

from decimal import Decimal, localcontext
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .actions import AnalysisConstraints
from .artifacts import ArtifactRef, SourceDependency
from .catalog import ImportSettings, SourceFormat
from .common import (
    Hash64, MoneyText, NonblankString, PositiveCount, Role, SafeCount, StrictRecord,
    TimestampText,
)
from .content import BlockID
from .evidence import OutputColumn
from .responses import CannotCompleteAssessment, ReviewOutcome
from .values import CanonicalUUID, RuntimeUUID, TypedScalar, UnicodeString


CaseID = Annotated[str, Field(strict=True, pattern=r"^[DH](0[1-9]|1[0-9]|2[0-4])$")]
Split = Literal["development", "held_out"]
Family = Literal[
    "selection_grouping", "cross_dataset_join", "exact_numeric", "temporal_boundary",
    "empty_null", "python_handoff", "chart_backing", "conceptual_direct", "direct_reuse",
    "clarification", "review_correction", "recovery_invalidation",
]
GateID = Annotated[str, Field(strict=True, pattern=r"^G(0[1-9]|10)$")]
Route = Literal["analysis", "direct", "clarify", "withhold"]


def _unique(values: list[str], subject: str) -> list[str]:
    if len(values) != len(set(values)):
        raise ValueError(f"{subject} must be unique")
    return values


def _money_sum(values: list[str]) -> Decimal:
    with localcontext() as context:
        context.prec = 512
        return sum((Decimal(value) for value in values), Decimal(0))


class FixtureSource(StrictRecord):
    dataset_id: RuntimeUUID
    source_format: SourceFormat
    filename: NonblankString
    source_bytes: ArtifactRef
    upload_hash: Hash64
    settings: ImportSettings
    expected_table_count: PositiveCount

    @model_validator(mode="after")
    def validate_source(self) -> "FixtureSource":
        if self.source_bytes.sha256 != self.upload_hash:
            raise ValueError("source artifact SHA-256 must equal upload_hash")
        if self.settings.source_format != self.source_format:
            raise ValueError("import settings format must equal source_format")
        return self


class FixtureObligation(StrictRecord):
    key: BlockID
    description: NonblankString
    deliverable: Literal["numerical", "chart", "clarification", "direct", "explanation"]
    constraints: AnalysisConstraints


class GoldValue(StrictRecord):
    key: NonblankString
    value: TypedScalar
    unit: NonblankString | None


class GoldTable(StrictRecord):
    columns: list[OutputColumn] = Field(min_length=1)
    rows: list[list[TypedScalar]]

    @model_validator(mode="after")
    def validate_table(self) -> "GoldTable":
        if len({column.name for column in self.columns}) != len(self.columns):
            raise ValueError("column names must be unique")
        for row in self.rows:
            if len(row) != len(self.columns):
                raise ValueError("row width must equal column count")
            for column, scalar in zip(self.columns, row, strict=True):
                if scalar.kind == "null":
                    if not column.nullable:
                        raise ValueError("null value requires a nullable column")
                    continue
                if scalar.kind != column.type.tag:
                    raise ValueError("scalar kind must match its column type")
                if scalar.kind == "decimal" and (
                    scalar.precision != column.type.precision or scalar.scale != column.type.scale
                ):
                    raise ValueError("decimal scalar precision and scale must match its column")
        return self


class PrecisionPolicy(StrictRecord):
    mode: Literal["exact", "decimal_places", "tolerance"]
    decimal_places: SafeCount | None
    absolute_tolerance: TypedScalar | None
    relative_tolerance: TypedScalar | None
    rounding_mode: Literal["half_even"]

    @staticmethod
    def _validate_tolerance(scalar: TypedScalar | None) -> None:
        if scalar is None:
            return
        if scalar.kind not in {"int64", "uint64", "decimal", "float64"}:
            raise ValueError("tolerances must be numeric scalars")
        if Decimal(str(scalar.value)) < 0:
            raise ValueError("tolerances must be nonnegative")

    @model_validator(mode="after")
    def validate_policy(self) -> "PrecisionPolicy":
        self._validate_tolerance(self.absolute_tolerance)
        self._validate_tolerance(self.relative_tolerance)
        if self.mode == "exact":
            if any(value is not None for value in (
                self.decimal_places, self.absolute_tolerance, self.relative_tolerance,
            )):
                raise ValueError("exact precision accepts no parameters")
        elif self.mode == "decimal_places":
            if self.decimal_places is None or any(value is not None for value in (
                self.absolute_tolerance, self.relative_tolerance,
            )):
                raise ValueError("decimal_places requires only decimal_places")
        elif self.decimal_places is not None or (
            self.absolute_tolerance is None and self.relative_tolerance is None
        ):
            raise ValueError("tolerance requires at least one tolerance and no decimal_places")
        return self


class OracleSpecification(StrictRecord):
    method: Literal["integer_decimal", "fraction", "enumeration", "temporal_membership", "rubric"]
    implementation_ref: ArtifactRef | None
    gold_values: list[GoldValue]
    gold_table: GoldTable | None
    precision: PrecisionPolicy
    coverage: NonblankString
    rubric: list[NonblankString]

    @model_validator(mode="after")
    def validate_oracle(self) -> "OracleSpecification":
        _unique([item.key for item in self.gold_values], "gold value keys")
        if self.method == "rubric":
            if not self.rubric:
                raise ValueError("rubric method requires rubric criteria")
        elif self.implementation_ref is None:
            raise ValueError("deterministic oracle methods require an implementation artifact")
        return self


class FaultInjection(StrictRecord):
    point: NonblankString
    kind: Literal[
        "provider_timeout", "unknown_completion", "renderer_failure", "lost_acknowledgement",
        "source_deletion", "draft_defect", "evidence_defect",
    ]
    payload_ref: ArtifactRef | None


class FixtureCase(StrictRecord):
    manifest_version: Literal["querivue-eval-v1"]
    case_id: CaseID
    split: Split
    family: Family
    template_family: NonblankString
    generator_hash: Hash64
    original_question: NonblankString
    obligations: list[FixtureObligation] = Field(min_length=1)
    sources: list[FixtureSource]
    expected_entry: Literal["accept", "reject", "clarify", "unavailable"]
    expected_route: Route
    expected_outcome: Literal[
        "complete", "partial", "invalidated", "waiting", "blocked", "operational_unavailable",
        "verification_stop", "rejected", "expired",
    ]
    complete_answer_eligible: bool
    required_events: list[NonblankString]
    forbidden_events: list[NonblankString]
    oracle: OracleSpecification
    scripted_replies: list[UnicodeString]
    fault: FaultInjection | None
    applicable_gates: list[GateID] = Field(min_length=1)
    dependencies: list[SourceDependency]
    fixture_hash: Hash64
    oracle_hash: Hash64
    rubric_hash: Hash64

    @model_validator(mode="after")
    def validate_case(self) -> "FixtureCase":
        if (self.split == "development") != self.case_id.startswith("D"):
            raise ValueError("case ID prefix must agree with split")
        _unique([item.key for item in self.obligations], "obligation keys")
        _unique([item.dataset_id for item in self.sources], "source dataset IDs")
        _unique(self.required_events, "required events")
        _unique(self.forbidden_events, "forbidden events")
        if set(self.required_events) & set(self.forbidden_events):
            raise ValueError("required and forbidden events must be disjoint")
        _unique(self.applicable_gates, "applicable gates")
        dependency_keys = [f"{item.dataset_id}:{item.snapshot_id}" for item in self.dependencies]
        _unique(dependency_keys, "dependencies")
        if self.expected_outcome != "complete" and self.complete_answer_eligible:
            raise ValueError("non-complete outcomes cannot be complete-answer eligible")
        return self


class OracleResult(StrictRecord):
    case_id: CaseID
    verdict: Literal["passed", "failed", "not_run", "blocked"]
    checked_obligations: list[BlockID]
    missing_obligations: list[BlockID]
    findings: list[NonblankString]
    actual_values: list[GoldValue]
    expected_values: list[GoldValue]
    checked_events: list[NonblankString]
    complete: bool
    oracle_hash: Hash64
    diagnostic_ref: ArtifactRef | None

    @model_validator(mode="after")
    def validate_result(self) -> "OracleResult":
        _unique(self.checked_obligations, "checked obligations")
        _unique(self.missing_obligations, "missing obligations")
        if set(self.checked_obligations) & set(self.missing_obligations):
            raise ValueError("checked and missing obligations must be disjoint")
        _unique([item.key for item in self.actual_values], "actual value keys")
        _unique([item.key for item in self.expected_values], "expected value keys")
        _unique(self.checked_events, "checked events")
        if self.verdict == "passed" and (
            not self.complete or self.missing_obligations or self.findings
        ):
            raise ValueError("passed requires a complete result without missing items or findings")
        if self.verdict in {"not_run", "blocked"} and self.complete:
            raise ValueError("not_run and blocked results cannot be complete")
        return self


class CostBreakdown(StrictRecord):
    model: MoneyText | None
    judge: MoneyText | None
    sandbox: MoneyText | None
    storage: MoneyText | None
    validator: MoneyText | None
    total: MoneyText | None

    @model_validator(mode="after")
    def validate_total(self) -> "CostBreakdown":
        components = [self.model, self.judge, self.sandbox, self.storage, self.validator]
        if any(value is None for value in components):
            if self.total is not None:
                raise ValueError("total must be unknown when any cost component is unknown")
        elif self.total is None or Decimal(self.total) != _money_sum(
            [value for value in components if value is not None]
        ):
            raise ValueError("total must equal the exact component sum")
        return self


class RoleForecast(StrictRecord):
    role: Role
    logical_calls: SafeCount
    physical_calls: SafeCount
    input_tokens: SafeCount
    output_tokens: SafeCount
    maximum_usd: MoneyText

    @model_validator(mode="after")
    def validate_calls(self) -> "RoleForecast":
        if self.physical_calls < self.logical_calls:
            raise ValueError("physical_calls must be at least logical_calls")
        return self


class SpendCaps(StrictRecord):
    operator: MoneyText
    project: MoneyText
    intake: MoneyText
    action: MoneyText
    run: MoneyText
    suite: MoneyText


class CostForecast(StrictRecord):
    roles: list[RoleForecast]
    non_model: CostBreakdown
    maximum_usd: MoneyText
    caps: SpendCaps
    cache_assumption: Literal["none", "explicit_verified"]
    cache_evidence_ref: CanonicalUUID | None
    repetitions: PositiveCount
    reason: NonblankString

    @model_validator(mode="after")
    def validate_forecast(self) -> "CostForecast":
        if (self.cache_assumption == "explicit_verified") != (self.cache_evidence_ref is not None):
            raise ValueError("verified cache assumptions require evidence; none forbids it")
        if self.non_model.total is None:
            raise ValueError("unknown non-model costs prevent a finite complete maximum")
        expected = _money_sum(
            [item.maximum_usd for item in self.roles] + [self.non_model.total]
        )
        if Decimal(self.maximum_usd) != expected:
            raise ValueError("maximum_usd must equal role maxima plus non-model total")
        return self


class GateResult(StrictRecord):
    gate_id: GateID
    status: Literal["passed", "failed", "not_run", "blocked"]
    evidence_kind: Literal["scripted", "live", "not_applicable"]
    evidence_ref: ArtifactRef | None
    explanation: NonblankString

    @model_validator(mode="after")
    def validate_evidence(self) -> "GateResult":
        if self.status == "passed" and self.evidence_ref is None:
            raise ValueError("passed gates require evidence")
        return self


class MetricCount(StrictRecord):
    name: NonblankString
    numerator: SafeCount
    denominator: SafeCount
    family: Family | None
    route: Route | None

    @model_validator(mode="after")
    def validate_count(self) -> "MetricCount":
        if self.numerator > self.denominator:
            raise ValueError("numerator cannot exceed denominator")
        return self

    @property
    def rate(self) -> Decimal | None:
        if self.denominator == 0:
            return None
        with localcontext() as context:
            context.prec = 28
            return Decimal(self.numerator) / Decimal(self.denominator)


TerminalClass = Literal[
    "correct_complete", "correct_partial", "appropriate_withholding", "operational_stop",
    "incorrect_publication", "incorrect_withholding",
]


class CaseEvaluation(StrictRecord):
    case_id: CaseID
    repetition: PositiveCount
    status: Literal["completed", "not_run", "preflight_failed"]
    run_id: CanonicalUUID | None
    terminal_class: TerminalClass | None
    oracle: OracleResult
    route: Route
    review: ReviewOutcome | CannotCompleteAssessment | None
    input_tokens: SafeCount | None
    output_tokens: SafeCount | None
    active_milliseconds: SafeCount | None
    wall_milliseconds: SafeCount | None
    costs: CostBreakdown
    events: list[NonblankString]

    @model_validator(mode="after")
    def validate_evaluation(self) -> "CaseEvaluation":
        if self.oracle.case_id != self.case_id:
            raise ValueError("oracle case ID must equal evaluation case ID")
        _unique(self.events, "events")
        if self.active_milliseconds is not None and self.wall_milliseconds is not None:
            if self.active_milliseconds > self.wall_milliseconds:
                raise ValueError("active time cannot exceed wall time")
        if self.status == "completed":
            if self.terminal_class is None:
                raise ValueError("completed evaluations require a terminal class")
        elif self.status == "not_run":
            if self.terminal_class is not None or self.run_id is not None:
                raise ValueError("not_run evaluations cannot claim a run or terminal class")
            if self.oracle.verdict != "not_run":
                raise ValueError("not_run evaluations require a not_run oracle result")
            usage = [
                self.input_tokens, self.output_tokens, self.active_milliseconds,
                self.wall_milliseconds, self.costs.model, self.costs.judge, self.costs.sandbox,
                self.costs.storage, self.costs.validator, self.costs.total,
            ]
            if any(value is not None for value in usage):
                raise ValueError("not_run evaluations cannot invent usage or cost")
        elif self.terminal_class != "operational_stop":
            raise ValueError("preflight failures must be operational stops")
        return self


class EvaluationReport(StrictRecord):
    report_id: RuntimeUUID
    manifest_hash: Hash64
    configuration_hash: Hash64
    commit: NonblankString
    dirty_patch_hash: Hash64 | None
    split: Split
    mode: Literal["scripted", "live"]
    scheduled_count: SafeCount
    completed_count: SafeCount
    case_results: list[CaseEvaluation]
    safety_gates: list[GateResult]
    metrics: list[MetricCount]
    costs: CostBreakdown
    forecast: CostForecast
    actual_build_manifest_ids: list[CanonicalUUID]
    generated_at: TimestampText

    @model_validator(mode="after")
    def validate_report(self) -> "EvaluationReport":
        keys = [f"{item.case_id}:{item.repetition}" for item in self.case_results]
        _unique(keys, "case/repetition pairs")
        _unique([item.gate_id for item in self.safety_gates], "gate IDs")
        _unique(self.actual_build_manifest_ids, "build manifest IDs")
        prefix = "D" if self.split == "development" else "H"
        if any(not item.case_id.startswith(prefix) for item in self.case_results):
            raise ValueError("case ID prefixes must agree with report split")
        if self.scheduled_count != len(self.case_results):
            raise ValueError("scheduled_count must include every case result")
        if self.completed_count != sum(item.status == "completed" for item in self.case_results):
            raise ValueError("completed_count must count completed statuses")
        for name in ("model", "judge", "sandbox", "storage", "validator"):
            case_values = [getattr(item.costs, name) for item in self.case_results]
            expected = None if any(value is None for value in case_values) else _money_sum(
                [value for value in case_values if value is not None]
            )
            reported = getattr(self.costs, name)
            if (reported is None) != (expected is None) or (
                reported is not None and expected is not None and Decimal(reported) != expected
            ):
                raise ValueError(f"report {name} cost must exactly aggregate all case results")
        return self
