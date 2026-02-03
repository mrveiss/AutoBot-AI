#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Node Agent - Standalone with Service Discovery

Lightweight daemon that runs on each managed node:
- Sends heartbeats to admin machine
- Collects and reports health data
- Discovers and reports all systemd services

Related to Issue #728
"""

import logging
import os
import platform
import signal
import subprocess
import sys
import time
from typing import Dict, List

import psutil
import requests
import urllib3
import yaml

# Suppress InsecureRequestWarning for self-signed certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("slm-agent")


class SLMAgent:
    """SLM Node Agent with service discovery."""

    def __init__(self, config_path: str = "/opt/autobot/config.yaml"):
        self.running = False
        self.config = self._load_config(config_path)
        self.hostname = platform.node()

    def _load_config(self, path: str) -> dict:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return yaml.safe_load(f)
        return {
            "node_id": os.environ.get("SLM_NODE_ID", "unknown"),
            "admin_url": os.environ.get("SLM_ADMIN_URL", "http://172.16.168.19:8000"),
            "heartbeat_interval": int(os.environ.get("SLM_HEARTBEAT_INTERVAL", "30")),
        }

    def collect_health(self) -> dict:
        """Collect system health metrics."""
        return {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage("/").percent,
            "load_avg": list(psutil.getloadavg()),
            "uptime_seconds": int(time.time() - psutil.boot_time()),
            "hostname": self.hostname,
        }

    def discover_all_services(self) -> List[Dict]:
        """
        Discover all systemd services on the node.

        Returns list of service info dicts with status, enabled state, etc.
        Related to Issue #728.
        """
        services = []
        try:
            # List all loaded service units with their states
            result = subprocess.run(
                [
                    "systemctl", "list-units",
                    "--type=service",
                    "--all",
                    "--no-pager",
                    "--no-legend",
                    "--plain",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                logger.warning("Failed to list services: %s", result.stderr)
                return services

            # Parse output: UNIT LOAD ACTIVE SUB DESCRIPTION
            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue

                parts = line.split(None, 4)
                if len(parts) < 4:
                    continue

                unit_name = parts[0]
                # Skip template units and non-.service units
                if "@" in unit_name or not unit_name.endswith(".service"):
                    continue

                service_name = unit_name.replace(".service", "")
                load_state = parts[1]  # loaded, not-found, masked
                active_state = parts[2]  # active, inactive, failed
                sub_state = parts[3]  # running, dead, exited, failed

                # Map to our status enum
                if active_state == "active" and sub_state == "running":
                    status = "running"
                elif active_state == "failed" or sub_state == "failed":
                    status = "failed"
                elif active_state == "inactive":
                    status = "stopped"
                else:
                    status = "unknown"

                service_info = {
                    "name": service_name,
                    "status": status,
                    "active_state": active_state,
                    "sub_state": sub_state,
                    "load_state": load_state,
                }

                # Get additional details for running services
                if status == "running":
                    details = self._get_service_details(service_name)
                    service_info.update(details)

                services.append(service_info)

        except subprocess.TimeoutExpired:
            logger.warning("Timeout discovering services")
        except FileNotFoundError:
            logger.warning("systemctl not found - not a systemd system")
        except Exception as e:
            logger.warning("Error discovering services: %s", e)

        return services

    def _get_service_details(self, service_name: str) -> Dict:
        """Get detailed info for a specific service."""
        details = {}
        try:
            result = subprocess.run(
                [
                    "systemctl", "show", service_name,
                    "--property=MainPID,MemoryCurrent,Description,UnitFileState",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if "=" in line:
                        key, value = line.split("=", 1)
                        if key == "MainPID" and value.isdigit():
                            details["main_pid"] = int(value)
                        elif key == "MemoryCurrent" and value.isdigit():
                            details["memory_bytes"] = int(value)
                        elif key == "Description":
                            details["description"] = value[:500]
                        elif key == "UnitFileState":
                            details["enabled"] = value == "enabled"

        except Exception as e:
            logger.debug("Could not get details for %s: %s", service_name, e)

        return details

    def send_heartbeat(self) -> bool:
        """Send heartbeat with health data and discovered services."""
        try:
            health = self.collect_health()
            discovered_services = self.discover_all_services()

            payload = {
                "cpu_percent": health.get("cpu_percent", 0.0),
                "memory_percent": health.get("memory_percent", 0.0),
                "disk_percent": health.get("disk_percent", 0.0),
                "agent_version": "1.1.0",
                "os_info": f"{platform.system()} {platform.release()}",
                "extra_data": {
                    "discovered_services": discovered_services,
                    "load_avg": health.get("load_avg", []),
                    "uptime_seconds": health.get("uptime_seconds", 0),
                    "hostname": health.get("hostname"),
                },
            }

            url = f"{self.config['admin_url']}/api/nodes/{self.config['node_id']}/heartbeat"
            response = requests.post(url, json=payload, timeout=10, verify=False)
            response.raise_for_status()

            logger.debug(
                "Heartbeat sent: %d services discovered",
                len(discovered_services)
            )
            return True
        except Exception as e:
            logger.error("Heartbeat failed: %s", e)
            return False

    def run(self):
        """Main agent loop."""
        self.running = True
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "running", False))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "running", False))

        logger.info("SLM Agent v1.1.0 starting - Node: %s", self.config["node_id"])
        logger.info("Admin URL: %s", self.config["admin_url"])
        logger.info("Heartbeat interval: %ds", self.config["heartbeat_interval"])

        while self.running:
            self.send_heartbeat()
            time.sleep(self.config["heartbeat_interval"])

        logger.info("SLM Agent stopped")


if __name__ == "__main__":
    agent = SLMAgent()
    agent.run()
