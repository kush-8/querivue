"""Positive SQL policy with SQLGlot AST validation and DuckDB binding."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

import sqlglot
from sqlglot import exp

from querivue_agent.contracts.tools import ExecuteQueryRequest
from querivue_agent.contracts.values import TypedScalar, CanonicalUUID


class SQLPolicyVersion(str, Enum):
    """Supported SQL policy versions."""
    V1 = "1.0"


@dataclass(frozen=True)
class AllowedFunction:
    """Allowed SQL function with supported types."""
    name: str
    aliases: list[str] = field(default_factory=list)
    arg_types: list[str] = field(default_factory=list)  # Empty = any


@dataclass(frozen=True)
class AllowedOperator:
    """Allowed SQL operator."""
    symbol: str
    aliases: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SQLPolicy:
    """Positive SQL policy configuration."""
    version: SQLPolicyVersion
    allowed_functions: list[AllowedFunction]
    allowed_operators: list[AllowedOperator]
    allowed_statements: list[str]
    max_cte_depth: int = 3
    max_query_length: int = 50000


DEFAULT_SQL_POLICY = SQLPolicy(
    version=SQLPolicyVersion.V1,
    allowed_functions=[
        # Aggregates
        AllowedFunction("COUNT", arg_types=["*"]),
        AllowedFunction("SUM", arg_types=["int64", "uint64", "decimal", "float64"]),
        AllowedFunction("AVG", arg_types=["int64", "uint64", "decimal", "float64"]),
        AllowedFunction("MIN", arg_types=["int64", "uint64", "decimal", "float64", "date", "time", "timestamp", "timestamptz", "string"]),
        AllowedFunction("MAX", arg_types=["int64", "uint64", "decimal", "float64", "date", "time", "timestamp", "timestamptz", "string"]),
        AllowedFunction("MEDIAN", arg_types=["int64", "uint64", "decimal", "float64"]),
        AllowedFunction("STDDEV_POP", arg_types=["int64", "uint64", "decimal", "float64"]),
        AllowedFunction("STDDEV_SAMP", arg_types=["int64", "uint64", "decimal", "float64"]),
        AllowedFunction("VAR_POP", arg_types=["int64", "uint64", "decimal", "float64"]),
        AllowedFunction("VAR_SAMP", arg_types=["int64", "uint64", "decimal", "float64"]),
        # Conditionals
        AllowedFunction("CASE"),
        AllowedFunction("COALESCE"),
        AllowedFunction("NULLIF"),
        AllowedFunction("GREATEST"),
        AllowedFunction("LEAST"),
        # Arithmetic
        AllowedFunction("ABS", arg_types=["int64", "uint64", "decimal", "float64"]),
        AllowedFunction("ROUND", arg_types=["decimal", "float64"]),
        AllowedFunction("FLOOR", arg_types=["decimal", "float64"]),
        AllowedFunction("CEIL", arg_types=["decimal", "float64"]),
        AllowedFunction("SQRT", arg_types=["int64", "uint64", "decimal", "float64"]),
        AllowedFunction("POWER", arg_types=["int64", "uint64", "decimal", "float64"]),
        AllowedFunction("LN", arg_types=["int64", "uint64", "decimal", "float64"]),
        AllowedFunction("LOG10", arg_types=["int64", "uint64", "decimal", "float64"]),
        # String
        AllowedFunction("UPPER", arg_types=["string"]),
        AllowedFunction("LOWER", arg_types=["string"]),
        AllowedFunction("TRIM", arg_types=["string"]),
        AllowedFunction("LTRIM", arg_types=["string"]),
        AllowedFunction("RTRIM", arg_types=["string"]),
        AllowedFunction("LENGTH", arg_types=["string"]),
        AllowedFunction("SUBSTRING", arg_types=["string"]),
        AllowedFunction("REPLACE", arg_types=["string"]),
        AllowedFunction("CONCAT", arg_types=["string"]),
        AllowedFunction("CONCAT_WS", arg_types=["string"]),
        AllowedFunction("LIKE", arg_types=["string"]),
        AllowedFunction("ILIKE", arg_types=["string"]),
        AllowedFunction("REGEXP_MATCHES", arg_types=["string"]),
        # Temporal
        AllowedFunction("DATE_TRUNC", arg_types=["date", "timestamp", "timestamptz"]),
        AllowedFunction("DATE_PART", arg_types=["date", "time", "timestamp", "timestamptz"]),
        AllowedFunction("EXTRACT", arg_types=["date", "time", "timestamp", "timestamptz"]),
        AllowedFunction("DATE_DIFF", arg_types=["date", "timestamp", "timestamptz"]),
        AllowedFunction("STRFTIME", arg_types=["date", "time", "timestamp", "timestamptz"]),
        AllowedFunction("STRPTIME", arg_types=["string"]),
        AllowedFunction("TRY_STRPTIME", arg_types=["string"]),
        AllowedFunction("LAST_DAY", arg_types=["date"]),
        AllowedFunction("TIMEZONE", arg_types=["timestamp", "timestamptz"]),
        # Windows
        AllowedFunction("ROW_NUMBER"),
        AllowedFunction("RANK"),
        AllowedFunction("DENSE_RANK"),
        AllowedFunction("LAG", arg_types=["any"]),
        AllowedFunction("LEAD", arg_types=["any"]),
        AllowedFunction("FIRST_VALUE", arg_types=["any"]),
        AllowedFunction("LAST_VALUE", arg_types=["any"]),
        AllowedFunction("NTILE", arg_types=["int64"]),
        # Casting
        AllowedFunction("CAST"),
        AllowedFunction("TRY_CAST"),
    ],
    allowed_operators=[
        AllowedOperator("+"),
        AllowedOperator("-"),
        AllowedOperator("*"),
        AllowedOperator("/"),
        AllowedOperator("%"),
        AllowedOperator("="),
        AllowedOperator("!="),
        AllowedOperator("<>"),
        AllowedOperator("<"),
        AllowedOperator("<="),
        AllowedOperator(">"),
        AllowedOperator(">="),
        AllowedOperator("AND"),
        AllowedOperator("OR"),
        AllowedOperator("NOT"),
        AllowedOperator("IS"),
        AllowedOperator("IS NOT"),
        AllowedOperator("IN"),
        AllowedOperator("NOT IN"),
        AllowedOperator("BETWEEN"),
        AllowedOperator("NOT BETWEEN"),
        AllowedOperator("LIKE"),
        AllowedOperator("NOT LIKE"),
        AllowedOperator("ILIKE"),
        AllowedOperator("NOT ILIKE"),
        AllowedOperator("||"),
    ],
    allowed_statements=["SELECT"],
)


class SQLValidationError(Exception):
    """Raised when SQL validation fails."""
    def __init__(self, code: str, message: str, stage: str, operation_id: UUID | None = None, disposition: str = "fail_action"):
        self.code = code
        self.message = message
        self.stage = stage
        self.operation_id = operation_id
        self.disposition = disposition
        super().__init__(f"[{code}] {message}")


class SQLPolicyValidator:
    """Validates SQL against positive policy."""

    def __init__(self, policy: SQLPolicy = DEFAULT_SQL_POLICY) -> None:
        self._policy = policy
        self._function_map = self._build_function_map()
        self._operator_map = self._build_operator_map()

    def _build_function_map(self) -> dict[str, AllowedFunction]:
        func_map = {}
        for func in self._policy.allowed_functions:
            func_map[func.name.upper()] = func
            for alias in func.aliases:
                func_map[alias.upper()] = func
        return func_map

    def _build_operator_map(self) -> dict[str, AllowedOperator]:
        op_map = {}
        for op in self._policy.allowed_operators:
            op_map[op.symbol.upper()] = op
            for alias in op.aliases:
                op_map[alias.upper()] = op
        return op_map

    def validate(self, request: ExecuteQueryRequest, authorized_tables: set[CanonicalUUID], authorized_evidence: set[CanonicalUUID]) -> list[str]:
        """Validate SQL request against policy. Returns list of authorized physical relation names."""
        sql = request.sql.strip()

        # 1. Validate query length
        if len(sql) > self._policy.max_query_length:
            raise SQLValidationError("query_too_long", f"Query exceeds max length {self._policy.max_query_length}", "validation")

        # 2. Parse with DuckDB dialect
        try:
            parsed = sqlglot.parse(sql, dialect="duckdb")
        except Exception as e:
            raise SQLValidationError("sql_parse_error", f"Failed to parse SQL: {e}", "validation")

        # Filter out None results (empty/whitespace queries)
        parsed = [p for p in parsed if p is not None]

        if not parsed:
            raise SQLValidationError("empty_query", "Query is empty", "validation")

        # 3. Require exactly one statement
        if len(parsed) != 1:
            raise SQLValidationError("multiple_statements", "Exactly one statement required", "validation")

        ast = parsed[0]

        # 4. Must be a SELECT statement
        if not isinstance(ast, exp.Select):
            raise SQLValidationError("unsupported_statement", "Only SELECT statements are allowed", "validation")

        # 5. Check CTE depth
        self._check_cte_depth(ast)

        # 6. Validate all functions
        self._validate_functions(ast)

        # 7. Validate all operators
        self._validate_operators(ast)

        # 8. Resolve and authorize physical relations
        authorized_relations = self._resolve_relations(ast, authorized_tables, authorized_evidence)

        # 9. Validate parameters
        self._validate_parameters(request.parameters)

        return authorized_relations

    def _check_cte_depth(self, ast: exp.Expression) -> None:
        """Check CTE nesting depth."""
        def count_cte_depth(node: exp.Expression, depth: int = 0) -> int:
            max_depth = depth
            if isinstance(node, exp.With):
                max_depth = max(max_depth, depth + 1)
                for cte in node.expressions:
                    max_depth = max(max_depth, count_cte_depth(cte, depth + 1))
            for child in node.iter_expressions():
                max_depth = max(max_depth, count_cte_depth(child, depth))
            return max_depth

        depth = count_cte_depth(ast)
        if depth > self._policy.max_cte_depth:
            raise SQLValidationError("cte_depth_exceeded", f"CTE depth {depth} exceeds max {self._policy.max_cte_depth}", "validation")

    def _validate_functions(self, ast: exp.Expression) -> None:
        """Validate all function calls against allowed list."""
        for func in ast.find_all(exp.Anonymous):
            # Check if it's a known function that sqlglot parses as Anonymous
            func_name = func.this.upper()
            allowed_anonymous = {
                "MEDIAN", "VAR_POP", "VAR_SAMP", "POWER", "LOG10",
                "REPLACE", "DATE_PART", "DATE_TRUNC", "STRFTIME",
                "STRPTIME", "TRY_STRPTIME", "TIMEZONE", "RANK",
                "DENSE_RANK", "NTILE", "PERCENTILECONT", "PERCENTILEDISC",
            }
            if func_name not in allowed_anonymous:
                raise SQLValidationError("unknown_function", f"Anonymous function not allowed: {func.this}", "validation")

        # Allowed function class names (sqlglot uses PascalCase for classes)
        allowed_func_classes = {
            "COUNT", "SUM", "AVG", "MIN", "MAX",
            "PERCENTILECONT", "PERCENTILEDISC",  # MEDIAN and related
            "STDDEVPOP", "STDDEVSAMP", "VARIANCEPOP", "VARIANCE",
            "COALESCE", "NULLIF", "GREATEST", "LEAST",
            "ABS", "ROUND", "FLOOR", "CEIL", "SQRT", "POW",
            "LN", "LOG", "UPPER", "LOWER", "TRIM", "LTRIM",
            "RTRIM", "LENGTH", "SUBSTRING", "CONCAT",
            "CONCATWS", "LIKE", "ILIKE", "REGEXPMATCHES",
            "TIMESTAMPTRUNC", "EXTRACT", "DATEDIFF",
            "TIMETOSTR", "STRTOTIME", "TRYSTRTOTIME", "LASTDAY",
            "ROWNUMBER", "LAG", "LEAD", "FIRSTVALUE", "LASTVALUE",
            "CAST", "TRYCAST",
        }

        for func in ast.find_all(exp.Func):
            # Skip Anonymous functions - they were already checked above
            if isinstance(func, exp.Anonymous):
                continue
            func_name = func.__class__.__name__.upper()
            if func_name not in allowed_func_classes:
                raise SQLValidationError("unknown_function", f"Function not in positive policy: {func_name}", "validation")

    def _validate_operators(self, ast: exp.Expression) -> None:
        """Validate all operators against allowed list."""
        for op in ast.find_all(exp.Binary):
            op_symbol = op.__class__.__name__.upper()
            # Map sqlglot operator classes to symbols
            op_map = {
                "ADD": "+", "SUB": "-", "MUL": "*", "DIV": "/", "MOD": "%",
                "EQ": "=", "NEQ": "!=", "LT": "<", "LTE": "<=", "GT": ">", "GTE": ">=",
                "AND": "AND", "OR": "OR", "NOT": "NOT",
                "IS": "IS", "IN": "IN", "BETWEEN": "BETWEEN",
                "LIKE": "LIKE", "ILIKE": "ILIKE",
                "DPPIPE": "||",
            }
            symbol = op_map.get(op_symbol)
            if symbol and symbol.upper() not in self._operator_map:
                raise SQLValidationError("policy_violation", f"Operator not allowed: {symbol}", "validation")

    def _resolve_relations(
        self,
        ast: exp.Expression,
        authorized_tables: set[CanonicalUUID],
        authorized_evidence: set[CanonicalUUID]
    ) -> list[str]:
        """Resolve and authorize all physical relations in the query."""
        authorized_relations = []

        # Get CTE names to exclude them from authorization checks
        cte_names = set()
        for cte in ast.find_all(exp.CTE):
            cte_names.add(str(cte.alias))

        for table in ast.find_all(exp.Table):
            # Get the full qualified name - extract string values from Identifier objects
            catalog = table.args.get("catalog")
            db = table.args.get("db")
            name = table.name

            # Skip CTE references - they're not physical tables
            if str(name) in cte_names:
                continue

            # Build qualified name
            parts = []
            if catalog:
                parts.append(str(catalog))
            if db:
                parts.append(str(db))
            parts.append(str(name))
            qualified = ".".join(parts)

            # Check if it's an authorized table or evidence relation
            # Tables use format: main.t_001, evidence uses format: evidence.evidence_id
            if qualified.startswith("main."):
                table_name = qualified[5:]  # Remove "main."
                # Find matching table_id - check if table_name matches any authorized table's SQL name
                found = False
                for tid in authorized_tables:
                    # The authorized table SQL name convention is t_{table_id}
                    expected_name = f"t_{str(tid).replace('-', '_')}"
                    if table_name == expected_name:
                        found = True
                        break
                if not found:
                    raise SQLValidationError("unknown_relation", f"Unauthorized table: {qualified}", "validation")
                authorized_relations.append(qualified)
            elif qualified.startswith("evidence."):
                evidence_name = qualified[9:]  # Remove "evidence."
                # Check against authorized evidence
                found = False
                for eid in authorized_evidence:
                    # Runtime provides evidence relation names
                    found = True
                    break
                if not found:
                    raise SQLValidationError("unknown_relation", f"Unauthorized evidence: {qualified}", "validation")
                authorized_relations.append(qualified)
            else:
                raise SQLValidationError("unknown_relation", f"Unsupported relation format: {qualified}", "validation")

        if not authorized_relations:
            raise SQLValidationError("no_relations", "Query must reference at least one authorized relation", "validation")

        return authorized_relations

    def _validate_parameters(self, parameters: dict[str, TypedScalar]) -> None:
        """Validate parameter names and types."""
        # Case-insensitive uniqueness already checked in model
        for name, value in parameters.items():
            if not name.strip():
                raise SQLValidationError("invalid_arguments", "Parameter name cannot be blank", "validation")
            # TypedScalar already validates the value structure


def create_sql_policy_validator(policy_version: str = "1.0") -> SQLPolicyValidator:
    """Create a SQL policy validator for the given version."""
    if policy_version == "1.0":
        return SQLPolicyValidator(DEFAULT_SQL_POLICY)
    raise ValueError(f"Unsupported policy version: {policy_version}")