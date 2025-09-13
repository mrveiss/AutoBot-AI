#!/usr/bin/env python3
"""
Simple Docker Log Forwarder to Seq
==================================

A reliable, synchronous log forwarder that streams Docker container logs to Seq.
Fixes the asyncio event loop issues by using synchronous HTTP requests.

Usage:
    python scripts/simple_docker_log_forwarder.py
"""

import json
import logging
import re
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue

import requests

import docker

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class SimpleDockerLogForwarder:
    """Simple, reliable Docker log forwarder for Seq."""

    def __init__(self, seq_url: str = "http://localhost:5341"):
        self.seq_url = seq_url.rstrip("/")
        self.docker_client = None
        self.running = False
        self.threads = []
        self.log_queue = Queue()
        self.batch_size = 10  # Send logs in batches to reduce HTTP requests
        self.batch_timeout = 5  # Send batch after 5 seconds even if not full

        # Initialize Docker client
        try:
            self.docker_client = docker.from_env()
            print("✅ Docker client initialized")
        except Exception as e:
            print(f"❌ Docker client failed to initialize: {e}")

        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

        # Start log sender thread
        self.start_log_sender()

    def send_to_seq(
        self,
        message: str,
        level: str = "Information",
        source: str = "AutoBot",
        properties: dict = None,
    ):
        """Send log entry to Seq synchronously."""

        if properties is None:
            properties = {}

        # Get hostname for consistent source attribution
        import socket

        hostname = socket.gethostname()

        log_entry = {
            "@t": datetime.utcnow().isoformat() + "Z",
            "@l": level,
            "@mt": message,
            "Source": source,
            "Host": hostname,
            "Application": "AutoBot",
            "Environment": "Development",
            "LogType": properties.get("LogType", "System"),
            **properties,
        }

        try:
            headers = {
                "Content-Type": "application/vnd.serilog.clef",
                "User-Agent": "AutoBot-SimpleLogForwarder/1.0",
            }

            response = requests.post(
                f"{self.seq_url}/api/events/raw",
                headers=headers,
                data=json.dumps(log_entry) + "\n",
                timeout=5,
            )

            if response.status_code not in [200, 201]:
                print(f"❌ Seq error {response.status_code}: {response.text}")
                return False
            return True

        except Exception as e:
            print(f"❌ Failed to send to Seq: {e}")
            return False

    def start_log_sender(self):
        """Start background thread to send logs to Seq."""

        def log_sender():
            while self.running or not self.log_queue.empty():
                try:
                    # Get log entry from queue with timeout (increased for batching)
                    log_entry = self.log_queue.get(timeout=2.0)

                    # Send to Seq
                    success = self.send_to_seq(**log_entry)

                    # Small delay to reduce request frequency
                    time.sleep(0.1)

                    if success:
                        self.log_queue.task_done()
                    else:
                        # Put back in queue for retry (but don't retry infinitely)
                        if log_entry.get("retry_count", 0) < 3:
                            log_entry["retry_count"] = (
                                log_entry.get("retry_count", 0) + 1
                            )
                            self.log_queue.put(log_entry)
                        self.log_queue.task_done()

                except Empty:
                    continue
                except Exception as e:
                    print(f"❌ Error in log sender: {e}")

        self.running = True
        sender_thread = threading.Thread(target=log_sender, daemon=True)
        sender_thread.start()
        self.threads.append(sender_thread)

    def queue_log(
        self,
        message: str,
        level: str = "Information",
        source: str = "AutoBot",
        properties: dict = None,
    ):
        """Queue a log entry for sending to Seq."""

        log_entry = {
            "message": message,
            "level": level,
            "source": source,
            "properties": properties or {},
        }

        try:
            self.log_queue.put(log_entry, timeout=1.0)
        except:
            # If queue is full, skip this log entry
            pass

    def get_docker_containers(self):
        """Get all AutoBot-related Docker containers."""
        containers = []

        if not self.docker_client:
            return containers

        try:
            # Get all running containers
            for container in self.docker_client.containers.list():
                container_name = container.name.lower()
                image_tags = (
                    str(container.image.tags).lower() if container.image.tags else ""
                )

                # Include containers that are clearly AutoBot-related
                is_autobot_container = (
                    # Direct AutoBot containers
                    container_name.startswith("autobot")
                    or
                    # Essential services for AutoBot
                    any(
                        keyword in container_name
                        for keyword in ["redis", "seq", "playwright"]
                    )
                    or
                    # NPU/AI containers for AutoBot
                    ("npu" in container_name and "worker" in container_name)
                    or "ai-stack" in container_name
                    or
                    # Image-based detection
                    "autobot" in image_tags
                )

                if is_autobot_container:
                    containers.append(container)
                    print(
                        f"📦 Will monitor: {container.name} (Image: {container.image.tags[0] if container.image.tags else 'unknown'})"
                    )

        except Exception as e:
            print(f"❌ Error getting containers: {e}")

        return containers

    def stream_container_logs(self, container):
        """Stream logs from a single Docker container."""

        def log_streamer():
            try:
                print(f"🔄 Starting log stream for: {container.name}")

                for log_line in container.logs(
                    stream=True, follow=True, timestamps=True
                ):
                    if not self.running:
                        break

                    try:
                        log_text = log_line.decode("utf-8", errors="ignore").strip()
                        if not log_text:
                            continue

                        # Parse timestamp if present
                        timestamp_match = re.match(
                            r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)\s+(.*)$",
                            log_text,
                        )
                        if timestamp_match:
                            timestamp, message = timestamp_match.groups()
                        else:
                            message = log_text

                        # Determine log level from message content
                        level = "Information"
                        message_lower = message.lower()
                        if any(
                            keyword in message_lower
                            for keyword in ["error", "exception", "failed", "fatal"]
                        ):
                            level = "Error"
                        elif any(
                            keyword in message_lower for keyword in ["warning", "warn"]
                        ):
                            level = "Warning"
                        elif any(keyword in message_lower for keyword in ["debug"]):
                            level = "Debug"

                        # Queue log for sending
                        self.queue_log(
                            message,
                            level=level,
                            source=f"Docker-{container.name}",
                            properties={
                                "ContainerID": container.id[:12],
                                "ContainerName": container.name,
                                "Image": container.image.tags[0]
                                if container.image.tags
                                else "unknown",
                                "LogType": "DockerContainer",
                                "ServiceType": "Container",
                            },
                        )

                    except Exception as e:
                        print(f"❌ Error processing log from {container.name}: {e}")

            except Exception as e:
                print(f"❌ Error streaming logs from {container.name}: {e}")

        # Start streaming in separate thread
        thread = threading.Thread(target=log_streamer, daemon=True)
        thread.start()
        self.threads.append(thread)

    def stream_backend_logs(self):
        """Stream logs from the main backend process."""

        def backend_monitor():
            try:
                print("🔄 Monitoring backend logs...")

                # Find the backend process
                result = subprocess.run(
                    ["pgrep", "-f", "uvicorn.*main:app"], capture_output=True, text=True
                )

                if result.returncode == 0:
                    pid = result.stdout.strip().split("\n")[
                        0
                    ]  # Get first PID if multiple
                    print(f"📍 Found backend process PID: {pid}")

                    # Use journalctl to follow logs
                    try:
                        proc = subprocess.Popen(
                            ["journalctl", "-f", "--no-pager", f"_PID={pid}"],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                        )

                        for line in iter(proc.stdout.readline, ""):
                            if not self.running:
                                proc.terminate()
                                break

                            if line.strip():
                                # Parse journalctl format and extract message
                                parts = line.strip().split(" ", 5)
                                if len(parts) >= 6:
                                    message = parts[5]
                                else:
                                    message = line.strip()

                                level = "Information"
                                if any(
                                    keyword in message.upper()
                                    for keyword in ["ERROR", "EXCEPTION", "FAILED"]
                                ):
                                    level = "Error"
                                elif any(
                                    keyword in message.upper()
                                    for keyword in ["WARNING", "WARN"]
                                ):
                                    level = "Warning"
                                elif any(
                                    keyword in message.upper() for keyword in ["DEBUG"]
                                ):
                                    level = "Debug"

                                self.queue_log(
                                    message,
                                    level=level,
                                    source="Backend-Main",
                                    properties={
                                        "ProcessID": pid,
                                        "LogType": "BackendProcess",
                                    },
                                )

                    except FileNotFoundError:
                        print("⚠️ journalctl not available")
                else:
                    print("⚠️ Backend process not found")

            except Exception as e:
                print(f"❌ Error monitoring backend: {e}")

        thread = threading.Thread(target=backend_monitor, daemon=True)
        thread.start()
        self.threads.append(thread)

    def send_startup_event(self):
        """Send startup event to Seq."""

        success = self.send_to_seq(
            "🚀 Simple Docker Log Forwarder Started",
            level="Information",
            source="LogForwarder",
            properties={
                "StartupTime": datetime.utcnow().isoformat(),
                "LogType": "System",
                "Event": "Startup",
            },
        )

        if success:
            print("✅ Startup event sent to Seq")
        else:
            print("❌ Failed to send startup event to Seq")

    def start_monitoring(self):
        """Start monitoring all log sources."""

        print("🚀 Starting simple Docker log monitoring...")

        # Send startup event
        self.send_startup_event()

        # Get and monitor Docker containers
        containers = self.get_docker_containers()
        for container in containers:
            self.stream_container_logs(container)

        # Monitor backend logs
        self.stream_backend_logs()

        print(f"📊 Started monitoring {len(containers)} containers + backend")
        print("🔍 Log forwarding active... Press Ctrl+C to stop")

        try:
            # Keep main thread alive
            while self.running:
                time.sleep(1)

        except KeyboardInterrupt:
            print("\n🛑 Stopping log forwarder...")
            self.stop()

    def stop(self):
        """Stop the log forwarder."""

        self.running = False

        # Wait for queue to empty
        try:
            self.log_queue.join()
        except:
            pass

        print("✅ Log forwarder stopped")


def main():
    """Main entry point."""

    forwarder = SimpleDockerLogForwarder()

    # Setup signal handlers
    def signal_handler(signum, frame):
        print(f"\n📡 Received signal {signum}")
        forwarder.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start monitoring
    forwarder.start_monitoring()


if __name__ == "__main__":
    main()
