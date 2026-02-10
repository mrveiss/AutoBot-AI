#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
API Endpoint Performance Profiler
Tests the actual API endpoints for response time analysis
"""

import asyncio
import os
import sys
import time

import logging

logger = logging.getLogger(__name__)

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_endpoint_performance(url, description, params=None):
    """Test a single endpoint performance"""
    try:
        start_time = time.time()
        response = requests.get(url, params=params, timeout=10)
        end_time = time.time()

        duration_ms = (end_time - start_time) * 1000
        status = "✅" if response.status_code == 200 else "❌"

        logger.info(
            f"{status} {description}: {duration_ms:.0f}ms (Status: {response.status_code})"
        )
        return duration_ms, response.status_code == 200

    except Exception as e:
        logger.error(f"❌ {description}: FAILED - {str(e)}")
        return None, False


async def test_api_endpoints():
    """Test all critical API endpoints"""
    logger.info("🚀 API Endpoint Performance Testing")
    logger.info("=" * 50)

    # Import configuration from centralized source
    import os
    import sys

    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import API_BASE_URL

    base_url = API_BASE_URL

    endpoints = [
        # Health endpoints
        (f"{base_url}/api/system/health", "Health Check (Fast)", None),
        (
            f"{base_url}/api/system/health",
            "Health Check (Detailed)",
            {"detailed": "true"},
        ),
        # Project status endpoints
        (f"{base_url}/api/project/status", "Project Status (Fast)", None),
        (
            f"{base_url}/api/project/status",
            "Project Status (Detailed)",
            {"detailed": "true"},
        ),
        # Other critical endpoints
        (f"{base_url}/api/system/status", "System Status", None),
        (f"{base_url}/api/system/models", "Available Models", None),
        (f"{base_url}/api/llm/status", "LLM Status", None),
        (f"{base_url}/api/redis/status", "Redis Status", None),
    ]

    results = []
    total_time = 0
    successful_tests = 0

    for url, description, params in endpoints:
        duration, success = test_endpoint_performance(url, description, params)
        if duration is not None:
            results.append((description, duration, success))
            total_time += duration
            if success:
                successful_tests += 1

    logger.info("\n" + "=" * 50)
    logger.info("📊 PERFORMANCE SUMMARY")
    logger.info("=" * 50)

    # Sort by performance (fastest first)
    results.sort(key=lambda x: x[1])

    for desc, duration, success in results:
        status_icon = "✅" if success else "❌"
        if duration < 100:
            speed_rating = "🚀 FAST"
        elif duration < 500:
            speed_rating = "⚡ GOOD"
        elif duration < 1000:
            speed_rating = "⚠️  SLOW"
        else:
            speed_rating = "🐌 VERY SLOW"

        logger.info(f"{status_icon} {desc:<25} {duration:>8.0f}ms {speed_rating}")

    logger.info(f"\n📈 Total test time: {total_time:.0f}ms")
    logger.info(f"🎯 Successful tests: {successful_tests}/{len(endpoints)}")

    if successful_tests == len(endpoints):
        logger.info("🎉 All endpoints are responding!")
    else:
        logger.error("⚠️  Some endpoints failed - check if backend is running")


if __name__ == "__main__":
    asyncio.run(test_api_endpoints())
