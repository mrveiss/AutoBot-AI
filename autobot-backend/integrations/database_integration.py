# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Database Management Integration (Issue #61)

Provides integration classes for PostgreSQL, MySQL, and MongoDB database
management. Supports connection testing, listing databases/tables/collections,
and executing read-only queries.
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List

from integrations.base import (
    BaseIntegration,
    IntegrationAction,
    IntegrationHealth,
    IntegrationStatus,
)

logger = logging.getLogger(__name__)


def _validate_readonly_query(query: str) -> bool:
    """
    Validate that a SQL query is read-only.

    Helper for execute_query validation (Issue #61).

    Args:
        query: SQL query string to validate

    Returns:
        True if query is safe (SELECT/SHOW/DESCRIBE/EXPLAIN), False otherwise
    """
    query_upper = query.strip().upper()
    safe_prefixes = ("SELECT", "SHOW", "DESCRIBE", "DESC", "EXPLAIN")

    # Must start with safe prefix
    if not any(query_upper.startswith(prefix) for prefix in safe_prefixes):
        return False

    # Reject dangerous keywords anywhere in query
    dangerous = (
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
    )
    for keyword in dangerous:
        if re.search(rf"\b{keyword}\b", query_upper):
            return False

    return True


class PostgreSQLIntegration(BaseIntegration):
    """PostgreSQL database integration using asyncpg."""

    async def test_connection(self) -> IntegrationHealth:
        """Test PostgreSQL connection and return health status."""
        start_time = datetime.utcnow()
        try:
            import asyncpg

            host = self.config.extra.get("host", "localhost")
            port = self.config.extra.get("port", 5432)
            database = self.config.extra.get("database", "postgres")

            conn = await asyncpg.connect(
                host=host,
                port=port,
                user=self.config.username,
                password=self.config.password,
                database=database,
                timeout=10.0,
            )

            version = await conn.fetchval("SELECT version()")
            await conn.close()

            elapsed = (datetime.utcnow() - start_time).total_seconds() * 1000
            self._status = IntegrationStatus.CONNECTED

            return IntegrationHealth(
                provider=self.provider,
                status=IntegrationStatus.CONNECTED,
                latency_ms=elapsed,
                message="Connected successfully",
                details={"version": version, "database": database},
            )

        except Exception as exc:
            elapsed = (datetime.utcnow() - start_time).total_seconds() * 1000
            self._status = IntegrationStatus.ERROR
            self.logger.error("PostgreSQL connection failed: %s", exc)

            return IntegrationHealth(
                provider=self.provider,
                status=IntegrationStatus.ERROR,
                latency_ms=elapsed,
                message=f"Connection failed: {str(exc)}",
            )

    def get_available_actions(self) -> List[IntegrationAction]:
        """Return list of available PostgreSQL actions."""
        return [
            IntegrationAction(
                name="list_databases",
                description="List all databases",
                method="GET",
                parameters={},
            ),
            IntegrationAction(
                name="list_tables",
                description="List tables in a database",
                method="GET",
                parameters={"database": "Database name"},
            ),
            IntegrationAction(
                name="execute_query",
                description="Execute a read-only SQL query",
                method="POST",
                parameters={"query": "SQL SELECT query", "database": "Database name"},
            ),
        ]

    async def execute_action(
        self, action: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a PostgreSQL action."""
        if action == "list_databases":
            return await self._list_databases()
        elif action == "list_tables":
            database = params.get("database", "postgres")
            return await self._list_tables(database)
        elif action == "execute_query":
            query = params.get("query", "")
            database = params.get("database", "postgres")
            return await self._execute_query(query, database)
        else:
            raise ValueError(f"Unknown action: {action}")

    async def _list_databases(self) -> Dict[str, Any]:
        """List all databases in PostgreSQL."""
        import asyncpg

        host = self.config.extra.get("host", "localhost")
        port = self.config.extra.get("port", 5432)

        conn = await asyncpg.connect(
            host=host,
            port=port,
            user=self.config.username,
            password=self.config.password,
            database="postgres",
            timeout=10.0,
        )

        rows = await conn.fetch(
            "SELECT datname FROM pg_database WHERE datistemplate = false"
        )
        await conn.close()

        databases = [row["datname"] for row in rows]
        return {"databases": databases, "count": len(databases)}

    async def _list_tables(self, database: str) -> Dict[str, Any]:
        """List tables in a PostgreSQL database."""
        import asyncpg

        host = self.config.extra.get("host", "localhost")
        port = self.config.extra.get("port", 5432)

        conn = await asyncpg.connect(
            host=host,
            port=port,
            user=self.config.username,
            password=self.config.password,
            database=database,
            timeout=10.0,
        )

        rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
        await conn.close()

        tables = [row["tablename"] for row in rows]
        return {"tables": tables, "count": len(tables), "database": database}

    async def _execute_query(self, query: str, database: str) -> Dict[str, Any]:
        """Execute a read-only query in PostgreSQL."""
        if not _validate_readonly_query(query):
            raise ValueError("Only SELECT queries are allowed")

        import asyncpg

        host = self.config.extra.get("host", "localhost")
        port = self.config.extra.get("port", 5432)

        conn = await asyncpg.connect(
            host=host,
            port=port,
            user=self.config.username,
            password=self.config.password,
            database=database,
            timeout=30.0,
        )

        rows = await conn.fetch(query)
        await conn.close()

        results = [dict(row) for row in rows]
        return {"results": results, "count": len(results), "database": database}


class MySQLIntegration(BaseIntegration):
    """MySQL database integration using aiomysql."""

    async def test_connection(self) -> IntegrationHealth:
        """Test MySQL connection and return health status."""
        start_time = datetime.utcnow()
        try:
            import aiomysql

            host = self.config.extra.get("host", "localhost")
            port = self.config.extra.get("port", 3306)
            database = self.config.extra.get("database", "mysql")

            conn = await aiomysql.connect(
                host=host,
                port=port,
                user=self.config.username,
                password=self.config.password,
                db=database,
                connect_timeout=10,
            )

            async with conn.cursor() as cursor:
                await cursor.execute("SELECT VERSION()")
                result = await cursor.fetchone()
                version = result[0] if result else "unknown"

            conn.close()

            elapsed = (datetime.utcnow() - start_time).total_seconds() * 1000
            self._status = IntegrationStatus.CONNECTED

            return IntegrationHealth(
                provider=self.provider,
                status=IntegrationStatus.CONNECTED,
                latency_ms=elapsed,
                message="Connected successfully",
                details={"version": version, "database": database},
            )

        except Exception as exc:
            elapsed = (datetime.utcnow() - start_time).total_seconds() * 1000
            self._status = IntegrationStatus.ERROR
            self.logger.error("MySQL connection failed: %s", exc)

            return IntegrationHealth(
                provider=self.provider,
                status=IntegrationStatus.ERROR,
                latency_ms=elapsed,
                message=f"Connection failed: {str(exc)}",
            )

    def get_available_actions(self) -> List[IntegrationAction]:
        """Return list of available MySQL actions."""
        return [
            IntegrationAction(
                name="list_databases",
                description="List all databases",
                method="GET",
                parameters={},
            ),
            IntegrationAction(
                name="list_tables",
                description="List tables in a database",
                method="GET",
                parameters={"database": "Database name"},
            ),
            IntegrationAction(
                name="execute_query",
                description="Execute a read-only SQL query",
                method="POST",
                parameters={"query": "SQL SELECT query", "database": "Database name"},
            ),
        ]

    async def execute_action(
        self, action: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a MySQL action."""
        if action == "list_databases":
            return await self._list_databases()
        elif action == "list_tables":
            database = params.get("database", "mysql")
            return await self._list_tables(database)
        elif action == "execute_query":
            query = params.get("query", "")
            database = params.get("database", "mysql")
            return await self._execute_query(query, database)
        else:
            raise ValueError(f"Unknown action: {action}")

    async def _list_databases(self) -> Dict[str, Any]:
        """List all databases in MySQL."""
        import aiomysql

        host = self.config.extra.get("host", "localhost")
        port = self.config.extra.get("port", 3306)

        conn = await aiomysql.connect(
            host=host,
            port=port,
            user=self.config.username,
            password=self.config.password,
            connect_timeout=10,
        )

        async with conn.cursor() as cursor:
            await cursor.execute("SHOW DATABASES")
            rows = await cursor.fetchall()

        conn.close()

        databases = [row[0] for row in rows]
        return {"databases": databases, "count": len(databases)}

    async def _list_tables(self, database: str) -> Dict[str, Any]:
        """List tables in a MySQL database."""
        import aiomysql

        host = self.config.extra.get("host", "localhost")
        port = self.config.extra.get("port", 3306)

        conn = await aiomysql.connect(
            host=host,
            port=port,
            user=self.config.username,
            password=self.config.password,
            db=database,
            connect_timeout=10,
        )

        async with conn.cursor() as cursor:
            await cursor.execute("SHOW TABLES")
            rows = await cursor.fetchall()

        conn.close()

        tables = [row[0] for row in rows]
        return {"tables": tables, "count": len(tables), "database": database}

    async def _execute_query(self, query: str, database: str) -> Dict[str, Any]:
        """Execute a read-only query in MySQL."""
        if not _validate_readonly_query(query):
            raise ValueError("Only SELECT queries are allowed")

        import aiomysql

        host = self.config.extra.get("host", "localhost")
        port = self.config.extra.get("port", 3306)

        conn = await aiomysql.connect(
            host=host,
            port=port,
            user=self.config.username,
            password=self.config.password,
            db=database,
            connect_timeout=30,
        )

        async with conn.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(query)
            rows = await cursor.fetchall()

        conn.close()

        return {"results": rows, "count": len(rows), "database": database}


class MongoDBIntegration(BaseIntegration):
    """MongoDB database integration using motor."""

    async def test_connection(self) -> IntegrationHealth:
        """Test MongoDB connection and return health status."""
        start_time = datetime.utcnow()
        try:
            from motor.motor_asyncio import AsyncIOMotorClient

            host = self.config.extra.get("host", "localhost")
            port = self.config.extra.get("port", 27017)
            database = self.config.extra.get("database", "admin")

            # Build connection string
            if self.config.username and self.config.password:
                conn_str = (
                    f"mongodb://{self.config.username}:"
                    f"{self.config.password}@{host}:{port}/{database}"
                )
            else:
                conn_str = f"mongodb://{host}:{port}/{database}"

            client = AsyncIOMotorClient(conn_str, serverSelectionTimeoutMS=10000)

            # Test connection
            server_info = await client.server_info()
            version = server_info.get("version", "unknown")

            client.close()

            elapsed = (datetime.utcnow() - start_time).total_seconds() * 1000
            self._status = IntegrationStatus.CONNECTED

            return IntegrationHealth(
                provider=self.provider,
                status=IntegrationStatus.CONNECTED,
                latency_ms=elapsed,
                message="Connected successfully",
                details={"version": version, "database": database},
            )

        except Exception as exc:
            elapsed = (datetime.utcnow() - start_time).total_seconds() * 1000
            self._status = IntegrationStatus.ERROR
            self.logger.error("MongoDB connection failed: %s", exc)

            return IntegrationHealth(
                provider=self.provider,
                status=IntegrationStatus.ERROR,
                latency_ms=elapsed,
                message=f"Connection failed: {str(exc)}",
            )

    def get_available_actions(self) -> List[IntegrationAction]:
        """Return list of available MongoDB actions."""
        return [
            IntegrationAction(
                name="list_databases",
                description="List all databases",
                method="GET",
                parameters={},
            ),
            IntegrationAction(
                name="list_collections",
                description="List collections in a database",
                method="GET",
                parameters={"database": "Database name"},
            ),
            IntegrationAction(
                name="query_collection",
                description="Query a collection",
                method="POST",
                parameters={
                    "database": "Database name",
                    "collection": "Collection name",
                    "filter": "Query filter (JSON)",
                    "limit": "Max results (default 100)",
                },
            ),
        ]

    async def execute_action(
        self, action: str, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a MongoDB action."""
        if action == "list_databases":
            return await self._list_databases()
        elif action == "list_collections":
            database = params.get("database", "admin")
            return await self._list_collections(database)
        elif action == "query_collection":
            database = params.get("database", "")
            collection = params.get("collection", "")
            filter_dict = params.get("filter", {})
            limit = params.get("limit", 100)
            return await self._query_collection(
                database, collection, filter_dict, limit
            )
        else:
            raise ValueError(f"Unknown action: {action}")

    async def _list_databases(self) -> Dict[str, Any]:
        """List all databases in MongoDB."""
        from motor.motor_asyncio import AsyncIOMotorClient

        host = self.config.extra.get("host", "localhost")
        port = self.config.extra.get("port", 27017)

        if self.config.username and self.config.password:
            conn_str = (
                f"mongodb://{self.config.username}:"
                f"{self.config.password}@{host}:{port}/admin"
            )
        else:
            conn_str = f"mongodb://{host}:{port}/admin"

        client = AsyncIOMotorClient(conn_str, serverSelectionTimeoutMS=10000)

        db_list = await client.list_database_names()
        client.close()

        return {"databases": db_list, "count": len(db_list)}

    async def _list_collections(self, database: str) -> Dict[str, Any]:
        """List collections in a MongoDB database."""
        from motor.motor_asyncio import AsyncIOMotorClient

        host = self.config.extra.get("host", "localhost")
        port = self.config.extra.get("port", 27017)

        if self.config.username and self.config.password:
            conn_str = (
                f"mongodb://{self.config.username}:"
                f"{self.config.password}@{host}:{port}/{database}"
            )
        else:
            conn_str = f"mongodb://{host}:{port}/{database}"

        client = AsyncIOMotorClient(conn_str, serverSelectionTimeoutMS=10000)
        db = client[database]

        collections = await db.list_collection_names()
        client.close()

        return {
            "collections": collections,
            "count": len(collections),
            "database": database,
        }

    async def _query_collection(
        self, database: str, collection: str, filter_dict: Dict, limit: int
    ) -> Dict[str, Any]:
        """Query a MongoDB collection."""
        from motor.motor_asyncio import AsyncIOMotorClient

        host = self.config.extra.get("host", "localhost")
        port = self.config.extra.get("port", 27017)

        if self.config.username and self.config.password:
            conn_str = (
                f"mongodb://{self.config.username}:"
                f"{self.config.password}@{host}:{port}/{database}"
            )
        else:
            conn_str = f"mongodb://{host}:{port}/{database}"

        client = AsyncIOMotorClient(conn_str, serverSelectionTimeoutMS=10000)
        db = client[database]
        coll = db[collection]

        cursor = coll.find(filter_dict).limit(limit)
        documents = await cursor.to_list(length=limit)
        client.close()

        # Convert ObjectId to string for JSON serialization
        for doc in documents:
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])

        return {
            "results": documents,
            "count": len(documents),
            "database": database,
            "collection": collection,
        }
