#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Detailed startup timing analysis to identify bottlenecks
"""
import time
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def time_import(module_name):
    """Time a single module import"""
    start = time.time()
    try:
        exec(f"import {module_name}")
        duration = time.time() - start
        print(f"✅ {module_name:<30} : {duration:6.3f}s")
        return duration
    except Exception as e:
        duration = time.time() - start
        print(f"❌ {module_name:<30} : {duration:6.3f}s (ERROR: {str(e)[:50]})")
        return duration


def main():
    """Entry point for backend startup timing analysis."""
    print("🔍 Backend Startup Timing Analysis")
    print("=" * 50)

    total_start = time.time()

    # Test individual imports
    imports_to_test = [
        "fastapi",
        "uvicorn",
        "pydantic",
        "asyncio",
        "logging",
        "numpy",
        "redis",
        "llama_index",
        "sentence_transformers",  # This should now be fast
        "chromadb",
        "pandas",
        "sklearn",
        "torch",
        "transformers"
    ]

    print("\n📦 Basic Library Imports:")
    basic_total = 0
    for module in imports_to_test:
        duration = time_import(module)
        basic_total += duration

    print(f"\nTotal basic imports: {basic_total:.3f}s")

    # Test AutoBot specific modules
    print("\n🤖 AutoBot Module Imports:")
    autobot_modules = [
        "src.config",
        "src.utils.config_manager",
        "src.utils.redis_client",
        "src.utils.logging_manager",
        "src.knowledge_base",
        "src.utils.semantic_chunker",
        "src.utils.entity_resolver"
    ]

    autobot_total = 0
    for module in autobot_modules:
        duration = time_import(module)
        autobot_total += duration

    print(f"\nTotal AutoBot imports: {autobot_total:.3f}s")

    # Test backend imports
    print("\n🏭 Backend Module Imports:")
    backend_modules = [
        "backend.main",
        "backend.app_factory"
    ]

    backend_total = 0
    for module in backend_modules:
        duration = time_import(module)
        backend_total += duration

    print(f"\nTotal backend imports: {backend_total:.3f}s")

    # Test app creation
    print("\n🚀 FastAPI App Creation:")
    app_start = time.time()
    try:
        from backend.app_factory import create_app
        app = create_app()
        app_duration = time.time() - app_start
        print(f"✅ create_app()                : {app_duration:6.3f}s")
    except Exception as e:
        app_duration = time.time() - app_start
        print(f"❌ create_app()                : {app_duration:6.3f}s (ERROR: {e})")

    total_time = time.time() - total_start
    print("\n🎯 SUMMARY:")
    print(f"Basic imports     : {basic_total:6.3f}s ({basic_total/total_time*100:4.1f}%)")
    print(f"AutoBot imports   : {autobot_total:6.3f}s ({autobot_total/total_time*100:4.1f}%)")
    print(f"Backend imports   : {backend_total:6.3f}s ({backend_total/total_time*100:4.1f}%)")
    print(f"App creation      : {app_duration:6.3f}s ({app_duration/total_time*100:4.1f}%)")
    print(f"Total time        : {total_time:6.3f}s")
    print(f"\n💡 Remaining delay: {total_time - basic_total - autobot_total - backend_total - app_duration:.3f}s")


if __name__ == "__main__":
    main()
