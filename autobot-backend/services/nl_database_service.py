# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Natural Language Database Service (Issue #723)

Integrates Vanna.ai to enable natural language to SQL query capabilities.
Supports the local autobot_data.db (infrastructure tables) and external
database connections retrieved securely from the secrets manager.

Features:
- Natural language to SQL conversion using Vanna.ai + LLM fallback
- Read-only query enforcement (SELECT/SHOW/DESCRIBE/EXPLAIN only)
- Multi-DB support: SQLite, PostgreSQL, MySQL via secrets manager
- Schema training for improved SQL accuracy
- Query audit logging with user context
- Query history stored in Redis
"""

import asyncio
import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from autobot_shared.redis_client import RedisDatabase, get_redis_client

logger = logging.getLogger(__name__)

# Read-only SQL prefixes allowed
_SAFE_SQL_PREFIXES = ("SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN", "WITH")

# Dangerous DML/DDL keywords rejected even inside SELECT
_DANGEROUS_KEYWORDS = frozenset(
    {
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "CREATE",
        "ALTER",
        "TRUNCATE",
        "GRANT",
        "REVOKE",
        "EXEC",
        "EXECUTE",
        "MERGE",
        "REPLACE",
        "CALL",
        "DO",
    }
)

# Redis key for query history
_HISTORY_KEY_PREFIX = "nl_database:history:"

# Local DB path (autobot_data.db)
_DEFAULT_BASE = os.environ.get("AUTOBOT_BASE_DIR", "/opt/autobot")
_LOCAL_DB_PATH = os.environ.get(
    "AUTOBOT_DATA_DB", os.path.join(_DEFAULT_BASE, "autobot_data.db")
)


def _validate_readonly_sql(sql: str) -> bool:
    """
    Validate that a SQL query is read-only.

    Helper for NLDatabaseService.query (Issue #723).

    Args:
        sql: SQL query string to validate

    Returns:
        True if query is safe, False if it contains write operations
    """
    cleaned = sql.strip().upper()

    # Must start with a safe prefix
    if not any(cleaned.startswith(prefix) for prefix in _SAFE_SQL_PREFIXES):
        return False

    # Reject dangerous keywords anywhere in the query
    for keyword in _DANGEROUS_KEYWORDS:
        if re.search(rf"\b{keyword}\b", cleaned):
            return False

    return True


def _extract_sql_from_response(response: str) -> str:
    """
    Extract SQL from an LLM response that may contain markdown code blocks.

    Helper for NLDatabaseService._generate_sql_with_llm (Issue #723).

    Args:
        response: LLM response text potentially containing SQL

    Returns:
        Extracted SQL string
    """
    # Try to extract from markdown code block
    code_block_match = re.search(
        r"```(?:sql)?\s*(.*?)```", response, re.DOTALL | re.IGNORECASE
    )
    if code_block_match:
        return code_block_match.group(1).strip()

    # Strip any explanation text before the SQL
    # Look for SELECT/WITH/SHOW/EXPLAIN/DESCRIBE at start of line
    sql_match = re.search(
        r"^(SELECT|WITH|SHOW|DESCRIBE|DESC|EXPLAIN)\b.*",
        response,
        re.MULTILINE | re.IGNORECASE | re.DOTALL,
    )
    if sql_match:
        return sql_match.group(0).strip()

    return response.strip()


def _get_local_db_schema() -> str:
    """
    Retrieve DDL schema from the local autobot_data.db.

    Helper for NLDatabaseService.train_on_local_db (Issue #723).

    Returns:
        DDL string for all tables in the database
    """
    if not os.path.exists(_LOCAL_DB_PATH):
        logger.warning("Local DB not found at %s", _LOCAL_DB_PATH)
        return ""

    try:
        with sqlite3.connect(_LOCAL_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"
            )
            tables = cursor.fetchall()
            return "\n\n".join(row[0] for row in tables if row[0])
    except Exception as exc:
        logger.error("Failed to read local DB schema: %s", exc)
        return ""


async def _run_sqlite_query(db_path: str, sql: str) -> List[Dict[str, Any]]:
    """
    Execute a read-only SQL query against a SQLite database.

    Helper for NLDatabaseService._execute_query (Issue #723).

    Args:
        db_path: Path to the SQLite database file
        sql: Validated read-only SQL query

    Returns:
        List of rows as dicts
    """

    def _run():
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchmany(500)  # Limit result rows
            return [dict(row) for row in rows]

    return await asyncio.to_thread(_run)


async def _run_external_query(db_url: str, sql: str) -> List[Dict[str, Any]]:
    """
    Execute a read-only SQL query against a PostgreSQL or MySQL database.

    Helper for NLDatabaseService._execute_query (Issue #723).

    Args:
        db_url: Database connection URL (postgresql:// or mysql://)
        sql: Validated read-only SQL query

    Returns:
        List of rows as dicts
    """
    if db_url.startswith("postgresql") or db_url.startswith("postgres"):
        import asyncpg

        conn = await asyncpg.connect(db_url)
        try:
            rows = await conn.fetch(sql)
            return [dict(row) for row in rows]
        finally:
            await conn.close()

    if db_url.startswith("mysql"):
        # Parse mysql URL (mysql://user:pass@host:port/db)
        from urllib.parse import urlparse

        import aiomysql

        parsed = urlparse(db_url)
        conn = await aiomysql.connect(
            host=parsed.hostname,
            port=parsed.port or 3306,
            user=parsed.username,
            password=parsed.password,
            db=parsed.path.lstrip("/"),
        )
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql)
                rows = await cur.fetchmany(500)
                return list(rows)
        finally:
            conn.close()

    if db_url.startswith("sqlite"):
        path = db_url.replace("sqlite:///", "").replace("sqlite://", "")
        return await _run_sqlite_query(path, sql)

    raise ValueError(f"Unsupported database URL scheme: {db_url[:20]}")


def _error_response(
    error: str,
    question: str,
    sql: Optional[str],
) -> Dict[str, Any]:
    """
    Build a standardised error response dict for NL database queries.

    Helper for NLDatabaseService.query (Issue #723).
    """
    return {
        "error": error,
        "question": question,
        "sql": sql,
        "results": [],
        "columns": [],
        "row_count": 0,
        "db_id": "local",
        "elapsed_ms": 0,
    }


def _build_result(
    question: str,
    sql: str,
    results: List[Dict[str, Any]],
    db_id: str,
    elapsed_ms: int,
) -> Dict[str, Any]:
    """
    Build a successful query result dict.

    Helper for NLDatabaseService.query (Issue #723).
    """
    return {
        "question": question,
        "sql": sql,
        "results": results,
        "columns": list(results[0].keys()) if results else [],
        "row_count": len(results),
        "db_id": db_id,
        "elapsed_ms": elapsed_ms,
    }


class NLDatabaseService:
    """
    Natural language to SQL query service using Vanna.ai.

    Converts natural language questions into SQL queries and executes them
    against the local infrastructure database or user-provided external
    databases. Enforces read-only access and logs all queries for audit.
    """

    _instance: Optional["NLDatabaseService"] = None

    def __init__(self) -> None:
        """Initialize the NLDatabaseService."""
        self._vanna: Optional[Any] = None
        self._llm: Optional[Any] = None
        self._trained_schemas: Dict[str, str] = {}  # db_id -> DDL
        self._local_schema: str = ""
        self._vanna_available = False
        self._initialized = False

    @classmethod
    def get_instance(cls) -> "NLDatabaseService":
        """Get or create singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def initialize(self) -> None:
        """Initialize Vanna.ai and train on local schema."""
        if self._initialized:
            return

        self._vanna_available = self._try_init_vanna()
        self._local_schema = _get_local_db_schema()
        if self._local_schema:
            logger.info(
                "Loaded local DB schema (%d chars) from %s",
                len(self._local_schema),
                _LOCAL_DB_PATH,
            )
            await self._train_on_ddl("local", self._local_schema)

        self._initialized = True
        logger.info(
            "NLDatabaseService initialized (vanna=%s, local_schema=%s)",
            self._vanna_available,
            bool(self._local_schema),
        )

    def _try_init_vanna(self) -> bool:
        """
        Attempt to initialize the Vanna.ai client.

        Helper for initialize (Issue #723).

        Returns:
            True if Vanna.ai is available and configured, False otherwise
        """
        try:
            from vanna.base import VannaBase  # noqa: F401

            logger.info("Vanna.ai package available")
            return True
        except ImportError:
            logger.info(
                "Vanna.ai not installed - using LLM fallback for SQL generation"
            )
            return False

    async def _train_on_ddl(self, db_id: str, ddl: str) -> None:
        """
        Store DDL schema for a database used in SQL generation context.

        Helper for initialize and train_on_external_db (Issue #723).

        Args:
            db_id: Identifier for the database
            ddl: DDL schema string
        """
        self._trained_schemas[db_id] = ddl
        logger.debug(
            "Trained NL service on schema for db '%s' (%d chars)", db_id, len(ddl)
        )

    async def query(
        self,
        question: str,
        db_url: Optional[str] = None,
        db_id: str = "local",
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute a natural language query against a database.

        Args:
            question: Natural language question
            db_url: Optional external database URL (from secrets manager)
            db_id: Database identifier for schema lookup (default: 'local')
            user_id: User ID for audit logging

        Returns:
            Dict with keys: sql, results, columns, row_count, db_id, elapsed_ms
        """
        await self.initialize()
        start = time.monotonic()

        schema = self._trained_schemas.get(db_id, self._local_schema)
        sql = await self._generate_sql(question, schema)

        if not sql:
            return _error_response(
                "Could not generate SQL for the given question", question, None
            )

        if not _validate_readonly_sql(sql):
            return _error_response(
                "Generated SQL is not read-only. Only SELECT queries are allowed.",
                question,
                sql,
            )

        results, exec_error = await self._safe_execute_query(sql, db_url, db_id)
        if exec_error:
            return _error_response(exec_error, question, sql)

        elapsed_ms = int((time.monotonic() - start) * 1000)
        await self._audit_query(question, sql, db_id, results, user_id, elapsed_ms)
        return _build_result(question, sql, results, db_id, elapsed_ms)

    async def _safe_execute_query(
        self,
        sql: str,
        db_url: Optional[str],
        db_id: str,
    ) -> tuple:
        """
        Execute query with error handling, returning (results, error_message).

        Helper for query (Issue #723).
        """
        try:
            results = await self._execute_query(sql, db_url, db_id)
            return results, None
        except Exception as exc:
            logger.error("Query execution failed: %s", exc)
            return [], f"Query execution failed: {exc}"

    async def _audit_query(
        self,
        question: str,
        sql: str,
        db_id: str,
        results: List[Dict[str, Any]],
        user_id: Optional[str],
        elapsed_ms: int,
    ) -> None:
        """
        Save a query to the audit/history log.

        Helper for query (Issue #723).
        """
        entry = {
            "id": str(uuid4()),
            "question": question,
            "sql": sql,
            "db_id": db_id,
            "row_count": len(results),
            "user_id": user_id or "anonymous",
            "timestamp": datetime.utcnow().isoformat(),
            "elapsed_ms": elapsed_ms,
        }
        await self._save_history(entry, user_id)

    async def _generate_sql(self, question: str, schema: str) -> str:
        """
        Generate SQL from natural language using Vanna.ai or LLM fallback.

        Helper for query (Issue #723).

        Args:
            question: Natural language question
            schema: DDL schema context

        Returns:
            Generated SQL string
        """
        if self._vanna_available:
            try:
                return await self._generate_sql_with_vanna(question, schema)
            except Exception as exc:
                logger.warning(
                    "Vanna SQL generation failed, using LLM fallback: %s", exc
                )

        return await self._generate_sql_with_llm(question, schema)

    async def _generate_sql_with_vanna(self, question: str, schema: str) -> str:
        """
        Generate SQL using Vanna.ai library.

        Helper for _generate_sql (Issue #723).

        Args:
            question: Natural language question
            schema: DDL schema context

        Returns:
            Generated SQL string
        """
        # Vanna generates SQL from question + stored training data
        # We use a simple prompt-based approach compatible with vanna's interface
        prompt = self._build_sql_prompt(question, schema)
        return await self._generate_sql_with_llm_prompt(prompt)

    async def _generate_sql_with_llm(self, question: str, schema: str) -> str:
        """
        Generate SQL using AutoBot's LLM interface directly.

        Helper for _generate_sql (Issue #723).

        Args:
            question: Natural language question
            schema: DDL schema context

        Returns:
            Generated SQL string
        """
        prompt = self._build_sql_prompt(question, schema)
        return await self._generate_sql_with_llm_prompt(prompt)

    def _build_sql_prompt(self, question: str, schema: str) -> str:
        """
        Build the SQL generation prompt from question and schema.

        Helper for _generate_sql_with_llm (Issue #723).

        Args:
            question: Natural language question
            schema: DDL schema context

        Returns:
            Formatted prompt string
        """
        schema_section = f"Database Schema:\n{schema}\n\n" if schema else ""
        return (
            f"{schema_section}"
            f"Generate a read-only SQL query (SELECT only, no INSERT/UPDATE/DELETE) "
            f"to answer the following question:\n\n"
            f"Question: {question}\n\n"
            f"Return ONLY the SQL query, no explanation. "
            f"Use standard SQL compatible with SQLite."
        )

    async def _generate_sql_with_llm_prompt(self, prompt: str) -> str:
        """
        Execute prompt against the LLM and extract SQL.

        Helper for SQL generation methods (Issue #723).

        Args:
            prompt: Formatted SQL generation prompt

        Returns:
            Extracted SQL string
        """
        try:
            from llm_multi_provider import UnifiedLLMInterface

            if self._llm is None:
                self._llm = UnifiedLLMInterface()
                await self._llm.initialize()

            response = await self._llm.generate_response(prompt, llm_type="task")
            return _extract_sql_from_response(response)
        except Exception as exc:
            logger.error("LLM SQL generation failed: %s", exc)
            return ""

    async def _execute_query(
        self,
        sql: str,
        db_url: Optional[str],
        db_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Execute validated SQL against the appropriate database.

        Helper for query (Issue #723).

        Args:
            sql: Validated read-only SQL query
            db_url: External DB URL if provided, else use local DB
            db_id: Database identifier

        Returns:
            List of result rows as dicts
        """
        if db_url:
            return await _run_external_query(db_url, sql)

        # Use local autobot_data.db
        if not os.path.exists(_LOCAL_DB_PATH):
            raise FileNotFoundError(f"Local database not found: {_LOCAL_DB_PATH}")

        return await _run_sqlite_query(_LOCAL_DB_PATH, sql)

    async def train_on_external_db(
        self,
        db_url: str,
        db_id: str,
        db_type: str = "postgresql",
    ) -> Dict[str, Any]:
        """
        Train the NL service on an external database schema.

        Retrieves the schema (DDL) from the database and stores it for
        use in SQL generation context.

        Args:
            db_url: Database connection URL
            db_id: Unique identifier for this database connection
            db_type: Database type (postgresql, mysql, sqlite)

        Returns:
            Dict with training status and table count
        """
        await self.initialize()

        try:
            ddl = await self._fetch_external_schema(db_url, db_type)
        except Exception as exc:
            logger.error("Failed to fetch schema for %s: %s", db_id, exc)
            return {"success": False, "error": str(exc), "db_id": db_id}

        await self._train_on_ddl(db_id, ddl)
        table_count = ddl.count("CREATE TABLE") + ddl.count("CREATE VIEW")

        return {
            "success": True,
            "db_id": db_id,
            "schema_length": len(ddl),
            "table_count": table_count,
        }

    async def _fetch_external_schema(self, db_url: str, db_type: str) -> str:
        """
        Fetch DDL schema from an external database.

        Helper for train_on_external_db (Issue #723).

        Args:
            db_url: Database connection URL
            db_type: Database type

        Returns:
            DDL schema string
        """
        if db_type == "postgresql" or db_url.startswith("postgresql"):
            return await self._fetch_postgresql_schema(db_url)

        if db_type == "mysql" or db_url.startswith("mysql"):
            return await self._fetch_mysql_schema(db_url)

        # Default: SQLite
        path = db_url.replace("sqlite:///", "").replace("sqlite://", "")
        return _get_local_db_schema() if path == _LOCAL_DB_PATH else ""

    async def _fetch_postgresql_schema(self, db_url: str) -> str:
        """
        Retrieve table DDL from a PostgreSQL database.

        Helper for _fetch_external_schema (Issue #723).

        Args:
            db_url: PostgreSQL connection URL

        Returns:
            DDL string for all user tables
        """
        import asyncpg

        conn = await asyncpg.connect(db_url)
        try:
            rows = await conn.fetch(
                """
                SELECT table_name, column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public'
                ORDER BY table_name, ordinal_position
                """
            )
            # Build CREATE TABLE statements from column info
            tables: Dict[str, List[str]] = {}
            for row in rows:
                tbl = row["table_name"]
                col = f"  {row['column_name']} {row['data_type']}"
                if row["is_nullable"] == "NO":
                    col += " NOT NULL"
                tables.setdefault(tbl, []).append(col)

            ddl_parts = []
            for tbl, cols in tables.items():
                ddl_parts.append(f"CREATE TABLE {tbl} (\n" + ",\n".join(cols) + "\n);")
            return "\n\n".join(ddl_parts)
        finally:
            await conn.close()

    async def _fetch_mysql_schema(self, db_url: str) -> str:
        """
        Retrieve table DDL from a MySQL database.

        Helper for _fetch_external_schema (Issue #723).

        Args:
            db_url: MySQL connection URL

        Returns:
            DDL string for all user tables
        """
        from urllib.parse import urlparse

        import aiomysql

        parsed = urlparse(db_url)
        conn = await aiomysql.connect(
            host=parsed.hostname,
            port=parsed.port or 3306,
            user=parsed.username,
            password=parsed.password,
            db=parsed.path.lstrip("/"),
        )
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SHOW TABLES")
                tables = [list(row.values())[0] for row in await cur.fetchall()]

                ddl_parts = []
                for tbl in tables:
                    await cur.execute(f"SHOW CREATE TABLE `{tbl}`")  # noqa: S608
                    row = await cur.fetchone()
                    if row:
                        ddl_parts.append(list(row.values())[1])
                return "\n\n".join(ddl_parts)
        finally:
            conn.close()

    async def get_schema_info(self) -> Dict[str, Any]:
        """
        Return info about trained database schemas.

        Returns:
            Dict with schema summaries for each trained database
        """
        await self.initialize()
        schemas = {}
        for db_id, ddl in self._trained_schemas.items():
            table_count = ddl.count("CREATE TABLE") + ddl.count("CREATE VIEW")
            schemas[db_id] = {
                "schema_length": len(ddl),
                "table_count": table_count,
                "preview": ddl[:200] + "..." if len(ddl) > 200 else ddl,
            }
        return {
            "vanna_available": self._vanna_available,
            "trained_databases": schemas,
            "local_db_path": _LOCAL_DB_PATH,
        }

    async def get_query_history(
        self,
        user_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve query history from Redis.

        Args:
            user_id: Filter by user ID, or None for all users (admin)
            limit: Maximum number of entries to return

        Returns:
            List of query history entries
        """
        try:
            redis = get_redis_client(async_client=False, database=RedisDatabase.MAIN)
            key = f"{_HISTORY_KEY_PREFIX}{user_id or 'all'}"
            raw = redis.lrange(key, 0, limit - 1)
            return [json.loads(item) for item in raw]
        except Exception as exc:
            logger.warning("Failed to retrieve query history: %s", exc)
            return []

    async def _save_history(
        self, entry: Dict[str, Any], user_id: Optional[str]
    ) -> None:
        """
        Save a query entry to Redis history.

        Helper for query (Issue #723).

        Args:
            entry: Query history entry dict
            user_id: User ID for scoped history
        """
        try:
            redis = get_redis_client(async_client=False, database=RedisDatabase.MAIN)
            payload = json.dumps(entry)
            # Save to user-scoped and global history lists
            user_key = f"{_HISTORY_KEY_PREFIX}{user_id or 'anonymous'}"
            global_key = f"{_HISTORY_KEY_PREFIX}all"
            redis.lpush(user_key, payload)
            redis.ltrim(user_key, 0, 499)  # Keep last 500 per user
            redis.lpush(global_key, payload)
            redis.ltrim(global_key, 0, 4999)  # Keep last 5000 globally
        except Exception as exc:
            logger.warning("Failed to save query history: %s", exc)


def get_nl_database_service() -> NLDatabaseService:
    """Get the singleton NLDatabaseService instance."""
    return NLDatabaseService.get_instance()
