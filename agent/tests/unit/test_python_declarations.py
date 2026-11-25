"""Unit tests for Python declarations and output validation."""

from __future__ import annotations

import pytest
from uuid import UUID, uuid4

from querivue_agent.contracts.tools import ExecutePythonRequest
from querivue_agent.contracts.evidence import EvidenceDeclaration, ChartDeclaration, OutputColumn, ChartSeries, ColumnOrdering, OutputDeclaration
from querivue_agent.contracts.values import CanonicalUUID


class TestExecutePythonRequest:
    """Tests for ExecutePythonRequest validation."""

    def test_valid_python_request(self):
        """Test valid Python execution request."""
        request = ExecutePythonRequest(
            code="import pandas as pd\nresult = pd.DataFrame({'x': [1, 2, 3]})",
            input_evidence_ids=[CanonicalUUID(str(uuid4()))],
            outputs=[
                EvidenceDeclaration(
                    name="result",
                    kind="evidence",
                    description="Result table",
                    shape="table",
                    columns=[
                        OutputColumn(name="x", type={"tag": "int64"}, nullable=False),
                    ],
                ),
            ],
        )
        assert request.code is not None
        assert len(request.input_evidence_ids) == 1
        assert len(request.outputs) == 1

    def test_valid_python_request_with_chart(self):
        """Test Python request with chart output."""
        evidence_id = CanonicalUUID(str(uuid4()))
        request = ExecutePythonRequest(
            code="import matplotlib.pyplot as plt\nplt.plot([1, 2, 3])\nplt.savefig('chart.png')",
            input_evidence_ids=[evidence_id],
            outputs=[
                ChartDeclaration(
                    name="chart",
                    kind="chart",
                    title="Test Chart",
                    description="A test chart",
                    series=[
                        ChartSeries(
                            label="series1",
                            evidence_id=evidence_id,
                            ordering=[ColumnOrdering(column="x", direction="asc")],
                            scales={"x": "linear", "y": "linear"},
                            columns={"x": "x", "y": "y"},
                        ),
                    ],
                    units={"x": "units", "y": "units"},
                    analysis_timezone="UTC",
                    limitations=[],
                ),
            ],
        )
        assert len(request.outputs) == 1
        assert request.outputs[0].kind == "chart"

    def test_invalid_duplicate_input_evidence(self):
        """Test that duplicate input evidence IDs are rejected."""
        evidence_id = CanonicalUUID(str(uuid4()))
        with pytest.raises(Exception) as exc:
            ExecutePythonRequest(
                code="print('hello')",
                input_evidence_ids=[evidence_id, evidence_id],
                outputs=[
                    EvidenceDeclaration(
                        name="result",
                        kind="evidence",
                        description="Result",
                        shape="table",
                        columns=[OutputColumn(name="x", type={"tag": "int64"}, nullable=False)],
                    ),
                ],
            )
        assert "unique" in str(exc.value).lower()

    def test_invalid_duplicate_output_names(self):
        """Test that duplicate output names are rejected."""
        evidence_id = CanonicalUUID(str(uuid4()))
        with pytest.raises(Exception) as exc:
            ExecutePythonRequest(
                code="print('hello')",
                input_evidence_ids=[evidence_id],
                outputs=[
                    EvidenceDeclaration(
                        name="result",
                        kind="evidence",
                        description="Result",
                        shape="table",
                        columns=[OutputColumn(name="x", type={"tag": "int64"}, nullable=False)],
                    ),
                    EvidenceDeclaration(
                        name="result",
                        kind="evidence",
                        description="Result 2",
                        shape="table",
                        columns=[OutputColumn(name="y", type={"tag": "int64"}, nullable=False)],
                    ),
                ],
            )
        assert "unique" in str(exc.value).lower()

    def test_invalid_chart_evidence_not_declared(self):
        """Test that chart output with undeclared evidence is rejected."""
        evidence_id1 = CanonicalUUID(str(uuid4()))
        evidence_id2 = CanonicalUUID(str(uuid4()))
        with pytest.raises(Exception) as exc:
            ExecutePythonRequest(
                code="print('hello')",
                input_evidence_ids=[evidence_id1],
                outputs=[
                    ChartDeclaration(
                        name="chart",
                        kind="chart",
                        title="Test",
                        description="Test chart",
                        series=[
                            ChartSeries(
                                label="series1",
                                evidence_id=evidence_id2,
                                ordering=[ColumnOrdering(column="x", direction="asc")],
                                scales={"x": "linear", "y": "linear"},
                                columns={"x": "x", "y": "y"},
                            ),
                        ],
                        units={"x": "units", "y": "units"},
                        analysis_timezone="UTC",
                        limitations=[],
                    ),
                ],
            )
        assert "declared" in str(exc.value).lower()

    def test_empty_code_rejected(self):
        """Test that empty code is rejected."""
        evidence_id = CanonicalUUID(str(uuid4()))
        with pytest.raises(Exception) as exc:
            ExecutePythonRequest(
                code="",
                input_evidence_ids=[evidence_id],
                outputs=[
                    EvidenceDeclaration(
                        name="result",
                        kind="evidence",
                        description="Result",
                        shape="table",
                        columns=[OutputColumn(name="x", type={"tag": "int64"}, nullable=False)],
                    ),
                ],
            )
        assert "nonblank" in str(exc.value).lower() or "empty" in str(exc.value).lower()

    def test_empty_input_evidence_rejected(self):
        """Test that empty input evidence is rejected."""
        with pytest.raises(Exception) as exc:
            ExecutePythonRequest(
                code="print('hello')",
                input_evidence_ids=[],
                outputs=[
                    EvidenceDeclaration(
                        name="result",
                        kind="evidence",
                        description="Result",
                        shape="table",
                        columns=[OutputColumn(name="x", type={"tag": "int64"}, nullable=False)],
                    ),
                ],
            )
        assert "min_length" in str(exc.value).lower() or "at least" in str(exc.value).lower()

    def test_empty_outputs_rejected(self):
        """Test that empty outputs is rejected."""
        evidence_id = CanonicalUUID(str(uuid4()))
        with pytest.raises(Exception) as exc:
            ExecutePythonRequest(
                code="print('hello')",
                input_evidence_ids=[evidence_id],
                outputs=[],
            )
        assert "min_length" in str(exc.value).lower() or "at least" in str(exc.value).lower()


class TestOutputDeclaration:
    """Tests for OutputDeclaration validation."""

    def test_valid_evidence_declaration(self):
        """Test valid evidence output declaration."""
        decl = EvidenceDeclaration(
            name="result",
            kind="evidence",
            description="Result table",
            shape="table",
            columns=[
                OutputColumn(name="x", type={"tag": "int64"}, nullable=False),
                OutputColumn(name="y", type={"tag": "float64"}, nullable=True),
            ],
        )
        assert decl.kind == "evidence"

    def test_valid_chart_declaration(self):
        """Test valid chart output declaration."""
        evidence_id = CanonicalUUID(str(uuid4()))
        decl = ChartDeclaration(
            name="chart",
            kind="chart",
            title="Test Chart",
            description="A test chart",
            series=[
                ChartSeries(
                    label="series1",
                    evidence_id=evidence_id,
                    ordering=[ColumnOrdering(column="x", direction="asc")],
                    scales={"x": "linear", "y": "linear"},
                    columns={"x": "x", "y": "y"},
                ),
            ],
            units={"x": "units", "y": "units"},
            analysis_timezone="UTC",
            limitations=[],
        )
        assert decl.kind == "chart"
        assert len(decl.series) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])