"""Unit tests for SQL runner."""

from __future__ import annotations

import tempfile
from pathlib import Path
from uuid import uuid4

import duckdb
import pytest

from querivue_agent.contracts.tools import ExecuteQueryRequest, InspectTableRequest, PreviewRowsRequest, InspectEvidenceRequest
from querivue_agent.contracts.values import CanonicalUUID, Int64Scalar
from querivue_agent.runtime.sql_runner import (
    SQLRunner,
    SQLRunnerConfig,
    MailboxRequest,
    MailboxResponse,
    create_sql_runner,
)


class TestSQLRunner:
    """Tests for SQL runner."""

    def setup_method(self):
        # Create a temporary DuckDB database with test data
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.duckdb"

        self.table_id = CanonicalUUID(str(uuid4()))
        self.action_id = uuid4()
        self.run_id = uuid4()
        self.runner_nonce = "test_nonce_123"
        self.sandbox_id = uuid4()

        conn = duckdb.connect(str(self.db_path))
        # Table name must match the convention used by the runner: t_{table_id}
        # Use main schema since the policy validator expects main. prefix
        table_name = f"t_{str(self.table_id).replace('-', '_')}"
        conn.execute(f"CREATE TABLE main.{table_name} (id INTEGER, revenue BIGINT, name VARCHAR)")
        conn.execute(f"INSERT INTO main.{table_name} VALUES (1, 100, 'Product A'), (2, 200, 'Product B'), (3, 300, 'Product C')")
        conn.close()

    def teardown_method(self):
        self.temp_dir.cleanup()

    def create_config(self, authorized_evidence=None):
        return SQLRunnerConfig(
            action_id=self.action_id,
            run_id=self.run_id,
            attempt=1,
            runner_nonce=self.runner_nonce,
            sandbox_id=self.sandbox_id,
            pid=12345,
            authorized_tables={self.table_id: self.db_path},
            authorized_evidence=authorized_evidence or {},
            analysis_timezone="UTC",
            policy_version="1.0",
            mailbox_dir=Path(self.temp_dir.name) / "mailbox",
            artifact_dir=Path(self.temp_dir.name) / "artifacts",
            resource_limits={"duckdb_memory_gib": 1.0},
        )

    @pytest.mark.asyncio
    async def test_runner_start(self):
        """Test runner startup."""
        config = self.create_config()
        runner = await create_sql_runner(config)
        assert runner._conn is not None
        await runner.shutdown()

    @pytest.mark.asyncio
    async def test_execute_query_simple(self):
        """Test simple query execution."""
        config = self.create_config()
        runner = await create_sql_runner(config)

        # The runner expects table names in format t_{table_id} (without main. prefix)
        # but the policy validator requires main. prefix
        # So we use the format that the validator accepts
        table_name_with_prefix = f"main.t_{str(self.table_id).replace('-', '_')}"
        request = ExecuteQueryRequest(
            sql=f"SELECT * FROM {table_name_with_prefix}",
            parameters={},
        )

        mailbox_request = MailboxRequest(
            mailbox_id=uuid4(),
            operation_id=uuid4(),
            action_id=self.action_id,
            attempt=1,
            runner_nonce=self.runner_nonce,
            request_type="execute_query",
            payload=request.model_dump(),
            request_digest="test_digest",
            deadline="2026-12-31T23:59:59Z",
        )

        response = await runner.handle_request_from_data(mailbox_request)
        assert response.status == "succeeded"
        assert response.result is not None
        assert "row_count" in response.result
        assert response.result["row_count"] == 3

        await runner.shutdown()

    @pytest.mark.asyncio
    async def test_execute_query_with_where(self):
        """Test query with WHERE clause."""
        config = self.create_config()
        runner = await create_sql_runner(config)

        # Use the correct table name format
        table_name_with_prefix = f"main.t_{str(self.table_id).replace('-', '_')}"
        request = ExecuteQueryRequest(
            sql=f"SELECT * FROM {table_name_with_prefix} WHERE revenue > 150",
            parameters={},
        )

        mailbox_request = MailboxRequest(
            mailbox_id=uuid4(),
            operation_id=uuid4(),
            action_id=self.action_id,
            attempt=1,
            runner_nonce=self.runner_nonce,
            request_type="execute_query",
            payload=request.model_dump(),
            request_digest="test_digest_2",
            deadline="2026-12-31T23:59:59Z",
        )

        response = await runner.handle_request_from_data(mailbox_request)
        assert response.status == "succeeded"
        assert response.result["row_count"] == 2

        await runner.shutdown()

    @pytest.mark.asyncio
    async def test_execute_query_with_aggregation(self):
        """Test query with aggregation."""
        config = self.create_config()
        runner = await create_sql_runner(config)

        # Use the correct table name format
        table_name_with_prefix = f"main.t_{str(self.table_id).replace('-', '_')}"
        request = ExecuteQueryRequest(
            sql=f"SELECT SUM(revenue) as total FROM {table_name_with_prefix}",
            parameters={},
        )

        mailbox_request = MailboxRequest(
            mailbox_id=uuid4(),
            operation_id=uuid4(),
            action_id=self.action_id,
            attempt=1,
            runner_nonce=self.runner_nonce,
            request_type="execute_query",
            payload=request.model_dump(),
            request_digest="test_digest_3",
            deadline="2026-12-31T23:59:59Z",
        )

        response = await runner.handle_request_from_data(mailbox_request)
        assert response.status == "succeeded"
        assert response.result["row_count"] == 1

        await runner.shutdown()

    @pytest.mark.asyncio
    async def test_execute_query_with_parameters(self):
        """Test query with typed parameters."""
        config = self.create_config()
        runner = await create_sql_runner(config)

        # Use the correct table name format
        table_name_with_prefix = f"main.t_{str(self.table_id).replace('-', '_')}"
        request = ExecuteQueryRequest(
            sql=f"SELECT * FROM {table_name_with_prefix} WHERE revenue > :threshold",
            parameters={"threshold": Int64Scalar(kind="int64", value="150")},
        )

        mailbox_request = MailboxRequest(
            mailbox_id=uuid4(),
            operation_id=uuid4(),
            action_id=self.action_id,
            attempt=1,
            runner_nonce=self.runner_nonce,
            request_type="execute_query",
            payload=request.model_dump(),
            request_digest="test_digest_4",
            deadline="2026-12-31T23:59:59Z",
        )

        response = await runner.handle_request_from_data(mailbox_request)
        assert response.status == "succeeded"
        assert response.result["row_count"] == 2

        await runner.shutdown()

    @pytest.mark.asyncio
    async def test_inspect_table(self):
        """Test inspect_table tool."""
        config = self.create_config()
        runner = await create_sql_runner(config)

        request = InspectTableRequest(table_id=self.table_id)

        mailbox_request = MailboxRequest(
            mailbox_id=uuid4(),
            operation_id=uuid4(),
            action_id=self.action_id,
            attempt=1,
            runner_nonce=self.runner_nonce,
            request_type="inspect_table",
            payload=request.model_dump(),
            request_digest="test_digest_5",
            deadline="2026-12-31T23:59:59Z",
        )

        response = await runner.handle_request_from_data(mailbox_request)
        assert response.status == "succeeded"
        assert response.result["table_id"] == str(self.table_id)
        assert response.result["row_count"] == 3
        assert len(response.result["columns"]) == 3

        await runner.shutdown()

    @pytest.mark.asyncio
    async def test_preview_rows(self):
        """Test preview_rows tool."""
        config = self.create_config()
        runner = await create_sql_runner(config)

        request = PreviewRowsRequest(
            table_id=self.table_id,
            columns=["id", "revenue"],
            limit=2,
        )

        mailbox_request = MailboxRequest(
            mailbox_id=uuid4(),
            operation_id=uuid4(),
            action_id=self.action_id,
            attempt=1,
            runner_nonce=self.runner_nonce,
            request_type="preview_rows",
            payload=request.model_dump(),
            request_digest="test_digest_6",
            deadline="2026-12-31T23:59:59Z",
        )

        response = await runner.handle_request_from_data(mailbox_request)
        assert response.status == "succeeded"
        assert response.result["returned_row_count"] == 2
        assert len(response.result["columns"]) == 2

        await runner.shutdown()

    @pytest.mark.asyncio
    async def test_duplicate_request_digest(self):
        """Test that duplicate request digests return cached response."""
        config = self.create_config()
        runner = await create_sql_runner(config)

        # The runner expects table names in format t_{table_id} (without main. prefix)
        # but the policy validator requires main. prefix
        # So we use the format that the validator accepts
        table_name_with_prefix = f"main.t_{str(self.table_id).replace('-', '_')}"
        request = ExecuteQueryRequest(
            sql=f"SELECT * FROM {table_name_with_prefix}",
            parameters={},
        )

        mailbox_request = MailboxRequest(
            mailbox_id=uuid4(),
            operation_id=uuid4(),
            action_id=self.action_id,
            attempt=1,
            runner_nonce=self.runner_nonce,
            request_type="execute_query",
            payload=request.model_dump(),
            request_digest="same_digest",
            deadline="2026-12-31T23:59:59Z",
        )

        response1 = await runner.handle_request_from_data(mailbox_request)
        response2 = await runner.handle_request_from_data(mailbox_request)

        assert response1.operation_id == response2.operation_id
        assert response1.response_digest == response2.response_digest

        await runner.shutdown()

    @pytest.mark.asyncio
    async def test_invalid_query_rejected(self):
        """Test that invalid queries are rejected."""
        config = self.create_config()
        runner = await create_sql_runner(config)

        request = ExecuteQueryRequest(
            sql="INVALID SQL",
            parameters={},
        )

        mailbox_request = MailboxRequest(
            mailbox_id=uuid4(),
            operation_id=uuid4(),
            action_id=self.action_id,
            attempt=1,
            runner_nonce=self.runner_nonce,
            request_type="execute_query",
            payload=request.model_dump(),
            request_digest="test_digest_7",
            deadline="2026-12-31T23:59:59Z",
        )

        response = await runner.handle_request_from_data(mailbox_request)
        assert response.status == "failed"
        assert response.error is not None
        assert response.error["code"] == "unsupported_statement"

        await runner.shutdown()

    @pytest.mark.asyncio
    async def test_unauthorized_table_rejected(self):
        """Test that unauthorized tables are rejected."""
        config = self.create_config()
        runner = await create_sql_runner(config)

        request = ExecuteQueryRequest(
            sql="SELECT * FROM main.unauthorized",
            parameters={},
        )

        mailbox_request = MailboxRequest(
            mailbox_id=uuid4(),
            operation_id=uuid4(),
            action_id=self.action_id,
            attempt=1,
            runner_nonce=self.runner_nonce,
            request_type="execute_query",
            payload=request.model_dump(),
            request_digest="test_digest_8",
            deadline="2026-12-31T23:59:59Z",
        )

        response = await runner.handle_request_from_data(mailbox_request)
        assert response.status == "failed"
        assert response.error is not None
        assert response.error["code"] == "unknown_relation"

        await runner.shutdown()

    @pytest.mark.asyncio
    async def test_non_select_rejected(self):
        """Test that non-SELECT statements are rejected."""
        config = self.create_config()
        runner = await create_sql_runner(config)

        request = ExecuteQueryRequest(
            sql="INSERT INTO main.t_001 VALUES (4, 400, 'Product D')",
            parameters={},
        )

        mailbox_request = MailboxRequest(
            mailbox_id=uuid4(),
            operation_id=uuid4(),
            action_id=self.action_id,
            attempt=1,
            runner_nonce=self.runner_nonce,
            request_type="execute_query",
            payload=request.model_dump(),
            request_digest="test_digest_9",
            deadline="2026-12-31T23:59:59Z",
        )

        response = await runner.handle_request_from_data(mailbox_request)
        assert response.status == "failed"
        assert response.error is not None
        assert response.error["code"] == "unsupported_statement"

        await runner.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])