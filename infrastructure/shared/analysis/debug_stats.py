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


def test_stats_endpoint():
    """Test the stats endpoint and show detailed response"""
    logger.info("=== Testing Knowledge Base Stats Endpoint ===")

    # Get backend API endpoint from configuration
    backend_config = unified_config_manager.get_backend_config()

    # Build API endpoint from configuration without hardcoded fallback
    host = backend_config.get("host")
    port = backend_config.get("port")

    if not host or not port:
        # Try system defaults as last resort
        system_defaults = (
            unified_config_manager.get_config_section("service_discovery_defaults")
            or {}
        )
        host = host or system_defaults.get("backend_host", "localhost")
        port = port or system_defaults.get("backend_port", 8001)

    api_endpoint = f"http://{host}:{port}"

    logger.info("Using API endpoint: %s", api_endpoint)

    try:
        # Test the basic stats endpoint
        response = requests.get(
            f"{api_endpoint}/api/knowledge_base/stats/basic",
            headers={"accept": "application/json"},
            timeout=10,
        )

        logger.info("Status Code: %s", response.status_code)
        logger.info("Response Headers: %s", dict(response.headers))

        if response.status_code == 200:
            data = response.json()
            logger.info("\n📊 Current Stats Response:")
            logger.info("%s", json.dumps(data, indent=2))

            # Check if we're getting the expected fields
            total_docs = data.get("total_documents", 0)

            if total_docs > 1000:
                logger.info("✅ SUCCESS: Showing realistic stats (%s documents)", total_docs)
            else:
                logger.error("❌ ISSUE: Still showing low stats (%s documents)", total_docs)

        else:
            logger.error("❌ ERROR: Status %s", response.status_code)
            logger.info("Response: %s", response.text)

    except Exception as e:
        logger.error("❌ Exception: %s", e)

    # Also test the other stats endpoint
    logger.info("\n=== Testing Other Stats Endpoint ===")

    try:
        response = requests.get(
            f"{api_endpoint}/api/knowledge_base/stats",
            headers={"accept": "application/json"},
            timeout=10,
        )

        logger.info("Status Code: %s", response.status_code)

        if response.status_code == 200:
            data = response.json()
            logger.info("\n📊 Other Stats Response:")
            logger.info("%s", json.dumps(data, indent=2))

    except Exception as e:
        logger.error("❌ Exception on second endpoint: %s", e)


if __name__ == "__main__":
    test_stats_endpoint()
