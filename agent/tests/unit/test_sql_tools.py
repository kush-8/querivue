"""Unit tests for SQL tools."""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

import duckdb
import pytest

from querivue_agent.contracts.tools import ExecuteQueryRequest, InspectTableRequest, PreviewRowsRequest, InspectEvidenceRequest, NonblankString
from querivue_agent.contracts.values import CanonicalUUID, TypedScalar, Int64Scalar
from querivue_agent.contracts.evidence import SQLInspectedEvidence
from querivue_agent.runtime.sql_tools import (
    SQLToolContext,
    SQLToolExecutor,
    create_sql_tool_executor,
)


class TestSQLToolExecutor:
    """Tests for SQL tool executor."""

    def setup_method(self):
        # Create a temporary DuckDB database with test data
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.duckdb"

        self.table_id = CanonicalUUID("00000000-0000-0000-0000-000000000001")
        self.evidence_id = CanonicalUUID("00000000-0000-0000-0000-000000000002")
        self.action_id = CanonicalUUID(str(uuid4()))
        self.run_id = CanonicalUUID(str(uuid4()))
        self.environment_manifest_id = CanonicalUUID(str(uuid4()))
        self.operation_id = CanonicalUUID(str(uuid4()))
        self.runner_nonce = "test_nonce_123"

        conn = duckdb.connect(str(self.db_path))
        # Table name must match the convention used by the runner: t_{table_id}
        table_name = f"t_{str(self.table_id).replace('-', '_')}"
        conn.execute(f"CREATE TABLE main.{table_name} (id INTEGER, revenue BIGINT, name VARCHAR)")
        conn.execute(f"INSERT INTO main.{table_name} VALUES (1, 100, 'Product A'), (2, 200, 'Product B'), (3, 300, 'Product C')")
        conn.close()

        # Create evidence parquet file
        self.evidence_path = Path(self.temp_dir.name) / "evidence.parquet"
        conn = duckdb.connect(str(self.db_path))
        conn.execute(f"COPY (SELECT * FROM main.{table_name}) TO '{self.evidence_path}' (FORMAT PARQUET)")
        conn.close()

    def teardown_method(self):
        self.temp_dir.cleanup()

    def create_context(self):
        return SQLToolContext(
            run_id=self.run_id,
            action_id=self.action_id,
            attempt=1,
            authorized_tables={self.table_id: self.db_path},
            authorized_evidence={self.evidence_id: self.evidence_path},
            analysis_timezone="UTC",
            policy_version="1.0",
            artifact_dir=Path(self.temp_dir.name) / "artifacts",
            environment_manifest_id=self.environment_manifest_id,
            operation_id=self.operation_id,
            runner_nonce=self.runner_nonce,
            deadline=None,  # Not used in tests
        )

    @pytest.mark.asyncio
    async def test_inspect_table(self):
        """Test inspect_table tool."""
        context = self.create_context()
        executor = await create_sql_tool_executor(context)

        request = InspectTableRequest(table_id=self.table_id)
        result = await executor.inspect_table(request)

        assert isinstance(result, SQLInspectedEvidence)
        assert result.evidence_id is not None
        assert result.row_count == 3
        assert len(result.columns) == 3
        assert result.sql_relation == "main.t_" + str(self.table_id).replace("-", "_")

        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_inspect_table_unauthorized(self):
        """Test inspect_table with unauthorized table."""
        context = self.create_context()
        executor = await create_sql_tool_executor(context)

        unauthorized_id = CanonicalUUID(str(uuid4()))
        request = InspectTableRequest(table_id=unauthorized_id)

        with pytest.raises(Exception) as exc:
            await executor.inspect_table(request)
        assert "not authorized" in str(exc.value).lower()

        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_preview_rows(self):
        """Test preview_rows tool."""
        context = self.create_context()
        executor = await create_sql_tool_executor(context)

        request = PreviewRowsRequest(
            table_id=self.table_id,
            columns=["id", "revenue"],
            limit=2,
        )
        result = await executor.preview_rows(request)

        assert result.returned_row_count == 2
        assert len(result.columns) == 2
        assert result.full_row_count == 3
        assert result.truncated is True

        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_preview_rows_all_columns(self):
        """Test preview_rows with all columns."""
        context = self.create_context()
        executor = await create_sql_tool_executor(context)

        request = PreviewRowsRequest(
            table_id=self.table_id,
            columns=None,
            limit=10,
        )
        result = await executor.preview_rows(request)

        assert result.returned_row_count == 3
        assert len(result.columns) == 3

        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_preview_rows_invalid_column(self):
        """Test preview_rows with invalid column."""
        context = self.create_context()
        executor = await create_sql_tool_executor(context)

        request = PreviewRowsRequest(
            table_id=self.table_id,
            columns=["nonexistent"],
            limit=10,
        )

        with pytest.raises(Exception) as exc:
            await executor.preview_rows(request)
        assert "not found" in str(exc.value).lower()

        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_inspect_evidence(self):
        """Test inspect_evidence tool."""
        context = self.create_context()
        executor = await create_sql_tool_executor(context)

        request = InspectEvidenceRequest(evidence_id=self.evidence_id)
        result = await executor.inspect_evidence(request)

        assert result.evidence_id == self.evidence_id
        assert result.row_count == 3
        assert len(result.columns) == 3
        assert result.sql_relation == "evidence_" + str(self.evidence_id).replace("-", "_")

        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_inspect_evidence_unauthorized(self):
        """Test inspect_evidence with unauthorized evidence."""
        context = self.create_context()
        executor = await create_sql_tool_executor(context)

        unauthorized_id = CanonicalUUID(str(uuid4()))
        request = InspectEvidenceRequest(evidence_id=unauthorized_id)

        with pytest.raises(Exception) as exc:
            await executor.inspect_evidence(request)
        assert "not authorized" in str(exc.value).lower()

        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_execute_query(self):
        """Test execute_query tool."""
        context = self.create_context()
        executor = await create_sql_tool_executor(context)

        request = ExecuteQueryRequest(
            sql="SELECT revenue, name FROM main.t_00000000_0000_0000_0000_000000000001 WHERE revenue > 150",
            parameters={},
        )
        result = await executor.execute_query(request)

        assert result.row_count == 2
        assert len(result.columns) == 2
        assert result.artifact.media_type == "application/vnd.apache.parquet"
        assert result.artifact.size_bytes > 0
        assert len(result.preview.rows) == 2

        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_execute_query_with_parameters(self):
        """Test execute_query with typed parameters."""
        context = self.create_context()
        executor = await create_sql_tool_executor(context)

        request = ExecuteQueryRequest(
            sql="SELECT * FROM main.t_00000000_0000_0000_0000_000000000001 WHERE revenue > :threshold",
            parameters={"threshold": Int64Scalar(kind="int64", value="150")},
        )
        result = await executor.execute_query(request)

        assert result.row_count == 2

        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_execute_query_aggregation(self):
        """Test execute_query with aggregation."""
        context = self.create_context()
        executor = await create_sql_tool_executor(context)

        request = ExecuteQueryRequest(
            sql="SELECT SUM(revenue) as total, COUNT(*) as cnt FROM main.t_00000000_0000_0000_0000_000000000001",
            parameters={},
        )
        result = await executor.execute_query(request)

        assert result.row_count == 1
        assert len(result.columns) == 2

        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_execute_query_invalid_sql(self):
        """Test execute_query with invalid SQL."""
        context = self.create_context()
        executor = await create_sql_tool_executor(context)

        request = ExecuteQueryRequest(
            sql="INVALID SQL",
            parameters={},
        )

        with pytest.raises(Exception) as exc:
            await executor.execute_query(request)
        assert "unsupported_statement" in str(exc.value).lower() or "select" in str(exc.value).lower()

        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_execute_query_unauthorized_table(self):
        """Test execute_query with unauthorized table reference."""
        context = self.create_context()
        executor = await create_sql_tool_executor(context)

        request = ExecuteQueryRequest(
            sql="SELECT * FROM main.unauthorized_table",
            parameters={},
        )

        with pytest.raises(Exception) as exc:
            await executor.execute_query(request)
        assert "unauthorized" in str(exc.value).lower() or "unknown" in str(exc.value).lower()

        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_execute_query_non_select(self):
        """Test execute_query with non-SELECT statement."""
        context = self.create_context()
        executor = await create_sql_tool_executor(context)

        request = ExecuteQueryRequest(
            sql="INSERT INTO main.t_00000000_0000_0000_0000_000000000001 VALUES (4, 400, 'Product D')",
            parameters={},
        )

        with pytest.raises(Exception) as exc:
            await executor.execute_query(request)
        assert "unsupported_statement" in str(exc.value).lower() or "select" in str(exc.value).lower()

        await executor.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])