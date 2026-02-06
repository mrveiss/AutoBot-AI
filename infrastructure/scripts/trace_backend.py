#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Function Call Tracer for Backend
Traces every function call with timing information
"""

import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FunctionTracer:
    def __init__(self, output_file=None):
        """Initialize tracer with output file path and call tracking state."""
        # Use proper output directory
        if output_file is None:
            project_root = Path(__file__).parent.parent
            logs_dir = project_root / "logs" / "performance"
            logs_dir.mkdir(parents=True, exist_ok=True)
            self.output_file = logs_dir / "backend_trace.log"
        else:
            self.output_file = output_file

        self.call_stack = []
        self.start_times = {}
        self.call_count = 0

        # Clear the log file
        with open(self.output_file, "w") as f:
            f.write("BACKEND FUNCTION CALL TRACE\n")
            f.write("=" * 50 + "\n\n")

    def trace_calls(self, frame, event, arg):
        """Trace function for sys.settrace()"""
        if event == "call":
            self.call_count += 1
            func_name = frame.f_code.co_name
            filename = frame.f_code.co_filename
            lineno = frame.f_lineno

            # Only trace our project files
            if any(path in filename for path in ["/AutoBot/", "backend/", "src/"]):
                indent = "  " * len(self.call_stack)
                timestamp = time.time()

                call_info = {
                    "name": func_name,
                    "file": Path(filename).name,
                    "line": lineno,
                    "start_time": timestamp,
                    "full_path": filename,
                }

                self.call_stack.append(call_info)
                self.start_times[id(frame)] = timestamp

                # Log the call
                with open(self.output_file, "a") as f:
                    f.write(
                        f"{indent}→ {func_name}() [{Path(filename).name}:{lineno}] @{timestamp:.6f}\n"
                    )

                # Print to console for real-time monitoring
                if len(self.call_stack) <= 5:  # Only show top-level calls
                    print(f"{indent}→ {func_name}() [{Path(filename).name}:{lineno}]")

        elif event == "return":
            if self.call_stack and id(frame) in self.start_times:
                call_info = self.call_stack.pop()
                start_time = self.start_times.pop(id(frame))
                duration = time.time() - start_time

                indent = "  " * len(self.call_stack)

                # Log the return with duration
                with open(self.output_file, "a") as f:
                    f.write(f"{indent}← {call_info['name']}() DONE ({duration:.6f}s)\n")

                # Highlight slow functions (> 0.1s)
                if duration > 0.1:
                    print(f"{indent}← {call_info['name']}() SLOW: {duration:.3f}s ⚠️")
                    with open(self.output_file, "a") as f:
                        f.write(f"{indent}*** SLOW FUNCTION: {duration:.6f}s ***\n")

        return self.trace_calls


def trace_backend_startup():
    """Trace backend startup with detailed function calls"""
    tracer = FunctionTracer()

    print("🕵️ Starting function call tracing...")
    print(f"📝 Trace log: {tracer.output_file}")

    # Set up tracing
    sys.settrace(tracer.trace_calls)

    try:
        print("📊 Tracing app creation...")
        from backend.app_factory import create_app

        create_app()
        print("✅ App creation traced successfully")

    except Exception as e:
        print(f"❌ Error during tracing: {e}")
        import traceback

        traceback.print_exc()
    finally:
        # Stop tracing
        sys.settrace(None)

        print(f"\n📊 Traced {tracer.call_count} function calls")
        print(f"📄 Full trace saved to: {tracer.output_file}")


if __name__ == "__main__":
    trace_backend_startup()
