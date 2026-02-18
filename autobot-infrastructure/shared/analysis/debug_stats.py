#!/usr/bin/env python3
"""
Debug script to check what's happening with the stats endpoint
"""

import json
import logging
import sys
from pathlib import Path

import requests

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import unified_config_manager

logger = logging.getLogger(__name__)


def _get_api_endpoint():
    """Build API endpoint URL from configuration.

    Helper for test_stats_endpoint (#825).
    """
    backend_config = unified_config_manager.get_backend_config()

    host = backend_config.get("host")
    port = backend_config.get("port")

    if not host or not port:
        system_defaults = (
            unified_config_manager.get_config_section("service_discovery_defaults")
            or {}
        )
        host = host or system_defaults.get("backend_host", "localhost")
        port = port or system_defaults.get("backend_port", 8001)

    return f"http://{host}:{port}"


def _test_single_stats_endpoint(api_endpoint, path, label):
    """Test a single stats endpoint and log the response.

    Helper for test_stats_endpoint (#825).
    """
    logger.info("\n=== %s ===", label)

    try:
        response = requests.get(
            f"{api_endpoint}{path}",
            headers={"accept": "application/json"},
            timeout=10,
        )

        logger.info("Status Code: %s", response.status_code)

        if response.status_code == 200:
            data = response.json()
            logger.info("📊 Response:")
            logger.info("%s", json.dumps(data, indent=2))

            total_docs = data.get("total_documents", 0)
            if total_docs is not None and total_docs > 1000:
                logger.info(
                    "✅ SUCCESS: Showing realistic stats " "(%s documents)", total_docs
                )
            elif total_docs is not None:
                logger.error(
                    "❌ ISSUE: Still showing low stats " "(%s documents)", total_docs
                )
        else:
            logger.error("❌ ERROR: Status %s", response.status_code)
            logger.info("Response: %s", response.text)

    except Exception as e:
        logger.error("❌ Exception: %s", e)


def test_stats_endpoint():
    """Test the stats endpoint and show detailed response."""
    api_endpoint = _get_api_endpoint()
    logger.info("Using API endpoint: %s", api_endpoint)

    _test_single_stats_endpoint(
        api_endpoint,
        "/api/knowledge_base/stats/basic",
        "Testing Knowledge Base Stats Endpoint",
    )
    _test_single_stats_endpoint(
        api_endpoint,
        "/api/knowledge_base/stats",
        "Testing Other Stats Endpoint",
    )


if __name__ == "__main__":
    test_stats_endpoint()
