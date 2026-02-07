#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Comprehensive Log Aggregator for AutoBot
=========================================

Captures and forwards logs from ALL sources to Seq:
1. Main Python backend logs
2. All Docker container logs
3. Frontend application logs
4. System events and errors
5. Real-time log streaming

Usage:
    python scripts/comprehensive_log_aggregator.py --start-all
"""

import asyncio
import json
import logging
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import List

import aiohttp
import docker

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.constants.threshold_constants import TimingConstants

# Issue #315 - extracted helper functions to reduce deep nesting


def _parse_log_timestamp(log_text: str) -> tuple:
    """Parse timestamp from log text if present (Issue #315 - extracted)."""
    timestamp_match = re.match(
        r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)\s+(.*)$",
        log_text,
    )
    if timestamp_match:
        return timestamp_match.groups()
    return None, log_text


def _determine_log_level(message: str) -> str:
    """Determine log level from message content (Issue #315 - extracted)."""
    message_lower = message.lower()

    if any(keyword in message_lower for keyword in ["error", "exception", "failed"]):
        return "Error"
    elif any(keyword in message_lower for keyword in ["warning", "warn"]):
        return "Warning"
    elif "debug" in message_lower:
        return "Debug"

    return "Information"


def _process_docker_log_line(
    log_line: bytes, container, send_callback, running_flag
) -> None:
    """Process single Docker log line (Issue #315 - extracted)."""
    if not running_flag():
        return

    try:
        log_text = log_line.decode("utf-8").strip()
        if not log_text:
            return

        # Parse timestamp if present
        timestamp, message = _parse_log_timestamp(log_text)

        # Determine log level from message content
        level = _determine_log_level(message)

        # Send to Seq asynchronously
        send_callback(
            message,
            level=level,
            source=f"Docker-{container.name}",
            properties={
                "ContainerID": container.id[:12],
                "ContainerName": container.name,
                "Image": container.image.tags[0] if container.image.tags else "unknown",
                "LogType": "DockerContainer",
            },
        )
    except Exception as e:
        print(f"❌ Error processing log line from {container.name}: {e}")


def _process_journalctl_line(line: str, pid: str, send_callback, running_flag) -> bool:
    """Process journalctl line and return True to continue (Issue #315 - extracted)."""
    if not running_flag():
        return False

    if not line.strip():
        return True

    # Parse journalctl format
    level = _determine_log_level(line)

    send_callback(
        line.strip(),
        level=level,
        source="Backend-Main",
        properties={
            "ProcessID": pid,
            "LogType": "BackendProcess",
        },
    )
    return True


def _monitor_log_files(log_aggregator, running_flag) -> None:
    """Monitor log files as alternative to journalctl (Issue #315 - extracted)."""
    log_files = [
        Path(__file__).parent.parent / "logs" / "autobot.log",
        Path("/var/log/autobot.log"),
        Path("./autobot.log"),
    ]

    for log_file in log_files:
        if log_file.exists():
            print(f"📄 Monitoring log file: {log_file}")
            log_aggregator.tail_log_file(str(log_file), "Backend-File")
            return

    print("⚠️ No backend log files found")


def _process_tail_log_line(
    line: str, source_name: str, file_path: str, send_callback, running_flag
) -> bool:
    """Process tail log line and return True to continue (Issue #315 - extracted)."""
    if not running_flag():
        return False

    if not line.strip():
        return True

    level = _determine_log_level(line)

    send_callback(
        line.strip(),
        level=level,
        source=source_name,
        properties={"FilePath": file_path, "LogType": "FileSystem"},
    )
    return True


class ComprehensiveLogAggregator:
    """Comprehensive log aggregation system for AutoBot."""

    def __init__(self, seq_url: str = "http://localhost:5341"):
        """Initialize log aggregator with Seq URL and Docker client."""
        self.seq_url = seq_url.rstrip("/")
        self.docker_client = None
        self.log_processes = {}
        self.running = False
        self.executor = ThreadPoolExecutor(max_workers=10)

        # Initialize Docker client
        try:
            self.docker_client = docker.from_env()
            print("✅ Docker client initialized")
        except Exception as e:
            print(f"⚠️ Docker client failed to initialize: {e}")

        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    async def send_to_seq(
        self,
        message: str,
        level: str = "Information",
        source: str = "AutoBot",
        properties: dict = None,
    ):
        """Send log entry to Seq with error handling."""

        if properties is None:
            properties = {}

        log_entry = {
            "@t": datetime.utcnow().isoformat() + "Z",
            "@l": level,
            "@mt": message,
            "Source": source,
            "Environment": "Development",
            "Application": "AutoBot",
            **properties,
        }

        try:
            headers = {
                "Content-Type": "application/vnd.serilog.clef",
                "User-Agent": "AutoBot-LogAggregator/1.0",
            }

            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5)
            ) as session:
                async with session.post(
                    f"{self.seq_url}/api/events/raw",
                    headers=headers,
                    data=json.dumps(log_entry) + "\n",
                ) as response:
                    if response.status not in [200, 201]:
                        print(f"❌ Seq error {response.status}: {await response.text()}")

        except Exception as e:
            print(f"❌ Failed to send to Seq: {e}")

    async def get_docker_containers(self) -> List[dict]:
        """Get all AutoBot-related Docker containers."""
        containers = []

        if not self.docker_client:
            return containers

        try:
            # Get all running containers
            for container in self.docker_client.containers.list():
                container_info = {
                    "id": container.id[:12],
                    "name": container.name,
                    "image": container.image.tags[0]
                    if container.image.tags
                    else "unknown",
                    "status": container.status,
                    "labels": container.labels,
                }

                # Include AutoBot-related containers
                if any(
                    keyword in container.name.lower()
                    for keyword in ["autobot", "redis", "seq", "npu", "worker"]
                ) or any(
                    keyword in str(container.image.tags).lower()
                    for keyword in ["autobot", "redis", "seq", "python", "node"]
                ):
                    containers.append(container_info)
                    print(
                        f"📦 Found container: {container.name} ({container_info['image']})"
                    )

        except Exception as e:
            print(f"❌ Error getting containers: {e}")

        return containers

    async def stream_docker_logs(self, container_name: str):
        """Stream logs from a Docker container to Seq (Issue #315 - refactored)."""
        if not self.docker_client:
            return

        try:
            container = self.docker_client.containers.get(container_name)
            print(f"🔄 Starting log stream for container: {container.name}")

            # Stream logs in a separate thread to avoid blocking
            def stream_logs():
                try:
                    for log_line in container.logs(
                        stream=True, follow=True, timestamps=True
                    ):
                        # Use extracted helper function to process log line
                        def send_callback(*args, **kwargs):
                            """Forward log arguments to Seq sender in event loop."""
                            asyncio.run_coroutine_threadsafe(
                                self.send_to_seq(*args, **kwargs),
                                asyncio.get_event_loop(),
                            )

                        _process_docker_log_line(
                            log_line,
                            container,
                            send_callback,
                            lambda: self.running,
                        )

                except Exception as e:
                    print(f"❌ Error streaming logs from {container.name}: {e}")

            # Start streaming in executor
            self.executor.submit(stream_logs)

        except Exception as e:
            print(f"❌ Error setting up log stream for {container_name}: {e}")

    async def stream_backend_logs(self):
        """Stream logs from the main Python backend (Issue #315 - refactored)."""
        print("🔄 Starting backend log monitoring...")

        # Monitor backend process logs
        def monitor_backend():
            """Monitor backend process logs via journalctl or log files."""
            try:
                # Find the backend process
                result = subprocess.run(
                    ["pgrep", "-", "python.*main.py"], capture_output=True, text=True
                )

                if result.returncode != 0:
                    print("⚠️ Backend process not found")
                    return

                pid = result.stdout.strip()
                print(f"📍 Found backend process PID: {pid}")

                # Use journalctl to follow logs if available
                try:
                    self._monitor_journalctl(pid)
                except FileNotFoundError:
                    print("⚠️ journalctl not available, using alternative method")
                    _monitor_log_files(self, lambda: self.running)

            except Exception as e:
                print(f"❌ Error monitoring backend logs: {e}")

        self.executor.submit(monitor_backend)

    def _monitor_journalctl(self, pid: str):
        """Monitor journalctl for backend process (Issue #315 - extracted)."""
        proc = subprocess.Popen(
            ["journalctl", "-", "--no-pager", f"_PID={pid}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        def send_callback(*args, **kwargs):
            """Send log message to Seq asynchronously via event loop."""
            asyncio.run_coroutine_threadsafe(
                self.send_to_seq(*args, **kwargs),
                asyncio.get_event_loop(),
            )

        for line in iter(proc.stdout.readline, ""):
            if not _process_journalctl_line(
                line, pid, send_callback, lambda: self.running
            ):
                proc.terminate()
                break

    def tail_log_file(self, file_path: str, source_name: str):
        """Tail a log file and send to Seq (Issue #315 - refactored)."""
        try:
            proc = subprocess.Popen(
                ["tail", "-f", file_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            def send_callback(*args, **kwargs):
                """Send log message to Seq asynchronously via event loop."""
                asyncio.run_coroutine_threadsafe(
                    self.send_to_seq(*args, **kwargs),
                    asyncio.get_event_loop(),
                )

            for line in iter(proc.stdout.readline, ""):
                if not _process_tail_log_line(
                    line, source_name, file_path, send_callback, lambda: self.running
                ):
                    proc.terminate()
                    break

        except Exception as e:
            print(f"❌ Error tailing file {file_path}: {e}")

    async def stream_system_logs(self):
        """Stream system-wide logs relevant to AutoBot."""

        print("🔄 Starting system log monitoring...")

        def monitor_system():
            """Monitor system journal logs for AutoBot-related entries."""
            try:
                # Monitor system logs for AutoBot-related entries
                proc = subprocess.Popen(
                    [
                        "journalctl",
                        "-f",
                        "--no-pager",
                        "--grep=autobot|AutoBot|python|docker",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

                for line in iter(proc.stdout.readline, ""):
                    if not self.running:
                        proc.terminate()
                        break

                    if line.strip() and (
                        "autobot" in line.lower() or "python" in line.lower()
                    ):
                        asyncio.run_coroutine_threadsafe(
                            self.send_to_seq(
                                line.strip(),
                                level="Information",
                                source="System-Journal",
                                properties={"LogType": "SystemLog"},
                            ),
                            asyncio.get_event_loop(),
                        )

            except Exception as e:
                print(f"❌ Error monitoring system logs: {e}")

        self.executor.submit(monitor_system)

    async def send_startup_event(self):
        """Send startup event to Seq."""

        await self.send_to_seq(
            "🚀 AutoBot Comprehensive Log Aggregator Started",
            level="Information",
            source="LogAggregator",
            properties={
                "StartupTime": datetime.utcnow().isoformat(),
                "LogType": "System",
                "Event": "Startup",
            },
        )

    async def send_test_logs(self):
        """Send test logs to verify Seq connectivity."""

        test_logs = [
            ("🧪 Test log - Information level", "Information"),
            ("⚠️ Test log - Warning level", "Warning"),
            ("❌ Test log - Error level", "Error"),
            ("🔍 Test log - Debug level", "Debug"),
        ]

        for message, level in test_logs:
            await self.send_to_seq(
                message,
                level=level,
                source="LogAggregator-Test",
                properties={
                    "TestRun": datetime.utcnow().isoformat(),
                    "LogType": "Test",
                },
            )

        print("✅ Test logs sent to Seq")

    async def start_all_monitoring(self):
        """Start monitoring all log sources."""

        self.running = True
        print("🚀 Starting comprehensive log aggregation...")

        # Send startup event
        await self.send_startup_event()

        # Start all monitoring tasks concurrently
        tasks = []

        # Get and monitor Docker containers
        containers = await self.get_docker_containers()
        for container in containers:
            task = asyncio.create_task(self.stream_docker_logs(container["name"]))
            tasks.append(task)

        # Start backend monitoring
        tasks.append(asyncio.create_task(self.stream_backend_logs()))

        # Start system monitoring
        tasks.append(asyncio.create_task(self.stream_system_logs()))

        print(f"📊 Started {len(tasks)} monitoring tasks")
        print("🔍 Log aggregation running... Press Ctrl+C to stop")

        try:
            # Keep running until interrupted
            while self.running:
                await asyncio.sleep(TimingConstants.STANDARD_DELAY)

        except KeyboardInterrupt:
            print("\n🛑 Stopping log aggregation...")
            self.running = False

            # Cancel all tasks
            for task in tasks:
                task.cancel()

            # Wait for tasks to complete
            await asyncio.gather(*tasks, return_exceptions=True)

        finally:
            self.executor.shutdown(wait=True)
            print("✅ Log aggregation stopped")


async def main():
    """Main entry point."""

    import argparse

    parser = argparse.ArgumentParser(description="AutoBot Comprehensive Log Aggregator")
    parser.add_argument(
        "--seq-url", default="http://localhost:5341", help="Seq server URL"
    )
    parser.add_argument(
        "--start-all", action="store_true", help="Start monitoring all log sources"
    )
    parser.add_argument(
        "--test-logs", action="store_true", help="Send test logs to Seq"
    )
    parser.add_argument(
        "--list-containers", action="store_true", help="List Docker containers"
    )

    args = parser.parse_args()

    aggregator = ComprehensiveLogAggregator(seq_url=args.seq_url)

    if args.test_logs:
        await aggregator.send_test_logs()
        return

    if args.list_containers:
        containers = await aggregator.get_docker_containers()
        print("\n📦 AutoBot Docker Containers:")
        for container in containers:
            print(
                f"  • {container['name']} ({container['image']}) - {container['status']}"
            )
        return

    if args.start_all:
        await aggregator.start_all_monitoring()
    else:
        print("Use --start-all to begin monitoring or --test-logs to test connectivity")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
