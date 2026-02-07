#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Seq Log Forwarder
========================

Forwards logs from AutoBot services directly to Seq for centralized viewing.

Usage:
    python scripts/seq_log_forwarder.py --tail-and-forward
    python scripts/seq_log_forwarder.py --send-test-logs
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import aiohttp

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.constants.threshold_constants import TimingConstants


class SeqLogForwarder:
    """Forwards logs to Seq centralized logging system."""

    def __init__(self, seq_url: str = "http://localhost:5341", api_key: str = None):
        """Initialize log forwarder with Seq server URL and optional API key."""
        self.seq_url = seq_url.rstrip("/")
        self.api_key = api_key
        self.logs_dir = Path(__file__).parent.parent / "logs"

    async def send_log_to_seq(
        self,
        message: str,
        level: str = "Information",
        source: str = "AutoBot",
        properties: dict = None,
    ):
        """Send a single log entry to Seq."""

        if properties is None:
            properties = {}

        # Seq log format
        log_entry = {
            "@t": datetime.utcnow().isoformat() + "Z",
            "@l": level,
            "@mt": message,
            "Source": source,
            **properties,
        }

        headers = {"Content-Type": "application/vnd.serilog.clef"}
        if self.api_key:
            headers["X-Seq-ApiKey"] = self.api_key

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.seq_url}/api/events/raw",
                    data=json.dumps(log_entry) + "\n",
                    headers=headers,
                ) as response:
                    if response.status == 201:
                        return True
                    else:
                        print(f"Failed to send log to Seq: {response.status}")
                        return False
        except Exception as e:
            print(f"Error sending log to Seq: {e}")
            return False

    async def send_test_logs(self):
        """Send test logs to verify Seq connection."""
        print("🧪 Sending test logs to Seq...")

        test_logs = [
            {
                "message": "AutoBot system started",
                "level": "Information",
                "source": "System",
            },
            {
                "message": "Backend service initialized",
                "level": "Information",
                "source": "Backend",
            },
            {
                "message": "Frontend service ready",
                "level": "Information",
                "source": "Frontend",
            },
            {
                "message": "Redis connection established",
                "level": "Information",
                "source": "Redis",
            },
            {"message": "Test warning message", "level": "Warning", "source": "Test"},
            {
                "message": "Test error message for demonstration",
                "level": "Error",
                "source": "Test",
            },
        ]

        for log in test_logs:
            success = await self.send_log_to_seq(
                log["message"],
                log["level"],
                log["source"],
                {"TestRun": True, "Timestamp": datetime.now().isoformat()},
            )
            if success:
                print(f"✅ Sent: {log['message']}")
            else:
                print(f"❌ Failed: {log['message']}")

            await asyncio.sleep(TimingConstants.SHORT_DELAY)

    async def _process_log_file(
        self, filepath: Path, source: str, file_positions: dict
    ) -> None:
        """Process a single log file for new content (Issue #315: extracted helper)."""
        filename = filepath.name
        if not filepath.exists():
            filepath.touch()
            file_positions[filename] = 0
            return

        current_size = filepath.stat().st_size
        last_position = file_positions.get(filename, 0)

        if current_size <= last_position:
            return

        with open(filepath, "r") as f:
            f.seek(last_position)
            new_content = f.read()

        for line in new_content.strip().split("\n"):
            if line.strip():
                await self.parse_and_send_log_line(line, source)

        file_positions[filename] = current_size

    async def tail_and_forward_logs(self):
        """Tail log files and forward to Seq (Issue #315: refactored)."""
        print("📡 Starting log forwarding to Seq...")
        print(f"   Seq URL: {self.seq_url}")
        print(f"   Logs Directory: {self.logs_dir}")

        # Check if logs directory exists
        if not self.logs_dir.exists():
            print("⚠️  Logs directory doesn't exist. Creating test logs...")
            self.logs_dir.mkdir(exist_ok=True)
            await self.create_sample_logs()

        # Log files to monitor
        log_files = {
            "backend.log": "Backend",
            "frontend.log": "Frontend",
            "system.log": "System",
        }

        file_positions = {}

        while True:
            try:
                for filename, source in log_files.items():
                    filepath = self.logs_dir / filename
                    await self._process_log_file(filepath, source, file_positions)

                # Check for new log entries periodically
                await asyncio.sleep(TimingConstants.STANDARD_DELAY)

            except KeyboardInterrupt:
                print("\n👋 Stopping log forwarder...")
                break
            except Exception as e:
                print(f"❌ Error in log forwarding: {e}")
                # Error recovery delay before retry
                await asyncio.sleep(TimingConstants.ERROR_RECOVERY_DELAY)

    async def parse_and_send_log_line(self, line: str, source: str):
        """Parse log line and send to Seq."""
        try:
            # Try to parse as JSON first
            if line.startswith("{"):
                log_data = json.loads(line)
                message = log_data.get("message", line)
                level = log_data.get("level", "Information")
                properties = {
                    k: v for k, v in log_data.items() if k not in ["message", "level"]
                }
            else:
                # Parse as text log
                message = line
                level = "Information"

                # Detect log level from message
                if any(word in line.upper() for word in ["ERROR", "FAIL"]):
                    level = "Error"
                elif any(word in line.upper() for word in ["WARN", "WARNING"]):
                    level = "Warning"
                elif any(word in line.upper() for word in ["DEBUG"]):
                    level = "Debug"

                properties = {"RawLine": line}

            await self.send_log_to_seq(message, level, source, properties)

        except json.JSONDecodeError:
            # Send as plain text if JSON parsing fails
            await self.send_log_to_seq(
                line, "Information", source, {"ParseError": True}
            )
        except Exception as e:
            print(f"Error parsing log line: {e}")

    async def create_sample_logs(self):
        """Create sample log files for demonstration."""
        print("📝 Creating sample logs...")

        # Backend logs
        backend_log = self.logs_dir / "backend.log"
        with open(backend_log, "w") as f:
            f.write(
                f'{{"timestamp": "{datetime.now().isoformat()}", "level": "INFO", "message": "Backend service started", "module": "main"}}\n'
            )
            f.write(
                f'{{"timestamp": "{datetime.now().isoformat()}", "level": "INFO", "message": "Database connection established", "module": "database"}}\n'
            )
            f.write(
                f'{{"timestamp": "{datetime.now().isoformat()}", "level": "WARNING", "message": "High memory usage detected", "module": "monitoring"}}\n'
            )

        # Frontend logs
        frontend_log = self.logs_dir / "frontend.log"
        with open(frontend_log, "w") as f:
            f.write(
                f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} [Frontend] INFO: Vite development server started\n'
            )
            f.write(
                f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} [Frontend] INFO: Hot module replacement enabled\n'
            )
            f.write(
                f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")} [Frontend] WARNING: Build took longer than expected\n'
            )

        # System logs
        system_log = self.logs_dir / "system.log"
        with open(system_log, "w") as f:
            f.write(
                f'{{"timestamp": "{datetime.now().isoformat()}", "level": "INFO", "service": "system", "message": "AutoBot system initialized"}}\n'
            )
            f.write(
                f'{{"timestamp": "{datetime.now().isoformat()}", "level": "INFO", "service": "docker", "message": "All containers are running"}}\n'
            )

        print("✅ Sample logs created")

    async def check_seq_connection(self):
        """Check if Seq is accessible."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.seq_url}/api") as response:
                    if response.status == 200:
                        print("✅ Seq is accessible")
                        return True
                    else:
                        print(f"⚠️  Seq returned status: {response.status}")
                        return False
        except Exception as e:
            print(f"❌ Cannot connect to Seq: {e}")
            print(f"   Make sure Seq is running at {self.seq_url}")
            return False


async def main() -> int:
    """Main entry point for CLI Seq log forwarder operations."""
    parser = argparse.ArgumentParser(description="AutoBot Seq Log Forwarder")

    parser.add_argument(
        "--tail-and-forward",
        action="store_true",
        help="Tail log files and forward to Seq",
    )
    parser.add_argument(
        "--send-test-logs", action="store_true", help="Send test logs to Seq"
    )
    parser.add_argument(
        "--check-connection", action="store_true", help="Check Seq connection"
    )
    parser.add_argument(
        "--seq-url", default="http://localhost:5341", help="Seq server URL"
    )
    parser.add_argument("--api-key", help="Seq API key")

    args = parser.parse_args()

    if not any([args.tail_and_forward, args.send_test_logs, args.check_connection]):
        parser.print_help()
        return 1

    forwarder = SeqLogForwarder(args.seq_url, args.api_key)

    try:
        if args.check_connection:
            await forwarder.check_seq_connection()

        if args.send_test_logs:
            connection_ok = await forwarder.check_seq_connection()
            if connection_ok:
                await forwarder.send_test_logs()
                print(f"\n🌐 Check Seq at: {args.seq_url}")
                print("   Username: admin")
                print("   Password: autobot123")

        if args.tail_and_forward:
            connection_ok = await forwarder.check_seq_connection()
            if connection_ok:
                await forwarder.tail_and_forward_logs()
            else:
                print("Cannot start log forwarding without Seq connection")
                return 1

    except KeyboardInterrupt:
        print("\n👋 Stopped")
        return 0
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
