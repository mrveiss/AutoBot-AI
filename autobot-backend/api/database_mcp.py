# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Database MCP Bridge
Exposes database operations as MCP tools for LLM agents
Supports SQLite for relational data and ChromaDB for vector operations

Provides comprehensive database capabilities:
- SQLite: Query, execute, schema inspection, table management
- ChromaDB: Vector search, collection management, embedding operations
- Cross-database: Statistics, health checks, backup info

Security Model:
- SQL injection prevention (parameterized queries ONLY)
- Read-only mode for production databases
- Query result size limits
- Database/table whitelisting
- Rate limiting for database operations
- Comprehensive audit logging

Issue #49 - Additional MCP Bridges (Browser, HTTP, Database, Git)
Issue #357 - Wrapped blocking SQLite operations with asyncio.to_thread() for non-blocking I/O
"""

import asyncio
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.security.sql_identifier import validate_sql_identifier
from autobot_shared.time_utils import now_utc
from services.mcp_bridge_manifest import MCPBridgeManifest
from type_defs.common import Metadata

from .schemas_code import (
    DatabaseDescribeSchemaResponse,
    DatabaseExecuteResponse,
    DatabaseListDatabasesResponse,
    DatabaseListTablesResponse,
    DatabaseMCPStatusResponse,
    DatabaseMCPTool,
    DatabaseQueryResponse,
    DatabaseStatisticsResponse,
    SchemaRequest,
    SQLExecuteRequest,
    SQLQueryRequest,
    TableListRequest,
)

MANIFEST = MCPBridgeManifest(
    name="database_mcp",
    version="1.0.0",
    description="Database Operations - SQLite Query and Management",
    features=["query", "execute", "schema", "tables", "statistics", "sql_injection_prevention"],
    endpoint="/api/database/mcp/tools",
)

logger = get_logger(__name__)
router = APIRouter(
    tags=["database_mcp", "mcp"],
    dependencies=[Depends(check_admin_permission)],
)

# Issue #380: Module-level tuple for allowed DML operations
_ALLOWED_DML_OPERATIONS = ("INSERT", "UPDATE", "DELETE")

# Security Configuration

# Database whitelist - only these databases can be accessed
DATABASE_WHITELIST = {
    "conversation_files": {
        "path": "data/conversation_files.db",
        "read_only": False,
        "description": "Conversation file tracking",
    },
    "agent_memory": {
        "path": "data/agent_memory.db",
        "read_only": False,
        "description": "Agent memory storage",
    },
    "knowledge_base": {
        "path": "data/knowledge_base.db",
        "read_only": True,
        "description": "Knowledge base (read-only)",
    },
    "project_state": {
        "path": "data/project_state.db",
        "read_only": False,
        "description": "Project state tracking",
    },
    "autobot": {
        "path": "data/autobot.db",
        "read_only": True,
        "description": "Core AutoBot data (read-only)",
    },
}

# SQL patterns that are BLOCKED (security)
BLOCKED_SQL_PATTERNS = [
    r";\s*DROP\s+",
    r";\s*DELETE\s+",
    r";\s*UPDATE\s+",
    r";\s*INSERT\s+",
    r";\s*ALTER\s+",
    r";\s*CREATE\s+",
    r";\s*TRUNCATE\s+",
    r"ATTACH\s+DATABASE",
    r"DETACH\s+DATABASE",
]

# #13520: comment tokens are checked against the query with string literals
# removed. Checked against the raw text they rejected legitimate queries — a
# WHERE clause matching a literal '--' or a path containing '/*' is ordinary SQL,
# not an injection attempt. Kept as a separate list because the relaxation is
# only safe for these two: the patterns above stay on the raw text, where a
# stacked statement must be caught wherever it appears.
BLOCKED_SQL_COMMENT_PATTERNS = [
    r"--",  # line comment
    r"/\*",  # block comment
]

# Rate limiting
MAX_QUERIES_PER_MINUTE = 60
query_counter = {"count": 0, "reset_time": now_utc()}
_rate_limit_lock = asyncio.Lock()

# Query limits
MAX_RESULT_ROWS = 1000
MAX_QUERY_LENGTH = 10000


def _is_readonly_statement(sql: str) -> bool:
    """Does *sql* begin with a statement that cannot modify data? (#13520)

    Deliberately a narrow allow-list rather than a denylist of write verbs: an
    unrecognised statement is treated as a write, so a SQLite keyword nobody
    thought of here fails closed.
    """
    first = sql.lstrip().split(None, 1)
    if not first:
        return False
    return first[0].upper() in {"SELECT", "WITH", "EXPLAIN", "PRAGMA"}


def _strip_sql_string_literals(sql: str) -> str:
    """Blank out single- and double-quoted spans so comment tokens inside them are ignored (#13520).

    Quoted content is replaced with spaces rather than removed, so the result is
    the same length as the input and any offsets stay meaningful.

    SQLite escapes a quote by doubling it (``'it''s'``), which this handles
    naturally: the second quote of the pair opens a new span that the following
    character closes.

    **Fails closed.** If quoting is unbalanced — an unterminated literal — the
    original text is returned unchanged, so the caller's comment check still runs
    over everything. Otherwise a trailing ``'`` would place the rest of the query
    "inside a literal" and hide exactly what this check exists to find.
    """
    out = []
    quote: str | None = None
    for char in sql:
        if quote is None:
            if char in ("'", '"'):
                quote = char
                out.append(" ")
            else:
                out.append(char)
        else:
            out.append(" ")
            if char == quote:
                quote = None

    if quote is not None:
        return sql

    return "".join(out)


def validate_sql_query(sql: str) -> bool:
    """
    Validate SQL query for dangerous patterns

    Security measures:
    - Block multiple statements (semicolon injection)
    - Block DDL operations (DROP, ALTER, CREATE)
    - Block DML operations in queries (use execute_sql for those)
    - Block SQL comments that could hide malicious code
    """
    if len(sql) > MAX_QUERY_LENGTH:
        logger.warning("Query too long: %s chars (max: %s)", len(sql), MAX_QUERY_LENGTH)
        return False

    # Check for blocked patterns
    for pattern in BLOCKED_SQL_PATTERNS:
        if re.search(pattern, sql, re.IGNORECASE):
            logger.warning("Blocked SQL pattern detected: %s", pattern)
            return False

    # #13520: comment tokens are checked outside string literals only.
    # `_strip_sql_string_literals` fails CLOSED — on unbalanced quoting it
    # returns the text unchanged, so a query that could hide a comment inside an
    # unterminated literal is still rejected.
    sql_outside_literals = _strip_sql_string_literals(sql)
    for pattern in BLOCKED_SQL_COMMENT_PATTERNS:
        if re.search(pattern, sql_outside_literals, re.IGNORECASE):
            logger.warning("Blocked SQL comment token detected: %s", pattern)
            return False

    # Count semicolons (should be 0 or 1 at the end)
    semicolons = sql.count(";")
    if semicolons > 1:
        logger.warning("Multiple statements detected: %s semicolons", semicolons)
        return False

    return True


def is_database_allowed(db_name: str) -> bool:
    """Check if database is in whitelist"""
    if db_name not in DATABASE_WHITELIST:
        logger.warning("Database not in whitelist: %s", db_name)
        return False
    return True


def get_database_path(db_name: str) -> Path:
    """Get full path for database"""
    if db_name not in DATABASE_WHITELIST:
        raise ValueError(f"Unknown database: {db_name}")

    db_config = DATABASE_WHITELIST[db_name]
    return Path(db_config["path"])


def is_database_read_only(db_name: str) -> bool:
    """Check if database is marked as read-only"""
    if db_name not in DATABASE_WHITELIST:
        return True  # Default to read-only for safety
    return DATABASE_WHITELIST[db_name].get("read_only", True)


async def check_rate_limit() -> bool:
    """
    Enforce rate limiting for database operations

    Uses asyncio.Lock for thread safety in concurrent async environments
    """

    async with _rate_limit_lock:
        now = now_utc()
        elapsed = (now - query_counter["reset_time"]).total_seconds()

        # Reset counter every minute (in-place modification for thread safety)
        if elapsed >= 60:
            query_counter["count"] = 0
            query_counter["reset_time"] = now

        if query_counter["count"] >= MAX_QUERIES_PER_MINUTE:
            logger.warning("Rate limit exceeded: %s queries/min", query_counter["count"])
            return False

        query_counter["count"] += 1
        return True


def _execute_sqlite_query_sync(db_path: Path, query: str, params: list | None, limit: int) -> tuple[list, list]:
    """Execute SQLite SELECT query synchronously (Issue #357: for use with asyncio.to_thread)."""
    conn = None
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Apply LIMIT if not already in query
        query_str = query.strip()
        if "LIMIT" not in query_str.upper():
            query_str = f"{query_str} LIMIT {limit}"

        # Execute with parameters
        if params:
            cursor.execute(query_str, params)
        else:
            cursor.execute(query_str)

        # Fetch results
        rows = cursor.fetchmany(limit)
        columns = [description[0] for description in cursor.description]

        # Convert to list of dicts
        results = [dict(zip(columns, row)) for row in rows]

        return results, columns
    finally:
        if conn:
            conn.close()


def _execute_sqlite_statement_sync(db_path: Path, statement: str, params: list | None) -> int:
    """Execute SQLite DML statement synchronously (Issue #357: for use with asyncio.to_thread)."""
    conn = None
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        if params:
            cursor.execute(statement, params)
        else:
            cursor.execute(statement)

        rows_affected = cursor.rowcount
        conn.commit()

        return rows_affected
    finally:
        if conn:
            conn.close()


def _list_tables_sync(db_path: Path) -> list[dict]:
    """List tables with row counts synchronously (Issue #357: for use with asyncio.to_thread).

    Issue #480: N+1 pattern acknowledged but unavoidable in SQLite.
    SQLite has no single query to get row counts for all tables.
    Alternative approaches considered:
    - dbstat virtual table: Not always enabled and doesn't provide exact counts
    - sqlite_stat1: Requires ANALYZE and provides estimates only
    The system tables are typically small, minimizing impact.
    """
    conn = None
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = cursor.fetchall()

        # Issue #480: Each table requires a separate COUNT query in SQLite.
        # This is unavoidable without approximate statistics.
        table_info = []
        for (table_name,) in tables:
            # table_name originates from sqlite_master (system catalogue), not user input.
            # SQLite does not support parameterised identifiers; f-string is unavoidable.
            # validate_sql_identifier enforces an allowlist as defence-in-depth.
            validate_sql_identifier(table_name, "table name")
            # Bare-assign the SQL so the nosec/nosemgrep stay on the flagged line:
            # black would split a call spanning several lines and orphan the
            # suppression comment onto the closing paren, defeating it (#9489).
            #
            # #13521: this explanation deliberately avoids writing the literal
            # suppression token followed by prose — bandit parses any such
            # occurrence as a test-id list and warns once per following word,
            # even inside a comment that is only talking about it.
            count_sql = f"SELECT COUNT(*) FROM [{table_name}]"  # nosec B608  # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query  # noqa: E501
            cursor.execute(count_sql)
            row_count = cursor.fetchone()[0]
            table_info.append({"name": table_name, "row_count": row_count})

        return table_info
    finally:
        if conn:
            conn.close()


def _describe_schema_sync(db_path: Path, table: str | None) -> dict:
    """Get schema info synchronously (Issue #357: for use with asyncio.to_thread)."""
    conn = None
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        schemas = {}

        if table:
            # table is validated by validate_sql_identifier (allowlist) above.
            # PRAGMA does not accept parameterised identifiers in SQLite.
            validate_sql_identifier(table, "table name")
            pragma_sql = f"PRAGMA table_info([{table}])"  # nosec B608  # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query  # noqa: E501
            cursor.execute(pragma_sql)
            columns = cursor.fetchall()
            schemas[table] = [
                {
                    "cid": col[0],
                    "name": col[1],
                    "type": col[2],
                    "notnull": bool(col[3]),
                    "default_value": col[4],
                    "primary_key": bool(col[5]),
                }
                for col in columns
            ]
        else:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = cursor.fetchall()

            for (table_name,) in tables:
                # table_name from sqlite_master; validate_sql_identifier enforces allowlist.
                # PRAGMA does not support ? parameters in SQLite.
                validate_sql_identifier(table_name, "table name")
                pragma_sql = f"PRAGMA table_info([{table_name}])"  # nosec B608  # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query  # noqa: E501
                cursor.execute(pragma_sql)
                columns = cursor.fetchall()
                schemas[table_name] = [
                    {
                        "cid": col[0],
                        "name": col[1],
                        "type": col[2],
                        "notnull": bool(col[3]),
                        "default_value": col[4],
                        "primary_key": bool(col[5]),
                    }
                    for col in columns
                ]

        return schemas
    finally:
        if conn:
            conn.close()


def _get_db_statistics_sync(db_path: Path) -> dict:
    """Get database statistics synchronously (Issue #357: for use with asyncio.to_thread).

    Issue #480: N+1 pattern for row counts acknowledged but unavoidable in SQLite.
    See _list_tables_sync docstring for detailed explanation.
    """
    conn = None
    try:
        stat_info = db_path.stat()
        size_bytes = stat_info.st_size
        last_modified = datetime.fromtimestamp(stat_info.st_mtime, tz=timezone.utc)

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        table_count = cursor.fetchone()[0]

        # Issue #480: Each table requires a separate COUNT query in SQLite.
        total_rows = 0
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        for (table_name,) in tables:
            # table_name from sqlite_master (system catalogue), not user input.
            # SQLite does not support parameterised identifiers; f-string unavoidable.
            # validate_sql_identifier enforces an allowlist as defence-in-depth.
            validate_sql_identifier(table_name, "table name")
            count_sql = f"SELECT COUNT(*) FROM [{table_name}]"  # nosec B608  # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query  # noqa: E501
            cursor.execute(count_sql)
            total_rows += cursor.fetchone()[0]

        cursor.execute("SELECT sqlite_version()")
        sqlite_version = cursor.fetchone()[0]

        return {
            "size_bytes": size_bytes,
            "size_mb": round(size_bytes / (1024 * 1024), 2),
            "table_count": table_count,
            "total_rows": total_rows,
            "last_modified": last_modified.isoformat(),
            "sqlite_version": sqlite_version,
        }
    finally:
        if conn:
            conn.close()


# MCP Tool Definitions


def _create_database_query_tool() -> DatabaseMCPTool:
    """
    Create MCP tool definition for database SELECT queries.

    Issue #620.
    """
    return DatabaseMCPTool(
        name="database_query",
        description=(
            "Execute SELECT query on SQLite database. Returns rows as JSON. Rate limited to 60"
            "queries/minute. Only whitelisted databases accessible."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "description": (
                        "Database name (conversation_files, agent_memory, " "knowledge_base, project_state, autobot)"
                    ),
                    "enum": list(DATABASE_WHITELIST.keys()),
                },
                "query": {
                    "type": "string",
                    "description": ("SQL SELECT query. Use ? for parameters to prevent injection."),
                },
                "params": {
                    "type": "array",
                    "description": "Parameters for ? placeholders in query",
                    "items": {},
                },
                "limit": {
                    "type": "integer",
                    "description": (f"Max rows to return (default: 100, max: {MAX_RESULT_ROWS})"),
                    "minimum": 1,
                    "maximum": MAX_RESULT_ROWS,
                },
            },
            "required": ["database", "query"],
        },
    )


def _create_database_execute_tool() -> DatabaseMCPTool:
    """
    Create MCP tool definition for database DML operations.

    Issue #620.
    """
    return DatabaseMCPTool(
        name="database_execute",
        description=(
            "Execute INSERT/UPDATE/DELETE on SQLite database. Only works on non-read-only"
            "databases. Use parameterized queries."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "description": "Database name (must not be read-only)",
                    "enum": list(DATABASE_WHITELIST.keys()),
                },
                "statement": {
                    "type": "string",
                    "description": ("SQL INSERT/UPDATE/DELETE statement. Use ? for parameters."),
                },
                "params": {
                    "type": "array",
                    "description": "Parameters for ? placeholders",
                    "items": {},
                },
            },
            "required": ["database", "statement"],
        },
    )


def _get_database_query_tools() -> List[DatabaseMCPTool]:
    """
    Get MCP tools for database query and execute operations.

    Issue #281: Extracted from get_database_mcp_tools to reduce function length.
    Issue #620: Further refactored to use individual tool creation helpers.

    Returns:
        List of MCPTool definitions for query/execute operations
    """
    return [
        _create_database_query_tool(),
        _create_database_execute_tool(),
    ]


def _create_list_tables_tool() -> DatabaseMCPTool:
    """
    Create MCP tool definition for listing database tables.

    Issue #620.
    """
    return DatabaseMCPTool(
        name="database_list_tables",
        description="List all tables in a SQLite database with row counts and basic info.",
        input_schema={
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "description": "Database name to list tables from",
                    "enum": list(DATABASE_WHITELIST.keys()),
                },
            },
            "required": ["database"],
        },
    )


def _create_describe_schema_tool() -> DatabaseMCPTool:
    """
    Create MCP tool definition for describing database schema.

    Issue #620.
    """
    return DatabaseMCPTool(
        name="database_describe_schema",
        description=("Get schema information for database tables including columns, types," "and constraints."),
        input_schema={
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "description": "Database name",
                    "enum": list(DATABASE_WHITELIST.keys()),
                },
                "table": {
                    "type": "string",
                    "description": ("Specific table to describe (optional, omit for all tables)"),
                },
            },
            "required": ["database"],
        },
    )


def _create_list_databases_tool() -> DatabaseMCPTool:
    """
    Create MCP tool definition for listing available databases.

    Issue #620.
    """
    return DatabaseMCPTool(
        name="database_list_databases",
        description=("List all available whitelisted databases with their access permissions and" "descriptions."),
        input_schema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    )


def _create_statistics_tool() -> DatabaseMCPTool:
    """
    Create MCP tool definition for getting database statistics.

    Issue #620.
    """
    return DatabaseMCPTool(
        name="database_statistics",
        description=("Get statistics for a database including size, table count," "and last modified time."),
        input_schema={
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "description": "Database name",
                    "enum": list(DATABASE_WHITELIST.keys()),
                },
            },
            "required": ["database"],
        },
    )


def _get_database_schema_tools() -> List[DatabaseMCPTool]:
    """
    Get MCP tools for database schema and metadata operations.

    Issue #281: Extracted from get_database_mcp_tools to reduce function length.
    Issue #620: Further refactored to use individual tool creation helpers.

    Returns:
        List of MCPTool definitions for schema/metadata operations
    """
    return [
        _create_list_tables_tool(),
        _create_describe_schema_tool(),
        _create_list_databases_tool(),
        _create_statistics_tool(),
    ]


@router.get("/mcp/tools", response_model=List[DatabaseMCPTool])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_database_mcp_tools",
    error_code_prefix="DATABASE_MCP",
)
async def get_database_mcp_tools() -> List[DatabaseMCPTool]:
    """
    Return all available Database MCP tools

    This endpoint follows the MCP specification for tool discovery.
    """
    # Issue #281: Use extracted helpers for tool definitions by category
    tools = []
    tools.extend(_get_database_query_tools())
    tools.extend(_get_database_schema_tools())
    return tools


# Tool Implementations


@router.post("/mcp/query", response_model=DatabaseQueryResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="database_query_mcp",
    error_code_prefix="DATABASE_MCP",
)
async def database_query_mcp(request: SQLQueryRequest) -> Metadata:
    """
    Execute SELECT query on SQLite database

    Security controls:
    - Database whitelist validation
    - SQL injection prevention (parameterized queries)
    - Query pattern validation
    - Result size limits
    - Rate limiting

    Issue #357: Uses asyncio.to_thread() for non-blocking database operations.
    """
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")

    if not is_database_allowed(request.database):
        raise HTTPException(status_code=403, detail=f"Database not in whitelist: {request.database}")

    if not validate_sql_query(request.query):
        raise HTTPException(status_code=400, detail="Query contains blocked patterns or is too long")

    # #13520: /mcp/execute consulted the read-only flag and this path did not.
    # Harmless in practice — SQLQueryRequest's validator already forbids anything
    # but SELECT, and the sync executor never commits — but that left the
    # guarantee resting on one check where it can rest on two independent ones.
    # A read-only database should refuse a write regardless of which endpoint
    # asks and regardless of whether a future edit relaxes the validator.
    if is_database_read_only(request.database) and not _is_readonly_statement(request.query):
        raise HTTPException(
            status_code=403,
            detail=f"Database {request.database} is read-only. Cannot execute modifications.",
        )

    # Get database path
    db_path = get_database_path(request.database)
    # Issue #358 - avoid blocking
    if not await asyncio.to_thread(db_path.exists):
        raise HTTPException(status_code=404, detail=f"Database file not found: {request.database}")

    # Log the operation
    logger.info("Database query on %s: %s...", request.database, request.query[:100])

    try:
        # Execute query in thread pool (Issue #357: non-blocking)
        results, columns = await asyncio.to_thread(
            _execute_sqlite_query_sync,
            db_path,
            request.query,
            request.params,
            request.limit or 100,
        )

        return {
            "success": True,
            "database": request.database,
            "query": request.query,
            "row_count": len(results),
            "columns": columns,
            "results": results,
            "timestamp": now_utc().isoformat(),
        }

    except sqlite3.Error as e:
        logger.error("SQLite error: %s", e)
        raise HTTPException(status_code=500, detail="Database query error")


@router.post("/mcp/execute", response_model=DatabaseExecuteResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="database_execute_mcp",
    error_code_prefix="DATABASE_MCP",
)
async def database_execute_mcp(request: SQLExecuteRequest) -> Metadata:
    """Execute INSERT/UPDATE/DELETE on SQLite with security controls. Ref: #1088."""
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")

    if not is_database_allowed(request.database):
        raise HTTPException(status_code=403, detail=f"Database not in whitelist: {request.database}")

    # Check if database is read-only
    if is_database_read_only(request.database):
        raise HTTPException(
            status_code=403,
            detail=f"Database {request.database} is read-only. Cannot execute modifications.",
        )

    if not validate_sql_query(request.statement):
        raise HTTPException(status_code=400, detail="Statement contains blocked patterns")

    # Get database path
    db_path = get_database_path(request.database)
    # Issue #358 - avoid blocking
    if not await asyncio.to_thread(db_path.exists):
        raise HTTPException(status_code=404, detail=f"Database file not found: {request.database}")

    # Log the operation with warning (data modification)
    logger.warning("Database EXECUTE on %s: %s...", request.database, request.statement[:100])

    try:
        # Execute statement in thread pool (Issue #357: non-blocking)
        rows_affected = await asyncio.to_thread(
            _execute_sqlite_statement_sync,
            db_path,
            request.statement,
            request.params,
        )

        return {
            "success": True,
            "database": request.database,
            "statement": request.statement,
            "rows_affected": rows_affected,
            "timestamp": now_utc().isoformat(),
        }

    except sqlite3.Error as e:
        logger.error("SQLite execute error: %s", e)
        raise HTTPException(status_code=500, detail="Database execute error")


@router.post("/mcp/list_tables", response_model=DatabaseListTablesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="database_list_tables_mcp",
    error_code_prefix="DATABASE_MCP",
)
async def database_list_tables_mcp(request: TableListRequest) -> Metadata:
    """
    List all tables in a SQLite database

    Returns table names with row counts
    """
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")

    if not is_database_allowed(request.database):
        raise HTTPException(status_code=403, detail=f"Database not in whitelist: {request.database}")

    # Get database path
    db_path = get_database_path(request.database)
    # Issue #358 - avoid blocking
    if not await asyncio.to_thread(db_path.exists):
        raise HTTPException(status_code=404, detail=f"Database file not found: {request.database}")

    logger.info("Listing tables in %s", request.database)

    try:
        # List tables in thread pool (Issue #357: non-blocking)
        table_info = await asyncio.to_thread(
            _list_tables_sync,
            db_path,
        )

        return {
            "success": True,
            "database": request.database,
            "table_count": len(table_info),
            "tables": table_info,
            "timestamp": now_utc().isoformat(),
        }

    except sqlite3.Error as e:
        logger.error("SQLite error listing tables: %s", e)
        raise HTTPException(status_code=500, detail="Error listing tables")


@router.post("/mcp/describe_schema", response_model=DatabaseDescribeSchemaResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="database_describe_schema_mcp",
    error_code_prefix="DATABASE_MCP",
)
async def database_describe_schema_mcp(request: SchemaRequest) -> Metadata:
    """
    Get schema information for database tables

    Returns column names, types, and constraints
    """
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")

    if not is_database_allowed(request.database):
        raise HTTPException(status_code=403, detail=f"Database not in whitelist: {request.database}")

    # Get database path
    db_path = get_database_path(request.database)
    # Issue #358 - avoid blocking
    if not await asyncio.to_thread(db_path.exists):
        raise HTTPException(status_code=404, detail=f"Database file not found: {request.database}")

    logger.info("Describing schema for %s", request.database)

    try:
        # Describe schema in thread pool (Issue #357: non-blocking)
        schemas = await asyncio.to_thread(
            _describe_schema_sync,
            db_path,
            request.table,
        )

        return {
            "success": True,
            "database": request.database,
            "table_count": len(schemas),
            "schemas": schemas,
            "timestamp": now_utc().isoformat(),
        }

    except ValueError as e:
        logger.warning("Invalid table identifier in describe_schema request: %s", e)
        raise HTTPException(status_code=400, detail="Invalid table identifier")
    except sqlite3.Error as e:
        logger.error("SQLite error describing schema: %s", e)
        raise HTTPException(status_code=500, detail="Error describing schema")


@router.get("/mcp/list_databases", response_model=DatabaseListDatabasesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="database_list_databases_mcp",
    error_code_prefix="DATABASE_MCP",
)
async def database_list_databases_mcp() -> Metadata:
    """
    List all available whitelisted databases

    Returns database names, paths, access permissions, and descriptions
    """
    # Security check
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")

    logger.info("Listing available databases")

    databases = []
    for db_name, db_config in DATABASE_WHITELIST.items():
        db_path = Path(db_config["path"])
        # Issue #358 - avoid blocking
        exists = await asyncio.to_thread(db_path.exists)
        size_bytes = (await asyncio.to_thread(db_path.stat)).st_size if exists else 0

        databases.append(
            {
                "name": db_name,
                "path": db_config["path"],
                "read_only": db_config["read_only"],
                "description": db_config["description"],
                "exists": exists,
                "size_mb": round(size_bytes / (1024 * 1024), 2),
            }
        )

    return {
        "success": True,
        "database_count": len(databases),
        "databases": databases,
        "timestamp": now_utc().isoformat(),
    }


@router.post("/mcp/statistics", response_model=DatabaseStatisticsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="database_statistics_mcp",
    error_code_prefix="DATABASE_MCP",
)
async def database_statistics_mcp(request: TableListRequest) -> Metadata:
    """
    Get statistics for a database

    Returns size, table count, total rows, and last modified time
    """
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")

    if not is_database_allowed(request.database):
        raise HTTPException(status_code=403, detail=f"Database not in whitelist: {request.database}")

    # Get database path
    db_path = get_database_path(request.database)
    # Issue #358 - avoid blocking
    if not await asyncio.to_thread(db_path.exists):
        raise HTTPException(status_code=404, detail=f"Database file not found: {request.database}")

    logger.info("Getting statistics for %s", request.database)

    try:
        # Get statistics in thread pool (Issue #357: non-blocking)
        stats = await asyncio.to_thread(
            _get_db_statistics_sync,
            db_path,
        )

        # Add read_only flag to stats
        stats["read_only"] = is_database_read_only(request.database)

        return {
            "success": True,
            "database": request.database,
            "statistics": stats,
            "timestamp": now_utc().isoformat(),
        }

    except sqlite3.Error as e:
        logger.error("SQLite error getting statistics: %s", e)
        raise HTTPException(status_code=500, detail="Error getting statistics")


@router.get("/mcp/status", response_model=DatabaseMCPStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_database_mcp_status",
    error_code_prefix="DATABASE_MCP",
)
async def get_database_mcp_status() -> Metadata:
    """
    Get Database MCP service status

    Returns:
    - Service health
    - Rate limit status
    - Configuration info
    - Database availability
    """

    async with _rate_limit_lock:
        current_rate = query_counter["count"]
        time_until_reset = max(
            0,
            60 - (now_utc() - query_counter["reset_time"]).total_seconds(),
        )

    # Check database availability
    db_status = {}
    for db_name, db_config in DATABASE_WHITELIST.items():
        db_path = Path(db_config["path"])
        # Issue #358 - avoid blocking
        db_exists = await asyncio.to_thread(db_path.exists)
        db_status[db_name] = {
            "available": db_exists,
            "read_only": db_config["read_only"],
        }

    return {
        "status": "operational",
        "service": "database_mcp",
        "rate_limit": {
            "current": current_rate,
            "max": MAX_QUERIES_PER_MINUTE,
            "reset_in_seconds": round(time_until_reset, 1),
        },
        "configuration": {
            "whitelisted_databases": len(DATABASE_WHITELIST),
            "max_result_rows": MAX_RESULT_ROWS,
            "max_query_length": MAX_QUERY_LENGTH,
        },
        "database_availability": db_status,
        "timestamp": now_utc().isoformat(),
    }
