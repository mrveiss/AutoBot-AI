#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Quick backend diagnostic script"""

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Optional

import requests

# Import configuration from centralized source
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.config import API_BASE_URL, OLLAMA_URL


@dataclass
class EndpointResult:
    """Result of endpoint health check."""
    url: str
    name: str
    status_code: Optional[int] = None
    elapsed: float = 0.0
    response_text: str = ""
    error: Optional[str] = None


def check_endpoint(url: str, name: str, timeout: int = 5) -> EndpointResult:
    """Check a single endpoint and return result."""
    start = time.time()
    try:
        response = requests.get(url, timeout=timeout)
        elapsed = time.time() - start
        return EndpointResult(
            url=url,
            name=name,
            status_code=response.status_code,
            elapsed=elapsed,
            response_text=response.text[:100] if response.status_code == 200 else "",
        )
    except requests.exceptions.Timeout:
        return EndpointResult(url=url, name=name, elapsed=time.time() - start, error="TIMEOUT after 5 seconds")
    except requests.exceptions.ConnectionError as e:
        return EndpointResult(url=url, name=name, elapsed=time.time() - start, error=f"CONNECTION ERROR: {e}")
    except Exception as e:
        return EndpointResult(url=url, name=name, elapsed=time.time() - start, error=f"{type(e).__name__}: {e}")


def check_endpoints_batch(endpoints: list) -> list:
    """Check multiple endpoints concurrently using ThreadPoolExecutor."""
    results = []
    with ThreadPoolExecutor(max_workers=min(len(endpoints), 10)) as executor:
        future_to_endpoint = {
            executor.submit(check_endpoint, url, name): (url, name)
            for url, name in endpoints
        }
        for future in as_completed(future_to_endpoint):
            results.append(future.result())
    return results


print("🔍 Checking backend health...")

# Test endpoints
endpoints = [
    (f"{API_BASE_URL}/api/hello", "Basic API"),
    (f"{API_BASE_URL}/api/system/health", "Health Check"),
    (f"{API_BASE_URL}/api/chat/list", "Chat List"),
]

# Batch check all endpoints concurrently
results = check_endpoints_batch(endpoints)

# Display results (sorted by original order)
endpoint_order = {url: i for i, (url, _) in enumerate(endpoints)}
results.sort(key=lambda r: endpoint_order.get(r.url, 999))

for result in results:
    print(f"\n📍 Testing {result.name}: {result.url}")
    if result.error:
        print(f"   ❌ {result.error}")
    else:
        print(f"   ✅ Status: {result.status_code} (took {result.elapsed:.2f}s)")
        if result.response_text:
            print(f"   📄 Response: {result.response_text}...")

# Check Ollama
print("\n🤖 Checking Ollama...")
try:
    response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
    if response.status_code == 200:
        models = response.json().get("models", [])
        print(f"   ✅ Ollama is running with {len(models)} models")
        for model in models[:3]:  # Show first 3
            print(f"      - {model['name']}")
    else:
        print(f"   ❌ Ollama returned status {response.status_code}")
except Exception as e:
    print(f"   ❌ Cannot connect to Ollama: {e}")

print("\n💡 Diagnosis Summary:")
print(
    "   - If all endpoints timeout, the backend is likely stuck during initialization"
)
print("   - Check the backend logs for LLM initialization errors")
print("   - Try restarting the backend with: pkill -f uvicorn && ./run_agent.sh")
