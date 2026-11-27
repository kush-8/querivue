"""Unit tests for SQL bindings and typed parameter round-tripping."""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

import duckdb
import pytest

from querivue_agent.contracts.tools import ExecuteQueryRequest
from querivue_agent.contracts.values import (
    CanonicalUUID,
    TypedScalar,
    Int64Scalar,
    Uint64Scalar,
    Float64Scalar,
    DecimalScalar,
    StringScalar,
    BooleanScalar,
    DateScalar,
    TimeScalar,
    TimestampScalar,
    TimestamptzScalar,
    NullScalar,
)
from querivue_agent.runtime.sql_runner import SQLRunner, SQLRunnerConfig
from querivue_agent.runtime.sql_tools import (
    SQLToolContext,
    SQLToolExecutor,
    create_sql_tool_executor,
)


class TestSQLBindings:
    """Tests for SQL typed parameter bindings."""

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
        table_name = f"t_{str(self.table_id).replace('-', '_')}"
        conn.execute(f"CREATE TABLE main.{table_name} (id INTEGER, revenue BIGINT, price DECIMAL(10,2), name VARCHAR, active BOOLEAN, sale_date DATE, created_at TIMESTAMP)")
        conn.execute(f"INSERT INTO main.{table_name} VALUES "
                     f"(1, 100, 19.99, 'Product A', true, '2024-01-15', '2024-01-15 10:00:00'), "
                     f"(2, 200, 29.99, 'Product B', false, '2024-02-20', '2024-02-20 14:30:00'), "
                     f"(3, 300, 39.99, 'Product C', true, '2024-03-10', '2024-03-10 09:15:00')")
        conn.close()

        # Create evidence parquet file
        self.evidence_path = Path(self.temp_dir.name) / "evidence.parquet"
        conn = duckdb.connect(str(self.db_path))
        conn.execute(f"COPY (SELECT * FROM main.{table_name}) TO '{self.evidence_path}' (FORMAT PARQUET)")
        conn.close()

    def teardown_method(self):
        self.temp_dir.cleanup()

    def create_runner_config(self):
        return SQLRunnerConfig(
            action_id=self.action_id,
            run_id=self.run_id,
            attempt=1,
            runner_nonce=self.runner_nonce,
            sandbox_id=CanonicalUUID(str(uuid4())),
            pid=0,
            authorized_tables={self.table_id: self.db_path},
            authorized_evidence={self.evidence_id: self.evidence_path},
            analysis_timezone="UTC",
            policy_version="1.0",
            mailbox_dir=Path(self.temp_dir.name) / "mailbox",
            artifact_dir=Path(self.temp_dir.name) / "artifacts",
            resource_limits={"duckdb_memory_gib": 1.0},
        )

    def create_tool_context(self):
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
            deadline=None,
        )

    @pytest.mark.asyncio
    async def test_int64_binding(self):
        """Test int64 parameter binding."""
        context = self.create_tool_context()
        executor = await create_sql_tool_executor(context)

        request = ExecuteQueryRequest(
            sql="SELECT * FROM main.t_00000000_0000_0000_0000_000000000001 WHERE revenue > :threshold",
            parameters={"threshold": Int64Scalar(kind="int64", value="150")},
        )
        result = await executor.execute_query(request)

        assert result.row_count == 2
        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_uint64_binding(self):
        """Test uint64 parameter binding."""
        context = self.create_tool_context()
        executor = await create_sql_tool_executor(context)

        request = ExecuteQueryRequest(
            sql="SELECT * FROM main.t_00000000_0000_0000_0000_000000000001 WHERE revenue < :max_revenue",
            parameters={"max_revenue": Uint64Scalar(kind="uint64", value="300")},
        )
        result = await executor.execute_query(request)

        assert result.row_count == 2
        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_float64_binding(self):
        """Test float64 parameter binding."""
        context = self.create_tool_context()
        executor = await create_sql_tool_executor(context)

        request = ExecuteQueryRequest(
            sql="SELECT * FROM main.t_00000000_0000_0000_0000_000000000001 WHERE price > :min_price",
            parameters={"min_price": Float64Scalar(kind="float64", value=25.0)},
        )
        result = await executor.execute_query(request)

        assert result.row_count == 2
        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_decimal_binding(self):
        """Test decimal parameter binding."""
        context = self.create_tool_context()
        executor = await create_sql_tool_executor(context)

        request = ExecuteQueryRequest(
            sql="SELECT * FROM main.t_00000000_0000_0000_0000_000000000001 WHERE price < :max_price",
            parameters={"max_price": DecimalScalar(kind="decimal", value="35.00", precision=5, scale=2)},
        )
        result = await executor.execute_query(request)

        assert result.row_count == 2
        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_string_binding(self):
        """Test string parameter binding."""
        context = self.create_tool_context()
        executor = await create_sql_tool_executor(context)

        request = ExecuteQueryRequest(
            sql="SELECT * FROM main.t_00000000_0000_0000_0000_000000000001 WHERE name = :product_name",
            parameters={"product_name": StringScalar(kind="string", value="Product B")},
        )
        result = await executor.execute_query(request)

        assert result.row_count == 1
        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_boolean_binding(self):
        """Test boolean parameter binding."""
        context = self.create_tool_context()
        executor = await create_sql_tool_executor(context)

        request = ExecuteQueryRequest(
            sql="SELECT * FROM main.t_00000000_0000_0000_0000_000000000001 WHERE active = :is_active",
            parameters={"is_active": BooleanScalar(kind="boolean", value=True)},
        )
        result = await executor.execute_query(request)

        assert result.row_count == 2
        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_date_binding(self):
        """Test date parameter binding."""
        context = self.create_tool_context()
        executor = await create_sql_tool_executor(context)

        request = ExecuteQueryRequest(
            sql="SELECT * FROM main.t_00000000_0000_0000_0000_000000000001 WHERE sale_date > :min_date",
            parameters={"min_date": DateScalar(kind="date", value="2024-02-01")},
        )
        result = await executor.execute_query(request)

        assert result.row_count == 2
        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_timestamp_binding(self):
        """Test timestamp parameter binding."""
        context = self.create_tool_context()
        executor = await create_sql_tool_executor(context)

        request = ExecuteQueryRequest(
            sql="SELECT * FROM main.t_00000000_0000_0000_0000_000000000001 WHERE created_at > :min_ts",
            parameters={"min_ts": TimestampScalar(kind="timestamp", value="2024-02-01T12:00:00")},
        )
        result = await executor.execute_query(request)

        assert result.row_count == 2
        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_timestamptz_binding(self):
        """Test timestamptz parameter binding."""
        context = self.create_tool_context()
        executor = await create_sql_tool_executor(context)

        request = ExecuteQueryRequest(
            sql="SELECT * FROM main.t_00000000_0000_0000_0000_000000000001 WHERE created_at > :min_ts",
            parameters={"min_ts": TimestamptzScalar(kind="timestamptz", value="2024-02-01T12:00:00+00:00")},
        )
        result = await executor.execute_query(request)

        assert result.row_count == 2
        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_null_binding(self):
        """Test null parameter binding."""
        context = self.create_tool_context()
        executor = await create_sql_tool_executor(context)

        request = ExecuteQueryRequest(
            sql="SELECT * FROM main.t_00000000_0000_0000_0000_000000000001 WHERE name IS NULL",
            parameters={},
        )
        result = await executor.execute_query(request)

        assert result.row_count == 0  # No rows have NULL name
        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_multiple_parameters(self):
        """Test multiple parameters of different types."""
        context = self.create_tool_context()
        executor = await create_sql_tool_executor(context)

        request = ExecuteQueryRequest(
            sql="SELECT * FROM main.t_00000000_0000_0000_0000_000000000001 WHERE revenue > :min_rev AND active = :is_active AND name LIKE :pattern",
            parameters={
                "min_rev": Int64Scalar(kind="int64", value="100"),
                "is_active": BooleanScalar(kind="boolean", value=True),
                "pattern": StringScalar(kind="string", value="Product%"),
            },
        )
        result = await executor.execute_query(request)

        # Should match: Product C (revenue=300, active=true) only = 1 row
        assert result.row_count == 1
        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_runner_int64_binding(self):
        """Test int64 parameter binding through SQLRunner."""
        config = self.create_runner_config()
        runner = SQLRunner(config)
        await runner.start()

        request = ExecuteQueryRequest(
            sql="SELECT * FROM main.t_00000000_0000_0000_0000_000000000001 WHERE revenue > :threshold",
            parameters={"threshold": Int64Scalar(kind="int64", value="150")},
        )

        import json
        import hashlib
        canonical = json.dumps(request.model_dump(), separators=(",", ":"), sort_keys=True)
        request_digest = hashlib.sha256(canonical.encode()).hexdigest()

        from querivue_agent.runtime.sql_runner import MailboxRequest
        mailbox_request = MailboxRequest(
            mailbox_id=uuid4(),
            operation_id=uuid4(),
            action_id=config.action_id,
            attempt=config.attempt,
            runner_nonce=config.runner_nonce,
            request_type="execute_query",
            payload=request.model_dump(),
            request_digest=request_digest,
            deadline="2099-12-31T23:59:59Z",
        )

        response = await runner.handle_request_from_data(mailbox_request)

        assert response.status == "succeeded"
        assert response.result["row_count"] == 2
        await runner.shutdown()

    @pytest.mark.asyncio
    async def test_runner_multiple_params(self):
        """Test multiple parameters through SQLRunner."""
        config = self.create_runner_config()
        runner = SQLRunner(config)
        await runner.start()

        request = ExecuteQueryRequest(
            sql="SELECT revenue, name FROM main.t_00000000_0000_0000_0000_000000000001 WHERE revenue > :min_rev AND name LIKE :pattern",
            parameters={
                "min_rev": Int64Scalar(kind="int64", value="100"),
                "pattern": StringScalar(kind="string", value="%B%"),
            },
        )

        import json
        import hashlib
        canonical = json.dumps(request.model_dump(), separators=(",", ":"), sort_keys=True)
        request_digest = hashlib.sha256(canonical.encode()).hexdigest()

        from querivue_agent.runtime.sql_runner import MailboxRequest
        mailbox_request = MailboxRequest(
            mailbox_id=uuid4(),
            operation_id=uuid4(),
            action_id=config.action_id,
            attempt=config.attempt,
            runner_nonce=config.runner_nonce,
            request_type="execute_query",
            payload=request.model_dump(),
            request_digest=request_digest,
            deadline="2099-12-31T23:59:59Z",
        )

        response = await runner.handle_request_from_data(mailbox_request)

        assert response.status == "succeeded"
        assert response.result["row_count"] == 1
        assert response.result["columns"][1]["name"] == "name"
        await runner.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])