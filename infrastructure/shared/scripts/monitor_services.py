#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Service Health Monitor
==============================

Real-time monitoring dashboard for AutoBot services across deployment modes.
Provides web-based dashboard and CLI monitoring capabilities.

Usage:
    python scripts/monitor_services.py --web --port 8080
    python scripts/monitor_services.py --cli --interval 5
    python scripts/monitor_services.py --json --output metrics.json
"""

import argparse
import asyncio
import json
import logging
import sys
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path
from threading import Thread
from typing import Any, Dict, List, Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.service_registry import ServiceStatus, get_service_registry

# Optional web dependencies
try:
    from flask import Flask, jsonify, render_template_string, request
    from flask_cors import CORS

    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False
    logging.warning("Flask not available. Web dashboard disabled.")

# Setup logger
logger = logging.getLogger(__name__)


class ServiceMonitor:
    """Monitors AutoBot services health and performance."""

    def __init__(self, config_file: Optional[str] = None):
        """Initialize service monitor with registry and monitoring data structures."""
        self.service_registry = get_service_registry(config_file)
        self.monitoring_data: Dict[str, List[Dict[str, Any]]] = {}
        self.is_monitoring = False
        self.start_time = datetime.now()

        # Initialize monitoring data for all services
        for service in self.service_registry.list_services():
            self.monitoring_data[service] = []

    async def check_all_services(self) -> Dict[str, Any]:
        """Check health of all services and return status."""
        try:
            health_results = await self.service_registry.check_all_services_health()
            deployment_info = self.service_registry.get_deployment_info()

            timestamp = datetime.now()

            # Store health data for each service
            for service, health in health_results.items():
                health_record = {
                    "timestamp": timestamp.isoformat(),
                    "status": health.status.value,
                    "response_time": getattr(health, "response_time", 0),
                    "error_message": getattr(health, "error", None),
                }

                # Keep last 100 records per service
                self.monitoring_data[service].append(health_record)
                if len(self.monitoring_data[service]) > 100:
                    self.monitoring_data[service].pop(0)

            # Calculate overall health statistics
            total_services = len(health_results)
            healthy_services = sum(
                1 for h in health_results.values() if h.status == ServiceStatus.HEALTHY
            )

            overall_status = {
                "timestamp": timestamp.isoformat(),
                "deployment_mode": deployment_info["deployment_mode"],
                "total_services": total_services,
                "healthy_services": healthy_services,
                "unhealthy_services": total_services - healthy_services,
                "health_percentage": (healthy_services / total_services * 100)
                if total_services > 0
                else 0,
                "uptime": str(timestamp - self.start_time),
                "services": {
                    service: {
                        "status": health.status.value,
                        "url": self.service_registry.get_service_url(service),
                        "response_time": getattr(health, "response_time", 0),
                        "last_check": timestamp.isoformat(),
                    }
                    for service, health in health_results.items()
                },
            }

            return overall_status

        except Exception as e:
            return {
                "timestamp": datetime.now().isoformat(),
                "error": str(e),
                "status": "monitoring_error",
            }

    async def start_monitoring(self, interval: int = 30):
        """Start continuous monitoring with specified interval."""
        self.is_monitoring = True
        logger.info("Starting service monitoring (interval: %ds)", interval)

        while self.is_monitoring:
            try:
                status = await self.check_all_services()
                yield status
                await asyncio.sleep(interval)
            except KeyboardInterrupt:
                self.is_monitoring = False
                break
            except Exception as e:
                logger.error("Monitoring error: %s", e)
                await asyncio.sleep(interval)

    def stop_monitoring(self):
        """Stop monitoring."""
        self.is_monitoring = False

    def get_service_history(
        self, service: str, hours: int = 24
    ) -> List[Dict[str, Any]]:
        """Get historical data for a specific service."""
        if service not in self.monitoring_data:
            return []

        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [
            record
            for record in self.monitoring_data[service]
            if datetime.fromisoformat(record["timestamp"]) > cutoff_time
        ]

    def generate_report(self) -> Dict[str, Any]:
        """Generate comprehensive monitoring report."""
        report = {
            "generated_at": datetime.now().isoformat(),
            "monitoring_duration": str(datetime.now() - self.start_time),
            "deployment_info": self.service_registry.get_deployment_info(),
            "services": {},
        }

        for service in self.service_registry.list_services():
            history = self.monitoring_data.get(service, [])

            if not history:
                report["services"][service] = {"status": "no_data"}
                continue

            # Calculate service statistics
            recent_checks = history[-10:] if len(history) >= 10 else history
            healthy_checks = sum(1 for r in recent_checks if r["status"] == "healthy")
            total_checks = len(recent_checks)

            avg_response_time = (
                sum(r.get("response_time", 0) for r in recent_checks) / total_checks
                if total_checks > 0
                else 0
            )

            report["services"][service] = {
                "current_status": history[-1]["status"] if history else "unknown",
                "availability_percentage": (healthy_checks / total_checks * 100)
                if total_checks > 0
                else 0,
                "average_response_time": round(avg_response_time, 3),
                "total_checks": len(history),
                "last_check": history[-1]["timestamp"] if history else None,
                "url": self.service_registry.get_service_url(service),
            }

        return report


class CLIMonitor:
    """Command-line interface for monitoring."""

    def __init__(self, monitor: ServiceMonitor):
        """Initialize CLI monitor with service monitor instance."""
        self.monitor = monitor

    def print_status_table(self, status: Dict[str, Any]):
        """Print status in a nice table format."""
        logger.info("=" * 80)
        logger.info("AutoBot Service Monitor - %s", status.get('timestamp', 'Unknown'))
        logger.info("Deployment Mode: %s", status.get('deployment_mode', 'Unknown'))
        logger.info(
            "Overall Health: %d/%d services healthy (%.1f%%)",
            status.get('healthy_services', 0),
            status.get('total_services', 0),
            status.get('health_percentage', 0)
        )
        logger.info("=" * 80)

        # Service status table
        logger.info("%-20s %-12s %-35s %-10s", 'Service', 'Status', 'URL', 'Response')
        logger.info("-" * 80)

        services = status.get("services", {})
        for service_name, service_data in services.items():
            status_icon = {
                "healthy": "✅",
                "unhealthy": "❌",
                "unreachable": "🔌",
                "circuit_open": "⚡",
            }.get(service_data["status"], "❓")

            response_time = service_data.get("response_time", 0)
            response_str = f"{response_time:.3f}s" if response_time > 0 else "N/A"

            logger.info(
                "%-20s %s %-10s %-35s %-10s",
                service_name,
                status_icon,
                service_data['status'],
                service_data['url'],
                response_str
            )

        logger.info("-" * 80)

    async def run_continuous(self, interval: int = 30):
        """Run continuous CLI monitoring."""
        try:
            async for status in self.monitor.start_monitoring(interval):
                # Clear screen (works on most terminals)
                logger.info("\033[2J\033[H")
                self.print_status_table(status)
                logger.info("Next check in %ds... (Ctrl+C to stop)", interval)
        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")


class WebDashboard:
    """Web-based monitoring dashboard."""

    def __init__(self, monitor: ServiceMonitor, port: int = 8080):
        """Initialize web dashboard with Flask application and routes."""
        if not FLASK_AVAILABLE:
            raise ImportError(
                "Flask required for web dashboard. Install with: pip install flask flask-cors"
            )

        self.monitor = monitor
        self.port = port
        self.app = Flask(__name__)
        CORS(self.app)

        self.setup_routes()

    def setup_routes(self):
        """Set up Flask routes for dashboard, API status, history, and reports."""

        @self.app.route("/")
        def dashboard():
            """Render the main dashboard HTML template."""
            return render_template_string(HTML_TEMPLATE)

        @self.app.route("/api/status")
        async def api_status():
            """Return current status of all monitored services as JSON."""
            status = await self.monitor.check_all_services()
            return jsonify(status)

        @self.app.route("/api/history/<service>")
        def api_service_history(service):
            """Return historical data for a specific service as JSON."""
            hours = int(request.args.get("hours", 24))
            history = self.monitor.get_service_history(service, hours)
            return jsonify(history)

        @self.app.route("/api/report")
        def api_report():
            """Return comprehensive monitoring report as JSON."""
            report = self.monitor.generate_report()
            return jsonify(report)

    def run(self):
        """Start the web dashboard server and open browser automatically."""
        logger.info("Starting web dashboard on http://localhost:%d", self.port)
        logger.info("Dashboard will auto-refresh every 30 seconds")

        # Open browser automatically
        webbrowser.open(f"http://localhost:{self.port}")

        self.app.run(host="0.0.0.0", port=self.port, debug=False)


# HTML template for web dashboard
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AutoBot Service Monitor</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: rgba(255,255,255,0.95);
            border-radius: 15px;
            padding: 30px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid #e0e0e0;
        }
        .title {
            color: #333;
            font-size: 2.5rem;
            margin-bottom: 10px;
            font-weight: 700;
        }
        .subtitle {
            color: #666;
            font-size: 1.1rem;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            text-align: center;
            border-left: 4px solid #667eea;
        }
        .stat-value {
            font-size: 2rem;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 5px;
        }
        .stat-label {
            color: #666;
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .services-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }
        .service-card {
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            transition: transform 0.2s ease;
        }
        .service-card:hover { transform: translateY(-2px); }
        .service-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }
        .service-name {
            font-size: 1.2rem;
            font-weight: 600;
            color: #333;
        }
        .status-badge {
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 500;
            text-transform: uppercase;
        }
        .status-healthy { background: #d4edda; color: #155724; }
        .status-unhealthy { background: #f8d7da; color: #721c24; }
        .status-unreachable { background: #fff3cd; color: #856404; }
        .service-url {
            color: #666;
            font-size: 0.9rem;
            margin-bottom: 10px;
            word-break: break-all;
        }
        .response-time {
            color: #667eea;
            font-weight: 500;
        }
        .last-updated {
            text-align: center;
            margin-top: 30px;
            color: #666;
            font-style: italic;
        }
        .loading {
            text-align: center;
            color: #667eea;
            font-size: 1.2rem;
            margin: 50px 0;
        }
        .error {
            background: #f8d7da;
            color: #721c24;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 class="title">🚀 AutoBot Service Monitor</h1>
            <p class="subtitle" id="deployment-mode">Loading deployment information...</p>
        </div>

        <div class="stats-grid" id="stats-grid">
            <div class="loading">Loading service statistics...</div>
        </div>

        <div class="services-grid" id="services-grid">
            <div class="loading">Loading service status...</div>
        </div>

        <div class="last-updated" id="last-updated"></div>
    </div>

    <script>
        async function fetchStatus() {
            try {
                const response = await fetch('/api/status');
                const data = await response.json();
                updateDashboard(data);
            } catch (error) {
                document.getElementById('services-grid').innerHTML =
                    '<div class="error">Failed to fetch service status: ' + error.message + '</div>';
            }
        }

        function updateDashboard(data) {
            // Update deployment mode
            document.getElementById('deployment-mode').textContent =
                `Deployment Mode: ${data.deployment_mode || 'Unknown'} | Uptime: ${data.uptime || 'Unknown'}`;

            // Update stats
            const statsHtml = `
                <div class="stat-card">
                    <div class="stat-value">${data.total_services || 0}</div>
                    <div class="stat-label">Total Services</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${data.healthy_services || 0}</div>
                    <div class="stat-label">Healthy Services</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${data.unhealthy_services || 0}</div>
                    <div class="stat-label">Unhealthy Services</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">${(data.health_percentage || 0).toFixed(1)}%</div>
                    <div class="stat-label">Overall Health</div>
                </div>
            `;
            document.getElementById('stats-grid').innerHTML = statsHtml;

            // Update services
            const services = data.services || {};
            const servicesHtml = Object.entries(services).map(([name, service]) => `
                <div class="service-card">
                    <div class="service-header">
                        <div class="service-name">${name}</div>
                        <span class="status-badge status-${service.status}">${service.status}</span>
                    </div>
                    <div class="service-url">${service.url}</div>
                    <div class="response-time">
                        Response Time: ${service.response_time > 0 ? service.response_time.toFixed(3) + 's' : 'N/A'}
                    </div>
                </div>
            `).join('');

            document.getElementById('services-grid').innerHTML = servicesHtml;

            // Update timestamp
            document.getElementById('last-updated').textContent =
                `Last updated: ${new Date(data.timestamp).toLocaleString()}`;
        }

        // Initial load and set up auto-refresh
        fetchStatus();
        setInterval(fetchStatus, 30000); // Refresh every 30 seconds
    </script>
</body>
</html>
"""


async def main():
    """Main entry point for service monitoring with CLI argument parsing."""
    parser = argparse.ArgumentParser(
        description="AutoBot Service Health Monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--config", help="Configuration file path")
    parser.add_argument("--web", action="store_true", help="Start web dashboard")
    parser.add_argument("--cli", action="store_true", help="Start CLI monitor")
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    parser.add_argument("--port", type=int, default=8080, help="Web dashboard port")
    parser.add_argument(
        "--interval", type=int, default=30, help="Check interval in seconds"
    )
    parser.add_argument("--output", help="Output file for JSON report")

    args = parser.parse_args()

    if not any([args.web, args.cli, args.json]):
        args.cli = True  # Default to CLI mode

    monitor = ServiceMonitor(args.config)

    try:
        if args.json:
            # Single check and JSON output
            status = await monitor.check_all_services()
            report = monitor.generate_report()

            output_data = {"current_status": status, "report": report}

            if args.output:
                with open(args.output, "w") as f:
                    json.dump(output_data, f, indent=2)
                logger.info("Report saved to: %s", args.output)
            else:
                logger.info(json.dumps(output_data, indent=2))

        elif args.web:
            # Start web dashboard
            dashboard = WebDashboard(monitor, args.port)

            # Start monitoring in background thread
            def background_monitor():
                asyncio.run(monitor.start_monitoring(args.interval))

            monitor_thread = Thread(target=background_monitor, daemon=True)
            monitor_thread.start()

            dashboard.run()

        elif args.cli:
            # Start CLI monitoring
            cli = CLIMonitor(monitor)
            await cli.run_continuous(args.interval)

    except KeyboardInterrupt:
        monitor.stop_monitoring()
        logger.info("Monitoring stopped")
    except Exception as e:
        logger.error("Error: %s", e)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
