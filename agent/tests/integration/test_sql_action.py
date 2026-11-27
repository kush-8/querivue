"""Integration tests for SQL action end-to-end flow."""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

import duckdb
import pytest

from querivue_agent.contracts.tools import (
    ExecuteQueryRequest,
    InspectTableRequest,
    PreviewRowsRequest,
    InspectEvidenceRequest,
)
from querivue_agent.contracts.values import (
    CanonicalUUID,
    Int64Scalar,
    StringScalar,
    BooleanScalar,
    DateScalar,
    Float64Scalar,
)
from querivue_agent.runtime.sql_runner import SQLRunner, SQLRunnerConfig
from querivue_agent.runtime.sql_tools import (
    SQLToolContext,
    create_sql_tool_executor,
)
from querivue_agent.runtime.sql_policy import SQLPolicyValidator, SQLValidationError


class TestSQLActionIntegration:
    """Integration tests for SQL action end-to-end flow."""

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
        conn.execute(f"""
            CREATE TABLE main.{table_name} (
                id INTEGER,
                revenue BIGINT,
                price DECIMAL(10,2),
                name VARCHAR,
                active BOOLEAN,
                sale_date DATE,
                created_at TIMESTAMP
            )
        """)
        conn.execute(f"""
            INSERT INTO main.{table_name} VALUES
            (1, 100, 19.99, 'Product A', true, '2024-01-15', '2024-01-15 10:00:00'),
            (2, 200, 29.99, 'Product B', false, '2024-02-20', '2024-02-20 14:30:00'),
            (3, 300, 39.99, 'Product C', true, '2024-03-10', '2024-03-10 09:15:00'),
            (4, 400, 49.99, 'Product D', true, '2024-04-05', '2024-04-05 16:45:00'),
            (5, 500, 59.99, 'Product E', false, '2024-05-12', '2024-05-12 11:20:00')
        """)
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
    async def test_inspect_table_via_runner(self):
        """Test inspect_table through SQLRunner mailbox protocol."""
        config = self.create_runner_config()
        runner = SQLRunner(config)
        await runner.start()

        import json
        import hashlib
        from querivue_agent.runtime.sql_runner import MailboxRequest

        request = InspectTableRequest(table_id=self.table_id)
        canonical = json.dumps(request.model_dump(), separators=(",", ":"), sort_keys=True)
        request_digest = hashlib.sha256(canonical.encode()).hexdigest()

        mailbox_request = MailboxRequest(
            mailbox_id=uuid4(),
            operation_id=uuid4(),
            action_id=self.table_id,
            attempt=config.attempt,
            runner_nonce=config.runner_nonce,
            request_type="inspect_table",
            payload=request.model_dump(),
            request_digest=request_digest,
            deadline="2099-12-31T23:59:59Z",
        )

        response = await runner.handle_request_from_data(mailbox_request)

        assert response.status == "succeeded"
        assert "columns" in response.result
        assert response.result["row_count"] == 5
        await runner.shutdown()

    @pytest.mark.asyncio
    async def test_preview_rows_via_runner(self):
        """Test preview_rows through SQLRunner mailbox protocol."""
        config = self.create_runner_config()
        runner = SQLRunner(config)
        await runner.start()

        import json
        import hashlib
        from querivue_agent.runtime.sql_runner import MailboxRequest

        request = PreviewRowsRequest(table_id=self.table_id, columns=["id", "name", "revenue"], limit=3)
        canonical = json.dumps(request.model_dump(), separators=(",", ":"), sort_keys=True)
        request_digest = hashlib.sha256(canonical.encode()).hexdigest()

        mailbox_request = MailboxRequest(
            mailbox_id=uuid4(),
            operation_id=uuid4(),
            action_id=self.table_id,
            attempt=config.attempt,
            runner_nonce=config.runner_nonce,
            request_type="preview_rows",
            payload=request.model_dump(),
            request_digest=request_digest,
            deadline="2099-12-31T23:59:59Z",
        )

        response = await runner.handle_request_from_data(mailbox_request)

        assert response.status == "succeeded"
        assert response.result["returned_row_count"] == 3
        await runner.shutdown()

    @pytest.mark.asyncio
    async def test_inspect_evidence_via_runner(self):
        """Test inspect_evidence through SQLRunner mailbox protocol."""
        config = self.create_runner_config()
        runner = SQLRunner(config)
        await runner.start()

        import json
        import hashlib
        from querivue_agent.runtime.sql_runner import MailboxRequest

        request = InspectEvidenceRequest(evidence_id=self.evidence_id)
        canonical = json.dumps(request.model_dump(), separators=(",", ":"), sort_keys=True)
        request_digest = hashlib.sha256(canonical.encode()).hexdigest()

        mailbox_request = MailboxRequest(
            mailbox_id=uuid4(),
            operation_id=uuid4(),
            action_id=self.evidence_id,
            attempt=config.attempt,
            runner_nonce=config.runner_nonce,
            request_type="inspect_evidence",
            payload=request.model_dump(),
            request_digest=request_digest,
            deadline="2099-12-31T23:59:59Z",
        )

        response = await runner.handle_request_from_data(mailbox_request)

        assert response.status == "succeeded"
        assert "columns" in response.result
        assert response.result["row_count"] == 5
        await runner.shutdown()

    @pytest.mark.asyncio
    async def test_execute_query_with_aggregation(self):
        """Test execute_query with aggregation functions."""
        context = self.create_tool_context()
        executor = await create_sql_tool_executor(context)

        request = ExecuteQueryRequest(
            sql="""
                SELECT COUNT(*) as cnt, SUM(revenue) as total_rev, AVG(price) as avg_price
                FROM main.t_00000000_0000_0000_0000_000000000001
            """,
            parameters={},
        )
        result = await executor.execute_query(request)

        assert result.row_count == 1
        assert result.columns[0].name == "cnt"
        assert result.columns[1].name == "total_rev"
        assert result.columns[2].name == "avg_price"
        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_execute_query_with_window_function(self):
        """Test execute_query with window functions."""
        context = self.create_tool_context()
        executor = await create_sql_tool_executor(context)

        request = ExecuteQueryRequest(
            sql="""
                SELECT
                    name,
                    revenue,
                    ROW_NUMBER() OVER (ORDER BY revenue DESC) as rn,
                    RANK() OVER (ORDER BY revenue DESC) as rk
                FROM main.t_00000000_0000_0000_0000_000000000001
                ORDER BY revenue DESC
            """,
            parameters={},
        )
        result = await executor.execute_query(request)

        assert result.row_count == 5
        assert "rn" in [c.name for c in result.columns]
        assert "rk" in [c.name for c in result.columns]
        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_execute_query_with_cte(self):
        """Test execute_query with CTE."""
        context = self.create_tool_context()
        executor = await create_sql_tool_executor(context)

        request = ExecuteQueryRequest(
            sql="""
                WITH filtered AS (
                    SELECT * FROM main.t_00000000_0000_0000_0000_000000000001 WHERE active = true
                )
                SELECT COUNT(*) as active_count FROM filtered
            """,
            parameters={},
        )
        result = await executor.execute_query(request)

        assert result.row_count == 1
        assert result.columns[0].name == "active_count"
        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_execute_query_with_parameters(self):
        """Test execute_query with multiple parameter types."""
        context = self.create_tool_context()
        executor = await create_sql_tool_executor(context)

        request = ExecuteQueryRequest(
            sql="""
                SELECT name, revenue, price
                FROM main.t_00000000_0000_0000_0000_000000000001
                WHERE revenue > :min_rev
                AND active = :is_active
                AND price < :max_price
            """,
            parameters={
                "min_rev": Int64Scalar(kind="int64", value="200"),
                "is_active": BooleanScalar(kind="boolean", value=True),
                "max_price": Float64Scalar(kind="float64", value=50.0),
            },
        )
        result = await executor.execute_query(request)

        assert result.row_count == 2  # Product C and D
        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_execute_query_with_date_filter(self):
        """Test execute_query with date parameter."""
        context = self.create_tool_context()
        executor = await create_sql_tool_executor(context)

        request = ExecuteQueryRequest(
            sql="""
                SELECT name, sale_date
                FROM main.t_00000000_0000_0000_0000_000000000001
                WHERE sale_date >= :start_date
            """,
            parameters={
                "start_date": DateScalar(kind="date", value="2024-03-01"),
            },
        )
        result = await executor.execute_query(request)

        assert result.row_count == 3  # Products C, D, E
        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_execute_query_with_string_parameter(self):
        """Test execute_query with string parameter."""
        context = self.create_tool_context()
        executor = await create_sql_tool_executor(context)

        request = ExecuteQueryRequest(
            sql="""
                SELECT name, revenue
                FROM main.t_00000000_0000_0000_0000_000000000001
                WHERE name LIKE :pattern
            """,
            parameters={
                "pattern": StringScalar(kind="string", value="Product C%"),
            },
        )
        result = await executor.execute_query(request)

        assert result.row_count == 1
        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_duplicate_request_deduplication(self):
        """Test that duplicate requests are deduplicated via digest."""
        config = self.create_runner_config()
        runner = SQLRunner(config)
        await runner.start()

        import json
        import hashlib
        from querivue_agent.runtime.sql_runner import MailboxRequest

        request = InspectTableRequest(table_id=self.table_id)
        canonical = json.dumps(request.model_dump(), separators=(",", ":"), sort_keys=True)
        request_digest = hashlib.sha256(canonical.encode()).hexdigest()

        mailbox_request = MailboxRequest(
            mailbox_id=uuid4(),
            operation_id=uuid4(),
            action_id=self.table_id,
            attempt=config.attempt,
            runner_nonce=config.runner_nonce,
            request_type="inspect_table",
            payload=request.model_dump(),
            request_digest=request_digest,
            deadline="2099-12-31T23:59:59Z",
        )

        # First request
        response1 = await runner.handle_request_from_data(mailbox_request)
        assert response1.status == "succeeded"

        # Second request with same digest should return cached response
        mailbox_request2 = MailboxRequest(
            mailbox_id=uuid4(),
            operation_id=uuid4(),
            action_id=self.table_id,
            attempt=config.attempt,
            runner_nonce=config.runner_nonce,
            request_type="inspect_table",
            payload=request.model_dump(),
            request_digest=request_digest,
            deadline="2099-12-31T23:59:59Z",
        )

        response2 = await runner.handle_request_from_data(mailbox_request2)
        assert response2.status == "succeeded"
        # Should be the same response object (cached)
        assert response2 is response1

        await runner.shutdown()

    @pytest.mark.asyncio
    async def test_policy_rejects_unauthorized_table(self):
        """Test that policy rejects unauthorized table references."""
        context = self.create_tool_context()
        executor = await create_sql_tool_executor(context)

        # Create an unauthorized table ID
        unauthorized_table_id = CanonicalUUID("00000000-0000-0000-0000-000000000099")

        request = ExecuteQueryRequest(
            sql=f"SELECT * FROM main.t_{str(unauthorized_table_id).replace('-', '_')}",
            parameters={},
        )

        with pytest.raises(SQLValidationError) as exc_info:
            await executor.execute_query(request)

        assert exc_info.value.code == "unknown_relation"
        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_policy_rejects_multiple_statements(self):
        """Test that policy rejects multiple statements."""
        context = self.create_tool_context()
        executor = await create_sql_tool_executor(context)

        request = ExecuteQueryRequest(
            sql="SELECT 1; SELECT 2;",
            parameters={},
        )

        with pytest.raises(SQLValidationError) as exc_info:
            await executor.execute_query(request)

        assert exc_info.value.code == "multiple_statements"
        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_policy_rejects_non_select(self):
        """Test that policy rejects non-SELECT statements."""
        context = self.create_tool_context()
        executor = await create_sql_tool_executor(context)

        request = ExecuteQueryRequest(
            sql="INSERT INTO main.t_00000000_0000_0000_0000_000000000001 VALUES (6, 600, 69.99, 'Product F', true, '2024-06-01', '2024-06-01 10:00:00')",
            parameters={},
        )

        with pytest.raises(SQLValidationError) as exc_info:
            await executor.execute_query(request)

        assert exc_info.value.code == "unsupported_statement"
        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_policy_rejects_unknown_function(self):
        """Test that policy rejects unknown functions."""
        context = self.create_tool_context()
        executor = await create_sql_tool_executor(context)

        request = ExecuteQueryRequest(
            sql="SELECT UNKNOWN_FUNC(revenue) FROM main.t_00000000_0000_0000_0000_000000000001",
            parameters={},
        )

        with pytest.raises(SQLValidationError) as exc_info:
            await executor.execute_query(request)

        assert exc_info.value.code in ("unknown_function", "policy_violation")
        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_policy_rejects_excessive_cte_depth(self):
        """Test that policy rejects CTE depth exceeding limit."""
        context = self.create_tool_context()
        executor = await create_sql_tool_executor(context)

        # Create deeply nested CTE (depth 4, limit is 3)
        request = ExecuteQueryRequest(
            sql="""
                WITH
                l1 AS (SELECT * FROM main.t_00000000_0000_0000_0000_000000000001),
                l2 AS (SELECT * FROM l1),
                l3 AS (SELECT * FROM l2),
                l4 AS (SELECT * FROM l3)
                SELECT * FROM l4
            """,
            parameters={},
        )

        with pytest.raises(SQLValidationError) as exc_info:
            await executor.execute_query(request)

        assert exc_info.value.code == "cte_depth_exceeded"
        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_policy_allows_valid_cte_depth(self):
        """Test that policy allows CTE depth within limit."""
        context = self.create_tool_context()
        executor = await create_sql_tool_executor(context)

        # CTE depth 3 (within limit)
        request = ExecuteQueryRequest(
            sql="""
                WITH
                l1 AS (SELECT * FROM main.t_00000000_0000_0000_0000_000000000001),
                l2 AS (SELECT * FROM l1),
                l3 AS (SELECT * FROM l2)
                SELECT * FROM l3
            """,
            parameters={},
        )

        result = await executor.execute_query(request)
        assert result.row_count == 5
        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_evidence_artifact_creation(self):
        """Test that execute_query creates evidence artifacts with hash."""
        context = self.create_tool_context()
        executor = await create_sql_tool_executor(context)

        request = ExecuteQueryRequest(
            sql="SELECT name, revenue FROM main.t_00000000_0000_0000_0000_000000000001 WHERE revenue > 200",
            parameters={},
        )
        result = await executor.execute_query(request)

        assert result.evidence_id is not None
        assert result.artifact is not None
        assert result.content_hash is not None
        assert len(result.content_hash) == 64  # SHA-256 hex
        await executor.shutdown()

    @pytest.mark.asyncio
    async def test_end_to_end_sql_flow(self):
        """Test complete SQL action flow: inspect -> preview -> query -> evidence."""
        config = self.create_runner_config()
        runner = SQLRunner(config)
        await runner.start()

        import json
        import hashlib
        from querivue_agent.runtime.sql_runner import MailboxRequest

        # 1. Inspect table
        request1 = InspectTableRequest(table_id=self.table_id)
        canonical1 = json.dumps(request1.model_dump(), separators=(",", ":"), sort_keys=True)
        digest1 = hashlib.sha256(canonical1.encode()).hexdigest()
        mr1 = MailboxRequest(
            mailbox_id=uuid4(), operation_id=uuid4(), action_id=self.table_id,
            attempt=config.attempt, runner_nonce=config.runner_nonce,
            request_type="inspect_table", payload=request1.model_dump(),
            request_digest=digest1, deadline="2099-12-31T23:59:59Z",
        )
        resp1 = await runner.handle_request_from_data(mr1)
        assert resp1.status == "succeeded"
        assert resp1.result["row_count"] == 5

        # 2. Preview rows
        request2 = PreviewRowsRequest(table_id=self.table_id, columns=["id", "name"], limit=2)
        canonical2 = json.dumps(request2.model_dump(), separators=(",", ":"), sort_keys=True)
        digest2 = hashlib.sha256(canonical2.encode()).hexdigest()
        mr2 = MailboxRequest(
            mailbox_id=uuid4(), operation_id=uuid4(), action_id=self.table_id,
            attempt=config.attempt, runner_nonce=config.runner_nonce,
            request_type="preview_rows", payload=request2.model_dump(),
            request_digest=digest2, deadline="2099-12-31T23:59:59Z",
        )
        resp2 = await runner.handle_request_from_data(mr2)
        assert resp2.status == "succeeded"
        assert resp2.result["returned_row_count"] == 2

        # 3. Execute query
        from querivue_agent.contracts.tools import ExecuteQueryRequest
        request3 = ExecuteQueryRequest(
            sql="SELECT COUNT(*) as cnt FROM main.t_00000000_0000_0000_0000_000000000001 WHERE active = true",
            parameters={},
        )
        canonical3 = json.dumps(request3.model_dump(), separators=(",", ":"), sort_keys=True)
        digest3 = hashlib.sha256(canonical3.encode()).hexdigest()
        mr3 = MailboxRequest(
            mailbox_id=uuid4(), operation_id=uuid4(), action_id=config.action_id,
            attempt=config.attempt, runner_nonce=config.runner_nonce,
            request_type="execute_query", payload=request3.model_dump(),
            request_digest=digest3, deadline="2099-12-31T23:59:59Z",
        )
        resp3 = await runner.handle_request_from_data(mr3)
        assert resp3.status == "succeeded"
        assert resp3.result["row_count"] == 1
        assert "evidence_id" in resp3.result
        assert "artifact_hash" in resp3.result

        await runner.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])