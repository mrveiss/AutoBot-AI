#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Startup Performance Profiler
Profiles AutoBot backend startup to identify bottlenecks
"""
import cProfile
import os
import pstats
import sys
import time


def profile_startup():
    """Profile the startup sequence"""
    print("🔍 Starting backend startup profiling...")

    # Add the project root to Python path
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    profiler = cProfile.Profile()
    profiler.enable()

    start_time = time.time()

    try:
        # Import main components
        print("Importing main modules...")
        from backend import app_factory

        print("Creating FastAPI app...")
        app_factory.create_app()

        end_time = time.time()

    except Exception as e:
        print(f"Error during profiling: {e}")
        return
    finally:
        profiler.disable()

    print(f"Startup completed in {end_time - start_time:.3f} seconds")

    # Save and display results
    stats = pstats.Stats(profiler)
    stats.sort_stats("cumulative")

    print("\n🔝 Top 10 slowest functions:")
    stats.print_stats(10)

    # Save detailed report to proper directory
    from pathlib import Path

    reports_dir = Path(__file__).parent.parent / "reports" / "performance"
    reports_dir.mkdir(parents=True, exist_ok=True)

    profile_file = reports_dir / "startup_profile.txt"
    with open(profile_file, "w") as f:
        stats.print_stats(file=f)

    print(f"\nDetailed profile saved to {profile_file}")


if __name__ == "__main__":
    profile_startup()
