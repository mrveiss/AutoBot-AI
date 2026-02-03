#!/usr/bin/env python3
"""
Debug script to check what's happening with the stats endpoint
"""

import requests
import json
import sys
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import unified_config_manager


def test_stats_endpoint():
    """Test the stats endpoint and show detailed response"""
    print("=== Testing Knowledge Base Stats Endpoint ===")

    # Get backend API endpoint from configuration
    backend_config = unified_config_manager.get_backend_config()

    # Build API endpoint from configuration without hardcoded fallback
    host = backend_config.get("host")
    port = backend_config.get("port")

    if not host or not port:
        # Try system defaults as last resort
        system_defaults = unified_config_manager.get_config_section("service_discovery_defaults") or {}
        host = host or system_defaults.get("backend_host", "localhost")
        port = port or system_defaults.get("backend_port", 8001)

    api_endpoint = f"http://{host}:{port}"

    print(f"Using API endpoint: {api_endpoint}")

    try:
        # Test the basic stats endpoint
        response = requests.get(
            f"{api_endpoint}/api/knowledge_base/stats/basic",
            headers={"accept": "application/json"},
            timeout=10
        )

        print(f"Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")

        if response.status_code == 200:
            data = response.json()
            print("\n📊 Current Stats Response:")
            print(json.dumps(data, indent=2))

            # Check if we're getting the expected fields
            total_docs = data.get('total_documents', 0)

            if total_docs > 1000:
                print(f"✅ SUCCESS: Showing realistic stats ({total_docs} documents)")
            else:
                print(f"❌ ISSUE: Still showing low stats ({total_docs} documents)")

        else:
            print(f"❌ ERROR: Status {response.status_code}")
            print(f"Response: {response.text}")

    except Exception as e:
        print(f"❌ Exception: {e}")

    # Also test the other stats endpoint
    print("\n=== Testing Other Stats Endpoint ===")

    try:
        response = requests.get(
            f"{api_endpoint}/api/knowledge_base/stats",
            headers={"accept": "application/json"},
            timeout=10
        )

        print(f"Status Code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print("\n📊 Other Stats Response:")
            print(json.dumps(data, indent=2))

    except Exception as e:
        print(f"❌ Exception on second endpoint: {e}")


if __name__ == "__main__":
    test_stats_endpoint()
