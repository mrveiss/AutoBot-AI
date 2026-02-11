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
import socket
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiohttp
from aiohttp import web


def sd_notify(state: str) -> bool:
    """
    Send notification to systemd.

    This is a lightweight implementation that doesn't require the sdnotify package.
    Used for watchdog support (prevents timeout restarts).

    Args:
        state: Notification state string (e.g., "READY=1", "WATCHDOG=1")

    Returns:
        True if notification was sent successfully, False otherwise.
    """
    notify_socket = os.environ.get("NOTIFY_SOCKET")
    if not notify_socket:
        return False

    try:
        # Handle abstract socket (starts with @)
        if notify_socket.startswith("@"):
            notify_socket = "\0" + notify_socket[1:]

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            sock.connect(notify_socket)
            sock.sendall(state.encode("utf-8"))
            return True
        finally:
            sock.close()
    except Exception:
        return False


from .health_collector import HealthCollector
from .version import get_agent_version

logger = logging.getLogger(__name__)

# Local notification server port (for git hooks)
DEFAULT_NOTIFY_PORT = int(os.getenv("SLM_NOTIFY_PORT", "8000"))

# Standalone agent defaults - agent runs on remote VMs, not AutoBot main host
# These are configured via CLI args or environment variables at deployment
# Issue #694: Use environment variable with fallback
DEFAULT_ADMIN_URL = os.getenv("SLM_ADMIN_URL", "https://172.16.168.19")
DEFAULT_HEARTBEAT_INTERVAL = 30  # seconds
# Buffer database path - use /var/lib/slm-agent for systemd compatibility
# (systemd service has ProtectHome=read-only and ReadWritePaths=/var/lib/slm-agent)
DEFAULT_BUFFER_DB = os.getenv("SLM_BUFFER_DB", "/var/lib/slm-agent/events.db")


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

        # Issue #741: Initialize version manager
        self.version_manager = get_agent_version()
        self._pending_update = False
        self._latest_version: Optional[str] = None

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

    def _process_heartbeat_response(self, response: dict) -> None:
        """
        Process heartbeat response from admin server.

        Issue #741: Handle update_available notification.
        """
        if response.get("update_available"):
            latest = response.get("latest_version", "unknown")
            current = self.version_manager.get_version() or "unknown"
            # Truncate long hashes for logging
            current_short = current[:12] if len(current) > 12 else current
            latest_short = latest[:12] if len(latest) > 12 else latest
            logger.info(
                "Update available: current=%s, latest=%s",
                current_short,
                latest_short,
            )
            self._pending_update = True
            self._latest_version = latest

    async def send_heartbeat(self) -> bool:
        """Send heartbeat with health data to admin."""
        import platform

        health = self.collector.collect()
        # Payload matches HeartbeatRequest schema
        os_info = f"{platform.system()} {platform.release()}"
        # Issue #741: Get code version for heartbeat
        code_version = self.version_manager.get_version()
        payload = {
            "cpu_percent": health.get("cpu_percent", 0.0),
            "memory_percent": health.get("memory_percent", 0.0),
            "disk_percent": health.get("disk_percent", 0.0),
            "agent_version": "1.0.0",
            "os_info": os_info,
            "code_version": code_version,  # Issue #741: Add code version
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
                        # Issue #741: Process heartbeat response
                        response_data = await response.json()
                        self._process_heartbeat_response(response_data)
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
                        # Safe: placeholders constructed from "?" chars
                        query = (
                            f"UPDATE event_buffer SET synced = 1 "  # nosec B608
                            f"WHERE id IN ({placeholders})"
                        )
                        conn.execute(query, ids)
                        conn.commit()
                        logger.info("Synced %d events", len(events))
        except aiohttp.ClientError as e:
            logger.warning("Failed to sync events: %s", e)
        finally:
            conn.close()

    async def run(
        self, enable_notify_server: bool = False, notify_port: int = DEFAULT_NOTIFY_PORT
    ):
        """Main agent loop."""
        self.running = True
        logger.info(
            "SLM Agent started (node_id=%s, admin=%s)", self.node_id, self.admin_url
        )

        # Notify systemd that we're ready
        sd_notify("READY=1")

        # Issue #741: Start notification server if enabled (code-source nodes)
        if enable_notify_server:
            await self.start_notify_server(notify_port)

        while self.running:
            # Send systemd watchdog notification (prevents timeout restart)
            sd_notify("WATCHDOG=1")

            # Send heartbeat
            success = await self.send_heartbeat()

            # If connected, try to sync buffered events
            if success:
                await self.sync_buffered_events()

            # Wait for next heartbeat
            await asyncio.sleep(self.heartbeat_interval)

        # Notify systemd we're stopping
        sd_notify("STOPPING=1")
        logger.info("SLM Agent stopped")

    def stop(self):
        """Stop the agent."""
        self.running = False

    @property
    def has_pending_update(self) -> bool:
        """
        Check if there's a pending update.

        Issue #741: Property to check update status.
        """
        return self._pending_update

    async def handle_code_change(self, request: web.Request) -> web.Response:
        """
        Handle code change notification from git hook (Issue #741).

        This endpoint receives notifications when code is committed
        on the code-source node and immediately reports the new
        version to the SLM server.
        """
        try:
            data = await request.json()
            commit = data.get("commit")
            branch = data.get("branch", "unknown")
            message = data.get("message", "")

            if not commit:
                return web.json_response({"error": "commit hash required"}, status=400)

            logger.info(
                "Code change notification: %s on %s",
                commit[:12],
                branch,
            )

            # Update local version info
            self.version_manager.save_version(
                commit=commit,
                extra_data={
                    "branch": branch,
                    "message": message[:200],
                    "source": "git-hook",
                },
            )
            self.version_manager.clear_cache()

            # Buffer the code change event
            self.buffer_event(
                "code_change",
                {
                    "commit": commit,
                    "branch": branch,
                    "message": message[:200],
                    "node_id": self.node_id,
                },
            )

            # Trigger immediate heartbeat to notify SLM server
            asyncio.create_task(self._notify_code_change(commit))

            return web.json_response(
                {
                    "status": "ok",
                    "commit": commit[:12],
                    "message": "Version updated, notifying SLM server",
                }
            )

        except json.JSONDecodeError:
            return web.json_response({"error": "invalid JSON"}, status=400)
        except Exception as e:
            logger.error("Error handling code change: %s", e)
            return web.json_response({"error": str(e)}, status=500)

    async def _notify_code_change(self, commit: str) -> None:
        """Send immediate notification to SLM server about code change."""
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.admin_url}/api/code-sync/notify"
                payload = {
                    "node_id": self.node_id,
                    "commit": commit,
                    "is_code_source": True,
                    "timestamp": datetime.utcnow().isoformat(),
                }
                async with session.post(
                    url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                    ssl=False,
                ) as response:
                    if response.status == 200:
                        logger.info(
                            "SLM server notified of new code version: %s",
                            commit[:12],
                        )
                    else:
                        logger.warning(
                            "Failed to notify SLM server: %s",
                            response.status,
                        )
        except Exception as e:
            logger.warning("Failed to notify SLM server: %s", e)
            # Event is already buffered, will sync on next heartbeat

    async def start_notify_server(self, port: int = DEFAULT_NOTIFY_PORT) -> None:
        """
        Start local HTTP server to receive notifications (Issue #741).

        This server listens for code change notifications from git hooks.
        """
        app = web.Application()
        app.router.add_post("/api/code-change", self.handle_code_change)
        app.router.add_get("/api/health", self._health_check)

        runner = web.AppRunner(app)
        await runner.setup()

        site = web.TCPSite(runner, "127.0.0.1", port)
        await site.start()
        logger.info("Notification server started on http://127.0.0.1:%d", port)

    async def _health_check(self, request: web.Request) -> web.Response:
        """Simple health check endpoint."""
        return web.json_response(
            {
                "status": "ok",
                "node_id": self.node_id,
                "version": self.version_manager.get_version(),
            }
        )


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
    parser.add_argument(
        "--code-source",
        action="store_true",
        default=os.environ.get("SLM_CODE_SOURCE", "").lower() == "true",
        help="Enable code-source mode (starts notify server for git hooks)",
    )
    parser.add_argument(
        "--notify-port",
        type=int,
        default=int(os.environ.get("SLM_NOTIFY_PORT", str(DEFAULT_NOTIFY_PORT))),
        help="Port for notification server (code-source mode)",
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

    # Issue #741: Pass code-source options
    asyncio.run(
        agent.run(
            enable_notify_server=args.code_source,
            notify_port=args.notify_port,
        )
    )


if __name__ == "__main__":
    main()
