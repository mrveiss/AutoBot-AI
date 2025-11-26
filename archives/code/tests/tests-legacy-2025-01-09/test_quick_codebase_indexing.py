#!/usr/bin/env python3
"""
Quick test for codebase indexing functionality
"""

import requests
import json
import time

def test_quick_indexing():
    """Test the codebase indexing endpoint with timeout"""
    print("🚀 Testing Codebase Indexing API")

    try:
        # Test with smaller scope first
        print("📂 Testing limited scope indexing...")

        start_time = time.time()
        response = requests.post(
            "http://localhost:8001/api/analytics/codebase/index",
            params={"root_path": "/home/kali/Desktop/AutoBot/backend/api"},  # Smaller scope
            timeout=30  # 30 second timeout
        )

        end_time = time.time()
        print(f"⏱️  Request took {end_time - start_time:.2f} seconds")

        print(f"📊 Status Code: {response.status_code}")
        print(f"📄 Response: {response.text}")

        if response.status_code == 200:
            data = response.json()
            print("✅ Indexing successful!")
            print(f"   📁 Files indexed: {data.get('stats', {}).get('total_files', 'unknown')}")
            print(f"   🐍 Python files: {data.get('stats', {}).get('python_files', 'unknown')}")
            print(f"   💾 Storage type: {data.get('storage_type', 'unknown')}")

            # Test stats endpoint
            print("\n📊 Testing stats endpoint...")
            stats_response = requests.get("http://localhost:8001/api/analytics/codebase/stats", timeout=10)
            if stats_response.status_code == 200:
                stats_data = stats_response.json()
                print("✅ Stats endpoint working!")
                print(f"   📈 Stats: {stats_data.get('stats', {})}")
            else:
                print(f"❌ Stats endpoint failed: {stats_response.status_code}")

            # Test hardcodes endpoint
            print("\n🔍 Testing hardcodes endpoint...")
            hardcodes_response = requests.get("http://localhost:8001/api/analytics/codebase/hardcodes", timeout=10)
            if hardcodes_response.status_code == 200:
                hardcodes_data = hardcodes_response.json()
                print("✅ Hardcodes endpoint working!")
                print(f"   🎯 Hardcodes found: {hardcodes_data.get('total_count', 0)}")
                print(f"   📂 Types: {hardcodes_data.get('hardcode_types', [])}")
            else:
                print(f"❌ Hardcodes endpoint failed: {hardcodes_response.status_code}")

        else:
            print(f"❌ Indexing failed with status {response.status_code}")
            try:
                error_data = response.json()
                print(f"   💬 Error: {error_data}")
            except:
                print(f"   💬 Raw error: {response.text}")

    except requests.exceptions.Timeout:
        print("❌ Request timed out - endpoint might be hanging")
    except requests.exceptions.ConnectionError:
        print("❌ Connection failed - backend might not be running")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    test_quick_indexing()
