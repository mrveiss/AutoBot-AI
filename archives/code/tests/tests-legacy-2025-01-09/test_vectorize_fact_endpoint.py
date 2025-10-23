#!/usr/bin/env python3
"""
Test script for individual document vectorization endpoints.

Tests:
1. POST /api/knowledge/vectorize_fact/{fact_id}
2. GET /api/knowledge/vectorize_job/{job_id}
"""

import requests
import time
import json

BASE_URL = "http://172.16.168.20:8001"

def test_vectorize_fact_endpoint():
    """Test individual fact vectorization with job tracking"""

    print("=" * 60)
    print("Testing Individual Document Vectorization")
    print("=" * 60)

    # Step 1: Get a fact ID from the knowledge base
    print("\n1. Getting existing facts...")
    response = requests.get(f"{BASE_URL}/api/knowledge/entries", params={"limit": 1})

    if response.status_code != 200:
        print(f"❌ Failed to get facts: {response.status_code}")
        print(response.text)
        return

    data = response.json()
    entries = data.get("entries", [])

    if not entries:
        print("❌ No facts found in knowledge base")
        print("Please add some facts first using /api/knowledge/add_text")
        return

    fact_id = entries[0]["id"]
    print(f"✓ Found fact: {fact_id}")
    print(f"  Title: {entries[0].get('title', 'Untitled')}")

    # Step 2: Start vectorization job
    print(f"\n2. Starting vectorization job for fact {fact_id}...")
    response = requests.post(
        f"{BASE_URL}/api/knowledge/vectorize_fact/{fact_id}",
        params={"force": True}  # Force re-vectorization for testing
    )

    if response.status_code != 200:
        print(f"❌ Failed to start vectorization: {response.status_code}")
        print(response.text)
        return

    job_data = response.json()
    job_id = job_data["job_id"]
    print(f"✓ Vectorization job started")
    print(f"  Job ID: {job_id}")
    print(f"  Fact ID: {job_data['fact_id']}")
    print(f"  Force: {job_data['force']}")

    # Step 3: Poll job status
    print(f"\n3. Monitoring job status...")
    max_attempts = 30
    attempt = 0

    while attempt < max_attempts:
        attempt += 1
        time.sleep(1)  # Wait 1 second between checks

        response = requests.get(f"{BASE_URL}/api/knowledge/vectorize_job/{job_id}")

        if response.status_code != 200:
            print(f"❌ Failed to get job status: {response.status_code}")
            print(response.text)
            return

        status_data = response.json()
        job = status_data["job"]

        print(f"  Attempt {attempt}: Status={job['status']}, Progress={job['progress']}%")

        if job["status"] in ["completed", "failed"]:
            print(f"\n4. Job finished!")
            print(f"  Status: {job['status']}")
            print(f"  Progress: {job['progress']}%")
            print(f"  Started: {job['started_at']}")
            print(f"  Completed: {job['completed_at']}")

            if job["status"] == "completed":
                print(f"  ✓ Vectorization successful!")
                result = job.get("result", {})
                print(f"  Result: {json.dumps(result, indent=2)}")
            else:
                print(f"  ❌ Vectorization failed!")
                print(f"  Error: {job.get('error', 'Unknown error')}")

            break
    else:
        print(f"\n❌ Job did not complete within {max_attempts} seconds")

    print("\n" + "=" * 60)
    print("Test completed")
    print("=" * 60)


if __name__ == "__main__":
    test_vectorize_fact_endpoint()
