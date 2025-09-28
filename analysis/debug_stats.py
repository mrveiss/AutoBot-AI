#!/usr/bin/env python3
"""
Debug script to check what's happening with the stats endpoint
"""

import requests
import json

def test_stats_endpoint():
    """Test the stats endpoint and show detailed response"""
    print("=== Testing Knowledge Base Stats Endpoint ===")

    try:
        # Test the basic stats endpoint
        response = requests.get(
            "http://127.0.0.1:8001/api/knowledge_base/stats/basic",
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
            total_chunks = data.get('total_chunks', 0)

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
            "http://127.0.0.1:8001/api/knowledge_base/stats",
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