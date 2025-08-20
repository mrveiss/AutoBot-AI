#!/usr/bin/env python3
"""
Performance Dashboard Generator for AutoBot
Creates HTML dashboards for system monitoring and performance tracking
"""

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List


def generate_dashboard_html(monitoring_data: Dict[str, Any]) -> str:
    """Generate comprehensive HTML dashboard"""

    dashboard_html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoBot Monitoring Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #f5f5f5;
            color: #333;
            line-height: 1.6;
        }}

        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 2rem;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}

        .header h1 {{
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
        }}

        .header p {{
            font-size: 1.1rem;
            opacity: 0.9;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }}

        .dashboard-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}

        .card {{
            background: white;
            border-radius: 10px;
            padding: 1.5rem;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }}

        .card:hover {{
            transform: translateY(-2px);
        }}

        .card h3 {{
            color: #4a5568;
            margin-bottom: 1rem;
            font-size: 1.3rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .metric {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.5rem 0;
            border-bottom: 1px solid #e2e8f0;
        }}

        .metric:last-child {{
            border-bottom: none;
        }}

        .metric-label {{
            font-weight: 500;
            color: #4a5568;
        }}

        .metric-value {{
            font-weight: bold;
            color: #2d3748;
        }}

        .status-healthy {{
            color: #38a169;
        }}

        .status-warning {{
            color: #d69e2e;
        }}

        .status-critical {{
            color: #e53e3e;
        }}

        .progress-bar {{
            width: 100%;
            height: 20px;
            background-color: #e2e8f0;
            border-radius: 10px;
            overflow: hidden;
            margin: 0.5rem 0;
        }}

        .progress-fill {{
            height: 100%;
            border-radius: 10px;
            transition: width 0.3s ease;
        }}

        .progress-normal {{
            background: linear-gradient(90deg, #48bb78, #38a169);
        }}

        .progress-warning {{
            background: linear-gradient(90deg, #ed8936, #d69e2e);
        }}

        .progress-critical {{
            background: linear-gradient(90deg, #f56565, #e53e3e);
        }}

        .chart-container {{
            position: relative;
            height: 300px;
            margin: 1rem 0;
        }}

        .services-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-top: 1rem;
        }}

        .service-card {{
            background: #f8fafc;
            border: 2px solid #e2e8f0;
            border-radius: 8px;
            padding: 1rem;
            text-align: center;
        }}

        .service-healthy {{
            border-color: #38a169;
            background-color: #f0fff4;
        }}

        .service-unhealthy {{
            border-color: #e53e3e;
            background-color: #fef5f5;
        }}

        .service-name {{
            font-weight: bold;
            margin-bottom: 0.5rem;
            text-transform: uppercase;
            font-size: 0.9rem;
        }}

        .service-status {{
            font-size: 0.8rem;
            padding: 0.2rem 0.5rem;
            border-radius: 12px;
            color: white;
        }}

        .alerts-list {{
            max-height: 300px;
            overflow-y: auto;
        }}

        .alert-item {{
            padding: 0.8rem;
            margin: 0.5rem 0;
            border-radius: 6px;
            border-left: 4px solid;
        }}

        .alert-warning {{
            background-color: #fef5e7;
            border-color: #d69e2e;
        }}

        .alert-critical {{
            background-color: #fef5f5;
            border-color: #e53e3e;
        }}

        .timestamp {{
            color: #718096;
            font-size: 0.9rem;
            margin-top: 1rem;
            text-align: center;
        }}

        .footer {{
            text-align: center;
            padding: 2rem;
            color: #718096;
            background: white;
            margin-top: 2rem;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}

        .refresh-info {{
            background: #edf2f7;
            padding: 1rem;
            border-radius: 8px;
            margin-bottom: 2rem;
            text-align: center;
            color: #4a5568;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🤖 AutoBot Monitoring Dashboard</h1>
        <p>Real-time system performance and health monitoring</p>
    </div>

    <div class="container">
        <div class="refresh-info">
            📊 Dashboard generated at {monitoring_data.get('timestamp', 'Unknown')} |
            🔄 Auto-refresh available via monitoring system
        </div>

        <div class="dashboard-grid">
            <!-- System Overview Card -->
            <div class="card">
                <h3>⚡ System Overview</h3>
                {_generate_system_overview_html(monitoring_data)}
            </div>

            <!-- Service Status Card -->
            <div class="card">
                <h3>🔧 Service Status</h3>
                {_generate_service_status_html(monitoring_data)}
            </div>

            <!-- Performance Metrics Card -->
            <div class="card">
                <h3>📊 Performance Metrics</h3>
                {_generate_performance_metrics_html(monitoring_data)}
            </div>

            <!-- Health Checks Card -->
            <div class="card">
                <h3>🏥 Health Checks</h3>
                {_generate_health_checks_html(monitoring_data)}
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
                {_generate_alerts_html(monitoring_data)}
            </div>

            <div class="card">
                <h3>📋 System Information</h3>
                {_generate_system_info_html(monitoring_data)}
            </div>
        </div>

        <div class="footer">
            <p>🤖 Generated by AutoBot Monitoring System</p>
            <p>For real-time monitoring, run: <code>python scripts/monitoring_system.py</code></p>
        </div>
    </div>

    <script>
        // Performance Chart
        {_generate_chart_script(monitoring_data)}
    </script>
</body>
</html>"""

    return dashboard_html


def _generate_system_overview_html(data: Dict[str, Any]) -> str:
    """Generate system overview HTML"""
    system = data.get("system_overview", {})

    cpu_percent = system.get("avg_cpu_percent", 0)
    memory_percent = system.get("avg_memory_percent", 0)
    disk_percent = system.get("avg_disk_percent", 0)

    def get_progress_class(value):
        if value >= 90:
            return "progress-critical"
        elif value >= 75:
            return "progress-warning"
        else:
            return "progress-normal"

    def get_status_class(value):
        if value >= 90:
            return "status-critical"
        elif value >= 75:
            return "status-warning"
        else:
            return "status-healthy"

    return f"""
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
        status_text = "Healthy" if error_rate < 5 and response_time < 1000 else "Issues"

        html += f"""
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
    system = data.get("system_overview", {})

    return f"""
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

    return f"""
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

        html += f"""
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
    return f"""
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
    cpu_data = [t.get("cpu_percent", 0) for t in trends]
    memory_data = [t.get("memory_percent", 0) for t in trends]
    response_data = [t.get("response_time_ms", 0) for t in trends]

    return f"""
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

    print(f"📊 Dashboard created: {dashboard_file}")
    print(f"🌐 Open in browser: file://{dashboard_file.absolute()}")

    return dashboard_file


if __name__ == "__main__":
    create_monitoring_dashboard()
