"""Unit tests for SQL policy validation."""

from __future__ import annotations

import pytest
from uuid import uuid4

from querivue_agent.contracts.tools import ExecuteQueryRequest
from querivue_agent.contracts.values import CanonicalUUID, Int64Scalar
from querivue_agent.runtime.sql_policy import (
    SQLPolicyValidator,
    SQLValidationError,
    DEFAULT_SQL_POLICY,
    create_sql_policy_validator,
)


class TestSQLPolicyValidator:
    """Tests for SQL policy validator."""

    def setup_method(self):
        self.validator = create_sql_policy_validator("1.0")
        # Use fixed table IDs that match the SQL queries
        self.table_id = CanonicalUUID("00000000-0000-0000-0000-000000000001")
        self.authorized_tables = {self.table_id}
        self.authorized_evidence = {CanonicalUUID(str(uuid4()))}

    def test_valid_simple_select(self):
        """Test valid simple SELECT query."""
        request = ExecuteQueryRequest(
            sql="SELECT revenue FROM main.t_00000000_0000_0000_0000_000000000001",
            parameters={},
        )
        relations = self.validator.validate(request, self.authorized_tables, self.authorized_evidence)
        assert len(relations) == 1
        assert relations[0].startswith("main.")

    def test_valid_select_with_where(self):
        """Test SELECT with WHERE clause."""
        request = ExecuteQueryRequest(
            sql="SELECT * FROM main.t_00000000_0000_0000_0000_000000000001 WHERE revenue > 100",
            parameters={},
        )
        relations = self.validator.validate(request, self.authorized_tables, self.authorized_evidence)
        assert len(relations) == 1

    def test_valid_select_with_aggregation(self):
        """Test SELECT with aggregation functions."""
        request = ExecuteQueryRequest(
            sql="SELECT SUM(revenue) FROM main.t_00000000_0000_0000_0000_000000000001",
            parameters={},
        )
        relations = self.validator.validate(request, self.authorized_tables, self.authorized_evidence)
        assert len(relations) == 1

    def test_valid_select_with_cte(self):
        """Test SELECT with CTE."""
        request = ExecuteQueryRequest(
            sql="WITH cte AS (SELECT revenue FROM main.t_00000000_0000_0000_0000_000000000001) SELECT * FROM cte",
            parameters={},
        )
        relations = self.validator.validate(request, self.authorized_tables, self.authorized_evidence)
        assert len(relations) == 1

    def test_valid_select_with_join(self):
        """Test SELECT with JOIN."""
        table2 = CanonicalUUID("00000000-0000-0000-0000-000000000002")
        tables = {*self.authorized_tables, table2}
        request = ExecuteQueryRequest(
            sql="SELECT t1.revenue, t2.cost FROM main.t_00000000_0000_0000_0000_000000000001 t1 JOIN main.t_00000000_0000_0000_0000_000000000002 t2 ON t1.id = t2.id",
            parameters={},
        )
        relations = self.validator.validate(request, tables, self.authorized_evidence)
        assert len(relations) >= 1

    def test_valid_with_parameters(self):
        """Test query with typed parameters."""
        request = ExecuteQueryRequest(
            sql="SELECT * FROM main.t_00000000_0000_0000_0000_000000000001 WHERE revenue > :threshold",
            parameters={"threshold": Int64Scalar(kind="int64", value="100")},
        )
        relations = self.validator.validate(request, self.authorized_tables, self.authorized_evidence)
        assert len(relations) == 1

    def test_rejects_multiple_statements(self):
        """Test that multiple statements are rejected."""
        request = ExecuteQueryRequest(
            sql="SELECT * FROM main.t_00000000_0000_0000_0000_000000000001; SELECT * FROM main.t_00000000_0000_0000_0000_000000000001",
            parameters={},
        )
        with pytest.raises(SQLValidationError) as exc:
            self.validator.validate(request, self.authorized_tables, self.authorized_evidence)
        assert exc.value.code == "multiple_statements"

    def test_rejects_non_select(self):
        """Test that non-SELECT statements are rejected."""
        request = ExecuteQueryRequest(
            sql="INSERT INTO main.t_00000000_0000_0000_0000_000000000001 VALUES (1)",
            parameters={},
        )
        with pytest.raises(SQLValidationError) as exc:
            self.validator.validate(request, self.authorized_tables, self.authorized_evidence)
        assert exc.value.code == "unsupported_statement"

    def test_rejects_empty_query(self):
        """Test that queries with no relations are rejected."""
        request = ExecuteQueryRequest(
            sql="SELECT 1",
            parameters={},
        )
        with pytest.raises(SQLValidationError) as exc:
            self.validator.validate(request, self.authorized_tables, self.authorized_evidence)
        assert exc.value.code == "no_relations"

    def test_rejects_unknown_function(self):
        """Test that unknown functions are rejected."""
        request = ExecuteQueryRequest(
            sql="SELECT UNKNOWN_FUNC(revenue) FROM main.t_00000000_0000_0000_0000_000000000001",
            parameters={},
        )
        with pytest.raises(SQLValidationError) as exc:
            self.validator.validate(request, self.authorized_tables, self.authorized_evidence)
        assert exc.value.code == "unknown_function"

    def test_rejects_anonymous_function(self):
        """Test that anonymous functions are rejected."""
        request = ExecuteQueryRequest(
            sql="SELECT my_udf(revenue) FROM main.t_00000000_0000_0000_0000_000000000001",
            parameters={},
        )
        with pytest.raises(SQLValidationError) as exc:
            self.validator.validate(request, self.authorized_tables, self.authorized_evidence)
        assert exc.value.code == "unknown_function"

    def test_rejects_unauthorized_table(self):
        """Test that unauthorized tables are rejected."""
        request = ExecuteQueryRequest(
            sql="SELECT * FROM main.unauthorized_table",
            parameters={},
        )
        with pytest.raises(SQLValidationError) as exc:
            self.validator.validate(request, set(), self.authorized_evidence)
        assert exc.value.code == "unknown_relation"

    def test_rejects_invalid_relation_format(self):
        """Test that invalid relation formats are rejected."""
        request = ExecuteQueryRequest(
            sql="SELECT * FROM other_schema.table",
            parameters={},
        )
        with pytest.raises(SQLValidationError) as exc:
            self.validator.validate(request, self.authorized_tables, self.authorized_evidence)
        assert exc.value.code == "unknown_relation"

    def test_rejects_no_relations(self):
        """Test that queries with no relations are rejected."""
        request = ExecuteQueryRequest(
            sql="SELECT 1",
            parameters={},
        )
        with pytest.raises(SQLValidationError) as exc:
            self.validator.validate(request, self.authorized_tables, self.authorized_evidence)
        assert exc.value.code == "no_relations"

    def test_rejects_cte_depth_exceeded(self):
        """Test that excessive CTE depth is rejected."""
        # Build actually nested CTE (depth > 3)
        # WITH cte1 AS (WITH cte2 AS (WITH cte3 AS (SELECT ...) SELECT ...) SELECT ...)
        nested_cte = "SELECT revenue FROM main.t_00000000_0000_0000_0000_000000000001"
        for i in range(5, 0, -1):
            nested_cte = f"WITH cte{i} AS ({nested_cte}) SELECT * FROM cte{i}"
        sql = nested_cte

        request = ExecuteQueryRequest(sql=sql, parameters={})
        with pytest.raises(SQLValidationError) as exc:
            self.validator.validate(request, self.authorized_tables, self.authorized_evidence)
        assert exc.value.code == "cte_depth_exceeded"

    def test_allows_allowed_functions(self):
        """Test that all allowed functions work."""
        functions_to_test = [
            "COUNT(*)",
            "SUM(revenue)",
            "AVG(revenue)",
            "MIN(revenue)",
            "MAX(revenue)",
            "MEDIAN(revenue)",
            "STDDEV_POP(revenue)",
            "COALESCE(revenue, 0)",
            "NULLIF(revenue, 0)",
            "GREATEST(revenue, cost)",
            "LEAST(revenue, cost)",
            "ABS(revenue)",
            "ROUND(revenue)",
            "FLOOR(revenue)",
            "CEIL(revenue)",
            "SQRT(revenue)",
            "POWER(revenue, 2)",
            "LN(revenue)",
            "LOG10(revenue)",
            "UPPER(name)",
            "LOWER(name)",
            "TRIM(name)",
            "SUBSTRING(name, 1, 5)",
            "REPLACE(name, 'a', 'b')",
            "CONCAT(name, 'suffix')",
            "DATE_TRUNC('month', date_col)",
            "DATE_PART('year', date_col)",
            "EXTRACT(year FROM date_col)",
            "DATE_DIFF('day', date1, date2)",
            "STRFTIME(date_col, '%Y-%m')",
            "STRPTIME('2024-01-01', '%Y-%m-%d')",
            "TRY_STRPTIME('2024-01-01', '%Y-%m-%d')",
            "LAST_DAY(date_col)",
            "TIMEZONE('UTC', ts_col)",
            "ROW_NUMBER() OVER ()",
            "RANK() OVER ()",
            "DENSE_RANK() OVER ()",
            "LAG(revenue) OVER ()",
            "LEAD(revenue) OVER ()",
            "FIRST_VALUE(revenue) OVER ()",
            "LAST_VALUE(revenue) OVER ()",
            "NTILE(4) OVER ()",
            "CAST(revenue AS VARCHAR)",
            "TRY_CAST(revenue AS VARCHAR)",
        ]

        for func in functions_to_test:
            request = ExecuteQueryRequest(
                sql=f"SELECT {func} FROM main.t_00000000_0000_0000_0000_000000000001",
                parameters={},
            )
            # Should not raise
            relations = self.validator.validate(request, self.authorized_tables, self.authorized_evidence)
            assert len(relations) == 1

    def test_allows_allowed_operators(self):
        """Test that all allowed operators work."""
        operators_to_test = [
            "revenue + cost",
            "revenue - cost",
            "revenue * cost",
            "revenue / cost",
            "revenue % 10",
            "revenue = 100",
            "revenue != 100",
            "revenue <> 100",
            "revenue < 100",
            "revenue <= 100",
            "revenue > 100",
            "revenue >= 100",
            "revenue > 100 AND cost < 50",
            "revenue > 100 OR cost < 50",
            "NOT revenue > 100",
            "revenue IS NULL",
            "revenue IS NOT NULL",
            "revenue IN (100, 200, 300)",
            "revenue NOT IN (100, 200)",
            "revenue BETWEEN 100 AND 200",
            "revenue NOT BETWEEN 100 AND 200",
            "name LIKE '%test%'",
            "name NOT LIKE '%test%'",
            "name ILIKE '%TEST%'",
            "name NOT ILIKE '%TEST%'",
            "str1 || str2",
        ]

        for op in operators_to_test:
            request = ExecuteQueryRequest(
                sql=f"SELECT * FROM main.t_00000000_0000_0000_0000_000000000001 WHERE {op}",
                parameters={},
            )
            # Should not raise
            relations = self.validator.validate(request, self.authorized_tables, self.authorized_evidence)
            assert len(relations) == 1

    def test_rejects_query_too_long(self):
        """Test that overly long queries are rejected."""
        long_sql = "SELECT " + ", ".join([f"col_{i}" for i in range(10000)]) + " FROM main.t_00000000_0000_0000_0000_000000000001"
        request = ExecuteQueryRequest(sql=long_sql, parameters={})
        with pytest.raises(SQLValidationError) as exc:
            self.validator.validate(request, self.authorized_tables, self.authorized_evidence)
        assert exc.value.code == "query_too_long"

    def test_case_insensitive_parameter_names(self):
        """Test that parameter names are validated case-insensitively at model level."""
        # This is validated in the model (Pydantic validator), not the policy validator
        with pytest.raises(Exception) as exc:
            ExecuteQueryRequest(
                sql="SELECT * FROM main.t_00000000_0000_0000_0000_000000000001 WHERE revenue > :threshold",
                parameters={
                    "threshold": Int64Scalar(kind="int64", value="100"),
                    "THRESHOLD": Int64Scalar(kind="int64", value="200"),  # Duplicate case-insensitive
                },
            )
        assert "case-insensitively" in str(exc.value).lower()


class TestSQLPolicyCreation:
    """Tests for SQL policy creation."""

    def test_create_validator_v1(self):
        """Test creating v1 validator."""
        validator = create_sql_policy_validator("1.0")
        assert isinstance(validator, SQLPolicyValidator)

    def test_create_validator_invalid_version(self):
        """Test creating validator with invalid version."""
        with pytest.raises(ValueError):
            create_sql_policy_validator("2.0")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])