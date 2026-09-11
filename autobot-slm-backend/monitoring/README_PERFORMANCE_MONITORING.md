# SLM `monitoring` package

`monitoring/__init__.py` imports only `prometheus_metrics.py`, which re-exports the
shared metrics manager (`get_metrics_manager`) from
`autobot_shared/monitoring/prometheus_metrics.py`. The domain recorders are in
`autobot_shared/monitoring/metrics/`.

Fleet monitoring runs inside the SLM process. `main.py` includes the monitoring and
performance routers behind service-management auth, so there is no separate
monitoring process to install, start or configure.

## Retired (#16282)

The standalone monitoring system that lived here was deprecated by #469. Each part
of it has a live equivalent:

| Retired | Where its function lives now |
| --- | --- |
| `advanced_apm_system.py` | request counting: `middleware/api_request_counter.py` and `record_request` in `autobot_shared/monitoring/metrics/api_requests.py`. Traces and alert rules: `get_traces` and `create_alert_rule` in `api/performance.py` |
| `ai_performance_analytics.py` | the `/metrics` route in `api/npu.py`; in `autobot_shared/monitoring/metrics/`: `update_npu_metrics` (`performance.py`), `record_search` (`knowledge_base.py`), `LLMProviderMetricsRecorder` (`llm_provider.py`) |
| `claude_api_monitor.py` | `record_claude_api_request` in `autobot_shared/monitoring/prometheus_metrics.py`, and `ClaudeAPIMetricsRecorder` in `autobot_shared/monitoring/metrics/claude_api.py` |
| `comprehensive_monitoring_controller.py`, `monitor_control.py`, `start_monitoring.sh`, `monitoring_config.yaml` | the in-process routers described above |
| `metrics_adapter.py` | callers use `get_metrics_manager()` directly |
| `performance_dashboard.py` | the `/dashboard` and `/metrics/fleet` routes in `api/monitoring.py` |
| `performance_monitor.py` | the `/metrics/fleet` route in `api/monitoring.py`, and `get_node_metrics` in `api/performance.py` |

## Being wired in

Three modules here have no live equivalent yet. Each has its own issue:

- `performance_benchmark.py` becomes an SLM fleet benchmark (#16305).
- `performance_optimizer.py`: its tuning logic folds into the reconciler, which
  stays the only path that changes the fleet, and then the module goes (#16306).
- `business_intelligence_dashboard.py`: cost and ROI analysis move to Company OS,
  and system-wide stats move under the SLM (#16307).

None of the three can be imported today. All three import the retired
`performance_monitor` (which itself needed the main backend's
`config.ConfigManager`), and `performance_benchmark.py` also imports
`src.constants`, which does not exist. Each issue replaces those imports.
