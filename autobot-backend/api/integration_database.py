# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Database Integration API (Issue #61)

Provides REST endpoints for managing database integrations with PostgreSQL,
MySQL, and MongoDB. Supports connection testing, listing databases/tables,
and executing read-only queries.
"""

import logging
from typing import Any, Dict, List, Optional

from backend.integrations.base import IntegrationConfig
from backend.integrations.database_integration import (
    MongoDBIntegration,
    MySQLIntegration,
    PostgreSQLIntegration,
)
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["integrations-database"])


class DatabaseConnectionRequest(BaseModel):
    """Request model for testing database connections."""

    provider: str = Field(
        ..., description="Database provider (postgresql/mysql/mongodb)"
    )
    host: str = Field("localhost", description="Database host")
    port: Optional[int] = Field(
        None, description="Database port (default: provider-specific)"
    )
    username: Optional[str] = Field(None, description="Database username")
    password: Optional[str] = Field(None, description="Database password")
    database: str = Field("", description="Database name")


class QueryRequest(BaseModel):
    """Request model for executing database queries."""

    query: str = Field(..., description="SQL query to execute (read-only)")
    database: str = Field("", description="Target database name")
    host: str = Field("localhost", description="Database host")
    port: Optional[int] = Field(None, description="Database port")
    username: Optional[str] = Field(None, description="Database username")
    password: Optional[str] = Field(None, description="Database password")


class MongoQueryRequest(BaseModel):
    """Request model for MongoDB collection queries."""

    database: str = Field(..., description="Database name")
    collection: str = Field(..., description="Collection name")
    filter: Dict[str, Any] = Field(default_factory=dict, description="Query filter")
    limit: int = Field(100, description="Maximum results to return")
    host: str = Field("localhost", description="MongoDB host")
    port: int = Field(27017, description="MongoDB port")
    username: Optional[str] = Field(None, description="MongoDB username")
    password: Optional[str] = Field(None, description="MongoDB password")


class DatabaseListRequest(BaseModel):
    """Request model for listing databases/tables."""

    host: str = Field("localhost", description="Database host")
    port: Optional[int] = Field(None, description="Database port")
    username: Optional[str] = Field(None, description="Database username")
    password: Optional[str] = Field(None, description="Database password")
    database: Optional[str] = Field(
        None, description="Database name (for table listing)"
    )


def _create_integration_config(
    provider: str,
    host: str,
    port: Optional[int],
    username: Optional[str],
    password: Optional[str],
    database: str,
) -> IntegrationConfig:
    """
    Create IntegrationConfig from request parameters.

    Helper for endpoint handlers (Issue #61).

    Args:
        provider: Database provider identifier
        host: Database host
        port: Database port (uses default if None)
        username: Database username
        password: Database password
        database: Database name

    Returns:
        Configured IntegrationConfig instance
    """
    # Set default ports if not provided
    if port is None:
        if provider == "postgresql":
            port = 5432
        elif provider == "mysql":
            port = 3306
        elif provider == "mongodb":
            port = 27017

    return IntegrationConfig(
        name=f"{provider}-integration",
        provider=provider,
        username=username,
        password=password,
        extra={
            "host": host,
            "port": port,
            "database": database or "",
        },
    )


def _get_integration_class(provider: str):
    """
    Get integration class for a database provider.

    Helper for endpoint handlers (Issue #61).

    Args:
        provider: Database provider (postgresql/mysql/mongodb)

    Returns:
        Integration class

    Raises:
        HTTPException: If provider is not supported
    """
    providers = {
        "postgresql": PostgreSQLIntegration,
        "mysql": MySQLIntegration,
        "mongodb": MongoDBIntegration,
    }

    integration_class = providers.get(provider.lower())
    if not integration_class:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported provider: {provider}. "
            f"Supported: {list(providers.keys())}",
        )

    return integration_class


@router.post("/test-connection")
async def test_database_connection(request: DatabaseConnectionRequest):
    """
    Test connection to a database.

    Args:
        request: Connection parameters

    Returns:
        Connection health status

    Raises:
        HTTPException: On validation or connection errors
    """
    try:
        config = _create_integration_config(
            provider=request.provider,
            host=request.host,
            port=request.port,
            username=request.username,
            password=request.password,
            database=request.database,
        )

        integration_class = _get_integration_class(request.provider)
        integration = integration_class(config)

        health = await integration.test_connection()
        return health.dict()

    except Exception as exc:
        logger.error("Database connection test failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/providers")
async def list_database_providers() -> Dict[str, List[Dict[str, Any]]]:
    """
    List all supported database providers.

    Returns:
        Dictionary with providers list and their details
    """
    providers = [
        {
            "id": "postgresql",
            "name": "PostgreSQL",
            "default_port": 5432,
            "description": "PostgreSQL relational database",
        },
        {
            "id": "mysql",
            "name": "MySQL",
            "default_port": 3306,
            "description": "MySQL relational database",
        },
        {
            "id": "mongodb",
            "name": "MongoDB",
            "default_port": 27017,
            "description": "MongoDB document database",
        },
    ]

    return {"providers": providers, "count": len(providers)}


@router.post("/{provider}/query")
async def execute_database_query(provider: str, request: QueryRequest):
    """
    Execute a read-only query on a database.

    Args:
        provider: Database provider (postgresql/mysql)
        request: Query parameters

    Returns:
        Query results

    Raises:
        HTTPException: On validation, permission, or execution errors
    """
    if provider.lower() == "mongodb":
        raise HTTPException(
            status_code=400,
            detail="Use /mongodb/query-collection endpoint for MongoDB queries",
        )

    try:
        config = _create_integration_config(
            provider=provider,
            host=request.host,
            port=request.port,
            username=request.username,
            password=request.password,
            database=request.database,
        )

        integration_class = _get_integration_class(provider)
        integration = integration_class(config)

        result = await integration.execute_action(
            "execute_query", {"query": request.query, "database": request.database}
        )

        return result

    except ValueError as exc:
        logger.warning("Query validation failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Query execution failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/mongodb/query-collection")
async def query_mongodb_collection(request: MongoQueryRequest):
    """
    Query a MongoDB collection.

    Args:
        request: MongoDB query parameters

    Returns:
        Query results

    Raises:
        HTTPException: On connection or query errors
    """
    try:
        config = _create_integration_config(
            provider="mongodb",
            host=request.host,
            port=request.port,
            username=request.username,
            password=request.password,
            database=request.database,
        )

        integration = MongoDBIntegration(config)

        result = await integration.execute_action(
            "query_collection",
            {
                "database": request.database,
                "collection": request.collection,
                "filter": request.filter,
                "limit": request.limit,
            },
        )

        return result

    except Exception as exc:
        logger.error("MongoDB query failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{provider}/databases")
async def list_databases(provider: str, request: DatabaseListRequest):
    """
    List all databases for a provider.

    Args:
        provider: Database provider (postgresql/mysql/mongodb)
        request: Connection parameters

    Returns:
        List of database names

    Raises:
        HTTPException: On connection or listing errors
    """
    try:
        config = _create_integration_config(
            provider=provider,
            host=request.host,
            port=request.port,
            username=request.username,
            password=request.password,
            database=request.database or "",
        )

        integration_class = _get_integration_class(provider)
        integration = integration_class(config)

        result = await integration.execute_action("list_databases", {})
        return result

    except Exception as exc:
        logger.error("Failed to list databases: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{provider}/tables")
async def list_tables(provider: str, request: DatabaseListRequest):
    """
    List all tables/collections in a database.

    Args:
        provider: Database provider (postgresql/mysql/mongodb)
        request: Connection parameters with database name

    Returns:
        List of table/collection names

    Raises:
        HTTPException: On connection or listing errors
    """
    if not request.database:
        raise HTTPException(status_code=400, detail="Database name is required")

    try:
        config = _create_integration_config(
            provider=provider,
            host=request.host,
            port=request.port,
            username=request.username,
            password=request.password,
            database=request.database,
        )

        integration_class = _get_integration_class(provider)
        integration = integration_class(config)

        # MongoDB uses collections instead of tables
        if provider.lower() == "mongodb":
            result = await integration.execute_action(
                "list_collections", {"database": request.database}
            )
        else:
            result = await integration.execute_action(
                "list_tables", {"database": request.database}
            )

        return result

    except Exception as exc:
        logger.error("Failed to list tables: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
