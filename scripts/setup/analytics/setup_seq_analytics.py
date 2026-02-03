#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
import sys
from datetime import datetime
from pathlib import Path

import requests

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class SeqAnalyticsSetup:
    """Setup comprehensive analytics for AutoBot in Seq."""

    def __init__(
        self,
        seq_url: str = "http://localhost:5341",
        username: str = "admin",
        password: str = "Autobot123!",
    ):
        """Initialize Seq analytics setup with connection credentials."""
        self.seq_url = seq_url.rstrip("/")
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.auth = (username, password)

        # Load queries configuration
        self.config_file = Path(__file__).parent.parent / "config" / "seq-queries.json"
        self.queries_config = self.load_queries_config()

    def load_queries_config(self):
        """Load queries configuration from JSON file."""
        try:
            with open(self.config_file, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ Failed to load queries config: {e}")
            return {"autobot_queries": {}, "dashboards": []}

    def test_connection(self):
        """Test connection to Seq."""
        try:
            response = self.session.get(f"{self.seq_url}/api")
            if response.status_code == 200:
                print("✅ Connected to Seq successfully")
                seq_info = response.json()
                print(f"   Seq Version: {seq_info.get('Version', 'Unknown')}")
                return True
            else:
                print(f"❌ Seq connection failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Cannot connect to Seq: {e}")
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
                print(f"✅ Created signal: {name}")
                return response.json()
            else:
                print(f"⚠️  Failed to create signal '{name}': {response.status_code}")
                print(f"   Response: {response.text}")
                return None

        except Exception as e:
            print(f"❌ Error creating signal '{name}': {e}")
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
                print(f"✅ Created dashboard: {title}")
                return response.json()
            else:
                print(
                    f"⚠️  Failed to create dashboard '{title}': {response.status_code}"
                )
                return None

        except Exception as e:
            print(f"❌ Error creating dashboard '{title}': {e}")
            return None

    def setup_retention_policy(self, days_to_keep=30):
        """Setup log retention policy."""
        try:
            # Get current retention policies
            response = self.session.get(f"{self.seq_url}/api/retentionpolicies")
            if response.status_code != 200:
                print(f"⚠️  Cannot fetch retention policies: {response.status_code}")
                return False

            policies = response.json()

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
                print(f"✅ Created retention policy: {days_to_keep} days")
                return True
            else:
                print(f"⚠️  Failed to create retention policy: {response.status_code}")
                return False

        except Exception as e:
            print(f"❌ Error setting up retention policy: {e}")
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
                print(f"✅ Created alert: {title}")
                return response.json()
            else:
                print(f"⚠️  Failed to create alert '{title}': {response.status_code}")
                return None

        except Exception as e:
            print(f"❌ Error creating alert '{title}': {e}")
            return None

    def setup_all_queries(self):
        """Setup all AutoBot queries as signals."""
        print("🔍 Setting up AutoBot analysis queries...")

        created_signals = []

        for category, queries in self.queries_config["autobot_queries"].items():
            print(f"\n📊 Setting up {category.replace('_', ' ').title()} queries...")

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

        print(f"\n✅ Created {len(created_signals)} analysis queries")
        return created_signals

    def setup_dashboards(self):
        """Setup AutoBot dashboards."""
        print("📈 Setting up AutoBot dashboards...")

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

        print(f"✅ Created {len(created_dashboards)} dashboards")
        return created_dashboards

    def setup_critical_alerts(self):
        """Setup critical alerts for AutoBot."""
        print("🚨 Setting up critical alerts...")

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
            created_alert = self.create_alert(
                title=alert["title"], signal_expression=alert["expression"]
            )
            if created_alert:
                created_alerts.append(created_alert)

        print(f"✅ Created {len(created_alerts)} critical alerts")
        return created_alerts

    def send_test_logs_for_analysis(self):
        """Send comprehensive test logs to verify analytics."""
        print("🧪 Sending comprehensive test logs for analytics verification...")

        test_logs = [
            # System startup logs
            {
                "@t": datetime.utcnow().isoformat() + "Z",
                "@l": "Information",
                "@mt": "AutoBot system started successfully",
                "Source": "System",
                "Application": "AutoBot",
                "LogType": "System",
            },
            # Backend logs
            {
                "@t": datetime.utcnow().isoformat() + "Z",
                "@l": "Information",
                "@mt": "Backend service initialized on port 8001",
                "Source": "Backend-Main",
                "Application": "AutoBot",
                "ProcessID": "12345",
            },
            # Docker container logs
            {
                "@t": datetime.utcnow().isoformat() + "Z",
                "@l": "Information",
                "@mt": "Container started successfully",
                "Source": "Docker-autobot-redis",
                "Application": "AutoBot",
                "ContainerName": "autobot-redis",
                "LogType": "DockerContainer",
            },
            {
                "@t": datetime.utcnow().isoformat() + "Z",
                "@l": "Information",
                "@mt": "NPU worker ready for processing",
                "Source": "Docker-autobot-npu-worker",
                "Application": "AutoBot",
                "ContainerName": "autobot-npu-worker",
                "LogType": "DockerContainer",
            },
            # WebSocket logs
            {
                "@t": datetime.utcnow().isoformat() + "Z",
                "@l": "Information",
                "@mt": "WebSocket connection established",
                "Source": "GlobalWebSocketService",
                "Application": "AutoBot",
                "ConnectionType": "Global",
            },
            # Performance logs
            {
                "@t": datetime.utcnow().isoformat() + "Z",
                "@l": "Information",
                "@mt": "API request completed in 45ms",
                "Source": "Backend-API",
                "Application": "AutoBot",
                "ResponseTime": "45ms",
            },
            {
                "@t": datetime.utcnow().isoformat() + "Z",
                "@l": "Warning",
                "@mt": "High memory usage detected: 85%",
                "Source": "System-Monitor",
                "Application": "AutoBot",
                "MemoryUsage": "85%",
            },
            # Error simulation
            {
                "@t": datetime.utcnow().isoformat() + "Z",
                "@l": "Error",
                "@mt": "Database connection failed - retrying",
                "Source": "Backend-Database",
                "Application": "AutoBot",
                "Error": "ConnectionTimeout",
            },
            {
                "@t": datetime.utcnow().isoformat() + "Z",
                "@l": "Warning",
                "@mt": "WebSocket disconnection detected",
                "Source": "GlobalWebSocketService",
                "Application": "AutoBot",
                "DisconnectionReason": "timeout",
            },
            # Chat system logs
            {
                "@t": datetime.utcnow().isoformat() + "Z",
                "@l": "Information",
                "@mt": "Chat message processed successfully",
                "Source": "ChatInterface",
                "Application": "AutoBot",
                "MessageType": "user",
            },
            # Security logs
            {
                "@t": datetime.utcnow().isoformat() + "Z",
                "@l": "Information",
                "@mt": "User authentication successful",
                "Source": "AuthService",
                "Application": "AutoBot",
                "AuthType": "session",
            },
        ]

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
                    print(f"⚠️  Failed to send test log: {response.status_code}")
            except Exception as e:
                print(f"❌ Error sending test log: {e}")

        print(f"✅ Sent {success_count}/{len(test_logs)} test logs for analytics")
        return success_count

    def setup_all(self):
        """Setup all Seq analytics components."""
        print("🚀 Setting up comprehensive AutoBot analytics in Seq...")
        print(f"   Seq URL: {self.seq_url}")
        print(f"   Time: {datetime.now()}")

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

        print("\n🎉 AutoBot Seq Analytics Setup Complete!")
        print(f"   📊 Signals created: {len(signals)}")
        print(f"   📈 Dashboards created: {len(dashboards)}")
        print(f"   🚨 Alerts created: {len(alerts)}")
        print(f"   🧪 Test logs sent: {test_logs_sent}")
        print(f"\n🌐 Access Seq at: {self.seq_url}")
        print(f"   Username: {self.username}")
        print(f"   Password: {self.password}")

        return True

    def cleanup_autobot_items(self):
        """Clean up AutoBot-related items in Seq."""
        print("🧹 Cleaning up existing AutoBot items...")

        # Delete signals
        try:
            response = self.session.get(f"{self.seq_url}/api/signals")
            if response.status_code == 200:
                signals = response.json()
                autobot_signals = [
                    s for s in signals if "AutoBot" in s.get("Title", "")
                ]

                for signal in autobot_signals:
                    delete_response = self.session.delete(
                        f"{self.seq_url}/api/signals/{signal['Id']}"
                    )
                    if delete_response.status_code == 200:
                        print(f"🗑️  Deleted signal: {signal['Title']}")
        except Exception as e:
            print(f"⚠️  Error cleaning up signals: {e}")

        # Delete dashboards
        try:
            response = self.session.get(f"{self.seq_url}/api/dashboards")
            if response.status_code == 200:
                dashboards = response.json()
                autobot_dashboards = [
                    d for d in dashboards if "AutoBot" in d.get("Title", "")
                ]

                for dashboard in autobot_dashboards:
                    delete_response = self.session.delete(
                        f"{self.seq_url}/api/dashboards/{dashboard['Id']}"
                    )
                    if delete_response.status_code == 200:
                        print(f"🗑️  Deleted dashboard: {dashboard['Title']}")
        except Exception as e:
            print(f"⚠️  Error cleaning up dashboards: {e}")


def main():
    """Entry point for Seq analytics setup CLI."""
    parser = argparse.ArgumentParser(description="AutoBot Seq Analytics Setup")

    parser.add_argument(
        "--setup-all", action="store_true", help="Setup all analytics components"
    )
    parser.add_argument(
        "--cleanup", action="store_true", help="Clean up existing AutoBot items"
    )
    parser.add_argument(
        "--test-connection", action="store_true", help="Test Seq connection"
    )
    parser.add_argument(
        "--send-test-logs", action="store_true", help="Send test logs for verification"
    )
    parser.add_argument(
        "--seq-url", default="http://localhost:5341", help="Seq server URL"
    )
    parser.add_argument("--username", default="admin", help="Seq username")
    parser.add_argument("--password", default="Autobot123!", help="Seq password")

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

    if not any(
        [args.setup_all, args.cleanup, args.test_connection, args.send_test_logs]
    ):
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
