# Prometheus Metrics Usage Guide

## Overview

AutoBot's Prometheus metrics system provides comprehensive monitoring for workflows, tasks, GitHub operations, and system performance.

## Accessing Metrics

**Metrics Endpoint:** `GET /api/monitoring/metrics`

Returns metrics in Prometheus text format for scraping.

**Health Check:** `GET /api/monitoring/health/metrics`

Verifies metrics collection is working and lists all available metric categories.

## Metric Categories

### 1. Workflow Metrics

Track workflow execution, duration, steps, and approvals.

#### Available Metrics

- `autobot_workflow_executions_total` - Total workflow executions (labels: workflow_type, status)
- `autobot_workflow_duration_seconds` - Workflow execution duration histogram (labels: workflow_type)
- `autobot_workflow_steps_executed_total` - Total workflow steps executed (labels: workflow_type, step_type, status)
- `autobot_active_workflows` - Currently active workflows gauge (labels: workflow_type)
- `autobot_workflow_approvals_total` - Total workflow approval requests (labels: workflow_type, decision)

#### Usage Example

```python
from src.monitoring.prometheus_metrics import get_metrics_manager
import time

# Get metrics manager
metrics = get_metrics_manager()

# Record workflow execution
workflow_type = "code_review"
start_time = time.time()

try:
    # Execute workflow...

    # Record successful execution
    duration = time.time() - start_time
    metrics.record_workflow_execution(
        workflow_type="code_review",
        status="success",
        duration=duration
    )

    # Record workflow steps
    metrics.record_workflow_step(
        workflow_type="code_review",
        step_type="analysis",
        status="completed"
    )

except Exception as e:
    # Record failed execution
    duration = time.time() - start_time
    metrics.record_workflow_execution(
        workflow_type="code_review",
        status="failed",
        duration=duration
    )

# Update active workflows count
metrics.update_active_workflows("code_review", 3)

# Record approval decision
metrics.record_workflow_approval(
    workflow_type="code_review",
    decision="approved"
)
```

### 2. GitHub Integration Metrics

Track GitHub API operations, rate limits, commits, PRs, and issues.

#### Available Metrics

- `autobot_github_operations_total` - Total GitHub API operations (labels: operation, status)
- `autobot_github_api_duration_seconds` - GitHub API call duration histogram (labels: operation)
- `autobot_github_rate_limit_remaining` - GitHub API rate limit remaining gauge (labels: resource_type)
- `autobot_github_commits_total` - Total GitHub commits created (labels: repository, status)
- `autobot_github_pull_requests_total` - Total GitHub pull requests (labels: repository, action, status)
- `autobot_github_issues_total` - Total GitHub issues (labels: repository, action, status)

#### Usage Example

```python
from src.monitoring.prometheus_metrics import get_metrics_manager
import time

metrics = get_metrics_manager()

# Record GitHub API operation
start_time = time.time()
try:
    # Make GitHub API call...
    response = github_client.create_commit(...)

    duration = time.time() - start_time
    metrics.record_github_operation(
        operation="create_commit",
        status="success",
        duration=duration
    )

    # Record commit
    metrics.record_github_commit(
        repository="owner/repo",
        status="created"
    )

    # Update rate limit
    metrics.update_github_rate_limit(
        resource_type="core",
        remaining=response.rate_limit.remaining
    )

except Exception as e:
    duration = time.time() - start_time
    metrics.record_github_operation(
        operation="create_commit",
        status="failed",
        duration=duration
    )

# Record pull request operations
metrics.record_github_pull_request(
    repository="owner/repo",
    action="create",
    status="success"
)

# Record issue operations
metrics.record_github_issue(
    repository="owner/repo",
    action="update",
    status="success"
)
```

### 3. Task Execution Metrics

Track task execution, duration, queues, and retries.

#### Available Metrics

- `autobot_tasks_executed_total` - Total tasks executed (labels: task_type, agent_type, status)
- `autobot_task_duration_seconds` - Task execution duration histogram (labels: task_type, agent_type)
- `autobot_active_tasks` - Currently active tasks gauge (labels: task_type, agent_type)
- `autobot_task_queue_size` - Tasks in queue gauge (labels: priority)
- `autobot_task_retries_total` - Total task retry attempts (labels: task_type, reason)

#### Usage Example

```python
from src.monitoring.prometheus_metrics import get_metrics_manager
import time

metrics = get_metrics_manager()

# Record task execution
task_type = "code_analysis"
agent_type = "code-reviewer"
start_time = time.time()

try:
    # Update active tasks
    metrics.update_active_tasks(task_type, agent_type, 5)

    # Execute task...

    # Record successful execution
    duration = time.time() - start_time
    metrics.record_task_execution(
        task_type=task_type,
        agent_type=agent_type,
        status="success",
        duration=duration
    )

except Exception as e:
    # Record retry attempt
    metrics.record_task_retry(
        task_type=task_type,
        reason="timeout"
    )

    # Record failed execution
    duration = time.time() - start_time
    metrics.record_task_execution(
        task_type=task_type,
        agent_type=agent_type,
        status="failed",
        duration=duration
    )

# Update queue sizes
metrics.update_task_queue_size("high", 10)
metrics.update_task_queue_size("normal", 25)
metrics.update_task_queue_size("low", 5)
```

### 4. Redis & Performance Metrics

#### Available Metrics

- `autobot_timeout_total` - Total timeout events (labels: operation_type, database, status)
- `autobot_operation_duration_seconds` - Operation duration histogram (labels: operation_type, database)
- `autobot_timeout_rate` - Percentage of operations timing out (labels: operation_type, database, time_window)
- `autobot_redis_pool_connections` - Redis connection pool metrics (labels: database, state)
- `autobot_redis_pool_saturation_ratio` - Redis pool saturation ratio (labels: database)
- `autobot_circuit_breaker_events_total` - Circuit breaker events (labels: database, event, reason)
- `autobot_circuit_breaker_state` - Circuit breaker state gauge (labels: database)
- `autobot_circuit_breaker_failure_count` - Failures before circuit opens (labels: database)
- `autobot_redis_requests_total` - Total Redis requests (labels: database, operation, status)
- `autobot_redis_success_rate` - Redis operation success rate (labels: database, time_window)

#### Usage Example

```python
from src.monitoring.prometheus_metrics import get_metrics_manager
import time

metrics = get_metrics_manager()

# Record operation duration
start_time = time.time()
try:
    # Perform Redis operation...
    result = redis_client.get(key)

    duration = time.time() - start_time
    metrics.record_operation_duration(
        operation_type="redis_get",
        database="main",
        duration=duration
    )

    # Record successful request
    metrics.record_request(
        database="main",
        operation="get",
        success=True
    )

except TimeoutError:
    # Record timeout
    metrics.record_timeout(
        operation_type="redis_get",
        database="main",
        timed_out=True
    )

# Update connection pool stats
metrics.update_connection_pool(
    database="main",
    active=10,
    idle=5,
    max_connections=20
)

# Record circuit breaker event
metrics.record_circuit_breaker_event(
    database="main",
    event="opened",
    reason="too_many_failures"
)

# Update circuit breaker state
metrics.update_circuit_breaker_state(
    database="main",
    state="open",
    failure_count=5
)
```

## Prometheus Configuration

### Scrape Configuration

Add to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'autobot'
    scrape_interval: 15s
    metrics_path: '/api/monitoring/metrics'
    static_configs:
      - targets: ['172.16.168.20:8001']
```

### Alert Rules

Example Prometheus alert rules:

```yaml
groups:
  - name: autobot_alerts
    rules:
      # Workflow alerts
      - alert: HighWorkflowFailureRate
        expr: |
          rate(autobot_workflow_executions_total{status="failed"}[5m])
          / rate(autobot_workflow_executions_total[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High workflow failure rate"
          description: "{{ $value }}% of workflows are failing"

      # GitHub rate limit alerts
      - alert: GitHubRateLimitLow
        expr: autobot_github_rate_limit_remaining < 100
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "GitHub rate limit running low"
          description: "Only {{ $value }} API calls remaining"

      # Task queue alerts
      - alert: HighPriorityTaskQueueBacklog
        expr: autobot_task_queue_size{priority="high"} > 50
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High priority task queue backlog"
          description: "{{ $value }} high priority tasks waiting"

      # Redis performance alerts
      - alert: RedisPoolSaturationHigh
        expr: autobot_redis_pool_saturation_ratio > 0.8
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Redis connection pool saturation high"
          description: "Pool is {{ $value }}% saturated"
```

## Grafana Dashboard

### Sample Queries

**Workflow Success Rate:**
```promql
sum(rate(autobot_workflow_executions_total{status="success"}[5m]))
/ sum(rate(autobot_workflow_executions_total[5m]))
```

**Average Workflow Duration:**
```promql
histogram_quantile(0.95,
  rate(autobot_workflow_duration_seconds_bucket[5m])
)
```

**GitHub API Call Rate:**
```promql
sum(rate(autobot_github_operations_total[5m])) by (operation)
```

**Active Tasks by Agent:**
```promql
sum(autobot_active_tasks) by (agent_type)
```

**Task Queue Depth:**
```promql
sum(autobot_task_queue_size) by (priority)
```

## Best Practices

1. **Always record duration with execution:** Provides visibility into performance trends
2. **Use descriptive labels:** Makes querying and alerting easier
3. **Record both successes and failures:** Essential for calculating success rates
4. **Update gauges regularly:** Keep current state metrics accurate
5. **Monitor rate limits:** Especially important for GitHub operations
6. **Track queue depths:** Early warning for capacity issues
7. **Use histograms for latency:** Better than averages for understanding performance

## Troubleshooting

### Metrics not appearing

1. Check metrics endpoint: `curl http://localhost:8001/api/monitoring/metrics`
2. Verify health check: `curl http://localhost:8001/api/monitoring/health/metrics`
3. Check logs: `tail -f logs/backend.log | grep prometheus`

### High cardinality warnings

If you see warnings about high cardinality:
- Review label values - are they unbounded?
- Avoid using IDs or timestamps as labels
- Use fixed sets of labels (status: success/failed, not error messages)

### Missing metrics after deployment

- Metrics reset on restart (counters start at 0)
- Gauges need to be explicitly set after restart
- Consider persisting metric state if needed

## See Also

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Dashboards](https://grafana.com/docs/)
- [Metric Naming Best Practices](https://prometheus.io/docs/practices/naming/)
- [AutoBot Monitoring API](../api/COMPREHENSIVE_API_DOCUMENTATION.md#monitoring)
