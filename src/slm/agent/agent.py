# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Node Agent

Lightweight daemon that runs on each managed node:
- Sends heartbeats to admin machine
- Collects and reports health data
- Buffers events when admin is offline
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiohttp

from .health_collector import HealthCollector

logger = logging.getLogger(__name__)

# Standalone agent defaults - agent runs on remote VMs, not AutoBot main host
# These are configured via CLI args or environment variables at deployment
# Issue #694: Use environment variable with fallback
DEFAULT_ADMIN_URL = os.getenv("SLM_ADMIN_URL", "http://172.16.168.19:8000")
DEFAULT_HEARTBEAT_INTERVAL = 30  # seconds
DEFAULT_BUFFER_DB = os.path.expanduser("~/.slm-agent/events.db")


class SLMAgent:
    """SLM Node Agent daemon."""

    def __init__(
        self,
        admin_url: str = DEFAULT_ADMIN_URL,
        heartbeat_interval: int = DEFAULT_HEARTBEAT_INTERVAL,
        buffer_db: str = DEFAULT_BUFFER_DB,
        services: Optional[list] = None,
        node_id: Optional[str] = None,
    ):
        """Initialize agent."""
        self.admin_url = admin_url.rstrip("/")
        self.heartbeat_interval = heartbeat_interval
        self.buffer_db = buffer_db
        self.node_id = node_id or os.environ.get("SLM_NODE_ID")
        self.running = False

        self.collector = HealthCollector(services=services or [])
        self._init_buffer_db()

    def _init_buffer_db(self):
        """Initialize SQLite buffer database."""
        Path(self.buffer_db).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.buffer_db)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS event_buffer (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                data TEXT NOT NULL,
                synced INTEGER DEFAULT 0
            )
        """
        )
        conn.commit()
        conn.close()
        logger.info("Event buffer initialized at %s", self.buffer_db)

    def buffer_event(self, event_type: str, data: dict):
        """Buffer an event for later sync."""
        conn = sqlite3.connect(self.buffer_db)
        conn.execute(
            "INSERT INTO event_buffer (timestamp, event_type, data) VALUES (?, ?, ?)",
            (datetime.utcnow().isoformat(), event_type, json.dumps(data)),
        )
        conn.commit()
        conn.close()

    async def send_heartbeat(self) -> bool:
        """Send heartbeat with health data to admin."""
        import platform

        health = self.collector.collect()
        # Payload matches HeartbeatRequest schema
        os_info = f"{platform.system()} {platform.release()}"
        payload = {
            "cpu_percent": health.get("cpu_percent", 0.0),
            "memory_percent": health.get("memory_percent", 0.0),
            "disk_percent": health.get("disk_percent", 0.0),
            "agent_version": "1.0.0",
            "os_info": os_info,
            "extra_data": {
                "services": health.get("services", {}),
                "discovered_services": health.get("discovered_services", []),
                "load_avg": health.get("load_avg", []),
                "uptime_seconds": health.get("uptime_seconds", 0),
                "hostname": health.get("hostname"),
            },
        }

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.admin_url}/api/nodes/{self.node_id}/heartbeat"
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                    ssl=False,  # mTLS pending PKI setup (Issue #725)
                ) as response:
                    if response.status == 200:
                        logger.debug("Heartbeat sent successfully")
                        return True
                    else:
                        logger.warning(
                            "Heartbeat rejected: %s %s",
                            response.status,
                            await response.text(),
                        )
                        return False
        except aiohttp.ClientError as e:
            logger.warning("Failed to send heartbeat: %s", e)
            self.buffer_event("heartbeat", payload)
            return False

    async def sync_buffered_events(self):
        """Sync buffered events to admin."""
        conn = sqlite3.connect(self.buffer_db)
        cursor = conn.execute(
            "SELECT id, event_type, data FROM event_buffer WHERE synced = 0 ORDER BY id LIMIT 100"
        )
        events = cursor.fetchall()

        if not events:
            return

        logger.info("Syncing %d buffered events", len(events))

        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.admin_url}/api/v1/slm/events/sync"
                payload = [
                    {"id": e[0], "type": e[1], "data": json.loads(e[2])} for e in events
                ]
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                    ssl=False,  # mTLS pending PKI setup (Issue #725)
                ) as response:
                    if response.status == 200:
                        # Mark as synced
                        ids = [e[0] for e in events]
                        placeholders = ",".join("?" * len(ids))
                        conn.execute(
                            f"UPDATE event_buffer SET synced = 1 WHERE id IN ({placeholders})",
                            ids,
                        )
                        conn.commit()
                        logger.info("Synced %d events", len(events))
        except aiohttp.ClientError as e:
            logger.warning("Failed to sync events: %s", e)
        finally:
            conn.close()

    async def run(self):
        """Main agent loop."""
        self.running = True
        logger.info(
            "SLM Agent started (node_id=%s, admin=%s)", self.node_id, self.admin_url
        )

        while self.running:
            # Send heartbeat
            success = await self.send_heartbeat()

            # If connected, try to sync buffered events
            if success:
                await self.sync_buffered_events()

            # Wait for next heartbeat
            await asyncio.sleep(self.heartbeat_interval)

        logger.info("SLM Agent stopped")

    def stop(self):
        """Stop the agent."""
        self.running = False


def _parse_cli_args():
    """
    Parse command-line arguments.

    Related to Issue #726.
    """
    parser = argparse.ArgumentParser(description="SLM Node Agent")
    parser.add_argument(
        "--admin-url",
        default=os.environ.get("SLM_ADMIN_URL", DEFAULT_ADMIN_URL),
        help="Admin machine URL",
    )
    parser.add_argument(
        "--node-id",
        default=os.environ.get("SLM_NODE_ID"),
        help="Node ID",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_HEARTBEAT_INTERVAL,
        help="Heartbeat interval in seconds",
    )
    parser.add_argument(
        "--services",
        nargs="*",
        default=[],
        help="Systemd services to monitor",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def _configure_logging(debug: bool):
    """
    Configure logging based on debug flag.

    Related to Issue #726.
    """
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _setup_signal_handlers(agent: SLMAgent):
    """
    Set up signal handlers for graceful shutdown.

    Related to Issue #726.
    """

    def shutdown_handler(signum, frame):
        logger.info("Received signal %s, shutting down", signum)
        agent.stop()

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)


def main():
    """CLI entrypoint for SLM agent."""
    args = _parse_cli_args()
    _configure_logging(args.debug)

    if not args.node_id:
        logger.error("Node ID required (--node-id or SLM_NODE_ID)")
        sys.exit(1)

    # Create agent
    agent = SLMAgent(
        admin_url=args.admin_url,
        heartbeat_interval=args.interval,
        services=args.services,
        node_id=args.node_id,
    )

    # Setup signal handlers and run
    _setup_signal_handlers(agent)
    asyncio.run(agent.run())


if __name__ == "__main__":
    main()
