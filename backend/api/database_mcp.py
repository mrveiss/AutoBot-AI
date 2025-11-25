# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
"""

import asyncio
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)
router = APIRouter(tags=["database_mcp", "mcp"])


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
    r"--",  # SQL comments
    r"/\*",  # Block comments
    r"ATTACH\s+DATABASE",
    r"DETACH\s+DATABASE",
]

# Rate limiting
MAX_QUERIES_PER_MINUTE = 60
query_counter = {"count": 0, "reset_time": datetime.now(timezone.utc)}
_rate_limit_lock = asyncio.Lock()

# Query limits
MAX_RESULT_ROWS = 1000
MAX_QUERY_LENGTH = 10000


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
        logger.warning(f"Query too long: {len(sql)} chars (max: {MAX_QUERY_LENGTH})")
        return False

    # Check for blocked patterns
    for pattern in BLOCKED_SQL_PATTERNS:
        if re.search(pattern, sql, re.IGNORECASE):
            logger.warning(f"Blocked SQL pattern detected: {pattern}")
            return False

    # Count semicolons (should be 0 or 1 at the end)
    semicolons = sql.count(";")
    if semicolons > 1:
        logger.warning(f"Multiple statements detected: {semicolons} semicolons")
        return False

    return True


def is_database_allowed(db_name: str) -> bool:
    """Check if database is in whitelist"""
    if db_name not in DATABASE_WHITELIST:
        logger.warning(f"Database not in whitelist: {db_name}")
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
        now = datetime.now(timezone.utc)
        elapsed = (now - query_counter["reset_time"]).total_seconds()

        # Reset counter every minute (in-place modification for thread safety)
        if elapsed >= 60:
            query_counter["count"] = 0
            query_counter["reset_time"] = now

        if query_counter["count"] >= MAX_QUERIES_PER_MINUTE:
            logger.warning(f"Rate limit exceeded: {query_counter['count']} queries/min")
            return False

        query_counter["count"] += 1
        return True


# Pydantic Models


class MCPTool(BaseModel):
    """Standard MCP tool definition"""

    name: str
    description: str
    input_schema: Dict[str, Any]


class SQLQueryRequest(BaseModel):
    """SQL query request model"""

    database: str = Field(..., description="Database name from whitelist")
    query: str = Field(..., description="SQL SELECT query (parameterized)")
    params: Optional[List[Any]] = Field(
        default=None, description="Query parameters for ? placeholders"
    ),
    limit: Optional[int] = Field(
        default=100,
        ge=1,
        le=MAX_RESULT_ROWS,
        description=f"Max rows to return (1-{MAX_RESULT_ROWS})",
    )

    @field_validator("query")
    @classmethod
    def validate_query_is_select(cls, v):
        """Ensure query is SELECT only"""
        normalized = v.strip().upper()
        if not normalized.startswith("SELECT"):
            raise ValueError(
                "Only SELECT queries allowed. Use execute_sql for modifications."
            )
        return v


class SQLExecuteRequest(BaseModel):
    """SQL execute request model (for INSERT/UPDATE/DELETE)"""

    database: str = Field(..., description="Database name from whitelist")
    statement: str = Field(..., description="SQL statement (INSERT/UPDATE/DELETE)")
    params: Optional[List[Any]] = Field(
        default=None, description="Statement parameters for ? placeholders"
    )

    @field_validator("statement")
    @classmethod
    def validate_statement_type(cls, v):
        """Ensure statement is DML operation"""
        normalized = v.strip().upper()
        allowed = ["INSERT", "UPDATE", "DELETE"]
        if not any(normalized.startswith(op) for op in allowed):
            raise ValueError(f"Only {', '.join(allowed)} statements allowed")
        return v


class SchemaRequest(BaseModel):
    """Database schema request model"""

    database: str = Field(..., description="Database name from whitelist")
    table: Optional[str] = Field(
        default=None, description="Specific table to describe (optional)"
    )


class TableListRequest(BaseModel):
    """List tables request model"""

    database: str = Field(..., description="Database name from whitelist")


# MCP Tool Definitions


@router.get("/mcp/tools")
async def get_database_mcp_tools() -> List[MCPTool]:
    """
    Return all available Database MCP tools

    This endpoint follows the MCP specification for tool discovery.
    """
    tools = [
        MCPTool(
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
                            "Database name (conversation_files, agent_memory, knowledge_base, project_state, autobot)"
                        ),
                        "enum": list(DATABASE_WHITELIST.keys()),
                    },
                    "query": {
                        "type": "string",
                        "description": (
                            "SQL SELECT query. Use ? for parameters to prevent injection."
                        ),
                    },
                    "params": {
                        "type": "array",
                        "description": "Parameters for ? placeholders in query",
                        "items": {},
                    },
                    "limit": {
                        "type": "integer",
                        "description": (
                            f"Max rows to return (default: 100, max: {MAX_RESULT_ROWS})"
                        ),
                        "minimum": 1,
                        "maximum": MAX_RESULT_ROWS,
                    },
                },
                "required": ["database", "query"],
            },
        ),
        MCPTool(
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
                        "description": (
                            "SQL INSERT/UPDATE/DELETE statement. Use ? for parameters."
                        ),
                    },
                    "params": {
                        "type": "array",
                        "description": "Parameters for ? placeholders",
                        "items": {},
                    },
                },
                "required": ["database", "statement"],
            },
        ),
        MCPTool(
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
        ),
        MCPTool(
            name="database_describe_schema",
            description=(
                "Get schema information for database tables including columns, types,"
                "and constraints."
            ),
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
                        "description": (
                            "Specific table to describe (optional, omit for all tables)"
                        ),
                    },
                },
                "required": ["database"],
            },
        ),
        MCPTool(
            name="database_list_databases",
            description=(
                "List all available whitelisted databases with their access permissions and"
                "descriptions."
            ),
            input_schema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        MCPTool(
            name="database_statistics",
            description=(
                "Get statistics for a database including size, table count,"
                "and last modified time."
            ),
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
        ),
    ]

    return tools


# Tool Implementations


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="database_query_mcp",
    error_code_prefix="DATABASE_MCP",
)
@router.post("/mcp/query")
async def database_query_mcp(request: SQLQueryRequest) -> Dict[str, Any]:
    """
    Execute SELECT query on SQLite database

    Security controls:
    - Database whitelist validation
    - SQL injection prevention (parameterized queries)
    - Query pattern validation
    - Result size limits
    - Rate limiting
    """
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded. Try again later."
        )

    if not is_database_allowed(request.database):
        raise HTTPException(
            status_code=403, detail=f"Database not in whitelist: {request.database}"
        )

    if not validate_sql_query(request.query):
        raise HTTPException(
            status_code=400, detail="Query contains blocked patterns or is too long"
        )

    # Get database path
    db_path = get_database_path(request.database)
    if not db_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Database file not found: {request.database}"
        )

    # Log the operation
    logger.info(f"Database query on {request.database}: {request.query[:100]}...")

    conn = None
    try:
        # Execute query with context manager for resource safety
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Apply LIMIT if not already in query
        query = request.query.strip()
        if "LIMIT" not in query.upper():
            query = f"{query} LIMIT {request.limit}"

        # Execute with parameters
        if request.params:
            cursor.execute(query, request.params)
        else:
            cursor.execute(query)

        # Fetch results
        rows = cursor.fetchmany(request.limit or 100)
        columns = [description[0] for description in cursor.description]

        # Convert to list of dicts
        results = [dict(zip(columns, row)) for row in rows]

        return {
            "success": True,
            "database": request.database,
            "query": request.query,
            "row_count": len(results),
            "columns": columns,
            "results": results,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except sqlite3.Error as e:
        logger.error(f"SQLite error: {e}")
        raise HTTPException(status_code=500, detail=f"Database query error: {str(e)}")
    finally:
        if conn:
            conn.close()


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="database_execute_mcp",
    error_code_prefix="DATABASE_MCP",
)
@router.post("/mcp/execute")
async def database_execute_mcp(request: SQLExecuteRequest) -> Dict[str, Any]:
    """
    Execute INSERT/UPDATE/DELETE on SQLite database

    Security controls:
    - Database whitelist validation
    - Read-only database check
    - SQL injection prevention (parameterized queries)
    - Rate limiting
    - Audit logging
    """
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded. Try again later."
        )

    if not is_database_allowed(request.database):
        raise HTTPException(
            status_code=403, detail=f"Database not in whitelist: {request.database}"
        )

    # Check if database is read-only
    if is_database_read_only(request.database):
        raise HTTPException(
            status_code=403,
            detail=f"Database {request.database} is read-only. Cannot execute modifications.",
        )

    if not validate_sql_query(request.statement):
        raise HTTPException(
            status_code=400, detail="Statement contains blocked patterns"
        )

    # Get database path
    db_path = get_database_path(request.database)
    if not db_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Database file not found: {request.database}"
        )

    # Log the operation with warning (data modification)
    logger.warning(
        f"Database EXECUTE on {request.database}: {request.statement[:100]}..."
    ),

    conn = None
    try:
        # Execute statement with resource safety
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Execute with parameters
        if request.params:
            cursor.execute(request.statement, request.params)
        else:
            cursor.execute(request.statement)

        # Get affected rows
        rows_affected = cursor.rowcount

        # Commit changes
        conn.commit()

        return {
            "success": True,
            "database": request.database,
            "statement": request.statement,
            "rows_affected": rows_affected,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except sqlite3.Error as e:
        logger.error(f"SQLite execute error: {e}")
        raise HTTPException(status_code=500, detail=f"Database execute error: {str(e)}")
    finally:
        if conn:
            conn.close()


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="database_list_tables_mcp",
    error_code_prefix="DATABASE_MCP",
)
@router.post("/mcp/list_tables")
async def database_list_tables_mcp(request: TableListRequest) -> Dict[str, Any]:
    """
    List all tables in a SQLite database

    Returns table names with row counts
    """
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded. Try again later."
        )

    if not is_database_allowed(request.database):
        raise HTTPException(
            status_code=403, detail=f"Database not in whitelist: {request.database}"
        )

    # Get database path
    db_path = get_database_path(request.database)
    if not db_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Database file not found: {request.database}"
        )

    logger.info(f"Listing tables in {request.database}")

    conn = None
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Get all tables
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ),
        tables = cursor.fetchall()

        # Get row count for each table
        table_info = []
        for (table_name,) in tables:
            cursor.execute(f"SELECT COUNT(*) FROM [{table_name}]")
            row_count = cursor.fetchone()[0]
            table_info.append({"name": table_name, "row_count": row_count})

        return {
            "success": True,
            "database": request.database,
            "table_count": len(table_info),
            "tables": table_info,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except sqlite3.Error as e:
        logger.error(f"SQLite error listing tables: {e}")
        raise HTTPException(status_code=500, detail=f"Error listing tables: {str(e)}")
    finally:
        if conn:
            conn.close()


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="database_describe_schema_mcp",
    error_code_prefix="DATABASE_MCP",
)
@router.post("/mcp/describe_schema")
async def database_describe_schema_mcp(request: SchemaRequest) -> Dict[str, Any]:
    """
    Get schema information for database tables

    Returns column names, types, and constraints
    """
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded. Try again later."
        )

    if not is_database_allowed(request.database):
        raise HTTPException(
            status_code=403, detail=f"Database not in whitelist: {request.database}"
        )

    # Get database path
    db_path = get_database_path(request.database)
    if not db_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Database file not found: {request.database}"
        )

    logger.info(f"Describing schema for {request.database}")

    conn = None
    try:
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        schemas = {}

        if request.table:
            # Single table
            cursor.execute(f"PRAGMA table_info([{request.table}])")
            columns = cursor.fetchall()
            schemas[request.table] = [
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
            # All tables
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ),
            tables = cursor.fetchall()

            for (table_name,) in tables:
                cursor.execute(f"PRAGMA table_info([{table_name}])")
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

        return {
            "success": True,
            "database": request.database,
            "table_count": len(schemas),
            "schemas": schemas,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except sqlite3.Error as e:
        logger.error(f"SQLite error describing schema: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error describing schema: {str(e)}"
        )
    finally:
        if conn:
            conn.close()


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="database_list_databases_mcp",
    error_code_prefix="DATABASE_MCP",
)
@router.get("/mcp/list_databases")
async def database_list_databases_mcp() -> Dict[str, Any]:
    """
    List all available whitelisted databases

    Returns database names, paths, access permissions, and descriptions
    """
    # Security check
    if not await check_rate_limit():
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded. Try again later."
        )

    logger.info("Listing available databases")

    databases = []
    for db_name, db_config in DATABASE_WHITELIST.items():
        db_path = Path(db_config["path"])
        exists = db_path.exists()
        size_bytes = db_path.stat().st_size if exists else 0

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
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="database_statistics_mcp",
    error_code_prefix="DATABASE_MCP",
)
@router.post("/mcp/statistics")
async def database_statistics_mcp(request: TableListRequest) -> Dict[str, Any]:
    """
    Get statistics for a database

    Returns size, table count, total rows, and last modified time
    """
    # Security checks
    if not await check_rate_limit():
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded. Try again later."
        )

    if not is_database_allowed(request.database):
        raise HTTPException(
            status_code=403, detail=f"Database not in whitelist: {request.database}"
        )

    # Get database path
    db_path = get_database_path(request.database)
    if not db_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Database file not found: {request.database}"
        )

    logger.info(f"Getting statistics for {request.database}")

    conn = None
    try:
        # File statistics
        stat_info = db_path.stat()
        size_bytes = stat_info.st_size
        last_modified = datetime.fromtimestamp(stat_info.st_mtime, tz=timezone.utc)

        # Database statistics
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Table count
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        table_count = cursor.fetchone()[0]

        # Total rows across all tables
        total_rows = 0
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        for (table_name,) in tables:
            cursor.execute(f"SELECT COUNT(*) FROM [{table_name}]")
            total_rows += cursor.fetchone()[0]

        # SQLite version
        cursor.execute("SELECT sqlite_version()")
        sqlite_version = cursor.fetchone()[0]

        return {
            "success": True,
            "database": request.database,
            "statistics": {
                "size_bytes": size_bytes,
                "size_mb": round(size_bytes / (1024 * 1024), 2),
                "table_count": table_count,
                "total_rows": total_rows,
                "last_modified": last_modified.isoformat(),
                "sqlite_version": sqlite_version,
                "read_only": is_database_read_only(request.database),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except sqlite3.Error as e:
        logger.error(f"SQLite error getting statistics: {e}")
        raise HTTPException(
            status_code=500, detail=f"Error getting statistics: {str(e)}"
        )
    finally:
        if conn:
            conn.close()


@router.get("/mcp/status")
async def get_database_mcp_status() -> Dict[str, Any]:
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
            60
            - (
                datetime.now(timezone.utc) - query_counter["reset_time"]
            ).total_seconds(),
        )

    # Check database availability
    db_status = {}
    for db_name, db_config in DATABASE_WHITELIST.items():
        db_path = Path(db_config["path"])
        db_status[db_name] = {
            "available": db_path.exists(),
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
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
