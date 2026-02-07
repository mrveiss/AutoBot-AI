#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Performance Dashboard Generator for AutoBot
Creates HTML dashboards for system monitoring and performance tracking

Issue #515: CSS extracted to templates/dashboards/styles/performance_dashboard.css
"""

import logging

logger = logging.getLogger(__name__)
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict

from src.utils.html_dashboard_utils import create_dashboard_header, get_light_theme_css
from src.utils.template_loader import load_css, template_exists


def _get_additional_dashboard_css() -> str:
    """
    Get additional CSS styles for dashboard-specific elements.

    Issue #281: Extracted from generate_dashboard_html to reduce function length.
    Issue #515: CSS moved to external template file for better maintainability.

    Returns:
        CSS string for dashboard grid, cards, metrics, progress bars, etc.
    """
    template_path = "dashboards/styles/performance_dashboard.css"

    if template_exists(template_path):
        return load_css("performance_dashboard")

    # Fallback for backwards compatibility if template is missing
    logger.warning("CSS template not found, using inline fallback: %s", template_path)
    return _get_fallback_css()


def _get_fallback_css() -> str:
    """
    Fallback CSS if template file is not available.

    Issue #515: Preserved for backwards compatibility during template migration.
    """
    return """
        .dashboard-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }
        .card {
            background: white;
            border-radius: 10px;
            padding: 1.5rem;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .metric {
            display: flex;
            justify-content: space-between;
            padding: 0.5rem 0;
            border-bottom: 1px solid #e2e8f0;
        }
        .progress-bar {
            width: 100%;
            height: 20px;
            background-color: #e2e8f0;
            border-radius: 10px;
            overflow: hidden;
        }
        .progress-fill { height: 100%; border-radius: 10px; }
        .progress-normal { background: linear-gradient(90deg, #48bb78, #38a169); }
        .progress-warning { background: linear-gradient(90deg, #ed8936, #d69e2e); }
        .progress-critical { background: linear-gradient(90deg, #f56565, #e53e3e); }
    """


def generate_dashboard_html(monitoring_data: Dict[str, Any]) -> str:
    """
    Generate comprehensive HTML dashboard.

    Issue #281: Extracted CSS to _get_additional_dashboard_css() to reduce
    function length from 281 to ~110 lines.
    """
    # Generate dashboard components using utility functions
    light_theme_css = get_light_theme_css()
    header_html = create_dashboard_header(
        title="🤖 AutoBot Monitoring Dashboard",
        subtitle="Real-time system performance and health monitoring",
        theme="light",
    )

    # Issue #281: Use extracted helper for additional CSS
    additional_css = _get_additional_dashboard_css()

    dashboard_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoBot Monitoring Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
{light_theme_css}
{additional_css}
    </style>
</head>
<body>
{header_html}

    <div class="container">
        <div class="refresh-info">
            📊 Dashboard generated at {timestamp} |
            🔄 Auto-refresh available via monitoring system
        </div>

        <div class="dashboard-grid">
            <!-- System Overview Card -->
            <div class="card">
                <h3>⚡ System Overview</h3>
                {system_overview_html}
            </div>

            <!-- Service Status Card -->
            <div class="card">
                <h3>🔧 Service Status</h3>
                {service_status_html}
            </div>

            <!-- Performance Metrics Card -->
            <div class="card">
                <h3>📊 Performance Metrics</h3>
                {performance_metrics_html}
            </div>

            <!-- Health Checks Card -->
            <div class="card">
                <h3>🏥 Health Checks</h3>
                {health_checks_html}
            </div>
        </div>

        <!-- Charts Section -->
        <div class="dashboard-grid">
            <div class="card" style="grid-column: 1 / -1;">
                <h3>📈 Performance Trends (Last 24 Hours)</h3>
                <div class="chart-container">
                    <canvas id="performanceChart"></canvas>
                </div>
            </div>
        </div>

        <!-- Alerts Section -->
        <div class="dashboard-grid">
            <div class="card">
                <h3>🚨 Recent Alerts</h3>
                {alerts_html}
            </div>

            <div class="card">
                <h3>📋 System Information</h3>
                {system_info_html}
            </div>
        </div>

        <div class="footer">
            <p>🤖 Generated by AutoBot Monitoring System</p>
            <p>For real-time monitoring, run: <code>python scripts/monitoring_system.py</code></p>
        </div>
    </div>

    <script>
        // Performance Chart
        {chart_script}
    </script>
</body>
</html>""".format(
        light_theme_css=light_theme_css,
        additional_css=additional_css,
        header_html=header_html,
        timestamp=monitoring_data.get("timestamp", "Unknown"),
        system_overview_html=_generate_system_overview_html(monitoring_data),
        service_status_html=_generate_service_status_html(monitoring_data),
        performance_metrics_html=_generate_performance_metrics_html(monitoring_data),
        health_checks_html=_generate_health_checks_html(monitoring_data),
        alerts_html=_generate_alerts_html(monitoring_data),
        system_info_html=_generate_system_info_html(monitoring_data),
        chart_script=_generate_chart_script(monitoring_data),
    )

    return dashboard_html


def _generate_system_overview_html(data: Dict[str, Any]) -> str:
    """Generate system overview HTML"""
    system = data.get("system_overview", {})

    system.get("avg_cpu_percent", 0)
    system.get("avg_memory_percent", 0)
    system.get("avg_disk_percent", 0)

    def get_progress_class(value):
        """Return CSS class based on resource usage threshold."""
        if value >= 90:
            return "progress-critical"
        elif value >= 75:
            return "progress-warning"
        else:
            return "progress-normal"

    def get_status_class(value):
        """Return CSS status class based on resource usage threshold."""
        if value >= 90:
            return "status-critical"
        elif value >= 75:
            return "status-warning"
        else:
            return "status-healthy"

    return """
        <div class="metric">
            <span class="metric-label">CPU Usage (Avg)</span>
            <span class="metric-value {get_status_class(cpu_percent)}">{cpu_percent:.1f}%</span>
        </div>
        <div class="progress-bar">
            <div class="progress-fill {get_progress_class(cpu_percent)}" style="width: {cpu_percent}%"></div>
        </div>

        <div class="metric">
            <span class="metric-label">Memory Usage (Avg)</span>
            <span class="metric-value {get_status_class(memory_percent)}">{memory_percent:.1f}%</span>
        </div>
        <div class="progress-bar">
            <div class="progress-fill {get_progress_class(memory_percent)}" style="width: {memory_percent}%"></div>
        </div>

        <div class="metric">
            <span class="metric-label">Disk Usage</span>
            <span class="metric-value {get_status_class(disk_percent)}">{disk_percent:.1f}%</span>
        </div>
        <div class="progress-bar">
            <div class="progress-fill {get_progress_class(disk_percent)}" style="width: {disk_percent}%"></div>
        </div>

        <div class="metric">
            <span class="metric-label">Data Points</span>
            <span class="metric-value">{system.get('data_points', 0):,}</span>
        </div>
    """


def _generate_service_status_html(data: Dict[str, Any]) -> str:
    """Generate service status HTML"""
    services = data.get("service_status", {})

    if not services:
        return "<p>No service data available</p>"

    html = '<div class="services-grid">'

    for service_name, service_data in services.items():
        error_rate = service_data.get("error_rate", 0)
        response_time = service_data.get("avg_response_time_ms", 0)

        status_class = (
            "service-healthy"
            if error_rate < 5 and response_time < 1000
            else "service-unhealthy"
        )
        "Healthy" if error_rate < 5 and response_time < 1000 else "Issues"

        html += """
        <div class="service-card {status_class}">
            <div class="service-name">{service_name}</div>
            <div class="service-status">{status_text}</div>
            <div style="font-size: 0.8rem; margin-top: 0.5rem;">
                <div>Response: {response_time:.0f}ms</div>
                <div>Error Rate: {error_rate:.1f}%</div>
            </div>
        </div>
        """

    html += "</div>"
    return html


def _generate_performance_metrics_html(data: Dict[str, Any]) -> str:
    """Generate performance metrics HTML"""
    data.get("system_overview", {})

    return """
        <div class="metric">
            <span class="metric-label">Peak CPU Usage</span>
            <span class="metric-value">{system.get('max_cpu_percent', 0):.1f}%</span>
        </div>
        <div class="metric">
            <span class="metric-label">Peak Memory Usage</span>
            <span class="metric-value">{system.get('max_memory_percent', 0):.1f}%</span>
        </div>
        <div class="metric">
            <span class="metric-label">Data Collection Points</span>
            <span class="metric-value">{system.get('data_points', 0):,}</span>
        </div>
        <div class="metric">
            <span class="metric-label">Monitoring Period</span>
            <span class="metric-value">Last 24 hours</span>
        </div>
    """


def _generate_health_checks_html(data: Dict[str, Any]) -> str:
    """Generate health checks HTML"""
    health = data.get("health_summary", {})

    # Mock health data if not available
    if not health:
        return """
        <div class="metric">
            <span class="metric-label">Overall Status</span>
            <span class="metric-value status-healthy">Monitoring Active</span>
        </div>
        <div class="metric">
            <span class="metric-label">Services Monitored</span>
            <span class="metric-value">3</span>
        </div>
        <div class="metric">
            <span class="metric-label">Last Check</span>
            <span class="metric-value">Just now</span>
        </div>
        """

    return """
        <div class="metric">
            <span class="metric-label">Overall Status</span>
            <span class="metric-value status-healthy">{health.get('overall_status', 'Unknown').title()}</span>
        </div>
        <div class="metric">
            <span class="metric-label">Services Checked</span>
            <span class="metric-value">{len(health.get('services', {}))}</span>
        </div>
        <div class="metric">
            <span class="metric-label">Issues Detected</span>
            <span class="metric-value">{len(health.get('issues', []))}</span>
        </div>
    """


def _generate_alerts_html(data: Dict[str, Any]) -> str:
    """Generate alerts HTML"""
    alerts = data.get("recent_alerts", [])

    if not alerts:
        return '<div class="alert-item" style="background-color: #f0fff4; border-color: #38a169;"><strong>✅ No recent alerts</strong><br>System is operating normally</div>'

    html = '<div class="alerts-list">'

    for alert in alerts[:5]:  # Show last 5 alerts
        alert_class = (
            "alert-critical" if alert.get("severity") == "critical" else "alert-warning"
        )
        severity_icon = "🔴" if alert.get("severity") == "critical" else "🟡"

        html += """
        <div class="alert-item {alert_class}">
            <strong>{severity_icon} {alert.get('severity', 'Unknown').title()}</strong><br>
            {alert.get('message', 'No message')}
            <div style="font-size: 0.8rem; color: #718096; margin-top: 0.5rem;">
                {alert.get('timestamp', 'Unknown time')}
            </div>
        </div>
        """

    html += "</div>"
    return html


def _generate_system_info_html(data: Dict[str, Any]) -> str:
    """Generate system information HTML"""
    return """
        <div class="metric">
            <span class="metric-label">Dashboard Version</span>
            <span class="metric-value">v1.0</span>
        </div>
        <div class="metric">
            <span class="metric-label">Monitoring Started</span>
            <span class="metric-value">System Boot</span>
        </div>
        <div class="metric">
            <span class="metric-label">Data Retention</span>
            <span class="metric-value">30 days</span>
        </div>
        <div class="metric">
            <span class="metric-label">Update Frequency</span>
            <span class="metric-value">Every 60 seconds</span>
        </div>
    """


def _generate_chart_script(data: Dict[str, Any]) -> str:
    """Generate Chart.js script for performance trends"""
    trends = data.get("performance_trends", [])

    if not trends:
        # Generate mock data for demonstration
        trends = []
        now = datetime.now()
        for i in range(24):
            hour = now - timedelta(hours=23 - i)
            trends.append(
                {
                    "hour": hour.strftime("%Y-%m-%d %H:00:00"),
                    "cpu_percent": 15 + (i % 10) * 3,
                    "memory_percent": 45 + (i % 8) * 2,
                    "response_time_ms": 200 + (i % 5) * 50,
                }
            )

    labels = [t["hour"][-8:-3] for t in trends]  # Extract HH:MM
    [t.get("cpu_percent", 0) for t in trends]
    [t.get("memory_percent", 0) for t in trends]
    [t.get("response_time_ms", 0) for t in trends]

    return """
        const ctx = document.getElementById('performanceChart').getContext('2d');
        const chart = new Chart(ctx, {{
            type: 'line',
            data: {{
                labels: {json.dumps(labels)},
                datasets: [{{
                    label: 'CPU Usage (%)',
                    data: {json.dumps(cpu_data)},
                    borderColor: '#667eea',
                    backgroundColor: 'rgba(102, 126, 234, 0.1)',
                    fill: true,
                    tension: 0.4
                }}, {{
                    label: 'Memory Usage (%)',
                    data: {json.dumps(memory_data)},
                    borderColor: '#f093fb',
                    backgroundColor: 'rgba(240, 147, 251, 0.1)',
                    fill: true,
                    tension: 0.4
                }}, {{
                    label: 'Response Time (ms)',
                    data: {json.dumps(response_data)},
                    borderColor: '#4ecdc4',
                    backgroundColor: 'rgba(78, 205, 196, 0.1)',
                    fill: true,
                    tension: 0.4,
                    yAxisID: 'y1'
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{
                        position: 'top',
                    }},
                    title: {{
                        display: true,
                        text: 'System Performance Over Time'
                    }}
                }},
                scales: {{
                    y: {{
                        type: 'linear',
                        display: true,
                        position: 'left',
                        title: {{
                            display: true,
                            text: 'Percentage (%)'
                        }}
                    }},
                    y1: {{
                        type: 'linear',
                        display: true,
                        position: 'right',
                        title: {{
                            display: true,
                            text: 'Response Time (ms)'
                        }},
                        grid: {{
                            drawOnChartArea: false,
                        }},
                    }}
                }}
            }}
        }});
    """


def create_monitoring_dashboard():
    """Create monitoring dashboard from latest data"""
    import sys

    sys.path.append(str(Path(__file__).parent))
    from monitoring_system import SystemMonitor

    project_root = Path(__file__).parent.parent
    monitor = SystemMonitor(project_root)

    # Generate dashboard data
    dashboard_data = monitor.generate_monitoring_dashboard()

    # Generate HTML
    html_content = generate_dashboard_html(dashboard_data)

    # Save dashboard
    dashboard_file = project_root / "reports" / "monitoring" / "dashboard.html"
    dashboard_file.parent.mkdir(parents=True, exist_ok=True)

    with open(dashboard_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    logger.info("Dashboard created: %s", dashboard_file)
    logger.info("Open in browser: file://%s", dashboard_file.absolute())

    return dashboard_file


if __name__ == "__main__":
    create_monitoring_dashboard()
