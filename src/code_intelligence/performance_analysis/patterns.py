# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Performance Pattern Detection Constants

Issue #381: Extracted from performance_analyzer.py god class refactoring.
Contains pattern dictionaries for blocking I/O, database operations, and HTTP operations.
"""

from typing import FrozenSet

# Issue #380: Module-level frozenset for legacy DB operation fallback
LEGACY_DB_OPERATIONS: FrozenSet[str] = frozenset(
    {"execute", "executemany", "fetchone", "fetchall", "fetchmany"}
)

# Issue #380: Module-level frozenset for DB context object names
DB_OBJECTS: FrozenSet[str] = frozenset(
    {
        "cursor",
        "conn",
        "connection",
        "session",
        "db",
        "redis_client",
        "pipe",
        "pipeline",
        "collection",
    }
)


# Issue #385: Context-aware blocking I/O detection with confidence scoring
# HIGH confidence (0.9+): Exact module.method matches - definitely blocking
# MEDIUM confidence (0.6-0.8): Likely blocking based on pattern
# LOW confidence (0.3-0.5): Potential match - flag as needs_review
#
# Structure: { pattern: (recommendation, confidence, is_exact_match) }
# is_exact_match=True means the call_name must equal the pattern exactly
# is_exact_match=False means substring matching (with context checks)

BLOCKING_IO_PATTERNS_HIGH_CONFIDENCE = {
    # HTTP - These are definitely blocking when from requests/urllib
    "requests.get": ("Use httpx.AsyncClient() or aiohttp", 0.95, True),
    "requests.post": ("Use httpx.AsyncClient() or aiohttp", 0.95, True),
    "requests.put": ("Use httpx.AsyncClient() or aiohttp", 0.95, True),
    "requests.delete": ("Use httpx.AsyncClient() or aiohttp", 0.95, True),
    "requests.patch": ("Use httpx.AsyncClient() or aiohttp", 0.95, True),
    "requests.head": ("Use httpx.AsyncClient() or aiohttp", 0.95, True),
    "requests.request": ("Use httpx.AsyncClient() or aiohttp", 0.95, True),
    "urllib.request.urlopen": ("Use aiohttp for async HTTP", 0.95, True),
    "urllib.urlopen": ("Use aiohttp for async HTTP", 0.95, True),
    # Sleep - definitely blocking
    "time.sleep": ("Use await asyncio.sleep() instead", 0.98, True),
    # File I/O - builtin open is blocking
    "builtins.open": ("Use aiofiles.open() for async file I/O", 0.90, True),
    # Subprocess - blocking
    "subprocess.run": ("Use asyncio.create_subprocess_exec()", 0.92, True),
    "subprocess.call": ("Use asyncio.create_subprocess_exec()", 0.92, True),
    "subprocess.check_output": ("Use asyncio.create_subprocess_exec()", 0.92, True),
    "subprocess.Popen": ("Use asyncio.create_subprocess_exec()", 0.88, True),
    # Database - sync drivers
    "sqlite3.connect": ("Use aiosqlite for async SQLite", 0.90, True),
    "psycopg2.connect": ("Use asyncpg for async PostgreSQL", 0.90, True),
    "pymysql.connect": ("Use aiomysql for async MySQL", 0.90, True),
    "redis.Redis": ("Use redis.asyncio.Redis for async Redis", 0.88, True),
}

BLOCKING_IO_PATTERNS_MEDIUM_CONFIDENCE = {
    # Generic patterns that need context - may have false positives
    "open(": ("Consider aiofiles.open() if in async context", 0.70, False),
    ".read(": ("Consider async read if this is file/network I/O", 0.60, False),
    ".write(": ("Consider async write if this is file/network I/O", 0.60, False),
    ".connect(": ("Consider async connection if this is network/DB", 0.65, False),
    ".execute(": ("Consider async execute if this is database", 0.60, False),
}

# Issue #363-366 + #385 + #569: Patterns that look like blocking but are safe
# These reduce confidence or mark as potential_false_positive
SAFE_PATTERNS = {
    # Dict/object attribute access - NOT I/O (Issue #569: expanded list)
    ".get(": "dict/object attribute access (O(1), not I/O)",
    "dict.get": "dictionary get method",
    "data.get": "dict data access",
    "item.get": "dict item access",
    "result.get": "dict result access",
    "results.get": "dict results access",
    "metadata.get": "dict metadata access",
    "params.get": "dict params access",
    "kwargs.get": "kwargs dict access",
    "args.get": "args dict access",
    "options.get": "options dict access",
    "response.get": "response dict access",
    "msg.get": "message dict access",
    "message.get": "message dict access",
    "info.get": "info dict access",
    "context.get": "context dict access",
    "headers.get": "headers dict access",
    "body.get": "body dict access",
    "json_data.get": "JSON data dict access",
    "payload.get": "payload dict access",
    "event.get": "event dict access",
    "record.get": "record dict access",
    "row.get": "row dict access",
    "entry.get": "entry dict access",
    "obj.get": "object dict access",
    "d.get": "dict access",
    "by_severity.get": "dict access by key",
    "severity_order.get": "severity ordering dict access",
    "severity_emoji.get": "severity emoji dict access",
    "fact.get": "fact dict access",
    "vector.get": "vector dict access",
    "issue.get": "issue dict access",
    "finding.get": "finding dict access",
    "error.get": "error dict access",
    "state.get": "state dict access",
    "cache.get": "cache dict access (in-memory)",
    "getattr(": "Python builtin for attribute access",
    "getattr": "Python builtin for attribute access",
    # Logging - initialization, not I/O during call
    "getlogger": "logging.getLogger() - logger initialization",
    "logging.getlogger": "logging.getLogger() - logger initialization",
    # FastAPI/web framework decorators - NOT HTTP calls
    "router.get": "FastAPI/Starlette route decorator",
    "router.post": "FastAPI/Starlette route decorator",
    "router.put": "FastAPI/Starlette route decorator",
    "router.delete": "FastAPI/Starlette route decorator",
    "router.patch": "FastAPI/Starlette route decorator",
    "app.get": "FastAPI/Starlette route decorator",
    "app.post": "FastAPI/Starlette route decorator",
    "app.put": "FastAPI/Starlette route decorator",
    "app.delete": "FastAPI/Starlette route decorator",
    # Config/environment access - in-memory, not I/O
    "config.get": "config dict access",
    "settings.get": "settings dict access",
    "environ.get": "environment variable access (in-memory)",
    "os.environ.get": "environment variable access (in-memory)",
    # Queue operations - thread-safe but not network I/O
    "queue.get": "thread-safe queue access",
    "queue.put": "thread-safe queue access",
    # Async patterns - already async
    "await ": "already awaited",
    "aiofiles": "already using aiofiles",
    "aiohttp": "already using aiohttp",
    "httpx.AsyncClient": "already using async httpx",
    "asyncpg": "already using async postgres",
    "aiosqlite": "already using async sqlite",
    "aiomysql": "already using async mysql",
}

# Legacy compatibility - keep for any code referencing old constant
BLOCKING_IO_OPERATIONS = {
    "open": "Use aiofiles.open() for async file I/O",
    "read": "Use async file reading",
    "write": "Use async file writing",
    "sleep": "Use asyncio.sleep() instead of time.sleep()",
    "request": "Use aiohttp or httpx for async HTTP",
    "get": "Use async HTTP client",
    "post": "Use async HTTP client",
    "urlopen": "Use aiohttp for async HTTP",
    "connect": "Use async database driver",
    "execute": "Use async database operations",
    "cursor": "Use async database cursor",
}

# Legacy compatibility
BLOCKING_IO_FALSE_POSITIVES = set(SAFE_PATTERNS.keys())

# Issue #371: Refined database operation patterns with context-aware matching
# Split into HIGH confidence (definitely DB) and contextual patterns
# Pattern format: (pattern, requires_prefix, prefix_patterns)
#   - requires_prefix: if True, must have a known DB-related prefix
#   - prefix_patterns: prefixes that indicate database context

# HIGH CONFIDENCE: Definitely database operations regardless of context
DB_OPERATIONS_HIGH_CONFIDENCE = {
    "cursor.execute",
    "cursor.executemany",
    "cursor.fetchone",
    "cursor.fetchall",
    "cursor.fetchmany",
    "conn.execute",
    "connection.execute",
    "session.execute",
    "session.query",
    "db.execute",
    "db.query",
    "collection.find",
    "collection.find_one",
    "collection.insert",
    "collection.insert_one",
    "collection.insert_many",
    "collection.update",
    "collection.update_one",
    "collection.update_many",
    "collection.delete",
    "collection.delete_one",
    "collection.delete_many",
    # Redis operations (high confidence when prefixed)
    "redis_client.get",
    "redis_client.set",
    "redis_client.hget",
    "redis_client.hset",
    "redis_client.hgetall",
    "redis_client.mget",
    "redis_client.mset",
    "redis_client.delete",
    "pipe.get",
    "pipe.set",
    "pipe.hget",
    "pipe.hset",
    "pipe.hgetall",
    "pipe.execute",
    "pipeline.get",
    "pipeline.set",
    "pipeline.hget",
    "pipeline.hset",
    "pipeline.execute",
    # SQLAlchemy patterns
    "session.add",
    "session.commit",
    "session.refresh",
    # Async DB patterns
    "await cursor.execute",
    "await conn.execute",
    "await session.execute",
}

# CONTEXTUAL: These operations need prefix validation
# They're only DB operations when called on database objects
DB_OPERATIONS_CONTEXTUAL = {
    "execute": {"cursor", "conn", "connection", "session", "db", "database"},
    "executemany": {"cursor"},
    "fetchone": {"cursor", "result"},
    "fetchall": {"cursor", "result"},
    "fetchmany": {"cursor", "result"},
    "query": {"session", "db", "database", "engine"},
    "find": {"collection", "model", "db"},
    "find_one": {"collection", "model", "db"},
    "insert": {"collection", "db"},
    "insert_one": {"collection"},
    "insert_many": {"collection"},
    "update": {"collection", "model", "db"},
    "update_one": {"collection"},
    "update_many": {"collection"},
    "delete": {"collection", "model", "db"},
    "delete_one": {"collection"},
    "delete_many": {"collection"},
}

# FALSE POSITIVE patterns - NEVER flag these as N+1
# These look like DB ops but are actually safe in-memory operations
DB_OPERATIONS_FALSE_POSITIVES = {
    # Dict/object access
    "dict.get",
    "result.get",  # Getting values from dict results
    "data.get",
    "item.get",
    "msg.get",
    "message.get",
    "config.get",
    "settings.get",
    "metadata.get",
    "results.get",
    "response.get",
    "params.get",
    "kwargs.get",
    "args.get",
    "options.get",
    "by_severity.get",
    "severity_emoji.get",
    "fact.get",
    # Python builtins
    "getattr",
    "setattr",
    "set",  # Python set() constructor
    # Regex operations
    "re.findall",
    "re.finditer",
    "re.find",
    "pattern.findall",
    "pattern.finditer",
    "pattern.find",
    # Inspect module
    "inspect.getsource",
    "inspect.getmembers",
    "inspect.getfile",
    # String operations
    "str.find",
    "text.find",
    # List/set operations
    "list.append",
    "findings.append",
    "results.append",
    # OS operations (not I/O in loop context)
    "os.path.getsize",
    "os.path.exists",
    "os.path.isfile",
    "os.path.isdir",
}

# Legacy compatibility - keep for backward compatibility
DB_OPERATIONS = {
    "execute",
    "executemany",
    "fetchone",
    "fetchall",
    "fetchmany",
    "query",
    "find",
    "find_one",
    "insert",
    "update",
    "delete",
    "select",
    "get",
    "set",
    "hget",
    "hset",
    "mget",
    "mset",
}

# HTTP operations
HTTP_OPERATIONS = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "request",
    "urlopen",
    "fetch",
}
