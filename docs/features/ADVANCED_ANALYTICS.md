# Advanced Analytics & Business Intelligence

**Author**: mrveiss
**Copyright**: © 2025 mrveiss
**Related Issue**: [#59 - Advanced Analytics & Business Intelligence](https://github.com/mrveiss/AutoBot-AI/issues/59)

## Overview

AutoBot's Advanced Analytics & Business Intelligence module provides comprehensive analytics capabilities for tracking user behavior, agent performance, system costs, and predictive maintenance recommendations.

## Features

### 1. User Behavior Analytics

Track and analyze how users interact with the AutoBot platform:

- **Feature usage tracking** - Monitor which features are used most frequently
- **Session behavior analysis** - Understand user session patterns
- **User journey mapping** - Track the path users take through the platform
- **Engagement metrics** - Sessions, page views, time on feature
- **Usage heatmaps** - Hourly usage patterns visualization

**API Endpoints:**
```
GET /api/analytics/behavior/engagement    - Engagement metrics
GET /api/analytics/behavior/features      - Feature usage stats
GET /api/analytics/behavior/stats/heatmap - Usage heatmap data
GET /api/analytics/behavior/journey/{id}  - User journey tracking
```

### 2. Agent Performance Analytics

Comprehensive monitoring of AI agent operations:

- **Task completion rates** - Track success vs failure
- **Execution time tracking** - Monitor agent speed
- **Error rate analysis** - Identify problematic agents
- **Agent comparison** - Compare agent performance
- **Historical trends** - Performance over time

**API Endpoints:**
```
GET /api/analytics/agents/performance     - All agents metrics
GET /api/analytics/agents/compare         - Agent comparison
GET /api/analytics/agents/{id}/history    - Agent task history
GET /api/analytics/agents/recommendations - Performance recommendations
```

### 3. Cost Tracking and Optimization

LLM cost management and forecasting:

- **Cost summaries** - Total and daily costs by model
- **Trend analysis** - Cost direction and growth rate
- **Cost forecasting** - Predict future costs
- **Budget alerts** - Set spending thresholds
- **Model pricing** - Current pricing information

**API Endpoints:**
```
GET  /api/analytics/cost/summary          - Cost summary
GET  /api/analytics/cost/trends           - Cost trends
GET  /api/analytics/cost/forecast         - Cost forecast
GET  /api/analytics/cost/by-model         - Cost by model
POST /api/analytics/cost/budget-alert     - Create budget alert
GET  /api/analytics/cost/budget-status    - Budget status
```

### 4. Predictive Maintenance

AI-powered analysis to predict and prevent issues:

- **Agent health monitoring** - Detect degrading agents
- **Cost anomaly detection** - Identify unusual spending
- **Resource monitoring** - Redis memory, cache hit rates
- **Proactive recommendations** - Fix issues before they impact users

**Priority Levels:**
- `critical` - Requires immediate attention
- `high` - Address within 24 hours
- `medium` - Schedule for maintenance window
- `low` - Nice to have improvements

**API Endpoints:**
```
GET /api/analytics/advanced/maintenance           - All recommendations
GET /api/analytics/advanced/maintenance/summary   - Summary for dashboard
GET /api/analytics/advanced/maintenance/category/{cat} - By category
```

### 5. Resource Optimization

Identify opportunities for cost savings and performance improvements:

- **LLM token optimization** - Model substitution, prompt caching
- **Agent task optimization** - Reduce failed tasks
- **Cache optimization** - Improve cache hit rates
- **Quick wins** - Low-effort, high-impact recommendations

**API Endpoints:**
```
GET /api/analytics/advanced/optimization            - All recommendations
GET /api/analytics/advanced/optimization/quick-wins - Low-effort improvements
GET /api/analytics/advanced/optimization/type/{type} - By resource type
```

### 6. Custom Report Generation

Generate tailored analytics reports:

- **Executive reports** - High-level summary with key metrics
- **Technical reports** - Detailed technical analysis
- **Cost reports** - Cost breakdown and optimization
- **Performance reports** - Agent and system performance

**API Endpoints:**
```
POST /api/analytics/advanced/report      - Generate custom report
GET  /api/analytics/advanced/report/executive - Quick executive summary
```

### 7. Export to BI Tools

Export analytics data for external analysis:

- **CSV exports** - Costs, agents, usage records
- **JSON exports** - Complete analytics snapshot
- **Prometheus format** - For Grafana scraping
- **Grafana dashboard** - Pre-configured dashboard JSON

**API Endpoints:**
```
GET /api/analytics/export/csv/costs          - Cost data CSV
GET /api/analytics/export/csv/agents         - Agent data CSV
GET /api/analytics/export/csv/usage          - Usage records CSV
GET /api/analytics/export/json/full          - Full JSON export
GET /api/analytics/export/prometheus         - Prometheus metrics
GET /api/analytics/export/grafana-dashboard  - Grafana dashboard JSON
```

## Architecture

### Backend Services

The analytics system consists of several specialized services:

```
backend/services/
├── analytics_service.py       # Centralized facade (Issue #59)
├── user_behavior_analytics.py # User behavior tracking
├── agent_analytics.py         # Agent performance tracking
└── llm_cost_tracker.py        # LLM cost tracking

backend/api/
├── analytics_maintenance.py      # Predictive maintenance & optimization
├── analytics_behavior.py      # User behavior endpoints
├── analytics_agents.py        # Agent analytics endpoints
├── analytics_cost.py          # Cost analytics endpoints
├── analytics_export.py        # Export functionality
└── analytics_reporting.py       # Unified dashboard
```

### Frontend Components

```
autobot-vue/src/
├── views/
│   └── AnalyticsView.vue     # Main analytics page (Issue #59)
└── components/analytics/
    ├── AdvancedAnalytics.vue # Tabbed analytics interface
    ├── AnalyticsHeader.vue   # Reusable header component
    └── EnhancedAnalyticsGrid.vue # Dashboard grid
```

### Data Storage

All analytics data is stored in Redis for real-time performance:

- **Database 4** (`RedisDatabase.ANALYTICS`) - Analytics data
- **Stream-based event storage** - For recent events
- **Hash-based aggregations** - For metrics summaries
- **TTL-based retention** - Automatic cleanup

## Usage Examples

### Track User Event (Backend)

```python
from backend.services.user_behavior_analytics import get_behavior_analytics, UserEvent

analytics = get_behavior_analytics()

event = UserEvent(
    event_type="page_view",
    feature="chat",
    user_id="user123",
    session_id="session456",
    duration_ms=5000
)

await analytics.track_event(event)
```

### Track Agent Task (Backend)

```python
from backend.services.agent_analytics import get_agent_analytics, TaskStatus

analytics = get_agent_analytics()

# Start tracking
record = await analytics.track_task_start(
    agent_id="chat-agent-1",
    agent_type="chat",
    task_id="task-123",
    task_name="Process user query"
)

# ... agent does work ...

# Complete tracking
await analytics.track_task_complete(
    task_id="task-123",
    status=TaskStatus.COMPLETED,
    tokens_used=1500
)
```

### Get Predictive Maintenance (API)

```bash
curl http://localhost:8001/api/analytics/advanced/maintenance
```

Response:
```json
{
  "timestamp": "2025-01-15T10:30:00Z",
  "total_recommendations": 3,
  "by_priority": {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 0
  },
  "recommendations": [
    {
      "id": "agent-error-chat-1",
      "title": "High Error Rate: chat-1",
      "description": "Agent chat-1 has an error rate of 25.5%",
      "priority": "high",
      "category": "agent_performance",
      "affected_component": "agent:chat-1",
      "predicted_issue": "Continued degradation may lead to task failures",
      "confidence": 0.85,
      "recommended_action": "Review agent logs, check for pattern issues",
      "estimated_impact": "Affects 150 tasks"
    }
  ]
}
```

### Generate Executive Report (API)

```bash
curl -X POST http://localhost:8001/api/analytics/advanced/report \
  -H "Content-Type: application/json" \
  -d '{"report_type": "executive", "days": 30}'
```

## Configuration

### Prometheus Integration

Add to your Prometheus configuration:

```yaml
scrape_configs:
  - job_name: 'autobot'
    static_configs:
      - targets: ['172.16.168.20:8001']
    metrics_path: '/api/analytics/export/prometheus'
    scrape_interval: 30s
```

### Grafana Dashboard Import

1. Download dashboard: `GET /api/analytics/export/grafana-dashboard`
2. In Grafana: Dashboards → Import → Upload JSON
3. Select Prometheus data source
4. Click Import

### Budget Alerts

Configure budget alerts to monitor spending:

```bash
curl -X POST http://localhost:8001/api/analytics/cost/budget-alert \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Monthly Budget",
    "threshold_usd": 100.00,
    "period": "monthly",
    "notify_at_percent": [50, 75, 90, 100]
  }'
```

## Best Practices

1. **Review maintenance recommendations weekly** - Proactive maintenance prevents issues
2. **Set budget alerts early** - Don't wait for cost overruns
3. **Export data regularly** - Maintain backup of analytics
4. **Monitor agent error rates** - Address agents > 10% error rate
5. **Track cost trends** - Take action on > 20% growth rate

## Troubleshooting

### No Analytics Data

1. Verify Redis connection: `curl http://localhost:8001/api/redis/health`
2. Check Redis database 4 has data: `redis-cli -n 4 KEYS "*"`
3. Verify analytics middleware is active

### High Memory Usage

1. Check Redis memory: `GET /api/analytics/advanced/maintenance`
2. Review data retention settings
3. Consider reducing event stream size

### Slow Dashboard Loading

1. Use summary endpoints for widgets
2. Limit date range for queries
3. Enable Redis pipelining (already implemented)

## Related Documentation

- [API Documentation](../api/COMPREHENSIVE_API_DOCUMENTATION.md)
- [System State](../system-state.md)
- [Redis Client Usage](../developer/REDIS_CLIENT_USAGE.md)
