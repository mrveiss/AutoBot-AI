#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
API Endpoint Performance Profiler
Tests the actual API endpoints for response time analysis
"""

import asyncio
import logging
import os
import sys
import time

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


def _get_endpoint_list(base_url: str) -> list:
    """Build list of API endpoints to test.

    Helper for test_api_endpoints (#825).
    """
    return [
        (f"{base_url}/api/system/health", "Health Check (Fast)", None),
        (
            f"{base_url}/api/system/health",
            "Health Check (Detailed)",
            {"detailed": "true"},
        ),
        (f"{base_url}/api/project/status", "Project Status (Fast)", None),
        (
            f"{base_url}/api/project/status",
            "Project Status (Detailed)",
            {"detailed": "true"},
        ),
        (f"{base_url}/api/system/status", "System Status", None),
        (f"{base_url}/api/system/models", "Available Models", None),
        (f"{base_url}/api/llm/status", "LLM Status", None),
        (f"{base_url}/api/redis/status", "Redis Status", None),
    ]


def _log_performance_summary(
    results: list, total_time: float, successful_tests: int, total_endpoints: int
):
    """Log sorted performance summary of test results.

    Helper for test_api_endpoints (#825).
    """
    logger.info("=" * 50)
    logger.info("PERFORMANCE SUMMARY")
    logger.info("=" * 50)

    results.sort(key=lambda x: x[1])
    for desc, duration, success in results:
        if duration < 100:
            speed_rating = "FAST"
        elif duration < 500:
            speed_rating = "GOOD"
        elif duration < 1000:
            speed_rating = "SLOW"
        else:
            speed_rating = "VERY SLOW"
        status = "OK" if success else "FAIL"
        logger.info("[%s] %-25s %8.0fms %s", status, desc, duration, speed_rating)

    logger.info("Total test time: %.0fms", total_time)
    logger.info("Successful tests: %s/%s", successful_tests, total_endpoints)
    if successful_tests == total_endpoints:
        logger.info("All endpoints are responding!")
    else:
        logger.error("Some endpoints failed - check if backend is running")


async def test_api_endpoints():
    """Test all critical API endpoints."""
    logger.info("API Endpoint Performance Testing")
    logger.info("=" * 50)

    from config import API_BASE_URL

    endpoints = _get_endpoint_list(API_BASE_URL)
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

    _log_performance_summary(results, total_time, successful_tests, len(endpoints))


if __name__ == "__main__":
    asyncio.run(test_api_endpoints())
