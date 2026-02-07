# GitHub Metrics Integration Pattern

**Date**: 2025-01-15
**Issue**: #22 - Prometheus Metrics Integration
**Status**: Documentation - GitHub metrics usage pattern

---

## Overview

AutoBot uses **GitHub MCP tools** (mcp__github__*) for GitHub operations rather than a dedicated API wrapper. This means GitHub metrics must be recorded at the **application code level** when using these MCP tools.

## Available GitHub Metrics

The `PrometheusMetricsManager` provides the following GitHub metrics recording methods:

### 1. General GitHub Operations
```python
from src.monitoring.prometheus_metrics import get_metrics_manager

metrics = get_metrics_manager()

# Record any GitHub API operation
metrics.record_github_operation(
    operation="create_issue",
    status="success",
    duration=1.23  # Optional: API call duration in seconds
)
```

**Available operations**:
- `create_issue`
- `update_issue`
- `close_issue`
- `create_pull_request`
- `merge_pull_request`
- `create_commit`
- `push_files`
- `fork_repository`
- `create_branch`
- `list_issues`
- `list_pull_requests`
- `search_repositories`
- Any other GitHub operation

**Status values**: `"success"` | `"error"`

---

### 2. GitHub Rate Limit Tracking
```python
# After making a GitHub API call, update rate limit
metrics.update_github_rate_limit(
    resource_type="core",  # or "search", "graphql"
    remaining=4999  # From X-RateLimit-Remaining header
)
```

**Resource types**:
- `core` - Core API endpoints (5000 requests/hour)
- `search` - Search API endpoints (30 requests/minute)
- `graphql` - GraphQL API (5000 points/hour)

---

### 3. GitHub Commits
```python
# Record commit creation
metrics.record_github_commit(
    repository="mrveiss/AutoBot-AI",
    status="success"
)
```

---

### 4. GitHub Pull Requests
```python
# Record PR operations
metrics.record_github_pull_request(
    repository="mrveiss/AutoBot-AI",
    action="create",  # or "update", "merge", "close"
    status="success"
)
```

---

### 5. GitHub Issues
```python
# Record issue operations
metrics.record_github_issue(
    repository="mrveiss/AutoBot-AI",
    action="create",  # or "update", "close", "comment"
    status="success"
)
```

---

## Integration Pattern

Since GitHub operations use MCP tools, metrics should be recorded **immediately after** successful tool calls:

### Example: Creating an Issue

```python
import time
from src.monitoring.prometheus_metrics import get_metrics_manager

metrics = get_metrics_manager()

# Start timing
start_time = time.time()

try:
    # Use MCP tool to create issue
    result = await mcp__github__create_issue(
        owner="mrveiss",
        repo="AutoBot-AI",
        title="Example Issue",
        body="Issue description",
        labels=["bug"]
    )

    # Record metrics on success
    duration = time.time() - start_time
    metrics.record_github_operation(
        operation="create_issue",
        status="success",
        duration=duration
    )
    metrics.record_github_issue(
        repository="mrveiss/AutoBot-AI",
        action="create",
        status="success"
    )

    # Update rate limit if available in response
    if "rate_limit" in result:
        metrics.update_github_rate_limit(
            resource_type="core",
            remaining=result["rate_limit"]["remaining"]
        )

except Exception as e:
    # Record metrics on error
    duration = time.time() - start_time
    metrics.record_github_operation(
        operation="create_issue",
        status="error",
        duration=duration
    )
    metrics.record_github_issue(
        repository="mrveiss/AutoBot-AI",
        action="create",
        status="error"
    )
    raise
```

---

## Where to Add GitHub Metrics

### Recommended Integration Points

1. **Backend API Endpoints** - When GitHub operations are triggered via API
   - Example: `autobot-user-backend/api/github_integration.py` (if exists)
   - Pattern: Wrap MCP tool calls with metrics

2. **Agent Code** - When agents perform GitHub operations
   - Example: `autobot-user-backend/agents/github_agent.py` (if exists)
   - Pattern: Record metrics in agent execution methods

3. **Workflow Automation** - When workflows include GitHub steps
   - Example: Already integrated in `autobot-user-backend/api/workflow_automation.py`
   - Pattern: Add GitHub-specific metrics for GitHub workflow steps

4. **Chat Handlers** - When chat commands trigger GitHub operations
   - Example: `autobot-user-backend/api/chat.py` (if exists)
   - Pattern: Record metrics after MCP tool calls

---

## Best Practices

### 1. Always Record Duration
```python
start_time = time.time()
# ... GitHub operation ...
duration = time.time() - start_time
metrics.record_github_operation(..., duration=duration)
```

### 2. Always Record Both Success and Error
```python
try:
    # GitHub operation
    metrics.record_github_operation(operation="...", status="success")
except Exception:
    metrics.record_github_operation(operation="...", status="error")
    raise
```

### 3. Use Specific Metrics When Available
```python
# ✅ GOOD - Use specific metric for commits
metrics.record_github_commit(repository="...", status="success")

# ❌ LESS GOOD - Generic operation metric only
metrics.record_github_operation(operation="create_commit", status="success")

# ✅ BEST - Use both for comprehensive tracking
metrics.record_github_operation(operation="create_commit", status="success", duration=1.23)
metrics.record_github_commit(repository="...", status="success")
```

### 4. Always Include Repository Name
```python
# Use full repository name: owner/repo
metrics.record_github_commit(repository="mrveiss/AutoBot-AI", status="success")
```

---

## Monitoring and Alerts

### Prometheus Queries

**GitHub operation success rate**:
```promql
rate(autobot_github_operations_total{status="success"}[5m])
/ rate(autobot_github_operations_total[5m])
```

**GitHub API rate limit status**:
```promql
autobot_github_rate_limit_remaining{resource_type="core"}
```

**GitHub operation duration (p95)**:
```promql
histogram_quantile(0.95, rate(autobot_github_api_duration_seconds_bucket[5m]))
```

---

## Future Enhancements

1. **Automatic Rate Limit Tracking** - Intercept MCP tool responses to auto-record rate limits
2. **GitHub API Wrapper** - Create a wrapper around MCP tools with built-in metrics
3. **Centralized GitHub Service** - Single service layer for all GitHub operations with automatic metrics

---

## Related Documentation

- Prometheus Metrics Manager: `src/monitoring/prometheus_metrics.py`
- Issue #22: Prometheus Metrics Integration
- GitHub MCP Tools: Available via `mcp__github__*` functions

**Status**: ✅ Pattern documented - Ready for integration at application level
