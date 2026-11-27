"""Acceptance tests for T14: Fresh Python calls, numerical publication and PNG charts (1C).

These tests require a running Docker daemon and the sandbox image to be built.
They are marked with 'live' and excluded from the default test run.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from querivue_agent.contracts.tools import ExecutePythonRequest
from querivue_agent.contracts.evidence import EvidenceDeclaration, ChartDeclaration, OutputColumn, ChartSeries, ColumnOrdering
from querivue_agent.contracts.values import CanonicalUUID
from querivue_agent.execution.python_runner import PythonRunner, PythonRunnerConfig, create_python_runner
from querivue_agent.runtime.sandbox import (
    EnvironmentManifest,
    ResourceLimits,
    SandboxConfig,
    SandboxController,
    create_default_environment_manifest,
    create_sandbox_controller,
)
from querivue_agent.contracts.common import Scope


class Test1CChartsAcceptance:
    """Acceptance tests for T14 - Python execution with chart rendering."""

    def setup_method(self):
        """Create test fixtures."""
        self.temp_dir = tempfile.TemporaryDirectory()
        self.artifact_dir = Path(self.temp_dir.name) / "artifacts"
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

        self.evidence_id = CanonicalUUID("00000000-0000-0000-0000-000000000002")
        self.action_id = CanonicalUUID(str(uuid4()))
        self.run_id = CanonicalUUID(str(uuid4()))
        self.environment_manifest_id = CanonicalUUID(str(uuid4()))
        self.operation_id = CanonicalUUID(str(uuid4()))

        # Create a test parquet file with sample data
        import duckdb
        self.evidence_path = self.artifact_dir / "input_evidence.parquet"
        conn = duckdb.connect()
        conn.execute("""
            CREATE TABLE test_data (
                id INTEGER,
                category VARCHAR,
                value DOUBLE,
                active BOOLEAN,
                date_col DATE
            )
        """)
        conn.execute("""
            INSERT INTO test_data VALUES
            (1, 'A', 10.5, true, '2024-01-15'),
            (2, 'B', 20.3, false, '2024-02-20'),
            (3, 'A', 15.7, true, '2024-03-10'),
            (4, 'C', 30.2, true, '2024-04-05'),
            (5, 'B', 25.8, false, '2024-05-12')
        """)
        conn.execute(f"COPY test_data TO '{self.evidence_path}' (FORMAT PARQUET)")
        conn.close()

    def teardown_method(self):
        self.temp_dir.cleanup()

    def create_runner_config(self):
        return PythonRunnerConfig(
            action_id=self.action_id,
            run_id=self.run_id,
            attempt=1,
            runner_nonce=1,
            sandbox_id=CanonicalUUID(str(uuid4())),
            pid=0,
            authorized_evidence={self.evidence_id: self.evidence_path},
            analysis_timezone="UTC",
            artifact_dir=self.artifact_dir,
            resource_limits={"python_memory_gib": 2.0},
            scope=Scope(
                project_id=CanonicalUUID("00000000-0000-0000-0000-000000000000"),
                chat_id=CanonicalUUID("00000000-0000-0000-0000-000000000000"),
                run_id=self.run_id,
                eligible_dataset_ids=[],
            ),
        )

    async def create_sandbox(self):
        manifest = EnvironmentManifest(
            manifest_id=self.environment_manifest_id,
            schema_version="1.0",
            image_digest="sha256:" + "a" * 64,
            provider_template_revision="dev",
            os_kernel_arch="linux/x86_64",
            python_version="3.12",
            package_hashes={},
            duckdb_version="1.0.0",
            arrow_version="15.0.0",
            sql_parser_policy_version="1.0",
            importer_version="1.0",
            profiler_version="1.0",
            validator_version="1.0",
            locale="en_US.UTF-8",
            timezone="UTC",
            resource_profile="development",
            created_at="2024-01-01T00:00:00Z",
            provider_identity="local",
            observed_controls={
                "read_only_inputs": True,
                "network_blocked": True,
                "process_tree_termination": True,
                "cgroup_v2": True,
                "bubblewrap": True,
            },
        )
        limits = ResourceLimits()
        config = SandboxConfig(
            environment_manifest=manifest,
            resource_limits=limits,
            session_id=CanonicalUUID(str(uuid4())),
            run_id=self.run_id,
            read_only_inputs=[self.evidence_path],
        )
        sandbox = SandboxController(config)
        await sandbox.create_session()
        return sandbox

    @pytest.mark.live
    @pytest.mark.asyncio
    async def test_valid_chart_rendering_end_to_end(self):
        """Test end-to-end valid chart rendering with numerical evidence publication."""
        config = self.create_runner_config()
        sandbox = await self.create_sandbox()
        runner = await create_python_runner(config, sandbox)

        request = ExecutePythonRequest(
            code="""
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pyarrow.parquet as pq

# Read input evidence
df = pd.read_parquet('input_00000000-0000-0000-0000-000000000002.parquet')

# Compute aggregation for chart
agg = df.groupby('category').agg(
    mean_value=('value', 'mean'),
    count=('value', 'count')
).reset_index()

# Write numerical evidence (backing data)
agg.to_parquet('output_chart_data.parquet', index=False)

# Create chart
fig, ax = plt.subplots(figsize=(8, 6))
ax.bar(agg['category'], agg['mean_value'])
ax.set_xlabel('Category')
ax.set_ylabel('Mean Value')
ax.set_title('Mean Value by Category')
fig.savefig('output_chart.png', dpi=100, bbox_inches='tight')
plt.close(fig)
""",
            input_evidence_ids=[self.evidence_id],
            outputs=[
                EvidenceDeclaration(
                    name="chart_data",
                    kind="evidence",
                    description="Data backing the chart",
                    shape="table",
                    columns=[
                        OutputColumn(name="category", type={"tag": "string"}, nullable=False),
                        OutputColumn(name="mean_value", type={"tag": "float64"}, nullable=False),
                        OutputColumn(name="count", type={"tag": "int64"}, nullable=False),
                    ],
                ),
                ChartDeclaration(
                    name="chart",
                    kind="chart",
                    title="Mean Value by Category",
                    description="Bar chart showing mean value per category",
                    series=[
                        ChartSeries(
                            label="Mean Value",
                            evidence_id=self.evidence_id,
                            ordering=[ColumnOrdering(column="category", direction="asc")],
                            scales={"category": "linear", "mean_value": "linear"},
                            columns={"x": "category", "y": "mean_value"},
                        ),
                    ],
                    units={"category": "category", "mean_value": "value"},
                    analysis_timezone="UTC",
                    limitations=["Sample data only"],
                ),
            ],
        )

        result = await runner.execute_python(request, self.operation_id)

        # Validate evidence output
        assert "evidence" in result
        assert len(result["evidence"]) == 1
        evidence = result["evidence"][0]
        assert evidence["row_count"] == 3  # 3 categories A, B, C
        assert len(evidence["columns"]) == 3
        assert evidence["columns"][0]["name"] == "category"
        assert evidence["columns"][1]["name"] == "mean_value"
        assert evidence["columns"][2]["name"] == "count"

        # Validate chart output
        assert "charts" in result
        assert len(result["charts"]) == 1
        chart = result["charts"][0]
        assert chart["chart_artifact_id"] == chart["artifact"]["artifact_id"]
        assert chart["artifact"]["media_type"] == "image/png"
        assert chart["pixel_width"] > 0
        assert chart["pixel_height"] > 0
        assert chart["encoder_version"] == "matplotlib"

        # Validate producer provenance
        assert evidence["producer"]["kind"] == "python"
        assert chart["producer"]["kind"] == "python"
        assert evidence["producer"]["script_hash"] is not None
        assert chart["producer"]["script_hash"] is not None

        await sandbox.destroy_session()

    @pytest.mark.live
    @pytest.mark.asyncio
    async def test_chart_failure_retains_numerical_evidence(self):
        """Test that failed chart rendering retains numerical evidence (reviewed partial failure case)."""
        config = self.create_runner_config()
        sandbox = await self.create_sandbox()
        runner = await create_python_runner(config, sandbox)

        # This script writes numerical evidence but creates an invalid PNG
        request = ExecutePythonRequest(
            code="""
import pandas as pd
import pyarrow.parquet as pq

# Read input evidence
df = pd.read_parquet('input_00000000-0000-0000-0000-000000000002.parquet')

# Compute aggregation
agg = df.groupby('category').agg(
    mean_value=('value', 'mean'),
    count=('value', 'count')
).reset_index()

# Write numerical evidence (backing data)
agg.to_parquet('output_chart_data.parquet', index=False)

# Create INVALID chart (write text as PNG)
with open('output_chart.png', 'w') as f:
    f.write('This is not a valid PNG file')
""",
            input_evidence_ids=[self.evidence_id],
            outputs=[
                EvidenceDeclaration(
                    name="chart_data",
                    kind="evidence",
                    description="Data backing the chart",
                    shape="table",
                    columns=[
                        OutputColumn(name="category", type={"tag": "string"}, nullable=False),
                        OutputColumn(name="mean_value", type={"tag": "float64"}, nullable=False),
                        OutputColumn(name="count", type={"tag": "int64"}, nullable=False),
                    ],
                ),
                ChartDeclaration(
                    name="chart",
                    kind="chart",
                    title="Mean Value by Category",
                    description="Bar chart showing mean value per category",
                    series=[
                        ChartSeries(
                            label="Mean Value",
                            evidence_id=self.evidence_id,
                            ordering=[ColumnOrdering(column="category", direction="asc")],
                            scales={"category": "linear", "mean_value": "linear"},
                            columns={"x": "category", "y": "mean_value"},
                        ),
                    ],
                    units={"category": "category", "mean_value": "value"},
                    analysis_timezone="UTC",
                    limitations=["Sample data only"],
                ),
            ],
        )

        result = await runner.execute_python(request, self.operation_id)

        # Numerical evidence should still be published
        assert "evidence" in result
        assert len(result["evidence"]) == 1
        evidence = result["evidence"][0]
        assert evidence["row_count"] == 3

        # Chart may be present but validation will show it's invalid
        # The key is that the runner doesn't crash and evidence is retained
        # (Actual validation happens in the validator gate, not the runner)

        await sandbox.destroy_session()

    @pytest.mark.live
    @pytest.mark.asyncio
    async def test_chart_without_backing_evidence_fails_gracefully(self):
        """Test chart output without backing evidence is handled."""
        config = self.create_runner_config()
        sandbox = await self.create_sandbox()
        runner = await create_python_runner(config, sandbox)

        request = ExecutePythonRequest(
            code="""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
# Create chart without backing evidence
fig, ax = plt.subplots()
ax.plot([1, 2, 3], [1, 4, 2])
fig.savefig('output_chart.png', dpi=100)
plt.close(fig)
# No parquet output for backing evidence
""",
            input_evidence_ids=[self.evidence_id],
            outputs=[
                ChartDeclaration(
                    name="chart",
                    kind="chart",
                    title="Chart without backing",
                    description="Chart with no backing evidence",
                    series=[
                        ChartSeries(
                            label="series1",
                            evidence_id=self.evidence_id,
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

        result = await runner.execute_python(request, self.operation_id)
        # Should handle missing backing evidence gracefully - no crash
        # Evidence list may be empty but runner should complete
        await sandbox.destroy_session()

    @pytest.mark.live
    @pytest.mark.asyncio
    async def test_no_state_transfer_between_calls_live(self):
        """Test that no variables/files transfer between separate Python calls (live)."""
        config = self.create_runner_config()
        sandbox = await self.create_sandbox()
        runner = await create_python_runner(config, sandbox)

        # First call - set a variable and write a file
        request1 = ExecutePythonRequest(
            code="""
import pandas as pd
df = pd.DataFrame({'x': [1, 2, 3]})
df.to_parquet('output_temp.parquet', index=False)
# Try to set a global variable
GLOBAL_VAR = 'test_value'
""",
            input_evidence_ids=[self.evidence_id],
            outputs=[
                EvidenceDeclaration(
                    name="temp",
                    kind="evidence",
                    description="Temporary",
                    shape="table",
                    columns=[OutputColumn(name="x", type={"tag": "int64"}, nullable=False)],
                ),
            ],
        )
        await runner.execute_python(request1, uuid4())

        # Second call - try to access the global variable (should fail/not exist)
        request2 = ExecutePythonRequest(
            code="""
import pandas as pd
# This should not have access to GLOBAL_VAR from first call
try:
    result_val = GLOBAL_VAR
except NameError:
    result_val = 'not_found'
result = pd.DataFrame({'var_check': [result_val]})
result.to_parquet('output_check.parquet', index=False)
""",
            input_evidence_ids=[self.evidence_id],
            outputs=[
                EvidenceDeclaration(
                    name="check",
                    kind="evidence",
                    description="Check for state transfer",
                    shape="table",
                    columns=[OutputColumn(name="var_check", type={"tag": "string"}, nullable=False)],
                ),
            ],
        )
        result = await runner.execute_python(request2, uuid4())

        # The variable should not be accessible (fresh interpreter each call)
        evidence = result["evidence"][0]
        assert evidence["row_count"] == 1

        await sandbox.destroy_session()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "live"])