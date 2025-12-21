#!/usr/bin/env python3
"""
AutoBot Performance Dashboard
Real-time web dashboard for monitoring AutoBot distributed system performance.
Provides interactive charts, alerts, and system status overview.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

import aiohttp_jinja2
import jinja2
from aiohttp import web, WSMsgType
from src.constants.network_constants import NetworkConstants

from performance_monitor import PerformanceMonitor

logger = logging.getLogger(__name__)
from src.utils.html_dashboard_utils import (
    get_dark_theme_css,
    create_dashboard_header,
    create_metric_card,
)
from src.utils.template_loader import load_css, template_exists


# ============================================================================
# Dashboard Template Helper Functions (Issue #398: extracted)
# ============================================================================


def _get_dashboard_additional_css() -> str:
    """
    Return additional CSS styles for the dashboard template.

    Issue #398: Extracted from main template.
    Issue #515: CSS moved to external template file for better maintainability.
    """
    template_path = "dashboards/styles/monitoring_dashboard.css"

    if template_exists(template_path):
        return load_css("monitoring_dashboard")

    # Fallback for backwards compatibility
    logger.warning("CSS template not found, using inline fallback: %s", template_path)
    return _get_fallback_css()


def _get_fallback_css() -> str:
    """Fallback CSS if template file is not available (Issue #515)."""
    return """
        .services-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 1rem; margin-bottom: 2rem; }
        .service-card { background: #161b22; border: 1px solid #30363d; border-radius: 0.5rem; padding: 1rem; }
        .status-dot { width: 8px; height: 8px; border-radius: 50%; }
        .status-up { background: #238636; }
        .status-down { background: #da3633; }
        .alerts-section { background: #161b22; border: 1px solid #30363d; border-radius: 0.5rem; padding: 1.5rem; }
        .alert-item { padding: 0.75rem; margin-bottom: 0.5rem; border-radius: 0.375rem; background: #3d1a00; border-left: 3px solid #d29922; }
        .vm-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 2rem; }
        .vm-card { background: #161b22; border: 1px solid #30363d; border-radius: 0.5rem; padding: 1rem; }
    """


def _get_dashboard_javascript() -> str:
    """Return JavaScript for the dashboard template (Issue #398: extracted)."""
    return """    <script>
        class AutoBotDashboard {
            constructor() {
                this.ws = null;
                this.reconnectAttempts = 0;
                this.maxReconnectAttempts = 5;
                this.performanceHistory = [];
                this.init();
            }

            init() {
                this.connectWebSocket();
                this.loadInitialData();
                setInterval(() => this.updateCharts(), 5000);
            }

            connectWebSocket() {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/ws`;

                this.ws = new WebSocket(wsUrl);

                this.ws.onopen = () => {
                    console.log('WebSocket connected');
                    this.reconnectAttempts = 0;
                };

                this.ws.onmessage = (event) => {
                    const data = JSON.parse(event.data);
                    this.handleRealtimeUpdate(data);
                };

                this.ws.onclose = () => {
                    console.log('WebSocket disconnected');
                    if (this.reconnectAttempts < this.maxReconnectAttempts) {
                        setTimeout(() => {
                            this.reconnectAttempts++;
                            this.connectWebSocket();
                        }, 5000);
                    }
                };
            }

            async loadInitialData() {
                try {
                    const response = await fetch('/api/metrics/current');
                    const data = await response.json();
                    this.updateDashboard(data);
                    document.getElementById('loading').style.display = 'none';
                    document.getElementById('dashboard-content').style.display = 'block';
                } catch (error) {
                    console.error('Error loading initial data:', error);
                }
            }

            handleRealtimeUpdate(data) {
                if (data.type === 'metrics_update') {
                    this.updateDashboard(data.data);
                    this.performanceHistory.push({
                        timestamp: new Date(),
                        ...data.data
                    });

                    // Keep only last 50 data points
                    if (this.performanceHistory.length > 50) {
                        this.performanceHistory.shift();
                    }
                }
            }

            updateDashboard(data) {
                // Update system metrics
                if (data.system) {
                    document.getElementById('cpu-usage').textContent = `${data.system.cpu_percent.toFixed(1)}%`;
                    document.getElementById('memory-usage').textContent = `${data.system.memory_percent.toFixed(1)}%`;
                    document.getElementById('memory-available').textContent = `${data.system.memory_available_gb.toFixed(1)}GB`;

                    if (data.system.gpu_utilization !== null) {
                        document.getElementById('gpu-usage').textContent = `${data.system.gpu_utilization.toFixed(1)}%`;
                    } else {
                        document.getElementById('gpu-usage').textContent = 'N/A';
                    }
                }

                // Update service count
                if (data.services) {
                    const healthyServices = data.services.filter(s => s.is_healthy).length;
                    document.getElementById('active-services').textContent = `${healthyServices}/${data.services.length}`;
                }

                // Update system status
                const alerts = data.alerts || [];
                const systemStatus = document.getElementById('system-status');
                if (alerts.length === 0) {
                    systemStatus.className = 'status-indicator status-healthy';
                    systemStatus.textContent = 'System Healthy';
                } else if (alerts.some(alert => alert.includes('DOWN') || alert.includes('ERROR'))) {
                    systemStatus.className = 'status-indicator status-error';
                    systemStatus.textContent = 'System Issues';
                } else {
                    systemStatus.className = 'status-indicator status-warning';
                    systemStatus.textContent = 'Warnings';
                }

                // Update VM status
                this.updateVMStatus(data);

                // Update services
                this.updateServices(data.services || []);

                // Update alerts
                this.updateAlerts(alerts);
            }

            updateVMStatus(data) {
                const vmGrid = document.getElementById('vm-status-grid');
                // VM IPs are managed by network_constants.py
                const vms = {
                    'main': '{{ main_ip }}',
                    'frontend': '{{ frontend_ip }}',
                    'npu-worker': '{{ npu_worker_ip }}',
                    'redis': '{{ redis_ip }}',
                    'ai-stack': '{{ ai_stack_ip }}',
                    'browser': '{{ browser_ip }}'
                };

                let vmHtml = '';
                for (const [vmName, vmIp] of Object.entries(vms)) {
                    const vmData = data.inter_vm?.find(vm => vm.target_vm === vmName) || {};
                    const latency = vmData.latency_ms || 0;
                    const packetLoss = vmData.packet_loss_percent || 0;

                    const statusClass = packetLoss > 10 ? 'status-down' : 'status-up';
                    const statusText = packetLoss > 10 ? 'Connection Issues' : 'Connected';

                    vmHtml += `
                        <div class="vm-card">
                            <div class="vm-name">${vmName.toUpperCase()}</div>
                            <div class="vm-ip">${vmIp}</div>
                            <div class="service-status">
                                <div class="status-dot ${statusClass}"></div>
                                <span>${statusText}</span>
                            </div>
                            <div class="vm-metrics">
                                <div class="vm-metric">
                                    <span>Latency:</span>
                                    <span>${latency.toFixed(1)}ms</span>
                                </div>
                                <div class="vm-metric">
                                    <span>Packet Loss:</span>
                                    <span>${packetLoss.toFixed(1)}%</span>
                                </div>
                            </div>
                        </div>
                    `;
                }
                vmGrid.innerHTML = vmHtml;
            }

            updateServices(services) {
                const servicesGrid = document.getElementById('services-grid');
                let servicesHtml = '';

                services.forEach(service => {
                    const statusClass = service.is_healthy ? 'status-up' : 'status-down';
                    const statusText = service.is_healthy ? 'Healthy' : 'Down';
                    const responseTime = service.response_time ? `${(service.response_time * 1000).toFixed(0)}ms` : 'N/A';

                    servicesHtml += `
                        <div class="service-card">
                            <div class="service-name">${service.service_name}</div>
                            <div class="service-status">
                                <div class="status-dot ${statusClass}"></div>
                                <span>${statusText}</span>
                            </div>
                            <div style="font-size: 0.875rem; color: #8b949e;">
                                Response: ${responseTime}
                            </div>
                            ${service.error_message ? `<div style="font-size: 0.75rem; color: #da3633; margin-top: 0.25rem;">${service.error_message}</div>` : ''}
                        </div>
                    `;
                });

                servicesGrid.innerHTML = servicesHtml;
            }

            updateAlerts(alerts) {
                const alertsContainer = document.getElementById('alerts-container');

                if (alerts.length === 0) {
                    alertsContainer.innerHTML = '<div style="color: #8b949e; text-align: center; padding: 1rem;">No active alerts</div>';
                    return;
                }

                let alertsHtml = '';
                alerts.forEach(alert => {
                    const isCritical = alert.includes('DOWN') || alert.includes('ERROR');
                    const alertClass = isCritical ? 'alert-item critical' : 'alert-item';

                    alertsHtml += `
                        <div class="${alertClass}">
                            <strong>${isCritical ? '🚨' : '⚠️'} ${alert}</strong>
                            <div style="font-size: 0.875rem; opacity: 0.8; margin-top: 0.25rem;">
                                ${new Date().toLocaleTimeString()}
                            </div>
                        </div>
                    `;
                });

                alertsContainer.innerHTML = alertsHtml;
            }

            updateCharts() {
                if (this.performanceHistory.length < 2) return;

                // Performance chart
                const times = this.performanceHistory.map(d => d.timestamp);
                const cpuData = this.performanceHistory.map(d => d.system?.cpu_percent || 0);
                const memoryData = this.performanceHistory.map(d => d.system?.memory_percent || 0);
                const gpuData = this.performanceHistory.map(d => d.system?.gpu_utilization || 0);

                const performanceTrace1 = {
                    x: times,
                    y: cpuData,
                    name: 'CPU %',
                    type: 'scatter',
                    line: { color: '#58a6ff' }
                };

                const performanceTrace2 = {
                    x: times,
                    y: memoryData,
                    name: 'Memory %',
                    type: 'scatter',
                    line: { color: '#56d364' }
                };

                const performanceTrace3 = {
                    x: times,
                    y: gpuData,
                    name: 'GPU %',
                    type: 'scatter',
                    line: { color: '#d29922' }
                };

                const performanceLayout = {
                    paper_bgcolor: '#0d1117',
                    plot_bgcolor: '#0d1117',
                    font: { color: '#c9d1d9' },
                    xaxis: { gridcolor: '#30363d' },
                    yaxis: { gridcolor: '#30363d', range: [0, 100] },
                    margin: { l: 50, r: 50, t: 20, b: 50 }
                };

                Plotly.newPlot('performance-chart', [performanceTrace1, performanceTrace2, performanceTrace3], performanceLayout, { responsive: true });
            }
        }

        // Initialize dashboard when page loads
        document.addEventListener('DOMContentLoaded', () => {
            new AutoBotDashboard();
        });
    </script>"""


def _get_dashboard_html_body(header_html: str, metric_cards: str) -> str:
    """Return the HTML body section for the dashboard (Issue #398: extracted)."""
    return f"""{header_html}

    <div class="container">
        <div id="loading" class="loading">
            <div>Loading performance data...</div>
        </div>

        <div id="dashboard-content" style="display: none;">
            <!-- System Overview Cards -->
            <div class="metrics-grid">
{metric_cards}
            </div>

            <!-- VM Status Grid -->
            <div class="vm-grid" id="vm-status-grid">
                <!-- VM cards will be populated by JavaScript -->
            </div>

            <!-- Performance Charts -->
            <div class="chart-container">
                <h3 style="margin-bottom: 1rem; color: #58a6ff;">System Performance Over Time</h3>
                <div id="performance-chart" style="height: 400px;"></div>
            </div>

            <!-- Services Status -->
            <h3 style="margin-bottom: 1rem; color: #58a6ff;">Service Status</h3>
            <div class="services-grid" id="services-grid">
                <!-- Service cards will be populated by JavaScript -->
            </div>

            <!-- Database Performance Chart -->
            <div class="chart-container">
                <h3 style="margin-bottom: 1rem; color: #58a6ff;">Database Performance</h3>
                <div id="database-chart" style="height: 300px;"></div>
            </div>

            <!-- Inter-VM Communication Chart -->
            <div class="chart-container">
                <h3 style="margin-bottom: 1rem; color: #58a6ff;">Inter-VM Communication</h3>
                <div id="intervm-chart" style="height: 300px;"></div>
            </div>

            <!-- Alerts Section -->
            <div class="alerts-section">
                <h3 style="margin-bottom: 1rem; color: #58a6ff;">Performance Alerts</h3>
                <div id="alerts-container">
                    <div style="color: #8b949e; text-align: center; padding: 1rem;">
                        No active alerts
                    </div>
                </div>
            </div>
        </div>
    </div>"""


def _build_dashboard_html(
    dark_theme_css: str,
    additional_css: str,
    body_html: str,
    javascript: str
) -> str:
    """Build the complete dashboard HTML template (Issue #398: extracted)."""
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoBot Performance Dashboard</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
{dark_theme_css}
{additional_css}
    </style>
</head>
<body>
{body_html}

{javascript}
</body>
</html>'''

class PerformanceDashboard:
    """Real-time performance dashboard for AutoBot distributed system."""

    def __init__(self, port: int = 9090):
        self.port = port
        self.app = web.Application()
        self.monitor = PerformanceMonitor()
        self.websocket_connections = set()
        self.redis_client = None
        self.setup_routes()
        self.setup_templates()

    def setup_routes(self):
        """Set up HTTP routes for the dashboard."""
        self.app.router.add_get('/', self.dashboard_home)
        self.app.router.add_get('/api/metrics/current', self.get_current_metrics)
        self.app.router.add_get('/api/metrics/history', self.get_metrics_history)
        self.app.router.add_get('/api/system/status', self.get_system_status)
        self.app.router.add_get('/api/alerts', self.get_alerts)
        self.app.router.add_get('/ws', self.websocket_handler)
        self.app.router.add_static('/static', Path(__file__).parent / 'static')

    def setup_templates(self):
        """Set up Jinja2 templates for HTML rendering."""
        template_dir = Path(__file__).parent / 'templates'
        template_dir.mkdir(exist_ok=True)
        aiohttp_jinja2.setup(self.app, loader=jinja2.FileSystemLoader(str(template_dir)))

        # Create dashboard HTML template if it doesn't exist
        self.create_dashboard_template()

    def create_dashboard_template(self):
        """Create the main dashboard HTML template (Issue #398: refactored)."""
        template_path = Path(__file__).parent / 'templates' / 'dashboard.html'
        template_path.parent.mkdir(exist_ok=True)

        # Generate dashboard components using utility functions
        header_html = create_dashboard_header(
            title="🤖 AutoBot Performance Dashboard",
            status="healthy",
            theme="dark"
        )

        # Generate metric cards
        metric_cards = "\n".join([
            create_metric_card("CPU Usage", "--%", "22-core Intel Ultra 9 185H", "cpu-usage"),
            create_metric_card("Memory Usage", "--%", '<span id="memory-available">--GB</span> available', "memory-usage"),
            create_metric_card("GPU Utilization", "--%", "NVIDIA RTX 4070", "gpu-usage"),
            create_metric_card("Active Services", "--/--", "Distributed across 6 VMs", "active-services"),
        ])

        # Build HTML content using extracted helper functions
        html_content = _build_dashboard_html(
            dark_theme_css=get_dark_theme_css(),
            additional_css=_get_dashboard_additional_css(),
            body_html=_get_dashboard_html_body(header_html, metric_cards),
            javascript=_get_dashboard_javascript()
        )

        with open(template_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

    @aiohttp_jinja2.template('dashboard.html')
    async def dashboard_home(self, request):
        """Serve the main dashboard page."""
        return {
            'main_ip': NetworkConstants.MAIN_MACHINE_IP,
            'frontend_ip': NetworkConstants.FRONTEND_VM_IP,
            'npu_worker_ip': NetworkConstants.NPU_WORKER_VM_IP,
            'redis_ip': NetworkConstants.REDIS_VM_IP,
            'ai_stack_ip': NetworkConstants.AI_STACK_VM_IP,
            'browser_ip': NetworkConstants.BROWSER_VM_IP
        }

    async def get_current_metrics(self, request):
        """Get current performance metrics."""
        try:
            metrics = await self.monitor.generate_performance_report()
            return web.json_response(metrics, dumps=lambda obj: json.dumps(obj, default=str))
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def get_metrics_history(self, request):
        """Get historical performance metrics."""
        try:
            # Connect to Redis for historical data using canonical utility
            # This follows CLAUDE.md "🔴 REDIS CLIENT USAGE" policy
            if not self.redis_client:
                from src.utils.redis_client import get_redis_client

                self.redis_client = get_redis_client(database="metrics")
                if self.redis_client is None:
                    return web.json_response(
                        {'error': 'Redis not available', 'history': []},
                        status=503
                    )

            # Get last 100 metrics entries
            history = self.redis_client.lrange("autobot:performance:history", 0, 99)
            parsed_history = []

            for entry in history:
                try:
                    parsed_entry = json.loads(entry)
                    parsed_history.append(parsed_entry)
                except json.JSONDecodeError:
                    continue

            return web.json_response(parsed_history)

        except Exception as e:
            return web.json_response({'error': str(e), 'history': []}, status=500)

    async def get_system_status(self, request):
        """Get overall system status summary."""
        try:
            metrics = await self.monitor.generate_performance_report()

            # Calculate overall system health
            system_health = "healthy"
            alerts = metrics.get("alerts", [])

            if any("DOWN" in alert or "ERROR" in alert for alert in alerts):
                system_health = "critical"
            elif len(alerts) > 0:
                system_health = "warning"

            # Service availability
            services = metrics.get("services", [])
            healthy_services = sum(1 for s in services if s.is_healthy)
            total_services = len(services)

            status_summary = {
                "system_health": system_health,
                "services": {
                    "healthy": healthy_services,
                    "total": total_services,
                    "availability": (healthy_services / total_services * 100) if total_services > 0 else 0
                },
                "alerts": len(alerts),
                "timestamp": datetime.now().isoformat()
            }

            return web.json_response(status_summary)

        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def get_alerts(self, request):
        """Get current performance alerts."""
        try:
            metrics = await self.monitor.generate_performance_report()
            alerts = metrics.get("alerts", [])

            # Categorize alerts by severity
            critical_alerts = [a for a in alerts if "DOWN" in a or "ERROR" in a]
            warning_alerts = [a for a in alerts if a not in critical_alerts]

            return web.json_response({
                "critical": critical_alerts,
                "warnings": warning_alerts,
                "total": len(alerts),
                "timestamp": datetime.now().isoformat()
            })

        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def websocket_handler(self, request):
        """Handle WebSocket connections for real-time updates."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self.websocket_connections.add(ws)

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    if msg.data == 'close':
                        await ws.close()
                elif msg.type == WSMsgType.ERROR:
                    logger.error(f'WebSocket error: {ws.exception()}')
        except Exception as e:
            logger.error(f'WebSocket connection error: {e}')
        finally:
            self.websocket_connections.discard(ws)

        return ws

    async def broadcast_metrics_update(self, metrics):
        """Broadcast metrics update to all connected WebSocket clients."""
        if not self.websocket_connections:
            return

        message = json.dumps({
            "type": "metrics_update",
            "data": metrics,
            "timestamp": datetime.now().isoformat()
        }, default=str)

        # Send to all connected clients
        disconnected = set()
        for ws in self.websocket_connections:
            try:
                await ws.send_str(message)
            except Exception:
                disconnected.add(ws)

        # Remove disconnected clients
        self.websocket_connections -= disconnected

    async def start_metrics_broadcasting(self):
        """Start background task for broadcasting metrics updates."""
        while True:
            try:
                # Generate current metrics
                metrics = await self.monitor.generate_performance_report()

                # Broadcast to WebSocket clients
                await self.broadcast_metrics_update(metrics)

            except Exception as e:
                logger.error(f"Error in metrics broadcasting: {e}")

            # Wait before next update
            await asyncio.sleep(10)  # Update every 10 seconds

    async def run(self):
        """Start the performance dashboard server."""
        # Initialize Redis connection for the monitor
        await self.monitor.initialize_redis_connection()

        # Start background metrics broadcasting
        asyncio.create_task(self.start_metrics_broadcasting())

        # Start the web server
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.port)
        await site.start()

        logger.info(f"AutoBot Performance Dashboard running on http://localhost:{self.port}")
        logger.info("Real-time monitoring active with WebSocket updates")

        # Keep the server running
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down dashboard...")
        finally:
            await runner.cleanup()

async def main():
    """Main function to run the performance dashboard."""
    import argparse

    parser = argparse.ArgumentParser(description='AutoBot Performance Dashboard')
    parser.add_argument('--port', type=int, default=9090, help='Dashboard port (default: 9090)')

    args = parser.parse_args()

    dashboard = PerformanceDashboard(port=args.port)
    await dashboard.run()

if __name__ == "__main__":
    asyncio.run(main())
