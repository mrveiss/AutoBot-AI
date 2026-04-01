# Codebase Analytics Engine -- API Guide


## Quick Answer

**How do you use the codebase analytics API to get API coverage for a project?**

Index the project, wait for completion, then fetch the endpoint coverage report.
Here is the complete flow:

```python
#!/usr/bin/env python3
"""Index a codebase and retrieve the API endpoint coverage report."""

import asyncio

import aiohttp
from autobot_shared.ssot_config import config

BACKEND = f"https://{config.vm.main}:{config.port.backend}"
API = f"{BACKEND}/api/analytics/codebase"


async def get_api_coverage(token: str, project_path: str = "/opt/autobot"):
    """Index a project and retrieve its API endpoint coverage report.

    Args:
        token: Admin JWT token.
        project_path: Absolute path to the project directory.
    """
    headers = {"Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession() as session:
        # Step 1: Start indexing
        resp = await session.post(
            f"{API}/index",
            json={"root_path": project_path},
            headers=headers,
            ssl=False,
        )
        index_result = await resp.json()
        print(f"Indexing started: {index_result.get('status')}")

        # Step 2: Poll until indexing completes
        while True:
            status_resp = await session.get(
                f"{API}/index/status",
                headers=headers,
                ssl=False,
            )
            status = await status_resp.json()
            if status.get("status") in ("completed", "idle"):
                print(f"Indexing done: {status.get('files_indexed', 0)} files")
                break
            print(f"Indexing: {status.get('progress', 0)}%")
            await asyncio.sleep(3)

        # Step 3: Get API endpoint coverage
        coverage_resp = await session.get(
            f"{API}/endpoint-coverage",
            headers=headers,
            ssl=False,
        )
        coverage = await coverage_resp.json()

        total = coverage.get("total_endpoints", 0)
        tested = coverage.get("tested_endpoints", 0)
        pct = (tested / total * 100) if total > 0 else 0
        print(f"API Coverage: {tested}/{total} endpoints ({pct:.1f}%)")

        # Step 4: Get full stats
        stats_resp = await session.get(
            f"{API}/stats",
            headers=headers,
            ssl=False,
        )
        stats = await stats_resp.json()
        print(f"Total functions: {stats.get('total_functions', 0)}")
        print(f"Total classes: {stats.get('total_classes', 0)}")

        return coverage


if __name__ == "__main__":
    import sys
    auth_token = sys.argv[1] if len(sys.argv) > 1 else "YOUR_JWT_TOKEN"
    asyncio.run(get_api_coverage(auth_token))
```

**curl quick check:**

```bash
# Index
curl -sk -X POST "$BACKEND/api/analytics/codebase/index" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"root_path": "/opt/autobot"}'

# Coverage
curl -sk "$BACKEND/api/analytics/codebase/endpoint-coverage" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

For the full endpoint reference, report generation, and SDK client, see
[Section 5](#5-api-endpoint-coverage-endpoints) and [Section 12](#12-python-sdk-client).

---


> **Base URL:** `https://172.16.168.20:8443`
> **API Prefix:** `/api/analytics/codebase`
> **Auth:** All endpoints require admin permission (`check_admin_permission` dependency)
> **Source code:** `autobot-backend/api/codebase_analytics/`

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Quick Start: Index a Project and Get the API Coverage Report](#2-quick-start-index-a-project-and-get-the-api-coverage-report)
3. [Indexing Endpoints](#3-indexing-endpoints)
4. [Statistics and Code Quality Endpoints](#4-statistics-and-code-quality-endpoints)
5. [API Endpoint Coverage Endpoints](#5-api-endpoint-coverage-endpoints)
6. [Analytics Endpoints](#6-analytics-endpoints)
7. [Code Source Registry](#7-code-source-registry)
8. [Report Generation](#8-report-generation)
9. [Environment Analysis](#9-environment-analysis)
10. [Code Ownership](#10-code-ownership)
11. [Source ID Filtering](#11-source-id-filtering)
12. [Python SDK Client](#12-python-sdk-client)
13. [Scanner and Analyzer Internals](#13-scanner-and-analyzer-internals)
14. [Storage Layer](#14-storage-layer)
15. [Frontend Dashboard Integration](#15-frontend-dashboard-integration)
16. [Troubleshooting](#16-troubleshooting)
17. [Complete Endpoint Reference Table](#17-complete-endpoint-reference-table)

---

## 1. Architecture Overview

The codebase analytics engine is a modular FastAPI subsystem that scans, indexes,
and analyzes source code repositories. It provides metrics on code quality, API
endpoint coverage, duplication, dependency graphs, call graphs, and more.

### Module Layout

```
autobot-backend/api/codebase_analytics/
|-- router.py                      # Main APIRouter, tags=["codebase-analytics"]
|-- routes.py                      # Backward-compat re-export of router
|-- scanner.py                     # Background indexing subprocess, progress tracking
|-- storage.py                     # Redis (analytics DB) + ChromaDB persistence
|-- models.py                      # Pydantic request/response models
|-- analyzers.py                   # Python / JS / Vue AST analyzers
|-- api_endpoint_scanner.py        # Backend+frontend endpoint coverage checker
|-- duplicate_detector.py          # Hash and token-based duplicate detection
|-- config_duplication_detector.py # Config value duplication finder
|-- npu_embeddings.py              # NPU-accelerated code embeddings
|-- source_models.py               # CodeSource Pydantic models
|-- source_storage.py              # Redis CRUD for code sources
|-- types.py                       # FileAnalysisResult and shared types
|-- endpoints/
|   |-- shared.py                  # ImportContext, stdlib/third-party sets
|   |-- indexing.py                # POST /index, GET /index/status, etc.
|   |-- stats.py                   # GET /stats, /hardcodes, /problems, /embedding-stats
|   |-- charts.py                  # GET /analytics/charts
|   |-- dependencies.py            # GET /analytics/dependencies
|   |-- import_tree.py             # GET /analytics/import-tree
|   |-- call_graph.py              # GET /analytics/call-graph
|   |-- declarations.py            # GET /declarations
|   |-- duplicates.py              # GET /duplicates, /config-duplicates
|   |-- cache.py                   # DELETE /cache
|   |-- report.py                  # GET /report (Markdown export)
|   |-- api_endpoints.py           # GET /api-endpoints, /endpoint-coverage
|   |-- environment.py             # GET /env-analysis, /env-recommendations
|   |-- ownership.py               # GET /ownership/analysis, /ownership/gaps
|   |-- cross_language_patterns.py # Cross-language pattern detection
|   |-- pattern_analysis.py        # Code pattern detection and optimization
|   |-- sources.py                 # CRUD for code source registry
|   |-- queue.py                   # GET /index/queue, DELETE /index/queue/{id}
```

### Router Registration

The codebase analytics router is mounted by `analytics_routers.py`:

```python
# autobot-backend/initialization/router_registry/analytics_routers.py
(
    "api.codebase_analytics",
    "/analytics/codebase",      # <-- prefix
    ["codebase-analytics"],     # <-- tags
    "codebase_analytics",       # <-- module
)
```

This means all endpoints listed in this guide are prefixed with
`/api/analytics/codebase`. For example, `POST /index` becomes
`POST /api/analytics/codebase/index`.

### Data Flow

```
1. POST /index                    -- Start background indexing
2. scanner.py subprocess          -- Walks filesystem, parses AST
3. analyzers.py                   -- Extracts functions, classes, problems
4. storage.py                     -- Writes to ChromaDB + Redis
5. GET /stats, /declarations, ... -- Read indexed data
6. GET /endpoint-coverage         -- Live scan of backend+frontend files
7. GET /report                    -- Renders full Markdown report
```

---

## 2. Quick Start: Index a Project and Get the API Coverage Report

This section answers the key question: **"How do I use the codebase analytics
engine to programmatically retrieve the API coverage report for a local project?"**

### Step 1: Index the Project

```python
import aiohttp
import asyncio
import json

BACKEND = f"https://{config.vm.main}:{config.port.backend}"
API = f"{BACKEND}/api/analytics/codebase"


async def index_project(root_path: str, source_id: str = None) -> dict:
    """Index a local project for codebase analytics.

    Args:
        root_path: Absolute filesystem path to the project directory.
                   Defaults to PROJECT_ROOT if omitted.
        source_id: Optional code source registry ID. When provided,
                   analytics data is scoped to that source.

    Returns:
        Final indexing status dict with result or error.
    """
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        # Start indexing
        payload = {"root_path": root_path}
        if source_id:
            payload["source_id"] = source_id

        resp = await session.post(f"{API}/index", json=payload)
        data = await resp.json()

        task_id = data.get("task_id")
        status = data.get("status")
        print(f"Indexing response: status={status}, task_id={task_id}")

        # Handle queued or syncing states
        if status in ("queued", "syncing"):
            print(f"Job is {status}: {data.get('message')}")
            return data

        if not task_id:
            print("No task_id returned -- check response")
            return data

        # Poll for completion
        while True:
            poll = await session.get(f"{API}/index/status/{task_id}")
            poll_data = await poll.json()
            current_status = poll_data["status"]
            progress = poll_data.get("progress", {})

            print(
                f"  [{current_status}] "
                f"{progress.get('percent', 0):.0f}% "
                f"({progress.get('current', 0)}/{progress.get('total', '?')} files) "
                f"-- {progress.get('current_file', '')}"
            )

            if current_status in ("completed", "failed", "cancelled"):
                return poll_data

            await asyncio.sleep(2)


# Usage:
result = asyncio.run(index_project("/opt/autobot/autobot-backend"))
print(json.dumps(result, indent=2))
```

### Step 2: Retrieve the API Coverage Report

The **API coverage report** is provided by the `/endpoint-coverage` endpoint.
It scans backend Python files for FastAPI route decorators and frontend
TypeScript/Vue files for API calls, then cross-references them.

```python
import aiohttp
import asyncio

BACKEND = f"https://{config.vm.main}:{config.port.backend}"
API = f"{BACKEND}/api/analytics/codebase"


async def get_api_coverage_report() -> dict:
    """Retrieve the API coverage report for the indexed project.

    This endpoint performs a live scan of:
    - Backend: all @router.get/post/put/delete decorators
    - Frontend: all API call patterns in .ts/.vue files

    Returns:
        Coverage report with summary, orphaned endpoints,
        missing endpoints, and coverage percentage.
    """
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        resp = await session.get(f"{API}/endpoint-coverage")
        data = await resp.json()

        summary = data.get("summary", {})
        print("=== API Coverage Report ===")
        print(f"Backend endpoints defined:  {summary.get('backend_endpoints', 0)}")
        print(f"Frontend API calls found:   {summary.get('frontend_calls', 0)}")
        print(f"Endpoints actively used:    {summary.get('used_endpoints', 0)}")
        print(f"Orphaned (never called):    {summary.get('orphaned_endpoints', 0)}")
        print(f"Missing (called, not def):  {summary.get('missing_endpoints', 0)}")
        print(f"Coverage percentage:        {summary.get('coverage_percentage', 0):.1f}%")
        print(f"Scan timestamp:             {data.get('scan_timestamp', 'N/A')}")

        return data


report = asyncio.run(get_api_coverage_report())
```

### Step 3: Combine with Codebase Statistics

For a richer report, combine the coverage data with indexed statistics:

```python
import aiohttp
import asyncio

BACKEND = f"https://{config.vm.main}:{config.port.backend}"
API = f"{BACKEND}/api/analytics/codebase"


async def get_comprehensive_api_report(source_id: str = None) -> dict:
    """Build a comprehensive API coverage report combining multiple endpoints.

    Args:
        source_id: Optional source filter for multi-project setups.

    Returns:
        Combined report dict with stats, coverage, declarations,
        call graph summary, and dependency summary.
    """
    params = {}
    if source_id:
        params["source_id"] = source_id

    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        # Fire all requests concurrently
        stats_task = session.get(f"{API}/stats", params=params)
        coverage_task = session.get(f"{API}/endpoint-coverage")
        declarations_task = session.get(f"{API}/declarations", params=params)
        call_graph_task = session.get(f"{API}/analytics/call-graph")
        deps_task = session.get(f"{API}/analytics/dependencies")

        responses = await asyncio.gather(
            stats_task, coverage_task, declarations_task,
            call_graph_task, deps_task,
        )

        stats = await responses[0].json()
        coverage = await responses[1].json()
        declarations = await responses[2].json()
        call_graph = await responses[3].json()
        deps = await responses[4].json()

    # Build combined report
    stats_data = stats.get("stats", {})
    cov_summary = coverage.get("summary", {})
    cg_summary = call_graph.get("summary", {})
    dep_data = deps.get("dependency_data", {})
    dep_summary = dep_data.get("summary", {})

    report = {
        "codebase_stats": {
            "total_files": stats_data.get("total_files", 0),
            "total_lines": stats_data.get("total_lines", 0),
            "total_functions": stats_data.get("total_functions", 0),
            "total_classes": stats_data.get("total_classes", 0),
            "code_lines": stats_data.get("code_lines", 0),
            "comment_lines": stats_data.get("comment_lines", 0),
            "last_indexed": stats.get("last_indexed", "Never"),
        },
        "api_coverage": {
            "backend_endpoints": cov_summary.get("backend_endpoints", 0),
            "frontend_calls": cov_summary.get("frontend_calls", 0),
            "used_endpoints": cov_summary.get("used_endpoints", 0),
            "orphaned_endpoints": cov_summary.get("orphaned_endpoints", 0),
            "missing_endpoints": cov_summary.get("missing_endpoints", 0),
            "coverage_percentage": cov_summary.get("coverage_percentage", 0),
        },
        "declarations": {
            "total": declarations.get("total_count", 0),
            "functions": declarations.get("functions", 0),
            "classes": declarations.get("classes", 0),
        },
        "call_graph": {
            "total_functions": cg_summary.get("total_functions", 0),
            "connected_functions": cg_summary.get("connected_functions", 0),
            "orphaned_functions": cg_summary.get("orphaned_functions", 0),
            "total_call_edges": cg_summary.get("total_call_relationships", 0),
            "resolution_rate": cg_summary.get("resolution_rate", 0),
        },
        "dependencies": {
            "total_modules": dep_summary.get("total_modules", 0),
            "import_relationships": dep_summary.get("total_import_relationships", 0),
            "circular_dependencies": dep_summary.get("circular_dependency_count", 0),
            "external_packages": dep_summary.get("external_dependency_count", 0),
        },
    }

    return report


report = asyncio.run(get_comprehensive_api_report())
import json
print(json.dumps(report, indent=2))
```

### Using curl

```bash
# Index a project
curl -sk -X POST "https://172.16.168.20:8443/api/analytics/codebase/index" \
  -H "Content-Type: application/json" \
  -d '{"root_path": "/opt/autobot/autobot-backend"}' | jq .

# Check indexing status
curl -sk "https://172.16.168.20:8443/api/analytics/codebase/index/status/<task_id>" | jq .

# Get API coverage report
curl -sk "https://172.16.168.20:8443/api/analytics/codebase/endpoint-coverage" | jq .

# Get codebase statistics
curl -sk "https://172.16.168.20:8443/api/analytics/codebase/stats" | jq .

# Get full endpoint analysis with details
curl -sk "https://172.16.168.20:8443/api/analytics/codebase/endpoint-analysis" | jq .
```

---

## 3. Indexing Endpoints

The indexing pipeline scans a filesystem path, parses source files with AST
analysis, and stores results in ChromaDB (code embeddings, declarations,
problems) and Redis (stats, hardcodes, indexing state).

### POST /index

Start background indexing of a codebase path.

**Request body** (all fields optional):

```json
{
  "root_path": "/opt/autobot/autobot-backend",
  "source_id": "github-abc123"
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `root_path` | string | PROJECT_ROOT | Absolute path to scan |
| `source_id` | string | null | Code source registry ID (resolves to clone_path) |

**Response** (started):

```json
{
  "task_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "started",
  "message": "Indexing started in background. Poll /api/analytics/codebase/index/status/<task_id> for progress."
}
```

**Response** (queued -- another job is running):

```json
{
  "task_id": null,
  "status": "queued",
  "position": 1,
  "message": "Queued behind current job (position 1). The job will start automatically when the running job finishes."
}
```

**Response** (syncing -- source needs git clone first):

```json
{
  "task_id": null,
  "status": "syncing",
  "message": "Source repository not yet cloned. Sync started -- indexing will begin automatically after sync."
}
```

**Implementation notes:**
- Only one indexing job runs at a time. Concurrent requests are queued (FIFO).
- The scanner runs in a subprocess to prevent ChromaDB SIGSEGV issues.
- Progress is written to Redis so the parent process can report it.
- A cleanup callback auto-starts the next queued job on completion.

### GET /index/status/{task_id}

Check the status and progress of a background indexing task.

**Response** (in progress):

```json
{
  "task_id": "a1b2c3d4-...",
  "status": "running",
  "progress": {
    "current": 120,
    "total": 267,
    "percent": 44.9,
    "current_file": "api/chat.py",
    "operation": "analyzing"
  },
  "result": null,
  "error": null,
  "started_at": "2026-03-15T10:30:00",
  "completed_at": null,
  "failed_at": null
}
```

**Response** (completed):

```json
{
  "task_id": "a1b2c3d4-...",
  "status": "completed",
  "progress": null,
  "result": {
    "total_files": 267,
    "total_functions": 1423,
    "total_classes": 89,
    "total_problems": 42,
    "scan_time_seconds": 38.2
  },
  "error": null,
  "started_at": "2026-03-15T10:30:00",
  "completed_at": "2026-03-15T10:30:38"
}
```

**Possible status values:** `running`, `completed`, `failed`, `cancelled`, `not_found`

### GET /index/current

Get the currently running indexing job (if any).

**Response** (active job):

```json
{
  "has_active_job": true,
  "task_id": "a1b2c3d4-...",
  "status": "running",
  "progress": { "current": 50, "total": 200, "percent": 25.0 },
  "phases": { "scanning": "complete", "analyzing": "in_progress" },
  "batches": { "current_batch": 3, "total_batches": 10 },
  "stats": { "files_processed": 50 },
  "started_at": "2026-03-15T10:30:00",
  "message": "Indexing job is in progress"
}
```

**Response** (no active job):

```json
{
  "has_active_job": false,
  "task_id": null,
  "status": "idle",
  "message": "No indexing job is currently running"
}
```

### POST /index/cancel

Cancel the currently running indexing job.

**Response:**

```json
{
  "success": true,
  "task_id": "a1b2c3d4-...",
  "message": "Indexing job cancelled successfully"
}
```

### GET /index/queue

View the current indexing queue state.

**Response:**

```json
{
  "running": {
    "task_id": "a1b2c3d4-...",
    "status": "running",
    "started_at": "2026-03-15T10:30:00",
    "source_id": null
  },
  "queue": [
    {
      "source_id": "github-abc123",
      "root_path": "/opt/autobot/data/code-sources/github-abc123",
      "queued_at": "2026-03-15T10:31:00",
      "requested_by": "api"
    }
  ],
  "queue_length": 1
}
```

### DELETE /index/queue/{source_id}

Remove all pending queue entries for a given source ID.

**Response:**

```json
{
  "success": true,
  "source_id": "github-abc123",
  "removed": 1,
  "remaining_queue_length": 0
}
```

---

## 4. Statistics and Code Quality Endpoints

### GET /stats

Get codebase statistics from the last indexing run.

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `source_id` | string | null | Filter to a specific code source |

**Response:**

```json
{
  "status": "success",
  "stats": {
    "total_files": 350,
    "python_files": 280,
    "javascript_files": 20,
    "typescript_files": 30,
    "vue_files": 20,
    "css_files": 15,
    "html_files": 5,
    "config_files": 25,
    "doc_files": 10,
    "total_lines": 45000,
    "total_functions": 1200,
    "total_classes": 85,
    "code_lines": 32000,
    "comment_lines": 5000,
    "docstring_lines": 3000,
    "blank_lines": 5000,
    "average_file_size": 128.5,
    "comment_ratio": "11.1%",
    "docstring_ratio": "6.7%",
    "lines_by_category": { "code": 32000, "config": 3000, "test": 8000 },
    "files_by_category": { "code": 280, "config": 25, "test": 45 }
  },
  "last_indexed": "2026-03-15T10:30:38",
  "storage_type": "chromadb"
}
```

When indexing is in progress, the response includes both the previous stats
and current indexing progress:

```json
{
  "status": "indexing",
  "message": "Showing previous stats. New indexing in progress.",
  "stats": { "total_files": 350, "..." : "..." },
  "indexing": {
    "task_id": "a1b2c3d4-...",
    "progress": { "current": 50, "total": 200, "percent": 25.0 },
    "started_at": "2026-03-15T10:30:00"
  }
}
```

### GET /hardcodes

Find hardcoded values in the codebase (IPs, credentials, magic numbers).

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `hardcode_type` | string | null | Filter by type (e.g., `ip_address`, `port`, `url`) |
| `source_id` | string | null | Filter to a specific code source |

**Response:**

```json
{
  "status": "success",
  "hardcodes": [
    {
      "file_path": "api/redis.py",
      "line": 42,
      "type": "ip_address",
      "value": "172.16.168.23",
      "context": "redis_host = '172.16.168.23'"
    }
  ],
  "total_count": 15,
  "hardcode_types": ["ip_address", "port", "url", "api_key"],
  "storage_type": "redis"
}
```

### GET /problems

Find code quality issues detected during indexing.

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `problem_type` | string | null | Filter by type (e.g., `complexity`, `security`) |
| `source_id` | string | null | Filter to a specific code source |

**Response:**

```json
{
  "status": "success",
  "problems": [
    {
      "type": "high_complexity",
      "severity": "high",
      "file_path": "api/chat.py",
      "file_category": "code",
      "line_number": 145,
      "description": "Function send_message has cyclomatic complexity of 18",
      "suggestion": "Extract helper methods to reduce complexity below 10"
    }
  ],
  "total_count": 42,
  "problem_types": ["high_complexity", "missing_docstring", "security_issue"],
  "storage_type": "chromadb"
}
```

### GET /embedding-stats

Get NPU embedding generation statistics from the indexing pipeline.

**Response:**

```json
{
  "status": "success",
  "embedding_stats": {
    "total_embeddings": 1200,
    "npu_embeddings": 1050,
    "fallback_embeddings": 150,
    "npu_percentage": 87.5,
    "total_time_ms": 4500,
    "npu_time_ms": 3200,
    "fallback_time_ms": 1300,
    "errors": 0
  },
  "npu_available": true
}
```

### POST /embedding-stats/reset

Reset NPU embedding statistics counters. Useful after configuration changes
or for benchmarking.

---

## 5. API Endpoint Coverage Endpoints

These endpoints provide the **API coverage report** -- the primary answer to
"which backend endpoints are actually used by the frontend?"

The `APIEndpointChecker` class (`api_endpoint_scanner.py`) performs a live
filesystem scan (not dependent on indexing) to find:
- Backend endpoints: `@router.get/post/put/delete/patch` decorators in Python files
- Frontend calls: API call patterns in TypeScript and Vue files

### GET /endpoint-coverage

**The primary endpoint for API coverage reporting.**

Returns a summary of backend endpoint coverage.

**Response:**

```json
{
  "status": "success",
  "summary": {
    "backend_endpoints": 147,
    "frontend_calls": 203,
    "used_endpoints": 98,
    "orphaned_endpoints": 49,
    "missing_endpoints": 12,
    "coverage_percentage": 66.7
  },
  "scan_timestamp": "2026-03-15T10:35:00"
}
```

| Field | Description |
|-------|-------------|
| `backend_endpoints` | Total FastAPI route definitions found |
| `frontend_calls` | Total API call patterns found in frontend code |
| `used_endpoints` | Endpoints that have at least one matching frontend call |
| `orphaned_endpoints` | Backend endpoints with no frontend callers |
| `missing_endpoints` | Frontend calls with no matching backend endpoint |
| `coverage_percentage` | `(used / backend_endpoints) * 100` |

### GET /endpoint-analysis

Full analysis including all endpoint details, call locations, and mismatches.
Use this when you need the complete data; use `/endpoint-coverage` for a
summary.

**Response:**

```json
{
  "status": "success",
  "analysis": {
    "backend_endpoints": 147,
    "frontend_calls": 203,
    "used_endpoints": 98,
    "orphaned_endpoints": 49,
    "missing_endpoints": 12,
    "coverage_percentage": 66.7,
    "endpoints": [
      {
        "method": "GET",
        "path": "/api/chat/history",
        "file_path": "api/chat.py",
        "line_number": 45,
        "function_name": "get_chat_history",
        "router_prefix": "/api/chat",
        "tags": ["chat"],
        "is_async": true
      }
    ],
    "api_calls": [
      {
        "method": "GET",
        "path": "/api/chat/history",
        "file_path": "src/services/chatService.ts",
        "line_number": 23,
        "context": "apiCall('/api/chat/history')",
        "is_dynamic": false
      }
    ],
    "orphaned": [
      {
        "type": "orphaned",
        "method": "GET",
        "path": "/api/legacy/status",
        "file_path": "api/legacy.py",
        "line_number": 12,
        "details": "No frontend calls found"
      }
    ],
    "missing": [
      {
        "type": "missing",
        "method": "POST",
        "path": "/api/v2/upload",
        "file_path": "src/components/Upload.vue",
        "line_number": 88,
        "details": "No backend endpoint found"
      }
    ],
    "used": [
      {
        "endpoint": { "method": "GET", "path": "/api/chat/history", "..." : "..." },
        "call_count": 3,
        "callers": [
          { "method": "GET", "path": "/api/chat/history", "file_path": "src/...", "..." : "..." }
        ]
      }
    ],
    "scan_timestamp": "2026-03-15T10:35:00"
  }
}
```

### GET /api-endpoints

List all backend API endpoint definitions (no cross-referencing).

**Response:**

```json
{
  "status": "success",
  "total": 147,
  "endpoints": [
    {
      "method": "POST",
      "path": "/api/chat/send",
      "file_path": "api/chat.py",
      "line_number": 78,
      "function_name": "send_message",
      "router_prefix": "/api/chat",
      "tags": ["chat"],
      "is_async": true
    }
  ]
}
```

### GET /api-calls

List all frontend API call patterns found in TypeScript and Vue files.

**Response:**

```json
{
  "status": "success",
  "total": 203,
  "api_calls": [
    {
      "method": "POST",
      "path": "/api/chat/send",
      "file_path": "src/services/chatService.ts",
      "line_number": 45,
      "context": "await api.post('/api/chat/send', payload)",
      "is_dynamic": false
    }
  ]
}
```

### GET /orphaned-endpoints

Endpoints defined in the backend but never called from the frontend.

### GET /missing-endpoints

API calls found in the frontend that have no matching backend endpoint.

### GET /used-endpoints

Endpoints that are both defined and called, sorted by call count (most-used first).

### POST /refresh-endpoint-cache

Force-refresh the endpoint analysis cache. Call this after making code changes.

---

## 6. Analytics Endpoints

### GET /analytics/charts

Aggregated chart data optimized for ApexCharts visualization.

**Response:**

```json
{
  "status": "success",
  "chart_data": {
    "problem_types": [
      { "type": "high_complexity", "count": 15 },
      { "type": "missing_docstring", "count": 28 }
    ],
    "severity_counts": [
      { "severity": "high", "count": 8 },
      { "severity": "medium", "count": 22 },
      { "severity": "low", "count": 12 }
    ],
    "race_conditions": [
      { "category": "thread_safety", "count": 3 }
    ],
    "top_files": [
      { "file": "api/chat.py", "count": 7 },
      { "file": "api/llm.py", "count": 5 }
    ],
    "summary": {
      "total_problems": 42,
      "unique_problem_types": 6,
      "files_with_problems": 18,
      "race_condition_count": 3
    }
  },
  "storage_type": "chromadb"
}
```

### GET /analytics/dependencies

File dependency analysis with circular dependency detection.

**Query parameters:** None (scans project root).

**Response:**

```json
{
  "status": "success",
  "dependency_data": {
    "modules": [
      {
        "path": "api/chat.py",
        "name": "chat",
        "package": "api",
        "functions": 12,
        "classes": 2,
        "imports": ["fastapi", "logging", "api.llm"],
        "import_count": 8
      }
    ],
    "import_relationships": [
      { "source": "api/chat.py", "target": "api.llm", "type": "import" }
    ],
    "graph": {
      "nodes": [{ "id": "api/chat.py", "name": "chat", "type": "module", "..." : "..." }],
      "edges": [{ "from": "api/chat.py", "to": "api.llm", "type": "import" }]
    },
    "circular_dependencies": [
      {
        "cycle": ["api/a.py", "api/b.py", "api/a.py"],
        "modules": ["api/a.py", "api/b.py", "api/a.py"],
        "length": 2,
        "severity": "high"
      }
    ],
    "external_dependencies": [
      { "package": "fastapi", "usage_count": 85 },
      { "package": "redis", "usage_count": 42 }
    ],
    "summary": {
      "total_modules": 200,
      "total_import_relationships": 1500,
      "circular_dependency_count": 2,
      "external_dependency_count": 35
    }
  }
}
```

**Background task variants:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/analytics/dependencies/analyze` | POST | Start background analysis |
| `/analytics/dependencies/status/{task_id}` | GET | Check analysis status |
| `/analytics/dependencies/cached` | GET | Get latest cached result |
| `/analytics/dependencies/tasks/clear-stuck` | POST | Clear stuck tasks |

### GET /analytics/import-tree

Bidirectional file import relationships for tree visualization.

**Response:**

```json
{
  "status": "success",
  "import_tree": [
    {
      "path": "api/chat.py",
      "imports": [
        { "module": "api.llm", "file": "api/llm.py", "is_external": false },
        { "module": "fastapi", "file": null, "is_external": true }
      ],
      "imported_by": [
        { "file": "api/routes.py", "module": "api.chat" }
      ]
    }
  ],
  "summary": {
    "total_files": 200,
    "total_import_relationships": 1500,
    "most_imported_files": [
      { "file": "utils/redis_client.py", "count": 45 }
    ],
    "most_importing_files": [
      { "file": "api/chat.py", "count": 18 }
    ]
  }
}
```

**Background task variants:** Same pattern as dependencies
(`/analyze`, `/status/{task_id}`, `/cached`, `/tasks/clear-stuck`).

### GET /analytics/call-graph

Function call graph with cross-module resolution.

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `refresh` | bool | false | Force refresh, bypass 5-minute Redis cache |

**Response:**

```json
{
  "status": "success",
  "call_graph": {
    "nodes": [
      {
        "id": "api.chat.send_message",
        "name": "send_message",
        "full_name": "send_message",
        "module": "api.chat",
        "class": null,
        "file": "api/chat.py",
        "line": 78,
        "is_async": true
      }
    ],
    "edges": [
      {
        "from": "api.chat.send_message",
        "to": "chat_workflow.llm_handler.prepare_prompt",
        "to_name": "prepare_prompt",
        "resolved": true,
        "count": 2
      }
    ]
  },
  "orphaned_functions": [
    {
      "id": "utils.old_helper.deprecated_func",
      "name": "deprecated_func",
      "module": "utils.old_helper",
      "file": "utils/old_helper.py",
      "line": 10,
      "is_async": false
    }
  ],
  "summary": {
    "total_functions": 1200,
    "connected_functions": 950,
    "orphaned_functions": 250,
    "total_call_relationships": 3500,
    "resolved_calls": 2800,
    "unresolved_calls": 700,
    "external_library_calls": 1200,
    "resolution_rate": 80.0,
    "top_callers": [
      { "function": "api.chat.send_message", "calls": 15 }
    ],
    "most_called": [
      { "function": "utils.redis_client.get_redis_client", "calls": 42 }
    ]
  },
  "from_cache": false
}
```

### GET /declarations

All code declarations (functions, classes) extracted during indexing.

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `declaration_type` | string | null | Filter by `function` or `class` |
| `source_id` | string | null | Filter to a specific code source |

**Response:**

```json
{
  "status": "success",
  "declarations": [
    {
      "name": "send_message",
      "type": "function",
      "file_path": "api/chat.py",
      "line_number": 78,
      "usage_count": 1,
      "is_exported": true,
      "parameters": ["self", "message", "context"]
    }
  ],
  "total_count": 1200,
  "functions": 1100,
  "classes": 85,
  "variables": 15,
  "storage_type": "chromadb"
}
```

### GET /duplicates

Duplicate code detection using hash matching and token-based similarity.

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `refresh` | bool | false | Force fresh analysis |
| `min_similarity` | float | 0.5 | Minimum similarity threshold (0.0--1.0) |
| `use_semantic` | bool | false | Enable LLM-based semantic analysis |

**Response:**

```json
{
  "status": "success",
  "duplicates": [
    {
      "file1": "api/chat.py",
      "file2": "api/llm.py",
      "start_line1": 45,
      "end_line1": 72,
      "start_line2": 120,
      "end_line2": 147,
      "similarity": 92.3,
      "lines": 27,
      "code_snippet": "def validate_input(data: dict) -> bool:..."
    }
  ],
  "total_count": 8,
  "high_similarity_count": 3,
  "medium_similarity_count": 4,
  "low_similarity_count": 1,
  "total_duplicate_lines": 215,
  "files_analyzed": 280,
  "scan_timestamp": "2026-03-15T10:40:00",
  "storage_type": "live_analysis"
}
```

**Background task variants:**
`/duplicates/analyze`, `/duplicates/status/{task_id}`, `/duplicates/cached`,
`/duplicates/tasks/clear-stuck`.

### GET /config-duplicates

Detect duplicated configuration values (same port, password, URL defined in
multiple places).

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `use_semantic` | bool | false | Enable LLM-based semantic analysis |

**Response:**

```json
{
  "status": "success",
  "duplicates_found": 5,
  "duplicates": [
    {
      "value": "8443",
      "count": 4,
      "locations": [
        { "file": "config/settings.py", "line": 12 },
        { "file": "docker-compose.yml", "line": 45 }
      ]
    }
  ],
  "report": "# Configuration Duplication Report\n..."
}
```

### DELETE /cache

Clear all codebase analytics data from Redis.

**Response:**

```json
{
  "status": "success",
  "message": "Cleared 45 cache entries from redis",
  "deleted_keys": 45,
  "storage_type": "redis"
}
```

---

## 7. Code Source Registry

The code source registry allows managing multiple projects (local directories
or GitHub repositories) as named sources. Each source has its own `source_id`
that scopes analytics data.

### GET /sources

List all registered code sources.

**Response:**

```json
{
  "sources": [
    {
      "id": "abc123-...",
      "name": "autobot-backend",
      "source_type": "local",
      "repo": null,
      "branch": "Dev_new_gui",
      "clone_path": "/opt/autobot/autobot-backend",
      "status": "ready",
      "last_synced": "2026-03-15T10:00:00",
      "access": "private",
      "credential_id": null,
      "error_message": null
    },
    {
      "id": "def456-...",
      "name": "external-lib",
      "source_type": "github",
      "repo": "mrveiss/external-lib",
      "branch": "main",
      "clone_path": "/opt/autobot/data/code-sources/def456-...",
      "status": "ready",
      "last_synced": "2026-03-15T09:45:00",
      "access": "private",
      "credential_id": "github-token-1",
      "error_message": null
    }
  ]
}
```

### POST /sources

Register a new code source. GitHub sources are auto-synced on creation.

**Request body:**

```json
{
  "name": "my-project",
  "source_type": "github",
  "repo": "mrveiss/my-project",
  "branch": "main",
  "credential_id": "github-token-1",
  "access": "private"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Human-readable name |
| `source_type` | string | yes | `"github"` or `"local"` |
| `repo` | string | yes | GitHub `owner/repo` or local absolute path |
| `branch` | string | no | Branch to clone (default: `main`) |
| `credential_id` | string | no | Secrets manager ID for auth token |
| `access` | string | no | `"private"` or `"shared"` |

### GET /sources/{source_id}

Retrieve a single source by ID.

### PUT /sources/{source_id}

Update an existing source. Accepts `name`, `branch`, `credential_id`, `access`.

### DELETE /sources/{source_id}

Delete a source and remove its clone directory (if inside the managed base path).

### POST /sources/{source_id}/sync

Trigger git clone (first time) or git pull (subsequent) for a source.
For local sources, validates the path and triggers indexing directly.

**Response:**

```json
{
  "source_id": "def456-...",
  "task_id": "sync-task-uuid",
  "status": "started",
  "message": "Sync started in background. Poll /sources/{id} for status."
}
```

### POST /sources/{source_id}/share

Update access control for a source.

**Request body:**

```json
{
  "access": "shared",
  "user_ids": ["user-1", "user-2"]
}
```

### GET /sources/summary

Batch-fetch summaries (last_indexed + last_commit) for all sources in one
request. Replaces N+1 per-source calls from the landing page.

**Response:**

```json
{
  "summaries": {
    "abc123-...": {
      "source_id": "abc123-...",
      "last_indexed": "2026-03-15T10:30:38",
      "last_commit": {
        "hash": "65bec0b06...",
        "short_hash": "65bec0b",
        "message": "feat(codebase): show commit message on project cards",
        "timestamp": "2026-03-15T09:00:00+00:00",
        "url": "https://github.com/mrveiss/AutoBot-AI/commit/65bec0b06..."
      }
    }
  }
}
```

### GET /sources/{source_id}/summary

Same as above but for a single source.

---

## 8. Report Generation

### GET /report

Generate a comprehensive Markdown analysis report combining all analytics
data into a single document.

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `format` | string | `"markdown"` | Output format (only markdown supported) |
| `include_api_analysis` | bool | true | Include API endpoint coverage section |
| `include_duplicate_analysis` | bool | true | Include duplicate code section |
| `include_bug_prediction` | bool | true | Include bug prediction section |
| `include_cross_language_analysis` | bool | true | Include cross-language patterns |
| `include_pattern_analysis` | bool | true | Include code pattern analysis |
| `quick` | bool | false | Skip expensive analyses for faster export |
| `use_semantic` | bool | false | Enable LLM-based semantic analysis |

**Response:** `text/plain` (Markdown document)

```
# AutoBot Codebase Analysis Report

Generated: 2026-03-15 10:45:00

## Code Issues Summary

### High Severity
- **api/chat.py:145**
  - Function send_message has cyclomatic complexity of 18
  - Suggestion: Extract helper methods

## API Endpoint Coverage
...

## Duplicate Code Analysis
...

## Bug Prediction
...
```

---

## 9. Environment Analysis

### GET /env-analysis

Analyze the codebase for hardcoded values and environment variable
opportunities. Uses the `EnvironmentAnalyzer` from `tools/code-analysis-suite`.

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | PROJECT_ROOT | Root path to analyze |
| `refresh` | bool | false | Force fresh analysis |
| `patterns` | string | `"**/*.py"` | Glob patterns (comma-separated) |
| `use_llm_filter` | bool | false | Use LLM to filter false positives |
| `llm_model` | string | `"gemma2:2b"` | Ollama model for LLM filtering |
| `filter_priority` | string | `"high"` | Priority level: `high`, `medium`, `low`, `all` |

**Response:**

```json
{
  "status": "success",
  "path": "/opt/autobot",
  "total_hardcoded_values": 85,
  "high_priority_count": 12,
  "recommendations_count": 20,
  "categories": { "security": 5, "port": 8, "hostname": 12, "url": 15 },
  "analysis_time_seconds": 8.3,
  "hardcoded_values": [ "..." ],
  "recommendations": [ "..." ],
  "storage_type": "live_analysis",
  "is_truncated": true
}
```

### GET /env-recommendations

Get actionable environment variable recommendations.

### GET /env-analysis/export

Export full analysis results without UI truncation, with optional filtering.

**Query parameters:** `category`, `severity`, `limit`, `include_recommendations`

---

## 10. Code Ownership

Endpoints are prefixed with `/ownership` (the sub-router has `prefix="/ownership"`).

### GET /ownership/analysis

Run code ownership analysis using `git log` data. Returns ownership per file
and directory, expertise scoring, and knowledge gap detection.

### GET /ownership/team-coverage

Get team coverage metrics showing how well the codebase is covered by
different contributors.

### GET /ownership/knowledge-gaps

Identify areas of the codebase with single-contributor knowledge (bus factor = 1).

---

## 11. Source ID Filtering

Most data-retrieval endpoints accept a `source_id` query parameter for
multi-project filtering. When provided, the endpoint returns data scoped to
that specific code source rather than the global dataset.

### How it works

1. During indexing with a `source_id`, the scanner stores data under
   source-scoped Redis keys (`codebase:{source_id}:stats`,
   `codebase:{source_id}:hardcodes:*`, etc.) and ChromaDB documents
   (`codebase_stats_{source_id}`).

2. When querying with `?source_id=X`, endpoints read from these scoped keys
   instead of the global ones.

### Endpoints that support source_id

| Endpoint | Parameter |
|----------|-----------|
| `GET /stats` | `?source_id=X` |
| `GET /hardcodes` | `?source_id=X` |
| `GET /problems` | `?source_id=X` |
| `GET /declarations` | `?source_id=X` |
| `POST /index` | `source_id` in request body |

### Example

```python
import aiohttp
import asyncio

BACKEND = f"https://{config.vm.main}:{config.port.backend}"
API = f"{BACKEND}/api/analytics/codebase"

async def get_project_stats(source_id: str) -> dict:
    """Get stats for a specific registered code source."""
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        resp = await session.get(
            f"{API}/stats",
            params={"source_id": source_id},
        )
        return await resp.json()

result = asyncio.run(get_project_stats("my-project-source-id"))
```

---

## 12. Python SDK Client

A reusable async client class for all codebase analytics operations:

```python
"""
Codebase Analytics API Client

Usage:
    from codebase_analytics_client import CodebaseAnalyticsClient

    client = CodebaseAnalyticsClient()
    report = asyncio.run(client.get_api_coverage())
"""

import asyncio
from typing import Optional

import aiohttp


class CodebaseAnalyticsClient:
    """Async Python client for the Codebase Analytics API.

    Args:
        base_url: Backend base URL (default: https://172.16.168.20:8443).
        verify_ssl: Whether to verify SSL certificates.
    """

    def __init__(
        self,
        base_url: str = "https://172.16.168.20:8443",
        verify_ssl: bool = False,
    ):
        """Initialize the client with backend URL."""
        self.base_url = base_url
        self.api = f"{base_url}/api/analytics/codebase"
        self.verify_ssl = verify_ssl

    async def _get(self, path: str, params: dict = None) -> dict:
        """Send a GET request and return JSON response.

        Args:
            path: API path relative to /api/analytics/codebase.
            params: Optional query parameters.

        Returns:
            Parsed JSON response.
        """
        connector = aiohttp.TCPConnector(ssl=self.verify_ssl)
        async with aiohttp.ClientSession(connector=connector) as session:
            resp = await session.get(f"{self.api}{path}", params=params)
            resp.raise_for_status()
            return await resp.json()

    async def _post(self, path: str, json: dict = None) -> dict:
        """Send a POST request and return JSON response.

        Args:
            path: API path relative to /api/analytics/codebase.
            json: Optional JSON request body.

        Returns:
            Parsed JSON response.
        """
        connector = aiohttp.TCPConnector(ssl=self.verify_ssl)
        async with aiohttp.ClientSession(connector=connector) as session:
            resp = await session.post(f"{self.api}{path}", json=json)
            resp.raise_for_status()
            return await resp.json()

    async def _delete(self, path: str) -> dict:
        """Send a DELETE request and return JSON response.

        Args:
            path: API path relative to /api/analytics/codebase.

        Returns:
            Parsed JSON response.
        """
        connector = aiohttp.TCPConnector(ssl=self.verify_ssl)
        async with aiohttp.ClientSession(connector=connector) as session:
            resp = await session.delete(f"{self.api}{path}")
            resp.raise_for_status()
            return await resp.json()

    # -- Indexing ----------------------------------------------------------

    async def index(
        self, root_path: str = None, source_id: str = None
    ) -> dict:
        """Start indexing a project.

        Args:
            root_path: Filesystem path to index (defaults to PROJECT_ROOT).
            source_id: Code source registry ID.

        Returns:
            Dict with task_id and status.
        """
        body = {}
        if root_path:
            body["root_path"] = root_path
        if source_id:
            body["source_id"] = source_id
        return await self._post("/index", json=body or None)

    async def get_index_status(self, task_id: str) -> dict:
        """Check indexing task status.

        Args:
            task_id: UUID returned by index().

        Returns:
            Status dict with progress, result, or error.
        """
        return await self._get(f"/index/status/{task_id}")

    async def get_current_job(self) -> dict:
        """Get the currently running indexing job."""
        return await self._get("/index/current")

    async def cancel_indexing(self) -> dict:
        """Cancel the currently running indexing job."""
        return await self._post("/index/cancel")

    async def wait_for_indexing(
        self, task_id: str, poll_interval: float = 2.0
    ) -> dict:
        """Poll until indexing completes or fails.

        Args:
            task_id: UUID returned by index().
            poll_interval: Seconds between polls.

        Returns:
            Final status dict.
        """
        while True:
            status = await self.get_index_status(task_id)
            if status.get("status") in ("completed", "failed", "cancelled"):
                return status
            await asyncio.sleep(poll_interval)

    # -- Statistics --------------------------------------------------------

    async def get_stats(self, source_id: str = None) -> dict:
        """Get codebase statistics.

        Args:
            source_id: Optional source filter.

        Returns:
            Stats dict with file counts, line counts, etc.
        """
        params = {"source_id": source_id} if source_id else None
        return await self._get("/stats", params=params)

    async def get_hardcodes(
        self, hardcode_type: str = None, source_id: str = None
    ) -> dict:
        """Get hardcoded values found in the codebase.

        Args:
            hardcode_type: Filter by type (ip_address, port, url, etc.).
            source_id: Optional source filter.

        Returns:
            Dict with hardcodes list and counts.
        """
        params = {}
        if hardcode_type:
            params["hardcode_type"] = hardcode_type
        if source_id:
            params["source_id"] = source_id
        return await self._get("/hardcodes", params=params or None)

    async def get_problems(
        self, problem_type: str = None, source_id: str = None
    ) -> dict:
        """Get code quality problems.

        Args:
            problem_type: Filter by problem type.
            source_id: Optional source filter.

        Returns:
            Dict with problems list sorted by severity.
        """
        params = {}
        if problem_type:
            params["problem_type"] = problem_type
        if source_id:
            params["source_id"] = source_id
        return await self._get("/problems", params=params or None)

    # -- API Coverage ------------------------------------------------------

    async def get_api_coverage(self) -> dict:
        """Get API endpoint coverage summary.

        Returns:
            Coverage report with backend_endpoints, frontend_calls,
            used_endpoints, orphaned_endpoints, missing_endpoints,
            and coverage_percentage.
        """
        return await self._get("/endpoint-coverage")

    async def get_api_analysis(self) -> dict:
        """Get full API endpoint analysis with all details.

        Returns:
            Complete analysis including endpoint lists,
            call locations, orphaned and missing endpoints.
        """
        return await self._get("/endpoint-analysis")

    async def get_orphaned_endpoints(self) -> dict:
        """Get endpoints defined but never called."""
        return await self._get("/orphaned-endpoints")

    async def get_missing_endpoints(self) -> dict:
        """Get frontend calls with no backend endpoint."""
        return await self._get("/missing-endpoints")

    async def get_used_endpoints(self) -> dict:
        """Get actively used endpoints with call counts."""
        return await self._get("/used-endpoints")

    # -- Analytics ---------------------------------------------------------

    async def get_declarations(
        self, declaration_type: str = None, source_id: str = None
    ) -> dict:
        """Get code declarations (functions, classes).

        Args:
            declaration_type: Filter by 'function' or 'class'.
            source_id: Optional source filter.

        Returns:
            Dict with declarations list and type counts.
        """
        params = {}
        if declaration_type:
            params["declaration_type"] = declaration_type
        if source_id:
            params["source_id"] = source_id
        return await self._get("/declarations", params=params or None)

    async def get_call_graph(self, refresh: bool = False) -> dict:
        """Get function call graph.

        Args:
            refresh: Force refresh, bypass Redis cache.

        Returns:
            Call graph with nodes, edges, and summary metrics.
        """
        params = {"refresh": "true"} if refresh else None
        return await self._get("/analytics/call-graph", params=params)

    async def get_dependencies(self) -> dict:
        """Get dependency analysis with circular detection.

        Returns:
            Dependency data with modules, graph, circular deps.
        """
        return await self._get("/analytics/dependencies")

    async def get_import_tree(self) -> dict:
        """Get bidirectional import tree.

        Returns:
            Import tree with per-file imports and imported_by.
        """
        return await self._get("/analytics/import-tree")

    async def get_charts(self) -> dict:
        """Get chart data for visualization.

        Returns:
            Aggregated chart data for problem types, severity, etc.
        """
        return await self._get("/analytics/charts")

    async def get_duplicates(
        self,
        refresh: bool = False,
        min_similarity: float = 0.5,
        use_semantic: bool = False,
    ) -> dict:
        """Get duplicate code analysis.

        Args:
            refresh: Force fresh analysis.
            min_similarity: Minimum similarity threshold (0.0-1.0).
            use_semantic: Enable LLM-based semantic analysis.

        Returns:
            Duplicates list with similarity scores.
        """
        params = {"min_similarity": min_similarity}
        if refresh:
            params["refresh"] = "true"
        if use_semantic:
            params["use_semantic"] = "true"
        return await self._get("/duplicates", params=params)

    # -- Cache -------------------------------------------------------------

    async def clear_cache(self) -> dict:
        """Clear all codebase analytics cache."""
        return await self._delete("/cache")

    # -- Report ------------------------------------------------------------

    async def generate_report(
        self, quick: bool = False, use_semantic: bool = False
    ) -> str:
        """Generate Markdown analysis report.

        Args:
            quick: Skip expensive analyses.
            use_semantic: Enable LLM-based semantic analysis.

        Returns:
            Markdown report as a string.
        """
        params = {}
        if quick:
            params["quick"] = "true"
        if use_semantic:
            params["use_semantic"] = "true"
        connector = aiohttp.TCPConnector(ssl=self.verify_ssl)
        async with aiohttp.ClientSession(connector=connector) as session:
            resp = await session.get(
                f"{self.api}/report", params=params or None
            )
            return await resp.text()
```

### SDK Usage Example

```python
import asyncio
from codebase_analytics_client import CodebaseAnalyticsClient


async def main():
    """Complete workflow: index, wait, then retrieve API coverage."""
    client = CodebaseAnalyticsClient()

    # Step 1: Index the project
    result = await client.index(root_path="/opt/autobot/autobot-backend")
    task_id = result.get("task_id")
    if not task_id:
        print(f"Indexing not started: {result}")
        return

    # Step 2: Wait for indexing to complete
    print("Waiting for indexing to complete...")
    final = await client.wait_for_indexing(task_id)
    print(f"Indexing finished: {final['status']}")

    # Step 3: Get the API coverage report
    coverage = await client.get_api_coverage()
    summary = coverage.get("summary", {})
    print(f"\nAPI Coverage: {summary.get('coverage_percentage', 0):.1f}%")
    print(f"  Endpoints: {summary.get('backend_endpoints', 0)}")
    print(f"  Used:      {summary.get('used_endpoints', 0)}")
    print(f"  Orphaned:  {summary.get('orphaned_endpoints', 0)}")
    print(f"  Missing:   {summary.get('missing_endpoints', 0)}")

    # Step 4: Get codebase stats
    stats = await client.get_stats()
    s = stats.get("stats", {})
    print(f"\nCodebase: {s.get('total_files', 0)} files, "
          f"{s.get('total_functions', 0)} functions, "
          f"{s.get('total_classes', 0)} classes")

    # Step 5: Check for code quality problems
    problems = await client.get_problems()
    print(f"\nCode problems: {problems.get('total_count', 0)}")

    # Step 6: Generate full report
    report = await client.generate_report(quick=True)
    print(f"\nReport generated ({len(report)} chars)")


asyncio.run(main())
```

---

## 13. Scanner and Analyzer Internals

### Indexing Pipeline

The scanner (`scanner.py`) orchestrates the indexing pipeline:

1. **File discovery:** Walks the target directory, filtering by extension
   and excluding directories in `SKIP_DIRS` (`.git`, `__pycache__`,
   `node_modules`, `venv`, `archive`, etc.).

2. **File categorization:** Each file is classified using
   `utils.file_categorization` into categories: `code`, `config`, `test`,
   `docs`, `assets`, `backup`, `archive`, `logs`, `data`.

3. **AST parsing:** Python files are parsed with `ast.parse()`. JavaScript
   and Vue files use regex-based extraction.

4. **Analysis:** `analyzers.py` provides three analyzer functions:
   - `analyze_python_file()` -- Extracts functions, classes, docstrings,
     complexity metrics, hardcoded values, and code problems.
   - `analyze_javascript_vue_file()` -- Extracts function definitions and
     exports from JS/TS/Vue files.
   - `analyze_documentation_file()` -- Extracts section structure from
     Markdown files.

5. **Change detection:** Files are hashed (SHA-256). During re-indexing,
   only changed files are re-analyzed (Redis key:
   `codebase:file_hash:{path}`).

6. **Storage:** Results are written to ChromaDB (embeddings, declarations,
   problems) and Redis (stats, hardcodes, metadata).

### Subprocess Architecture

Indexing runs in a subprocess (`_run_indexing_subprocess`) to isolate
ChromaDB operations from the main FastAPI process. This prevents SIGSEGV
crashes that occur when ChromaDB's C++ internals run in a forked process.

Key configuration:
- **Hard timeout:** 30 minutes (`_SUBPROCESS_HARD_TIMEOUT`)
- **Progress timeout:** 5 minutes without progress = stale
  (`_SUBPROCESS_PROGRESS_TIMEOUT`)
- **Watchdog interval:** 30 seconds (`_SUBPROCESS_WATCHDOG_INTERVAL`)
- **Dedicated thread pool:** 4 threads (`_INDEXING_EXECUTOR_MAX_WORKERS`)

Progress is communicated through Redis (the subprocess writes progress
updates to a Redis key that the parent process reads via
`_load_task_from_redis`).

### NPU Embeddings

When available, the scanner uses NPU (Neural Processing Unit) acceleration
for generating code embeddings via `npu_embeddings.py`. This offloads
embedding computation to dedicated hardware on VM .22.

---

## 14. Storage Layer

### Redis (Analytics Database)

The analytics engine uses Redis database 11 (`analytics`) for:
- **Indexing state:** Task progress, status, results
  (`indexing:task:{task_id}`)
- **File hashes:** Change detection between re-indexing runs
  (`codebase:file_hash:{path}`)
- **Hardcoded values:** Detected hardcodes by type
  (`codebase:hardcodes:{type}`)
- **Problems:** Code quality issues by type
  (`codebase:problems:{type}`)
- **Call graph cache:** 5-minute TTL cache
  (`codebase:call_graph:cache:{hash}`)
- **Per-source scoping:** Source-specific keys use prefix
  `codebase:{source_id}:` instead of `codebase:`

Connection is obtained via the canonical utility:

```python
from autobot_shared.redis_client import get_redis_client

# Sync client (use with asyncio.to_thread)
redis_client = get_redis_client(database="analytics", async_client=False)

# Async client (native async operations)
redis_client = await get_redis_client(database="analytics", async_client=True)
```

### ChromaDB

ChromaDB stores code embeddings and structured metadata in a persistent
collection named `autobot_code`. Location: `{PROJECT_ROOT}/data/chromadb/`.

Document types stored in ChromaDB:
- `type=function` -- Function declarations with metadata
- `type=class` -- Class declarations with metadata
- `type=problem` -- Code quality issues
- `type=duplicate` -- Duplicate code blocks (fallback cache)
- `codebase_stats` / `codebase_stats_{source_id}` -- Aggregate statistics

### In-Memory Fallback

When Redis is unavailable, `InMemoryStorage` (in `storage.py`) provides a
basic dict-based fallback implementing `set`, `get`, `hset`, `hgetall`,
`sadd`, `smembers`, `scan_iter`, `delete`, and `exists`.

---

## 15. Frontend Dashboard Integration

The Vue.js `CodebaseAnalytics.vue` component provides a full dashboard UI
that consumes all the endpoints documented here.

### Dashboard Sections

1. **Project Cards** -- List of registered code sources with commit messages,
   last-indexed timestamps, and sync status. Uses `GET /sources` and
   `GET /sources/summary`.

2. **Indexing Panel** -- Start/cancel indexing with real-time progress.
   Uses `POST /index`, `GET /index/current`, `POST /index/cancel`.

3. **Statistics Overview** -- File counts, line counts, language breakdown.
   Uses `GET /stats`.

4. **Problem Dashboard** -- Code quality issues by severity.
   Uses `GET /problems`.

5. **Hardcode Detection** -- IP addresses, credentials, magic numbers.
   Uses `GET /hardcodes`.

6. **Charts** -- ApexCharts visualizations of problem types and severity.
   Uses `GET /analytics/charts`.

7. **Dependency Graph** -- Interactive module dependency visualization.
   Uses `GET /analytics/dependencies`.

8. **Import Tree** -- Bidirectional import browser.
   Uses `GET /analytics/import-tree`.

9. **Call Graph** -- Function call relationship graph.
   Uses `GET /analytics/call-graph`.

10. **Declarations** -- Searchable list of all functions and classes.
    Uses `GET /declarations`.

11. **Duplicate Code** -- Duplicate detection with similarity scores.
    Uses `GET /duplicates`.

12. **API Coverage** -- Endpoint coverage analysis with orphaned/missing.
    Uses `GET /endpoint-coverage`.

13. **Environment Analysis** -- Hardcoded value recommendations.
    Uses `GET /env-analysis`.

14. **Code Ownership** -- Contributor expertise and knowledge gaps.
    Uses `GET /ownership/analysis`.

### Source ID Filtering in the UI

The dashboard stores a `selectedSourceId` reactive ref. When a user selects
a project card, this value is passed as `?source_id=X` to all data-fetching
endpoints, ensuring analytics are scoped to that project.

---

## 16. Troubleshooting

### "No codebase data found. Run indexing first."

**Cause:** No indexing has been run, or the data was cleared.

**Fix:** Run indexing via `POST /index` or click "Start Indexing" in the UI.

### Indexing is stuck at 0%

**Cause:** The subprocess may have crashed silently.

**Fix:**
1. Check `GET /index/current` -- if `has_active_job` is true but progress
   is not advancing, cancel with `POST /index/cancel`.
2. Check backend logs: `journalctl -u autobot-backend --since "10 minutes ago" | grep -i codebase`
3. Ensure ChromaDB data directory is writable: `ls -la /opt/autobot/data/chromadb/`

### Stale indexing task (shows "running" but nothing happens)

**Cause:** The subprocess crashed but the parent did not detect it. Tasks
older than 1 hour are automatically marked stale by `_is_task_stale()`.

**Fix:** Cancel the task, then restart indexing. The stale task will be
ignored automatically after 1 hour.

### ChromaDB connection failed

**Cause:** ChromaDB persistent directory is missing or corrupted.

**Fix:**
```bash
# Verify data directory exists
ls -la /opt/autobot/data/chromadb/

# If missing, create it
mkdir -p /opt/autobot/data/chromadb/

# If corrupted, clear and re-index
curl -sk -X DELETE "https://172.16.168.20:8443/api/analytics/codebase/cache"
curl -sk -X POST "https://172.16.168.20:8443/api/analytics/codebase/index"
```

### Redis connection failed (using in-memory storage)

**Cause:** Redis on VM .23 is unreachable.

**Fix:**
```bash
# Check Redis connectivity from backend host
redis-cli -h 172.16.168.23 -p 6379 -n 11 ping

# Check Redis service on .23
ssh autobot@172.16.168.23 "sudo systemctl status redis"
```

The system falls back to in-memory storage, but data is lost on restart.

### API coverage shows 0 endpoints

**Cause:** The `APIEndpointChecker` scans the filesystem at the project root.
If the backend files are not at the expected location, no endpoints are found.

**Fix:** Ensure the backend code is at `{PROJECT_ROOT}/autobot-backend/api/`
(or the path configured in `api_endpoint_scanner.py`).

### "Analysis timed out"

**Cause:** Duplicate detection or environment analysis exceeded the timeout
(60s for duplicates, 120s for environment analysis).

**Fix:** Use a higher `min_similarity` threshold for duplicates, or reduce
the file patterns for environment analysis.

### Queued jobs not starting

**Cause:** The cleanup callback (`_create_cleanup_callback`) failed to
trigger `_start_next_queued_job`.

**Fix:** Cancel the stuck job with `POST /index/cancel`, which resets the
`_current_indexing_task_id` and allows queued jobs to proceed.

### Source sync fails with "not a git repository"

**Cause:** A previous clone attempt failed partway through, leaving a
non-git directory at the clone path.

**Fix:** Delete the source (`DELETE /sources/{id}`) and recreate it, or
manually remove the partial clone directory and re-sync.

---

## 17. Complete Endpoint Reference Table

All endpoints are prefixed with `/api/analytics/codebase`.

| Method | Path | Description | Source File |
|--------|------|-------------|-------------|
| POST | `/index` | Start background indexing | `endpoints/indexing.py` |
| GET | `/index/status/{task_id}` | Check indexing progress | `endpoints/indexing.py` |
| GET | `/index/current` | Get current indexing job | `endpoints/indexing.py` |
| POST | `/index/cancel` | Cancel current indexing | `endpoints/indexing.py` |
| GET | `/index/queue` | View indexing queue | `endpoints/queue.py` |
| DELETE | `/index/queue/{source_id}` | Remove queued entries | `endpoints/queue.py` |
| GET | `/stats` | Codebase statistics | `endpoints/stats.py` |
| GET | `/hardcodes` | Hardcoded value detection | `endpoints/stats.py` |
| GET | `/problems` | Code quality problems | `endpoints/stats.py` |
| GET | `/embedding-stats` | NPU embedding metrics | `endpoints/stats.py` |
| POST | `/embedding-stats/reset` | Reset embedding counters | `endpoints/stats.py` |
| GET | `/declarations` | Function/class declarations | `endpoints/declarations.py` |
| GET | `/analytics/charts` | Chart data for visualization | `endpoints/charts.py` |
| GET | `/analytics/dependencies` | Dependency analysis | `endpoints/dependencies.py` |
| GET | `/analytics/dependencies/cached` | Cached dependency result | `endpoints/dependencies.py` |
| POST | `/analytics/dependencies/analyze` | Start background analysis | `endpoints/dependencies.py` |
| GET | `/analytics/dependencies/status/{task_id}` | Check analysis status | `endpoints/dependencies.py` |
| POST | `/analytics/dependencies/tasks/clear-stuck` | Clear stuck tasks | `endpoints/dependencies.py` |
| GET | `/analytics/import-tree` | Import relationship tree | `endpoints/import_tree.py` |
| GET | `/analytics/import-tree/cached` | Cached import tree | `endpoints/import_tree.py` |
| POST | `/analytics/import-tree/analyze` | Start background analysis | `endpoints/import_tree.py` |
| GET | `/analytics/import-tree/status/{task_id}` | Check analysis status | `endpoints/import_tree.py` |
| POST | `/analytics/import-tree/tasks/clear-stuck` | Clear stuck tasks | `endpoints/import_tree.py` |
| GET | `/analytics/call-graph` | Function call graph | `endpoints/call_graph.py` |
| GET | `/duplicates` | Duplicate code detection | `endpoints/duplicates.py` |
| GET | `/duplicates/cached` | Cached duplicate result | `endpoints/duplicates.py` |
| POST | `/duplicates/analyze` | Start background analysis | `endpoints/duplicates.py` |
| GET | `/duplicates/status/{task_id}` | Check analysis status | `endpoints/duplicates.py` |
| POST | `/duplicates/tasks/clear-stuck` | Clear stuck tasks | `endpoints/duplicates.py` |
| GET | `/config-duplicates` | Config value duplication | `endpoints/duplicates.py` |
| DELETE | `/cache` | Clear analytics cache | `endpoints/cache.py` |
| GET | `/report` | Markdown analysis report | `endpoints/report.py` |
| GET | `/api-endpoints` | List backend endpoints | `endpoints/api_endpoints.py` |
| GET | `/api-calls` | List frontend API calls | `endpoints/api_endpoints.py` |
| GET | `/endpoint-coverage` | API coverage summary | `endpoints/api_endpoints.py` |
| GET | `/endpoint-analysis` | Full endpoint analysis | `endpoints/api_endpoints.py` |
| GET | `/orphaned-endpoints` | Unused backend endpoints | `endpoints/api_endpoints.py` |
| GET | `/missing-endpoints` | Missing backend endpoints | `endpoints/api_endpoints.py` |
| GET | `/used-endpoints` | Used endpoints with counts | `endpoints/api_endpoints.py` |
| POST | `/refresh-endpoint-cache` | Refresh endpoint cache | `endpoints/api_endpoints.py` |
| GET | `/env-analysis` | Environment analysis | `endpoints/environment.py` |
| GET | `/env-recommendations` | Environment recommendations | `endpoints/environment.py` |
| GET | `/env-analysis/export` | Export env analysis | `endpoints/environment.py` |
| GET | `/sources` | List code sources | `endpoints/sources.py` |
| POST | `/sources` | Create code source | `endpoints/sources.py` |
| GET | `/sources/summary` | Batch source summaries | `endpoints/sources.py` |
| GET | `/sources/{source_id}` | Get source by ID | `endpoints/sources.py` |
| PUT | `/sources/{source_id}` | Update source | `endpoints/sources.py` |
| DELETE | `/sources/{source_id}` | Delete source | `endpoints/sources.py` |
| POST | `/sources/{source_id}/sync` | Trigger source sync | `endpoints/sources.py` |
| POST | `/sources/{source_id}/share` | Update access control | `endpoints/sources.py` |
| GET | `/sources/{source_id}/summary` | Source summary | `endpoints/sources.py` |
| GET | `/ownership/analysis` | Ownership analysis | `endpoints/ownership.py` |
| GET | `/ownership/team-coverage` | Team coverage metrics | `endpoints/ownership.py` |
| GET | `/ownership/knowledge-gaps` | Knowledge gap detection | `endpoints/ownership.py` |
