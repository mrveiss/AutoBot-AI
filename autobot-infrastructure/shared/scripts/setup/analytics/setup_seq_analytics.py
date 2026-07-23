#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Seq Analytics Setup for AutoBot
==============================

Configures Seq for comprehensive AutoBot log analysis including:
- Dashboards for system monitoring
- Queries for error analysis and performance tracking
- Retention policies for log management
- Alerts for critical issues

Usage:
    python scripts/setup_seq_analytics.py --setup-all
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class SeqAnalyticsSetup:
    """Setup comprehensive analytics for AutoBot in Seq."""

    def __init__(
        self,
        seq_url: str = "http://localhost:5341",
        username: str = "admin",
        password: str = "",
    ):
        """Initialize Seq analytics setup with connection credentials."""
        self.seq_url = seq_url.rstrip("/")
        self.username = username
        self.password = password or os.environ.get("SEQ_PASSWORD", "")
        self.session = requests.Session()
        self.session.auth = (username, self.password)

        # Load queries configuration
        self.config_file = Path(__file__).parent.parent / "config" / "seq-queries.json"
        self.queries_config = self.load_queries_config()

    def load_queries_config(self):
        """Load queries configuration from JSON file."""
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to load queries config: %s", e)
            return {"autobot_queries": {}, "dashboards": []}

    def test_connection(self):
        """Test connection to Seq."""
        try:
            response = self.session.get(f"{self.seq_url}/api")
            if response.status_code == 200:
                logger.info("Connected to Seq successfully")
                seq_info = response.json()
                logger.info("Seq Version: %s", seq_info.get("Version", "Unknown"))
                return True
            else:
                logger.error("Seq connection failed: %s", response.status_code)
                return False
        except Exception as e:
            logger.error("Cannot connect to Seq: %s", e)
            return False

    def create_signal(self, name, description, filter_expression, is_protected=False):
        """Create a Seq signal (saved query)."""
        try:
            signal_data = {
                "Title": name,
                "Description": description,
                "FilterExpression": filter_expression,
                "IsProtected": is_protected,
                "Tags": ["AutoBot", "Analytics"],
            }

            response = self.session.post(
                f"{self.seq_url}/api/signals",
                json=signal_data,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code in [200, 201]:
                logger.info("Created signal: %s", name)
                return response.json()
            else:
                logger.warning("Failed to create signal '%s': %s", name, response.status_code)
                logger.warning("Response: %s", response.text)
                return None

        except Exception as e:
            logger.error("Error creating signal '%s': %s", name, e)
            return None

    def create_dashboard(self, name, title, charts):
        """Create a Seq dashboard."""
        try:
            dashboard_data = {
                "Title": title,
                "Charts": charts,
                "Tags": ["AutoBot", "System"],
            }

            response = self.session.post(
                f"{self.seq_url}/api/dashboards",
                json=dashboard_data,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code in [200, 201]:
                logger.info("Created dashboard: %s", title)
                return response.json()
            else:
                logger.warning("Failed to create dashboard '%s': %s", title, response.status_code)
                return None

        except Exception as e:
            logger.error("Error creating dashboard '%s': %s", title, e)
            return None

    def setup_retention_policy(self, days_to_keep=30):
        """Setup log retention policy."""
        try:
            # Get current retention policies
            response = self.session.get(f"{self.seq_url}/api/retentionpolicies")
            if response.status_code != 200:
                logger.warning("Cannot fetch retention policies: %s", response.status_code)
                return False

            response.json()

            # Create AutoBot-specific retention policy
            retention_policy = {
                "FilterExpression": "Application = 'AutoBot'",
                "RetentionTime": f"{days_to_keep}.00:00:00",  # TimeSpan format
                "Name": "AutoBot Logs",
                "Description": f"Retain AutoBot logs for {days_to_keep} days",
            }

            response = self.session.post(
                f"{self.seq_url}/api/retentionpolicies",
                json=retention_policy,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code in [200, 201]:
                logger.info("Created retention policy: %s days", days_to_keep)
                return True
            else:
                logger.warning("Failed to create retention policy: %s", response.status_code)
                return False

        except Exception as e:
            logger.error("Error setting up retention policy: %s", e)
            return False

    def create_alert(self, title, signal_expression, webhook_url=None):
        """Create a Seq alert."""
        try:
            alert_data = {
                "Title": title,
                "FilterExpression": signal_expression,
                "Description": f"AutoBot alert: {title}",
                "IsActive": True,
                "SuppressionTime": "00:05:00",  # 5 minutes
                "Tags": ["AutoBot", "Alert"],
            }

            if webhook_url:
                alert_data["Actions"] = [
                    {
                        "ActionType": "Webhook",
                        "Configuration": {"Url": webhook_url, "Method": "POST"},
                    }
                ]

            response = self.session.post(
                f"{self.seq_url}/api/alerts",
                json=alert_data,
                headers={"Content-Type": "application/json"},
            )

            if response.status_code in [200, 201]:
                logger.info("Created alert: %s", title)
                return response.json()
            else:
                logger.warning("Failed to create alert '%s': %s", title, response.status_code)
                return None

        except Exception as e:
            logger.error("Error creating alert '%s': %s", title, e)
            return None

    def setup_all_queries(self):
        """Setup all AutoBot queries as signals."""
        logger.info("Setting up AutoBot analysis queries...")

        created_signals = []

        for category, queries in self.queries_config["autobot_queries"].items():
            logger.info("Setting up %s queries...", category.replace("_", " ").title())

            for query in queries:
                name = f"AutoBot - {query['name']}"
                signal = self.create_signal(
                    name=name,
                    description=query["description"],
                    filter_expression=query["query"],
                    is_protected=False,
                )
                if signal:
                    created_signals.append(signal)

        logger.info("Created %s analysis queries", len(created_signals))
        return created_signals

    def setup_dashboards(self):
        """Setup AutoBot dashboards."""
        logger.info("Setting up AutoBot dashboards...")

        created_dashboards = []

        for dashboard_config in self.queries_config["dashboards"]:
            charts = []

            for i, query in enumerate(dashboard_config["queries"]):
                chart = {
                    "Title": f"Chart {i+1}",
                    "Type": "Table",  # Can be "Table", "Line", "Bar", etc.
                    "Query": query,
                    "RefreshInterval": "00:01:00",  # 1 minute
                }
                charts.append(chart)

            dashboard = self.create_dashboard(
                name=dashboard_config["name"].lower().replace(" ", "_"),
                title=dashboard_config["name"],
                charts=charts,
            )

            if dashboard:
                created_dashboards.append(dashboard)

        logger.info("Created %s dashboards", len(created_dashboards))
        return created_dashboards

    def setup_critical_alerts(self):
        """Setup critical alerts for AutoBot."""
        logger.info("Setting up critical alerts...")

        critical_alerts = [
            {
                "title": "AutoBot Critical Errors",
                "expression": "@l = 'Error' and Application = 'AutoBot' and (@mt like '%Exception%' or @mt like '%Failed%' or @mt like '%Critical%')",
            },
            {
                "title": "AutoBot WebSocket Disconnections",
                "expression": "Source like 'GlobalWebSocketService' and @l in ['Error', 'Warning'] and @mt like '%disconnect%'",
            },
            {
                "title": "AutoBot Backend Service Down",
                "expression": "Source like 'Backend*' and @l = 'Error' and (@mt like '%startup%' or @mt like '%failed%')",
            },
            {
                "title": "AutoBot Container Issues",
                "expression": "LogType = 'DockerContainer' and @l = 'Error' and (@mt like '%container%' or @mt like '%docker%')",
            },
        ]

        created_alerts = []

        for alert in critical_alerts:
            created_alert = self.create_alert(title=alert["title"], signal_expression=alert["expression"])
            if created_alert:
                created_alerts.append(created_alert)

        logger.info("Created %s critical alerts", len(created_alerts))
        return created_alerts

    def _build_test_log_entries(self):
        """Build test log entries for analytics verification (#1792)."""
        now = datetime.now(timezone.utc).isoformat()
        base = {"Application": "AutoBot"}

        def _entry(level, message, source, **extra):
            return {"@t": now, "@l": level, "@mt": message, "Source": source, **base, **extra}

        return [
            _entry("Information", "AutoBot system started successfully", "System", LogType="System"),
            _entry("Information", "Backend service initialized on port 8001", "Backend-Main", ProcessID="12345"),
            _entry(
                "Information",
                "Container started successfully",
                "Docker-autobot-redis",
                ContainerName="autobot-redis",
                LogType="DockerContainer",
            ),
            _entry(
                "Information",
                "NPU worker ready for processing",
                "Docker-autobot-npu-worker",
                ContainerName="autobot-npu-worker",
                LogType="DockerContainer",
            ),
            _entry(
                "Information", "WebSocket connection established", "GlobalWebSocketService", ConnectionType="Global"
            ),
            _entry("Information", "API request completed in 45ms", "Backend-API", ResponseTime="45ms"),
            _entry("Warning", "High memory usage detected: 85%", "System-Monitor", MemoryUsage="85%"),
            _entry("Error", "Database connection failed - retrying", "Backend-Database", Error="ConnectionTimeout"),
            _entry(
                "Warning", "WebSocket disconnection detected", "GlobalWebSocketService", DisconnectionReason="timeout"
            ),
            _entry("Information", "Chat message processed successfully", "ChatInterface", MessageType="user"),
            _entry("Information", "User authentication successful", "AuthService", AuthType="session"),
        ]

    def send_test_logs_for_analysis(self):
        """Send comprehensive test logs to verify analytics."""
        logger.info("Sending comprehensive test logs for analytics verification...")

        test_logs = self._build_test_log_entries()
        headers = {
            "Content-Type": "application/vnd.serilog.clef",
            "User-Agent": "AutoBot-SeqSetup/1.0",
        }

        success_count = 0

        for log_entry in test_logs:
            try:
                response = requests.post(
                    f"{self.seq_url}/api/events/raw",
                    headers=headers,
                    data=json.dumps(log_entry) + "\n",
                    timeout=5,
                )

                if response.status_code in [200, 201]:
                    success_count += 1
                else:
                    logger.warning("Failed to send test log: %s", response.status_code)
            except Exception as e:
                logger.error("Error sending test log: %s", e)

        logger.info("Sent %s/%s test logs for analytics", success_count, len(test_logs))
        return success_count

    def setup_all(self):
        """Setup all Seq analytics components."""
        logger.info("Setting up comprehensive AutoBot analytics in Seq...")
        logger.info("Seq URL: %s", self.seq_url)
        logger.info("Time: %s", datetime.now())

        if not self.test_connection():
            return False

        # Setup retention policy
        self.setup_retention_policy(days_to_keep=30)

        # Setup queries as signals
        signals = self.setup_all_queries()

        # Setup dashboards
        dashboards = self.setup_dashboards()

        # Setup critical alerts
        alerts = self.setup_critical_alerts()

        # Send test logs
        test_logs_sent = self.send_test_logs_for_analysis()

        logger.info("AutoBot Seq Analytics Setup Complete!")
        logger.info("Signals created: %s", len(signals))
        logger.info("Dashboards created: %s", len(dashboards))
        logger.info("Alerts created: %s", len(alerts))
        logger.info("Test logs sent: %s", test_logs_sent)
        logger.info("Access Seq at: %s", self.seq_url)
        logger.info("Username: %s", self.username)
        logger.info("Password: [REDACTED]")

        return True

    def cleanup_autobot_items(self):
        """Clean up AutoBot-related items in Seq."""
        logger.info("Cleaning up existing AutoBot items...")

        # Delete signals
        try:
            response = self.session.get(f"{self.seq_url}/api/signals")
            if response.status_code == 200:
                signals = response.json()
                autobot_signals = [s for s in signals if "AutoBot" in s.get("Title", "")]

                for signal in autobot_signals:
                    delete_response = self.session.delete(f"{self.seq_url}/api/signals/{signal['Id']}")
                    if delete_response.status_code == 200:
                        logger.info("Deleted signal: %s", signal["Title"])
        except Exception as e:
            logger.warning("Error cleaning up signals: %s", e)

        # Delete dashboards
        try:
            response = self.session.get(f"{self.seq_url}/api/dashboards")
            if response.status_code == 200:
                dashboards = response.json()
                autobot_dashboards = [d for d in dashboards if "AutoBot" in d.get("Title", "")]

                for dashboard in autobot_dashboards:
                    delete_response = self.session.delete(f"{self.seq_url}/api/dashboards/{dashboard['Id']}")
                    if delete_response.status_code == 200:
                        logger.info("Deleted dashboard: %s", dashboard["Title"])
        except Exception as e:
            logger.warning("Error cleaning up dashboards: %s", e)


def main():
    """Entry point for Seq analytics setup CLI."""
    parser = argparse.ArgumentParser(description="AutoBot Seq Analytics Setup")

    parser.add_argument("--setup-all", action="store_true", help="Setup all analytics components")
    parser.add_argument("--cleanup", action="store_true", help="Clean up existing AutoBot items")
    parser.add_argument("--test-connection", action="store_true", help="Test Seq connection")
    parser.add_argument("--send-test-logs", action="store_true", help="Send test logs for verification")
    parser.add_argument("--seq-url", default="http://localhost:5341", help="Seq server URL")
    parser.add_argument("--username", default="admin", help="Seq username")
    parser.add_argument(
        "--password",
        default=os.environ.get("SEQ_PASSWORD", ""),
        help="Seq password (default: $SEQ_PASSWORD)",
    )

    args = parser.parse_args()

    setup = SeqAnalyticsSetup(args.seq_url, args.username, args.password)

    if args.cleanup:
        setup.cleanup_autobot_items()

    if args.test_connection:
        setup.test_connection()

    if args.send_test_logs:
        setup.send_test_logs_for_analysis()

    if args.setup_all:
        success = setup.setup_all()
        return 0 if success else 1

    if not any([args.setup_all, args.cleanup, args.test_connection, args.send_test_logs]):
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(main())
