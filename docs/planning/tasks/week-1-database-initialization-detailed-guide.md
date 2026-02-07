# Week 1: Database Initialization - Detailed Implementation Guide

**Status:** Ready for Implementation (Awaiting Agent Session Reset)
**Priority:** CRITICAL (MUST FIX FIRST - Blocks all other fixes)
**Timeline:** 5 days
**Effort:** 22 hours total

---

## Executive Summary

Implement database schema initialization system for `ConversationFileManager` to fix Issue #2 (Database Initialization Missing). Current state: system crashes on fresh deployment with `sqlite3.OperationalError: no such table: conversation_files`.

**Impact:** System cannot start on fresh deployment without manual database setup.

---

## Task 1.1: Schema Initialization Method (4 hours)

**Agent:** database-engineer
**File:** `src/conversation_file_manager.py`

### Implementation

Add the following method to `ConversationFileManager` class:

```python
class ConversationFileManager:
    SCHEMA_VERSION = "1.0.0"

    async def initialize(self):
        """Initialize database schema with version tracking.

        This method is idempotent and safe to call multiple times.
        On first run, creates all required tables from schema file.
        On subsequent runs, skips initialization or applies migrations.
        """
        async with self._lock:
            # Check current schema version
            version = await self._get_schema_version()

            if version is None:
                # First-time initialization
                logger.info("Initializing conversation files database schema")
                await self._apply_schema()
                await self._set_schema_version(self.SCHEMA_VERSION)
                logger.info(f"✅ Database initialized with schema version {self.SCHEMA_VERSION}")

            elif version < self.SCHEMA_VERSION:
                # Migration needed
                logger.info(f"Migrating schema from {version} to {self.SCHEMA_VERSION}")
                await self._apply_migrations(version, self.SCHEMA_VERSION)
                await self._set_schema_version(self.SCHEMA_VERSION)
                logger.info("✅ Schema migration completed")
            else:
                logger.info(f"Database schema is up-to-date (version {version})")

            # Verify schema integrity
            await self._verify_schema_integrity()
            logger.info("✅ Database schema integrity verified")
```

### Verification

- Method added to class
- Proper async/await syntax
- Comprehensive logging at each step
- Idempotent behavior (safe to call multiple times)

---

## Task 1.2: Schema Versioning System (6 hours)

**Agent:** database-engineer
**File:** `src/conversation_file_manager.py`

### Implementation - Method 1: Get Schema Version

```python
async def _get_schema_version(self) -> Optional[str]:
    """Get current schema version from database.

    Returns:
        Current schema version string, or None if not initialized
    """
    def _query_version():
        connection = self._get_db_connection()
        cursor = connection.cursor()

        # Create version table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version TEXT PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.commit()

        # Query current version
        cursor.execute(
            "SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1"
        )
        result = cursor.fetchone()

        connection.close()
        return result[0] if result else None

    return await asyncio.to_thread(_query_version)
```

### Implementation - Method 2: Set Schema Version

```python
async def _set_schema_version(self, version: str):
    """Record schema version in database.

    Args:
        version: Schema version string (e.g., "1.0.0")
    """
    def _set_version():
        connection = self._get_db_connection()
        cursor = connection.cursor()

        cursor.execute(
            "INSERT INTO schema_version (version) VALUES (?)",
            (version,)
        )
        connection.commit()
        connection.close()

    await asyncio.to_thread(_set_version)
    logger.info(f"Schema version set to {version}")
```

### Implementation - Method 3: Apply Schema

```python
async def _apply_schema(self):
    """Apply database schema from SQL file.

    Loads schema from database/schemas/conversation_files_schema.sql
    and executes all CREATE TABLE statements.
    """
    import aiofiles

    schema_path = Path(__file__).parent.parent / "database/schemas/conversation_files_schema.sql"

    if not schema_path.exists():
        raise RuntimeError(f"Schema file not found: {schema_path}")

    # Read schema file
    async with aiofiles.open(schema_path, 'r', encoding='utf-8') as f:
        schema_sql = await f.read()

    # Execute schema in thread pool (SQLite blocks)
    def _execute_schema():
        connection = self._get_db_connection()
        connection.executescript(schema_sql)
        connection.commit()
        connection.close()

    await asyncio.to_thread(_execute_schema)
    logger.info("Database schema applied successfully")
```

### Implementation - Method 4: Apply Migrations

```python
async def _apply_migrations(self, from_version: str, to_version: str):
    """Apply database migrations from one version to another.

    Args:
        from_version: Current schema version
        to_version: Target schema version

    This is a framework for future migrations.
    Currently no migrations exist (only version 1.0.0).
    """
    # Migration framework for future use
    # Example: if from_version == "1.0.0" and to_version >= "1.1.0":
    #     await self._apply_migration_1_0_to_1_1()

    logger.info(f"No migrations needed from {from_version} to {to_version}")
```

### Implementation - Method 5: Verify Schema Integrity

```python
async def _verify_schema_integrity(self):
    """Verify all required tables exist in database.

    Raises:
        RuntimeError: If any required table is missing
    """
    required_tables = [
        'conversation_files',
        'file_metadata',
        'session_file_associations',
        'file_access_log',
        'file_cleanup_queue'
    ]

    def _verify():
        connection = self._get_db_connection()
        cursor = connection.cursor()

        missing_tables = []
        for table in required_tables:
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,)
            )
            if not cursor.fetchone():
                missing_tables.append(table)

        connection.close()

        if missing_tables:
            raise RuntimeError(
                f"Required tables missing: {', '.join(missing_tables)}"
            )

    await asyncio.to_thread(_verify)
```

### Required Imports

Add to top of `src/conversation_file_manager.py`:

```python
import asyncio
import aiofiles
from pathlib import Path
from typing import Optional
```

### Verification

- All 5 methods implemented
- Proper async/await with `asyncio.to_thread()` for blocking operations
- Comprehensive error handling
- Clear logging messages
- Type hints for all methods

---

## Task 1.3: Schema Integrity Verification Integration (3 hours)

**Agent:** database-engineer
**File:** `autobot-user-backend/api/system.py` or create new health check endpoint

### Implementation - Health Check Endpoint

```python
from fastapi import APIRouter, Depends
from typing import Dict, Any

router = APIRouter(prefix="/api", tags=["system"])

@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Comprehensive health check endpoint.

    Returns:
        Health status for all system components
    """
    from backend.app_factory import app

    checks = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            "database": {
                "conversation_files": "unknown",
                "schema_version": None
            },
            "redis": "unknown",
            "backend": "running"
        }
    }

    # Check conversation files database
    try:
        if hasattr(app.state, 'conversation_file_manager'):
            manager = app.state.conversation_file_manager

            # Get schema version
            version = await manager._get_schema_version()

            if version:
                # Verify integrity
                await manager._verify_schema_integrity()
                checks["components"]["database"]["conversation_files"] = "healthy"
                checks["components"]["database"]["schema_version"] = version
            else:
                checks["components"]["database"]["conversation_files"] = "not_initialized"
                checks["status"] = "degraded"
        else:
            checks["components"]["database"]["conversation_files"] = "not_configured"
            checks["status"] = "degraded"

    except Exception as e:
        checks["components"]["database"]["conversation_files"] = f"error: {str(e)}"
        checks["status"] = "unhealthy"

    return checks
```

### Verification

- Health check endpoint returns database status
- Reports schema version
- Detects missing tables
- Returns proper HTTP status codes

---

## Task 1.4: Backend Startup Integration (2 hours)

**Agent:** senior-backend-engineer
**File:** `backend/app_factory.py`

### Implementation - Startup Event Handler

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
import logging

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager - handles startup and shutdown."""

    # STARTUP
    logger.info("=== Backend Startup - Database Initialization ===")

    try:
        # Initialize conversation file manager database
        if hasattr(app.state, 'conversation_file_manager'):
            logger.info("Initializing conversation files database...")
            await app.state.conversation_file_manager.initialize()
            logger.info("✅ Conversation files database initialized")
        else:
            logger.error("❌ ConversationFileManager not found in app state")
            raise RuntimeError("ConversationFileManager not configured")

        logger.info("=== Backend Startup Complete ===")

    except Exception as e:
        logger.error(f"❌ CRITICAL: Database initialization failed: {e}")
        logger.error("Backend startup aborted - fix database issues before proceeding")
        raise RuntimeError(f"Database initialization failed: {e}")

    # Application is running
    yield

    # SHUTDOWN
    logger.info("=== Backend Shutdown ===")
    # Cleanup tasks here if needed

# Use lifespan in FastAPI app
app = FastAPI(lifespan=lifespan)
```

### Alternative: On Event Decorator (if lifespan not used)

```python
@app.on_event("startup")
async def startup_event():
    """Application startup event handler."""
    logger.info("=== Application Startup ===")

    # Initialize conversation file manager database
    try:
        if hasattr(app.state, 'conversation_file_manager'):
            logger.info("Initializing conversation files database...")
            await app.state.conversation_file_manager.initialize()
            logger.info("✅ Conversation files database initialized")
        else:
            logger.warning("ConversationFileManager not found in app state")
    except Exception as e:
        logger.error(f"❌ Failed to initialize conversation files database: {e}")
        # CRITICAL: Do not start if database initialization fails
        raise RuntimeError(f"Database initialization failed: {e}")

    logger.info("=== Application Startup Complete ===")
```

### Verification

- Initialization called during startup
- Startup logs show initialization progress
- Backend refuses to start if initialization fails
- Clear error messages for debugging

---

## Task 1.5: Unit Tests (4 hours)

**Agent:** testing-engineer
**File:** `tests/unit/test_conversation_file_manager.py`

### Implementation

Create comprehensive test file (see planning document for full code).

### Test Cases Required

1. `test_first_time_initialization` - Fresh database creation
2. `test_idempotent_initialization` - Multiple calls safe
3. `test_schema_version_tracking` - Version recorded correctly
4. `test_integrity_verification_passes` - Complete schema passes
5. `test_integrity_verification_fails_missing_table` - Detects missing tables
6. `test_schema_migration_framework` - Migration system works

### Run Tests

```bash
# Create tests directory if needed
mkdir -p tests/unit

# Run unit tests
pytest tests/unit/test_conversation_file_manager.py -v

# Run with coverage
pytest tests/unit/test_conversation_file_manager.py --cov=src.conversation_file_manager --cov-report=html
```

### Coverage Target

- **Minimum:** 80% code coverage
- **Target:** 100% for initialization code (critical infrastructure)

---

## Task 1.6: Distributed Integration Testing (3 hours)

**Agent:** testing-engineer
**File:** `tests/distributed/test_db_initialization.py`

### Implementation

Create distributed test file (see planning document for full code).

### Test Scenarios

1. Fresh VM0 deployment creates schema
2. NPU Worker (VM2) file upload works
3. Browser (VM5) screenshot save works
4. Frontend (VM1) file upload succeeds
5. Concurrent initialization from multiple VMs is safe

### Run Tests

```bash
# Create tests directory if needed
mkdir -p tests/distributed

# Run integration tests
pytest tests/distributed/test_db_initialization.py -v -m integration
```

---

## Deployment Strategy

### Phase 1: Development Testing (Days 1-3)

1. Implement all changes locally
2. Test with temporary database
3. Verify initialization in development environment
4. Code review by code-reviewer agent

### Phase 2: Staging Deployment (Day 4)

1. Deploy to staging environment
2. Test fresh deployment scenario
3. Test existing deployment scenario
4. Run full test suite
5. Verify health check reports correct status

### Phase 3: Production Deployment (Day 5)

1. Schedule deployment during maintenance window
2. Backup existing database (if any)
3. Deploy new backend version
4. Monitor initialization logs
5. Verify health check endpoint
6. Verify all 6 VMs can access database
7. Rollback plan: restore previous backend version

---

## Success Criteria

- ✅ Fresh deployment succeeds without manual DB setup
- ✅ All 5 tables created automatically:
  - conversation_files
  - file_metadata
  - session_file_associations
  - file_access_log
  - file_cleanup_queue
- ✅ Schema version tracked correctly
- ✅ Health check reports DB status
- ✅ Zero deployment failures
- ✅ 100% test coverage for initialization code
- ✅ All 6 VMs can perform file operations

---

## Files Modified Summary

1. `src/conversation_file_manager.py` - Database initialization methods
2. `backend/app_factory.py` - Startup integration
3. `autobot-user-backend/api/system.py` - Health check endpoint
4. `tests/unit/test_conversation_file_manager.py` - Unit tests (NEW)
5. `tests/distributed/test_db_initialization.py` - Integration tests (NEW)

---

## Agent Assignments

1. **database-engineer**: Tasks 1.1, 1.2, 1.3 (13 hours)
2. **senior-backend-engineer**: Task 1.4 (2 hours)
3. **testing-engineer**: Tasks 1.5, 1.6 (7 hours)

**Total Effort:** 22 hours
**Parallel Execution:** Tasks 1.1-1.3 can partially overlap with 1.4

---

## Next Steps After Week 1 Completion

1. Mark Week 1 tasks as completed in Memory MCP
2. Update TODO list
3. Begin Week 2: Async Operations (depends on working database)
4. Continue with 5-week implementation plan

---

**Status:** Ready for agent execution when session limit resets
**Last Updated:** 2025-10-05
**Stored in Memory MCP:** Yes (entity created)
