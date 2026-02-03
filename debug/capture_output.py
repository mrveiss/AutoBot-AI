#!/usr/bin/env python3
"""
Terminal Output Capture Utility for AutoBot
Captures and logs all output from AutoBot processes
"""

import subprocess
import sys
import os
from datetime import datetime
import threading
import queue

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.utils.terminal_input_handler import safe_input
from src.constants.network_constants import NetworkConstants

# Build URLs from centralized configuration
BASE_URL = f"http://{NetworkConstants.MAIN_MACHINE_IP}:{NetworkConstants.BACKEND_PORT}"


class OutputCapture:
    """Capture terminal output from subprocess with real-time display."""

    def __init__(self, log_file=None):
        if log_file is None:
            # Use proper logs directory
            from pathlib import Path
            logs_dir = Path(__file__).parent.parent / "logs" / "debug"
            logs_dir.mkdir(parents=True, exist_ok=True)
            self.log_file = str(logs_dir / f"autobot_output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        else:
            self.log_file = log_file
        self.output_queue = queue.Queue()

    def capture_line(self, pipe, prefix=""):
        """Capture output line by line."""
        for line in iter(pipe.readline, b""):
            if line:
                decoded_line = line.decode("utf-8", errors="replace")
                timestamped_line = (
                    f"[{datetime.now().strftime('%H:%M:%S')}] {prefix}{decoded_line}"
                )

                # Print to terminal
                sys.stdout.write(timestamped_line)
                sys.stdout.flush()

                # Add to queue for logging
                self.output_queue.put(timestamped_line)

    def log_output(self):
        """Write queued output to log file."""
        with open(self.log_file, "a") as f:
            while True:
                try:
                    line = self.output_queue.get(timeout=0.1)
                    f.write(line)
                    f.flush()
                except queue.Empty:
                    continue
                except Exception as e:
                    print(f"Logging error: {e}")

    def run_command(self, command, shell=True):
        """Run command and capture output."""
        print(f"🚀 Starting command: {command}")
        print(f"📝 Logging to: {self.log_file}")
        print("=" * 60)

        # Start logging thread
        log_thread = threading.Thread(target=self.log_output, daemon=True)
        log_thread.start()

        # Run the command
        process = subprocess.Popen(
            command,
            shell=shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,
        )

        # Create threads to capture stdout and stderr
        stdout_thread = threading.Thread(
            target=self.capture_line, args=(process.stdout, "[STDOUT] "), daemon=True
        )
        stderr_thread = threading.Thread(
            target=self.capture_line, args=(process.stderr, "[STDERR] "), daemon=True
        )

        stdout_thread.start()
        stderr_thread.start()

        # Wait for process to complete
        return_code = process.wait()

        # Wait for threads to finish
        stdout_thread.join()
        stderr_thread.join()

        print("=" * 60)
        print(f"✅ Command completed with return code: {return_code}")
        print(f"📄 Output saved to: {self.log_file}")

        return return_code


def capture_autobot_output():
    """Capture AutoBot startup and runtime output."""
    capture = OutputCapture("autobot_full_output.log")

    # Example: Capture AutoBot startup
    print("🤖 AutoBot Output Capture Utility")
    print("This will capture all terminal output from AutoBot")
    print()

    commands = {
        "1": ("Run AutoBot", "./run_agent.sh"),
        "2": ("Run AutoBot in test mode", "./run_agent.sh --test-mode"),
        "3": (
            "Check system health",
            f'curl -s "{BASE_URL}/api/system/health" | python3 -m json.tool',
        ),
        "4": ("Run workflow test", "python3 test_workflow_api.py"),
        "5": ("Custom command", None),
    }

    print("Select what to capture:")
    for key, (desc, _) in commands.items():
        print(f"  {key}. {desc}")

    choice = safe_input("\nEnter your choice (1-5): ", default="1").strip()

    if choice in commands:
        desc, command = commands[choice]

        if command is None:
            command = safe_input("Enter custom command: ", default="./run_agent.sh").strip()

        if command:
            capture.run_command(command)
    else:
        print("Invalid choice")


def capture_specific_test():
    """Capture output from a specific test or command."""
    import argparse

    parser = argparse.ArgumentParser(description="Capture terminal output")
    parser.add_argument("command", nargs="?", help="Command to run")
    parser.add_argument("-o", "--output", help="Output log file")
    parser.add_argument(
        "-t", "--tail", action="store_true", help="Tail the log file after"
    )

    args = parser.parse_args()

    if not args.command:
        capture_autobot_output()
    else:
        capture = OutputCapture(args.output)
        capture.run_command(args.command)

        if args.tail and os.path.exists(capture.log_file):
            print(f"\n📜 Tailing log file: {capture.log_file}")
            print("Press Ctrl+C to stop")
            try:
                subprocess.run(["tail", "-f", capture.log_file])
            except KeyboardInterrupt:
                print("\n✋ Stopped tailing")


if __name__ == "__main__":
    capture_specific_test()
