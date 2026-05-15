# Use the codebase analytics engine to programmatically retrieve the API coverage report for a local project

AutoBot's codebase analytics engine indexes a local project, cross-references backend endpoint definitions with frontend API calls, and produces a coverage report showing which endpoints are used, orphaned, or missing.

## Full workflow

```python
import httpx
import time

BASE_URL = "https://autobot.example.com:8443/api"
TOKEN    = "your-jwt-token"

client = httpx.Client(
    base_url=BASE_URL,
    headers={"Authorization": f"Bearer {TOKEN}"},
    verify=False,
)

# ── Step 1: Register the local project as a code source ──────────────────────
source = client.post("/analytics/codebase/sources", json={
    "name":        "my-project",
    "source_type": "local",
    "branch":      "main",
    "access":      "private",
}).json()

source_id = source["id"]
print(f"Registered source: {source_id}")

# ── Step 2: Index the project ─────────────────────────────────────────────────
index_job = client.post("/analytics/codebase/index", json={
    "source_id": source_id,
    # Or use root_path for a path directly accessible to the backend:
    # "root_path": "/opt/projects/my-project"
}).json()

task_id = index_job["task_id"]
print(f"Indexing started: {task_id}")

# Poll until indexing completes
while True:
    status = client.get(f"/analytics/codebase/index/status/{task_id}").json()
    pct = status.get("progress", {}).get("percent", 0)
    print(f"  indexing... {pct}%")
    if status["status"] in ("completed", "failed"):
        break
    time.sleep(3)

if status["status"] == "failed":
    raise RuntimeError(f"Indexing failed: {status.get('message')}")

print("Indexing complete.")

# ── Step 3: Retrieve the API coverage report ──────────────────────────────────
coverage = client.get("/analytics/codebase/endpoint-coverage").json()

summary = coverage["summary"]
print(f"\nAPI Coverage Report")
print(f"  Backend endpoints:   {summary['backend_endpoints']}")
print(f"  Frontend API calls:  {summary['frontend_calls']}")
print(f"  Used endpoints:      {summary['used_endpoints']}")
print(f"  Orphaned endpoints:  {summary['orphaned_endpoints']}")
print(f"  Missing endpoints:   {summary['missing_endpoints']}")
print(f"  Coverage:            {summary['coverage_percentage']:.1f}%")
print(f"  Scanned at:          {coverage['scan_timestamp']}")
```

## Coverage report endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /analytics/codebase/endpoint-coverage` | Summary + full endpoint coverage analysis |
| `GET /analytics/codebase/api-endpoints` | All backend API endpoints discovered |
| `GET /analytics/codebase/api-calls` | All frontend API calls discovered |
| `GET /analytics/codebase/orphaned-endpoints` | Endpoints defined but never called from frontend |
| `GET /analytics/codebase/missing-endpoints` | Endpoints called from frontend but not defined |
| `GET /analytics/codebase/used-endpoints` | Active endpoints with call counts |
| `POST /analytics/codebase/refresh-endpoint-cache` | Force re-analysis (clears cache) |

## Coverage report response shape

```json
{
  "summary": {
    "backend_endpoints":   47,
    "frontend_calls":      39,
    "used_endpoints":      35,
    "orphaned_endpoints":   12,
    "missing_endpoints":    4,
    "coverage_percentage": 74.5
  },
  "scan_timestamp": "2025-10-15T14:30:00Z"
}
```

`coverage_percentage` = `used_endpoints / backend_endpoints * 100`

## Retrieve detailed endpoint lists

```python
# All orphaned endpoints (defined but never called)
orphaned = client.get("/analytics/codebase/orphaned-endpoints").json()
for ep in orphaned.get("endpoints", []):
    print(f"  ORPHANED  {ep['method']} {ep['path']}  ({ep['file']})")

# All missing endpoints (called but not defined)
missing = client.get("/analytics/codebase/missing-endpoints").json()
for ep in missing.get("endpoints", []):
    print(f"  MISSING   {ep['method']} {ep['path']}  (called from {ep['caller_file']})")

# Full analysis in one call
analysis = client.get("/analytics/codebase/endpoint-analysis").json()
```

## Source registration — `CodeSourceCreateRequest` model

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | required | Human-readable project name |
| `source_type` | `local` or `github` | required | How to access the project |
| `repo` | string | — | `owner/repo` (GitHub only) |
| `branch` | string | `main` | Branch to index |
| `credential_id` | string | — | GitHub token secret ID (GitHub only) |
| `access` | `private`, `shared`, `public` | required | Visibility scope |

## Indexing status values

| Status | Meaning |
|--------|---------|
| `started` | Indexing job queued |
| `running` | Actively scanning files |
| `completed` | Index ready — coverage reports available |
| `failed` | Check `message` field for error detail |

## Codebase statistics alongside coverage

The indexer also produces file-level statistics accessible at `GET /analytics/codebase/stats`:

```json
{
  "total_files":      312,
  "total_lines":      48291,
  "python_files":     187,
  "javascript_files":  43,
  "vue_files":         82,
  "total_functions":  1204,
  "total_classes":     156,
  "average_file_size": 154.8,
  "last_indexed":     "2025-10-15T14:30:00Z"
}
```

## Architecture reference

- **Source registry** — `autobot-backend/api/codebase_analytics/endpoints/sources.py`
- **Indexing job** — `autobot-backend/api/codebase_analytics/endpoints/indexing.py`
- **Coverage endpoints** — `autobot-backend/api/codebase_analytics/endpoints/api_endpoints.py`
- **Data models** — `autobot-backend/api/codebase_analytics/models.py`
- **Storage** (ChromaDB + Redis) — `autobot-backend/api/codebase_analytics/storage.py`
- **Router** — `autobot-backend/api/codebase_analytics/router.py`
