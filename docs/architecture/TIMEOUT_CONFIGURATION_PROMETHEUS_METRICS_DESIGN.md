# Timeout Configuration & Prometheus Metrics Architecture Design

**Design Document for KB-ASYNC-014 and KB-ASYNC-015**

**Version:** 1.0
**Date:** 2025-10-10
**Status:** Design Phase - Awaiting Review & Approval

---

## Executive Summary

This document provides a comprehensive architectural design for moving hardcoded timeout values to centralized configuration (KB-ASYNC-014) and implementing Prometheus metrics for timeout tracking and performance monitoring (KB-ASYNC-015).

**Current State:**
- Hardcoded timeouts: 2s (Redis), 10s (LlamaIndex), 30s (documents)
- No centralized timeout management
- No Prometheus metrics integration
- Limited visibility into timeout events and performance

**Target State:**
- Hierarchical, environment-aware timeout configuration
- Prometheus metrics for comprehensive monitoring
- Real-time alerting on timeout anomalies
- Production-ready observability infrastructure

---

## Part 1: Timeout Configuration Architecture (KB-ASYNC-014)

### 1.1 Configuration Schema Design

#### **Proposed config.yaml Structure**

```yaml
# Timeout configuration (all values in seconds)
timeouts:
  # Redis operation timeouts
  redis:
    # Connection-level timeouts
    connection:
      socket_connect: 2.0      # Initial connection establishment
      socket_timeout: 2.0      # Individual socket operations
      health_check: 1.0        # Quick health check pings

    # Operation-level timeouts
    operations:
      get: 1.0                 # Simple key retrieval
      set: 1.0                 # Simple key storage
      hgetall: 2.0             # Hash retrieval
      pipeline: 5.0            # Batch pipeline execution
      scan_iter: 10.0          # Large key scans
      ft_info: 2.0             # Search index info
      flushdb: 30.0            # Database flush (destructive)

    # Circuit breaker timeouts
    circuit_breaker:
      timeout: 60.0            # How long circuit stays open
      threshold: 5             # Failures before opening circuit

  # LlamaIndex / Vector operations
  llamaindex:
    embedding:
      generation: 10.0         # Single embedding generation
      batch: 30.0              # Batch embedding generation

    indexing:
      single_document: 10.0    # Index single document
      batch_documents: 60.0    # Index multiple documents
      vector_store_init: 10.0  # Initialize vector store

    search:
      query: 10.0              # Semantic search query
      hybrid: 15.0             # Hybrid search (vector + text)

  # Document processing timeouts
  documents:
    processing:
      pdf_extraction: 30.0     # Extract text from PDF
      text_chunking: 5.0       # Chunk text for indexing
      metadata_extraction: 3.0 # Extract metadata

    operations:
      add_document: 30.0       # Complete document addition
      batch_upload: 120.0      # Multiple document upload
      export: 60.0             # Export knowledge base

  # HTTP / API timeouts
  http:
    standard: 30.0             # Standard HTTP request
    long_running: 120.0        # Long-running operations
    streaming: 300.0           # Streaming responses

  # LLM timeouts
  llm:
    default: 120.0             # Default LLM generation
    fast: 30.0                 # Quick responses
    reasoning: 300.0           # Deep reasoning tasks

# Environment-specific overrides
environments:
  development:
    timeouts:
      redis:
        operations:
          scan_iter: 30.0      # More lenient for debugging
      llamaindex:
        search:
          query: 20.0          # More time for debugging

  production:
    timeouts:
      redis:
        operations:
          get: 0.5             # Tighter for production
          set: 0.5
      llamaindex:
        search:
          query: 5.0           # Faster production queries
```

#### **Configuration Access Pattern**

```python
# Existing UnifiedConfig method (already implemented):
timeout = config.get_timeout('redis', 'operations.get', default=2.0)

# Enhanced method for nested paths:
timeout = config.get_timeout('redis.operations', 'get', default=2.0)

# Environment-aware access (NEW):
timeout = config.get_timeout_for_env('redis.operations', 'get', environment='production')

# Batch access for related timeouts (NEW):
redis_timeouts = config.get_timeout_group('redis.operations')
# Returns: {'get': 1.0, 'set': 1.0, 'hgetall': 2.0, ...}
```

### 1.2 Implementation Strategy

#### **Phase 1: Configuration File Update**

1. **Add timeout configuration to config.yaml** (schema above)
2. **Validate with UnifiedConfig.validate()** to ensure all required keys exist
3. **Add environment-specific overrides** for dev vs prod
4. **Document timeout tuning guidelines** in configuration comments

#### **Phase 2: UnifiedConfig Enhancement**

**New methods to add to `/home/kali/Desktop/AutoBot/src/unified_config.py`:**

```python
def get_timeout_for_env(self, category: str, timeout_type: str,
                        environment: str = None, default: float = 60.0) -> float:
    """
    Get environment-aware timeout value.

    Args:
        category: Category path (e.g., 'redis.operations')
        timeout_type: Specific timeout type (e.g., 'get')
        environment: Environment name ('development', 'production')
        default: Fallback value if not found

    Returns:
        Timeout value in seconds
    """
    if environment is None:
        environment = os.getenv('AUTOBOT_ENVIRONMENT', 'production')

    # Try environment-specific override first
    env_path = f'environments.{environment}.timeouts.{category}.{timeout_type}'
    env_timeout = self.get(env_path)
    if env_timeout is not None:
        return float(env_timeout)

    # Fall back to base configuration
    base_path = f'timeouts.{category}.{timeout_type}'
    base_timeout = self.get(base_path, default)
    return float(base_timeout)

def get_timeout_group(self, category: str, environment: str = None) -> Dict[str, float]:
    """
    Get all timeouts for a category as a dictionary.

    Args:
        category: Category path (e.g., 'redis.operations')
        environment: Environment name (optional)

    Returns:
        Dictionary of timeout names to values
    """
    base_path = f'timeouts.{category}'
    base_config = self.get(base_path, {})

    if not isinstance(base_config, dict):
        return {}

    # Apply environment overrides if specified
    if environment:
        env_path = f'environments.{environment}.timeouts.{category}'
        env_overrides = self.get(env_path, {})
        base_config.update(env_overrides)

    # Convert all values to float
    return {k: float(v) for k, v in base_config.items() if isinstance(v, (int, float))}

def validate_timeouts(self) -> Dict[str, Any]:
    """
    Validate all timeout configurations.

    Returns:
        Validation report with issues and warnings
    """
    issues = []
    warnings = []

    # Check required timeout categories
    required_categories = ['redis', 'llamaindex', 'documents', 'http', 'llm']
    for category in required_categories:
        timeout_config = self.get(f'timeouts.{category}')
        if timeout_config is None:
            issues.append(f"Missing timeout configuration for '{category}'")

    # Validate timeout ranges
    all_timeouts = self.get('timeouts', {})
    def check_timeout_values(config, path=''):
        for key, value in config.items():
            current_path = f'{path}.{key}' if path else key
            if isinstance(value, dict):
                check_timeout_values(value, current_path)
            elif isinstance(value, (int, float)):
                if value <= 0:
                    issues.append(f"Invalid timeout '{current_path}': {value} (must be > 0)")
                elif value > 600:
                    warnings.append(f"Very long timeout '{current_path}': {value}s (> 10 minutes)")

    check_timeout_values(all_timeouts)

    return {
        'valid': len(issues) == 0,
        'issues': issues,
        'warnings': warnings
    }
```

#### **Phase 3: Migration from Hardcoded Values**

**Identified Hardcoded Timeouts in `/home/kali/Desktop/AutoBot/src/knowledge_base.py`:**

| Line | Current Value | Config Path | Replacement |
|------|--------------|-------------|-------------|
| 83, 228, 258, 273, 297, 361, 472, 491, 627, 772, 814, 867 | `2.0` | `timeouts.redis.operations.{operation}` | `config.get_timeout('redis.operations', 'get', 2.0)` |
| 164, 555, 594, 736, 742 | `10.0` | `timeouts.llamaindex.{operation}` | `config.get_timeout('llamaindex.indexing', 'single_document', 10.0)` |
| 684 | `30.0` | `timeouts.documents.operations.add_document` | `config.get_timeout('documents.operations', 'add_document', 30.0)` |
| 54 | `30.0` | `timeouts.llm.default` | `config.get_timeout('llm', 'default', 30.0)` |

**Migration Steps:**

1. **Create timeout accessor class for knowledge_base.py**:

```python
class KnowledgeBaseTimeouts:
    """Centralized timeout configuration for KnowledgeBase operations"""

    def __init__(self, config: UnifiedConfig):
        self.config = config

        # Cache timeout groups for performance
        self._redis_timeouts = config.get_timeout_group('redis.operations')
        self._llamaindex_timeouts = config.get_timeout_group('llamaindex.indexing')
        self._document_timeouts = config.get_timeout_group('documents.operations')

    # Redis operation timeouts
    @property
    def redis_ping(self) -> float:
        return self._redis_timeouts.get('health_check', 1.0)

    @property
    def redis_get(self) -> float:
        return self._redis_timeouts.get('get', 1.0)

    @property
    def redis_set(self) -> float:
        return self._redis_timeouts.get('set', 1.0)

    @property
    def redis_hgetall(self) -> float:
        return self._redis_timeouts.get('hgetall', 2.0)

    @property
    def redis_pipeline(self) -> float:
        return self._redis_timeouts.get('pipeline', 5.0)

    @property
    def redis_scan_iter(self) -> float:
        return self._redis_timeouts.get('scan_iter', 10.0)

    @property
    def redis_ft_info(self) -> float:
        return self._redis_timeouts.get('ft_info', 2.0)

    # LlamaIndex timeouts
    @property
    def llamaindex_indexing(self) -> float:
        return self._llamaindex_timeouts.get('single_document', 10.0)

    @property
    def llamaindex_query(self) -> float:
        return self.config.get_timeout('llamaindex.search', 'query', 10.0)

    # Document operation timeouts
    @property
    def document_add(self) -> float:
        return self._document_timeouts.get('add_document', 30.0)
```

2. **Add to KnowledgeBase.__init__()**:

```python
def __init__(self):
    # ... existing code ...

    # Initialize timeout configuration
    self.timeouts = KnowledgeBaseTimeouts(config)
```

3. **Replace hardcoded timeouts**:

```python
# Before:
await asyncio.wait_for(self.aioredis_client.ping(), timeout=2.0)

# After:
await asyncio.wait_for(self.aioredis_client.ping(), timeout=self.timeouts.redis_ping)
```

### 1.3 Configuration Validation

#### **Pre-Deployment Validation**

```python
# Validation script: scripts/validate_timeout_config.py
import yaml
from src.unified_config import config

def validate_timeout_configuration():
    """Validate timeout configuration before deployment"""

    # 1. Schema validation
    validation = config.validate_timeouts()
    if not validation['valid']:
        print("VALIDATION FAILED:")
        for issue in validation['issues']:
            print(f"  - {issue}")
        return False

    if validation['warnings']:
        print("WARNINGS:")
        for warning in validation['warnings']:
            print(f"  - {warning}")

    # 2. Environment consistency check
    environments = ['development', 'production']
    for env in environments:
        redis_timeouts = config.get_timeout_group('redis.operations', environment=env)
        print(f"\n{env.upper()} Redis timeouts:")
        for op, timeout in redis_timeouts.items():
            print(f"  {op}: {timeout}s")

    # 3. Backward compatibility check
    legacy_values = {
        'redis.operations.get': 2.0,
        'llamaindex.indexing.single_document': 10.0,
        'documents.operations.add_document': 30.0
    }

    print("\nBackward compatibility check:")
    for path, expected in legacy_values.items():
        category, operation = path.rsplit('.', 1)
        actual = config.get_timeout(category, operation)
        status = "✅" if actual == expected else "⚠️"
        print(f"  {status} {path}: expected={expected}s, actual={actual}s")

    return True

if __name__ == "__main__":
    validate_timeout_configuration()
```

### 1.4 Backward Compatibility Strategy

**Approach:**

1. **Graceful Defaults**: All timeout accessors have sensible defaults matching current hardcoded values
2. **Environment Variable Fallback**: Support `AUTOBOT_REDIS_TIMEOUT` etc. as override mechanism
3. **Gradual Migration**: Deploy configuration first, migrate code incrementally
4. **Validation Gate**: CI/CD pipeline validates timeout config before deployment

**Migration Checklist:**

- [ ] Add timeout configuration to `config.yaml`
- [ ] Implement new UnifiedConfig methods
- [ ] Create KnowledgeBaseTimeouts accessor class
- [ ] Replace hardcoded values in knowledge_base.py (15 locations)
- [ ] Update AsyncRedisManager to use centralized config
- [ ] Add validation to CI/CD pipeline
- [ ] Document timeout tuning guidelines
- [ ] Test in development environment
- [ ] Deploy to production with monitoring

---

## Part 2: Prometheus Metrics Architecture (KB-ASYNC-015)

### 2.1 Metrics Design

#### **Metric Categories**

**1. Timeout Event Metrics (Counter)**

```python
# Timeout events by operation type
autobot_timeout_total{
    operation_type="redis_get|redis_set|llamaindex_query|...",
    database="main|knowledge|cache|...",
    status="timeout|success"
}

# Circuit breaker events
autobot_circuit_breaker_events_total{
    database="main|knowledge|cache|...",
    event="opened|closed|half_open",
    reason="timeout_threshold|manual_reset"
}
```

**2. Operation Latency Metrics (Histogram)**

```python
# Operation duration distribution
autobot_operation_duration_seconds{
    operation_type="redis_get|redis_set|llamaindex_query|...",
    database="main|knowledge|cache|..."
}
# Buckets: [0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]

# Timeout ratio gauge (percentage of operations timing out)
autobot_timeout_rate{
    operation_type="...",
    database="...",
    time_window="1m|5m|15m"
}
```

**3. Redis Connection Pool Metrics (Gauge)**

```python
# Current connection pool utilization
autobot_redis_pool_connections{
    database="main|knowledge|cache|...",
    state="active|idle|total"
}

# Connection pool saturation
autobot_redis_pool_saturation_ratio{
    database="main|knowledge|cache|..."
}
# Value: active_connections / max_connections
```

**4. Circuit Breaker State Metrics (Gauge)**

```python
# Circuit breaker state (0=closed, 1=open, 2=half_open)
autobot_circuit_breaker_state{
    database="main|knowledge|cache|..."
}

# Failure count before circuit opens
autobot_circuit_breaker_failure_count{
    database="main|knowledge|cache|..."
}
```

**5. Request Success/Failure Metrics (Counter)**

```python
# Total requests by status
autobot_redis_requests_total{
    database="main|knowledge|cache|...",
    operation="get|set|hgetall|...",
    status="success|failure|timeout"
}

# Success rate gauge (derived metric)
autobot_redis_success_rate{
    database="main|knowledge|cache|...",
    time_window="1m|5m|15m"
}
```

### 2.2 Integration Architecture

#### **Prometheus Client Library Setup**

**1. Add dependency to `requirements.txt`:**

```
prometheus-client==0.20.0
```

**2. Create Prometheus metrics manager:**

**File:** `/home/kali/Desktop/AutoBot/src/monitoring/prometheus_metrics.py`

```python
"""
Prometheus Metrics Manager for AutoBot
Provides centralized metrics collection and exposure.
"""

from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest
from typing import Dict, Optional
import time

class PrometheusMetricsManager:
    """Centralized Prometheus metrics manager"""

    def __init__(self, registry: Optional[CollectorRegistry] = None):
        self.registry = registry or CollectorRegistry()

        # Initialize all metrics
        self._init_timeout_metrics()
        self._init_latency_metrics()
        self._init_connection_metrics()
        self._init_circuit_breaker_metrics()
        self._init_request_metrics()

    def _init_timeout_metrics(self):
        """Initialize timeout-related metrics"""
        self.timeout_total = Counter(
            'autobot_timeout_total',
            'Total number of timeout events',
            ['operation_type', 'database', 'status'],
            registry=self.registry
        )

    def _init_latency_metrics(self):
        """Initialize latency histogram metrics"""
        # Custom buckets optimized for our timeout ranges
        buckets = [0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]

        self.operation_duration = Histogram(
            'autobot_operation_duration_seconds',
            'Duration of operations in seconds',
            ['operation_type', 'database'],
            buckets=buckets,
            registry=self.registry
        )

        self.timeout_rate = Gauge(
            'autobot_timeout_rate',
            'Percentage of operations timing out',
            ['operation_type', 'database', 'time_window'],
            registry=self.registry
        )

    def _init_connection_metrics(self):
        """Initialize Redis connection pool metrics"""
        self.pool_connections = Gauge(
            'autobot_redis_pool_connections',
            'Redis connection pool connections',
            ['database', 'state'],
            registry=self.registry
        )

        self.pool_saturation = Gauge(
            'autobot_redis_pool_saturation_ratio',
            'Redis connection pool saturation ratio',
            ['database'],
            registry=self.registry
        )

    def _init_circuit_breaker_metrics(self):
        """Initialize circuit breaker metrics"""
        self.circuit_breaker_events = Counter(
            'autobot_circuit_breaker_events_total',
            'Total circuit breaker events',
            ['database', 'event', 'reason'],
            registry=self.registry
        )

        self.circuit_breaker_state = Gauge(
            'autobot_circuit_breaker_state',
            'Circuit breaker state (0=closed, 1=open, 2=half_open)',
            ['database'],
            registry=self.registry
        )

        self.circuit_breaker_failures = Gauge(
            'autobot_circuit_breaker_failure_count',
            'Number of failures before circuit opens',
            ['database'],
            registry=self.registry
        )

    def _init_request_metrics(self):
        """Initialize request success/failure metrics"""
        self.requests_total = Counter(
            'autobot_redis_requests_total',
            'Total Redis requests',
            ['database', 'operation', 'status'],
            registry=self.registry
        )

        self.success_rate = Gauge(
            'autobot_redis_success_rate',
            'Redis operation success rate percentage',
            ['database', 'time_window'],
            registry=self.registry
        )

    # Metric recording methods

    def record_timeout(self, operation_type: str, database: str, timed_out: bool):
        """Record a timeout event"""
        status = 'timeout' if timed_out else 'success'
        self.timeout_total.labels(
            operation_type=operation_type,
            database=database,
            status=status
        ).inc()

    def record_operation_duration(self, operation_type: str, database: str, duration: float):
        """Record operation duration"""
        self.operation_duration.labels(
            operation_type=operation_type,
            database=database
        ).observe(duration)

    def record_circuit_breaker_event(self, database: str, event: str, reason: str):
        """Record circuit breaker state change"""
        self.circuit_breaker_events.labels(
            database=database,
            event=event,
            reason=reason
        ).inc()

    def update_circuit_breaker_state(self, database: str, state: str, failure_count: int):
        """Update circuit breaker state gauge"""
        state_value = {'closed': 0, 'open': 1, 'half_open': 2}.get(state, 0)
        self.circuit_breaker_state.labels(database=database).set(state_value)
        self.circuit_breaker_failures.labels(database=database).set(failure_count)

    def update_connection_pool(self, database: str, active: int, idle: int, max_connections: int):
        """Update connection pool metrics"""
        self.pool_connections.labels(database=database, state='active').set(active)
        self.pool_connections.labels(database=database, state='idle').set(idle)
        self.pool_connections.labels(database=database, state='total').set(max_connections)

        # Calculate saturation ratio
        saturation = active / max_connections if max_connections > 0 else 0
        self.pool_saturation.labels(database=database).set(saturation)

    def record_request(self, database: str, operation: str, success: bool):
        """Record a request success or failure"""
        status = 'success' if success else 'failure'
        self.requests_total.labels(
            database=database,
            operation=operation,
            status=status
        ).inc()

    def get_metrics(self) -> bytes:
        """Get metrics in Prometheus format"""
        return generate_latest(self.registry)


# Global metrics instance
_metrics_instance: Optional[PrometheusMetricsManager] = None

def get_metrics_manager() -> PrometheusMetricsManager:
    """Get or create global metrics manager"""
    global _metrics_instance
    if _metrics_instance is None:
        _metrics_instance = PrometheusMetricsManager()
    return _metrics_instance
```

#### **3. Instrument AsyncRedisManager**

**Modifications to `/home/kali/Desktop/AutoBot/backend/utils/async_redis_manager.py`:**

```python
from src.monitoring.prometheus_metrics import get_metrics_manager

class AsyncRedisDatabase:
    def __init__(self, name: str, config: DatabaseConfig, host: str = None, port: int = None):
        # ... existing code ...

        # Prometheus metrics
        self._metrics = get_metrics_manager()

    def _record_success(self, response_time: float):
        """Record successful request"""
        # ... existing code ...

        # Record to Prometheus
        self._metrics.record_operation_duration(
            operation_type=f"redis_{getattr(self, '_current_operation', 'unknown')}",
            database=self.name,
            duration=response_time
        )
        self._metrics.record_timeout(
            operation_type=f"redis_{getattr(self, '_current_operation', 'unknown')}",
            database=self.name,
            timed_out=False
        )

    def _record_failure(self):
        """Record failed request and update circuit breaker"""
        # ... existing code ...

        # Record to Prometheus
        self._metrics.record_timeout(
            operation_type=f"redis_{getattr(self, '_current_operation', 'unknown')}",
            database=self.name,
            timed_out=True
        )

        # Update circuit breaker state
        state = 'open' if self._circuit_open else 'closed'
        self._metrics.update_circuit_breaker_state(
            database=self.name,
            state=state,
            failure_count=self._failure_count
        )

        if self._circuit_open:
            self._metrics.record_circuit_breaker_event(
                database=self.name,
                event='opened',
                reason='timeout_threshold'
            )

    async def _execute_with_retry(self, operation, *args, **kwargs):
        """Execute Redis operation with retry logic and circuit breaker"""
        # Track operation name for metrics
        self._current_operation = operation.__name__ if hasattr(operation, '__name__') else 'unknown'

        # ... existing retry logic ...

        # Update connection pool metrics
        active_connections = len(self._active_connections)
        idle_connections = self.config.max_connections - active_connections
        self._metrics.update_connection_pool(
            database=self.name,
            active=active_connections,
            idle=idle_connections,
            max_connections=self.config.max_connections
        )
```

#### **4. Add Metrics Endpoint to FastAPI**

**File:** `/home/kali/Desktop/AutoBot/autobot-user-backend/api/monitoring.py`

```python
"""
Prometheus Metrics Endpoint
"""

from fastapi import APIRouter, Response
from src.monitoring.prometheus_metrics import get_metrics_manager

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

@router.get("/metrics",
            summary="Prometheus Metrics Endpoint",
            description="Exposes metrics in Prometheus format for scraping")
async def get_metrics():
    """
    Prometheus metrics endpoint.

    Returns metrics in Prometheus text format for scraping by Prometheus server.
    """
    metrics_manager = get_metrics_manager()
    metrics_data = metrics_manager.get_metrics()

    return Response(
        content=metrics_data,
        media_type="text/plain; version=0.0.4; charset=utf-8"
    )


@router.get("/health/metrics",
            summary="Metrics Health Check",
            description="Verify metrics collection is working")
async def metrics_health():
    """Health check for metrics system"""
    try:
        metrics_manager = get_metrics_manager()
        metrics_data = metrics_manager.get_metrics()

        return {
            "status": "healthy",
            "metrics_count": len(metrics_data.decode('utf-8').split('\n')),
            "endpoint": "/monitoring/metrics"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }
```

**Register in main FastAPI app:**

```python
# In backend/fast_app_factory_fix.py or main app file
from backend.api.monitoring import router as monitoring_router

app.include_router(monitoring_router)
```

### 2.3 Prometheus Server Configuration

#### **Prometheus Configuration**

**File:** `/home/kali/Desktop/AutoBot/config/prometheus.yml`

```yaml
# Prometheus configuration for AutoBot

global:
  scrape_interval: 15s      # Scrape targets every 15 seconds
  evaluation_interval: 15s  # Evaluate rules every 15 seconds
  scrape_timeout: 10s       # Timeout for each scrape

# Scrape configurations
scrape_configs:
  - job_name: 'autobot-backend'
    static_configs:
      - targets: ['172.16.168.20:8443']  # Main machine backend
        labels:
          service: 'autobot'
          component: 'backend'
          environment: 'production'

    metrics_path: '/monitoring/metrics'

    # Scrape more frequently for critical metrics
    scrape_interval: 10s

  - job_name: 'redis-exporter'
    static_configs:
      - targets: ['172.16.168.23:9121']  # Redis exporter (if deployed)
        labels:
          service: 'redis'
          environment: 'production'

# Alerting configuration
alerting:
  alertmanagers:
    - static_configs:
        - targets: ['172.16.168.20:9093']  # Alertmanager address

# Rule files for alerting
rule_files:
  - '/etc/prometheus/alert_rules.yml'
```

**Deployment via Docker Compose:**

```yaml
# Add to compose.yml
services:
  prometheus:
    image: prom/prometheus:latest
    container_name: autobot-prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--storage.tsdb.retention.time=30d'
    volumes:
      - ./config/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - ./config/prometheus/alert_rules.yml:/etc/prometheus/alert_rules.yml:ro
      - prometheus-data:/prometheus
    ports:
      - "9090:9090"
    networks:
      - autobot-network
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    container_name: autobot-grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_INSTALL_PLUGINS=redis-datasource
    volumes:
      - grafana-data:/var/lib/grafana
      - ./config/grafana/dashboards:/etc/grafana/provisioning/dashboards:ro
    ports:
      - "3001:3000"
    networks:
      - autobot-network
    restart: unless-stopped
    depends_on:
      - prometheus

volumes:
  prometheus-data:
  grafana-data:
```

### 2.4 Alert Rules Configuration

**File:** `/home/kali/Desktop/AutoBot/config/prometheus/alert_rules.yml`

```yaml
groups:
  - name: autobot_timeout_alerts
    interval: 30s
    rules:
      # High timeout rate alert
      - alert: HighTimeoutRate
        expr: |
          (
            rate(autobot_timeout_total{status="timeout"}[5m]) /
            rate(autobot_timeout_total[5m])
          ) > 0.1
        for: 2m
        labels:
          severity: warning
          component: redis
        annotations:
          summary: "High timeout rate detected"
          description: "{{ $labels.operation_type }} on {{ $labels.database }} has >10% timeout rate (current: {{ $value | humanizePercentage }})"

      # Circuit breaker opened
      - alert: CircuitBreakerOpened
        expr: autobot_circuit_breaker_state > 0
        for: 1m
        labels:
          severity: critical
          component: redis
        annotations:
          summary: "Circuit breaker opened"
          description: "Circuit breaker for {{ $labels.database }} is open, indicating persistent failures"

      # Connection pool saturation
      - alert: ConnectionPoolSaturated
        expr: autobot_redis_pool_saturation_ratio > 0.9
        for: 3m
        labels:
          severity: warning
          component: redis
        annotations:
          summary: "Redis connection pool near saturation"
          description: "{{ $labels.database }} connection pool is {{ $value | humanizePercentage }} utilized"

      # Slow operation latency
      - alert: SlowOperationLatency
        expr: |
          histogram_quantile(0.95,
            rate(autobot_operation_duration_seconds_bucket[5m])
          ) > 5.0
        for: 5m
        labels:
          severity: warning
          component: performance
        annotations:
          summary: "95th percentile latency is high"
          description: "{{ $labels.operation_type }} on {{ $labels.database }} P95 latency is {{ $value }}s"

      # Low success rate
      - alert: LowSuccessRate
        expr: autobot_redis_success_rate{time_window="5m"} < 95
        for: 5m
        labels:
          severity: critical
          component: redis
        annotations:
          summary: "Redis success rate below 95%"
          description: "{{ $labels.database }} success rate is {{ $value }}% over last 5 minutes"

  - name: autobot_circuit_breaker_alerts
    interval: 15s
    rules:
      # Circuit breaker approaching threshold
      - alert: CircuitBreakerNearThreshold
        expr: |
          autobot_circuit_breaker_failure_count /
          (autobot_circuit_breaker_state == 0)
          > 0.8
        for: 1m
        labels:
          severity: warning
          component: redis
        annotations:
          summary: "Circuit breaker nearing threshold"
          description: "{{ $labels.database }} has {{ $value }} failures, approaching circuit breaker threshold"
```

### 2.5 Grafana Dashboard Configuration

**Dashboard JSON:** `/home/kali/Desktop/AutoBot/config/grafana/dashboards/autobot-timeouts.json`

**Dashboard Panels:**

1. **Timeout Rate Over Time** (Graph)
   - Query: `rate(autobot_timeout_total{status="timeout"}[5m])`
   - Panel type: Time series
   - Legend: `{{ operation_type }} - {{ database }}`

2. **Operation Latency Distribution** (Heatmap)
   - Query: `rate(autobot_operation_duration_seconds_bucket[5m])`
   - Panel type: Heatmap
   - Y-axis: Latency buckets

3. **Circuit Breaker States** (Status Panel)
   - Query: `autobot_circuit_breaker_state`
   - Panel type: Stat
   - Thresholds: 0=green, 1=red

4. **Connection Pool Utilization** (Gauge)
   - Query: `autobot_redis_pool_saturation_ratio * 100`
   - Panel type: Gauge
   - Units: Percent (0-100)
   - Thresholds: 0-70=green, 70-90=yellow, 90-100=red

5. **Success Rate by Database** (Bar chart)
   - Query: `autobot_redis_success_rate{time_window="5m"}`
   - Panel type: Bar gauge
   - Units: Percent

6. **Request Rate** (Graph)
   - Query: `rate(autobot_redis_requests_total[5m])`
   - Panel type: Time series
   - Stack: True

---

## Part 3: Implementation Approach

### 3.1 Development Phases

**Phase 1: Configuration Foundation (Week 1)**

1. Add timeout configuration schema to `config.yaml`
2. Implement `get_timeout_for_env()` and `get_timeout_group()` in UnifiedConfig
3. Add validation logic and validation script
4. Test configuration loading and environment overrides

**Phase 2: Code Migration (Week 1-2)**

1. Create `KnowledgeBaseTimeouts` accessor class
2. Replace all 15 hardcoded timeout locations in `knowledge_base.py`
3. Update `AsyncRedisManager` to use centralized config
4. Add integration tests for timeout configuration

**Phase 3: Prometheus Integration (Week 2)**

1. Add `prometheus-client` dependency
2. Implement `PrometheusMetricsManager` class
3. Instrument `AsyncRedisDatabase` for metrics collection
4. Add `/monitoring/metrics` endpoint to FastAPI

**Phase 4: Monitoring Infrastructure (Week 3)**

1. Deploy Prometheus server via Docker Compose
2. Configure scrape targets and alert rules
3. Deploy Grafana with pre-configured dashboards
4. Set up Alertmanager for notifications

**Phase 5: Testing & Validation (Week 3-4)**

1. Load testing to validate metrics accuracy
2. Timeout scenario testing (simulate slow operations)
3. Circuit breaker testing (force failures)
4. Alert rule testing (trigger alerts deliberately)

**Phase 6: Production Deployment (Week 4)**

1. Deploy configuration changes to production
2. Enable Prometheus scraping
3. Activate alert rules
4. Monitor for 48 hours before declaring success

### 3.2 Testing Strategy

**Unit Tests:**

```python
# tests/unit/test_timeout_configuration.py
def test_timeout_config_loading():
    """Test timeout configuration loads correctly"""
    timeout = config.get_timeout('redis.operations', 'get')
    assert timeout == 1.0

def test_environment_overrides():
    """Test environment-specific timeout overrides"""
    dev_timeout = config.get_timeout_for_env('redis.operations', 'scan_iter', 'development')
    prod_timeout = config.get_timeout_for_env('redis.operations', 'scan_iter', 'production')
    assert dev_timeout == 30.0
    assert prod_timeout == 10.0

def test_timeout_validation():
    """Test timeout validation catches invalid values"""
    validation = config.validate_timeouts()
    assert validation['valid'] is True
    assert len(validation['issues']) == 0
```

**Integration Tests:**

```python
# tests/integration/test_prometheus_metrics.py
async def test_metrics_endpoint():
    """Test Prometheus metrics endpoint"""
    response = await client.get("/monitoring/metrics")
    assert response.status_code == 200
    assert "autobot_timeout_total" in response.text

async def test_timeout_metrics_recorded():
    """Test that timeout events are recorded in metrics"""
    # Force a timeout
    kb = KnowledgeBase()
    # ... trigger timeout scenario ...

    # Check metrics
    response = await client.get("/monitoring/metrics")
    assert "autobot_timeout_total{status=\"timeout\"}" in response.text
```

**Performance Tests:**

```python
# tests/performance/test_metrics_overhead.py
async def test_metrics_collection_overhead():
    """Ensure metrics collection adds <5ms overhead"""
    kb = KnowledgeBase()

    # Measure without metrics
    start = time.time()
    await kb.aioredis_client.get("test_key")
    baseline = time.time() - start

    # Measure with metrics
    start = time.time()
    kb._metrics.record_operation_duration("redis_get", "main", 0.001)
    overhead = time.time() - start

    assert overhead < 0.005  # Less than 5ms overhead
```

### 3.3 Rollback Plan

**If issues arise during deployment:**

1. **Configuration Rollback:**
   - Revert `config.yaml` to previous version
   - Redeploy configuration via Ansible
   - Restart affected services

2. **Code Rollback:**
   - Git revert to commit before timeout migration
   - Redeploy codebase
   - Hardcoded timeouts will be active again

3. **Metrics Rollback:**
   - Stop Prometheus scraping (comment out job in prometheus.yml)
   - Remove `/monitoring/metrics` endpoint (feature flag)
   - Metrics collection overhead eliminated

**Rollback Triggers:**

- Timeout configuration causes service disruptions
- Metrics collection overhead >10ms per operation
- Alert storm from misconfigured alert rules
- Circuit breaker false positives

### 3.4 Success Metrics

**Configuration Success Criteria:**

- [ ] All 15 hardcoded timeouts replaced with config values
- [ ] Configuration validation passes in CI/CD
- [ ] No performance degradation from config lookups
- [ ] Environment-specific timeouts working correctly

**Prometheus Success Criteria:**

- [ ] `/monitoring/metrics` endpoint returns 200 OK
- [ ] Prometheus successfully scrapes metrics every 15s
- [ ] All 5 metric categories collecting data
- [ ] Grafana dashboards display real-time data
- [ ] Alert rules trigger correctly during test scenarios
- [ ] Metrics collection overhead <5ms per operation

---

## Part 4: Operational Runbook

### 4.1 Timeout Tuning Guidelines

**When to Adjust Timeouts:**

1. **Increase Timeouts If:**
   - Timeout rate >5% for specific operation
   - Circuit breaker opening frequently (>1/hour)
   - P95 latency consistently near timeout threshold
   - Load testing reveals timeouts under expected load

2. **Decrease Timeouts If:**
   - P95 latency <50% of timeout value
   - Slow operations blocking healthy ones
   - User experience degraded by long waits

**Tuning Process:**

1. Analyze Grafana latency distribution heatmap
2. Identify P99 latency for operation
3. Set timeout = P99 + 20% buffer
4. Test in development environment
5. Deploy to production and monitor for 48 hours
6. Adjust if timeout rate >2% or circuit breaker activates

### 4.2 Alert Response Procedures

**HighTimeoutRate Alert:**

1. Check Grafana for affected operation/database
2. Investigate Redis server health (CPU, memory, network)
3. Check for slow queries or lock contention
4. Review recent code changes affecting operation
5. Increase timeout temporarily if issue unresolved
6. Create incident ticket for root cause analysis

**CircuitBreakerOpened Alert:**

1. **IMMEDIATE:** Check Redis server availability
2. Verify network connectivity between services
3. Review last 10 minutes of logs for error patterns
4. Manual circuit breaker reset if transient issue
5. Scale Redis resources if persistent load issue

**ConnectionPoolSaturated Alert:**

1. Check current connection count in Redis
2. Identify operations holding connections long-term
3. Increase `max_connections` in DatabaseConfig if needed
4. Investigate connection leaks (unclosed connections)
5. Review application connection pooling logic

### 4.3 Monitoring Dashboard Access

**Prometheus:**
- URL: `http://172.16.168.20:9090`
- Query examples:
  - Timeout rate: `rate(autobot_timeout_total{status="timeout"}[5m])`
  - Circuit breaker state: `autobot_circuit_breaker_state`

**Grafana:**
- URL: `http://172.16.168.20:3001`
- Default credentials: admin/admin
- Dashboard: "AutoBot Timeout & Performance Monitoring"

**Metrics Endpoint:**
- URL: `https://172.16.168.20:8443/monitoring/metrics`
- Format: Prometheus text format
- Refresh: Real-time

---

## Part 5: Dependencies & Prerequisites

### 5.1 Software Dependencies

**Python Packages:**
```
prometheus-client==0.20.0
```

**Docker Images:**
```
prom/prometheus:latest
grafana/grafana:latest
prom/alertmanager:latest  (optional)
```

### 5.2 Configuration Files

**New Files to Create:**

1. `/home/kali/Desktop/AutoBot/config/prometheus.yml`
2. `/home/kali/Desktop/AutoBot/config/prometheus/alert_rules.yml`
3. `/home/kali/Desktop/AutoBot/config/grafana/dashboards/autobot-timeouts.json`
4. `/home/kali/Desktop/AutoBot/src/monitoring/prometheus_metrics.py`
5. `/home/kali/Desktop/AutoBot/autobot-user-backend/api/monitoring.py`
6. `/home/kali/Desktop/AutoBot/scripts/validate_timeout_config.py`

**Modified Files:**

1. `/home/kali/Desktop/AutoBot/config/config.yaml` - Add timeout configuration
2. `/home/kali/Desktop/AutoBot/src/unified_config.py` - Add new methods
3. `/home/kali/Desktop/AutoBot/src/knowledge_base.py` - Replace hardcoded timeouts
4. `/home/kali/Desktop/AutoBot/backend/utils/async_redis_manager.py` - Add metrics instrumentation
5. `/home/kali/Desktop/AutoBot/compose.yml` - Add Prometheus/Grafana services
6. `/home/kali/Desktop/AutoBot/requirements.txt` - Add prometheus-client

### 5.3 Infrastructure Requirements

**Main Machine (172.16.168.20):**
- FastAPI backend with `/monitoring/metrics` endpoint
- Prometheus server (port 9090)
- Grafana server (port 3001)
- Alertmanager (port 9093, optional)

**Redis VM (172.16.168.23):**
- Redis server accessible for connection pool metrics
- Optional: Redis exporter for native Redis metrics

---

## Part 6: Risk Assessment & Mitigation

### 6.1 Identified Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Configuration errors break services | Medium | High | Comprehensive validation + CI/CD gates |
| Metrics collection overhead impacts performance | Low | Medium | Performance testing + overhead limits (<5ms) |
| Alert storm from misconfigured rules | Medium | Low | Gradual alert activation + tuning period |
| Prometheus scraping fails silently | Low | Medium | Health check endpoint + monitoring of scraper |
| Timeout tuning causes new timeouts | Medium | Medium | Gradual rollout + A/B testing |

### 6.2 Mitigation Strategies

**Configuration Safety:**

1. Schema validation in CI/CD pipeline
2. Dry-run validation before deployment
3. Backward compatibility with hardcoded values as fallback
4. Rollback automation via Ansible playbooks

**Performance Safety:**

1. Metrics overhead budget: <5ms per operation
2. Asynchronous metrics collection where possible
3. Metric cardinality limits (prevent label explosion)
4. Performance regression tests in CI/CD

**Operational Safety:**

1. Feature flags for metrics collection (disable if issues)
2. Alert silencing during known maintenance windows
3. Graduated alert thresholds (warn before critical)
4. Dashboard templates for quick issue diagnosis

---

## Appendix A: Configuration Schema Reference

**Complete timeout configuration paths:**

```
timeouts.redis.connection.socket_connect
timeouts.redis.connection.socket_timeout
timeouts.redis.connection.health_check
timeouts.redis.operations.get
timeouts.redis.operations.set
timeouts.redis.operations.hgetall
timeouts.redis.operations.pipeline
timeouts.redis.operations.scan_iter
timeouts.redis.operations.ft_info
timeouts.redis.operations.flushdb
timeouts.redis.circuit_breaker.timeout
timeouts.redis.circuit_breaker.threshold
timeouts.llamaindex.embedding.generation
timeouts.llamaindex.embedding.batch
timeouts.llamaindex.indexing.single_document
timeouts.llamaindex.indexing.batch_documents
timeouts.llamaindex.indexing.vector_store_init
timeouts.llamaindex.search.query
timeouts.llamaindex.search.hybrid
timeouts.documents.processing.pdf_extraction
timeouts.documents.processing.text_chunking
timeouts.documents.processing.metadata_extraction
timeouts.documents.operations.add_document
timeouts.documents.operations.batch_upload
timeouts.documents.operations.export
timeouts.http.standard
timeouts.http.long_running
timeouts.http.streaming
timeouts.llm.default
timeouts.llm.fast
timeouts.llm.reasoning
```

---

## Appendix B: Prometheus Query Examples

**Useful Prometheus queries for troubleshooting:**

```promql
# Total timeout rate across all operations (5-minute average)
sum(rate(autobot_timeout_total{status="timeout"}[5m])) /
sum(rate(autobot_timeout_total[5m])) * 100

# Top 5 slowest operations by P95 latency
topk(5,
  histogram_quantile(0.95,
    rate(autobot_operation_duration_seconds_bucket[5m])
  )
) by (operation_type, database)

# Connection pool utilization over time
autobot_redis_pool_saturation_ratio * 100

# Circuit breaker state history
changes(autobot_circuit_breaker_state[1h])

# Request rate by status (success vs failure)
sum(rate(autobot_redis_requests_total[5m])) by (status)

# Average latency per operation type
avg(rate(autobot_operation_duration_seconds_sum[5m])) by (operation_type) /
avg(rate(autobot_operation_duration_seconds_count[5m])) by (operation_type)
```

---

## Approval Checklist

**Before proceeding to implementation:**

- [ ] Configuration schema approved by systems architect
- [ ] Prometheus metrics design reviewed by DevOps team
- [ ] Alert thresholds validated by operations team
- [ ] Rollback plan tested in staging environment
- [ ] Performance overhead limits agreed upon
- [ ] Documentation complete and accessible
- [ ] Implementation phases scheduled
- [ ] Stakeholders notified of deployment timeline

---

**Document Status:** READY FOR REVIEW
**Next Steps:**
1. Review by systems-architect agent
2. Review by devops-engineer agent
3. Risk assessment by code-skeptic agent
4. Approval from project manager
5. Proceed to implementation (KB-ASYNC-014 → KB-ASYNC-015)
