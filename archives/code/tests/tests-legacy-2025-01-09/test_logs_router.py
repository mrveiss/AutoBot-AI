#!/usr/bin/env python3
"""
Test script to verify logs router functionality
Run this after backend restart to verify the logs API endpoints
"""
import requests
import json
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = "http://localhost:8001"

def test_endpoint(endpoint, expected_status=200):
    """Test an API endpoint and return the result"""
    try:
        url = f"{BASE_URL}{endpoint}"
        print(f"Testing: {url}")

        response = requests.get(url, timeout=10)

        if response.status_code == expected_status:
            print(f"✅ {endpoint} - Status: {response.status_code}")
            if response.headers.get('content-type', '').startswith('application/json'):
                data = response.json()
                if isinstance(data, dict) and 'total_sources' in data:
                    print(f"   Found {data['total_sources']} log sources")
                elif isinstance(data, dict) and 'count' in data:
                    print(f"   Returned {data['count']} log entries")
                elif isinstance(data, list):
                    print(f"   Returned {len(data)} items")
            return True
        else:
            print(f"❌ {endpoint} - Status: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False

    except requests.exceptions.ConnectionError:
        print(f"❌ {endpoint} - Connection failed (backend not running?)")
        return False
    except Exception as e:
        print(f"❌ {endpoint} - Error: {e}")
        return False

def main():
    """Test all logs endpoints"""
    print("🔍 Testing AutoBot Logs API Endpoints")
    print("=" * 50)

    # Test backend health first
    if not test_endpoint("/api/health"):
        print("❌ Backend is not responding. Please start the backend first.")
        return

    print("\n📋 Testing Logs API Endpoints:")
    print("-" * 30)

    endpoints_to_test = [
        "/api/logs/sources",      # Main endpoint that was failing
        "/api/logs/recent",       # Recent logs endpoint
        "/api/logs/list",         # List log files
        "/api/logs/unified",      # Unified logs
        "/api/logs/search?query=info",  # Search with query
    ]

    results = []
    for endpoint in endpoints_to_test:
        success = test_endpoint(endpoint)
        results.append((endpoint, success))
        print()

    print("📊 Test Summary:")
    print("-" * 20)
    total_tests = len(results)
    passed_tests = sum(1 for _, success in results if success)

    for endpoint, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {endpoint}")

    print(f"\nResults: {passed_tests}/{total_tests} tests passed")

    if passed_tests == total_tests:
        print("🎉 All logs endpoints are working correctly!")
    else:
        print("⚠️  Some endpoints failed. Check backend logs for details.")

if __name__ == "__main__":
    main()
