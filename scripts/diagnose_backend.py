#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Quick backend diagnostic script"""

import os
import sys
import time

import requests

# Import configuration from centralized source
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.unified_config import API_BASE_URL, OLLAMA_URL

print("🔍 Checking backend health...")

# Test endpoints
endpoints = [
    (f"{API_BASE_URL}/api/hello", "Basic API"),
    (f"{API_BASE_URL}/api/system/health", "Health Check"),
    (f"{API_BASE_URL}/api/chat/list", "Chat List"),
]

for url, name in endpoints:
    print(f"\n📍 Testing {name}: {url}")
    start = time.time()
    try:
        response = requests.get(url, timeout=5)
        elapsed = time.time() - start
        print(f"   ✅ Status: {response.status_code} (took {elapsed:.2f}s)")
        if response.status_code == 200:
            print(f"   📄 Response: {response.text[:100]}...")
    except requests.exceptions.Timeout:
        print(f"   ❌ TIMEOUT after 5 seconds")
    except requests.exceptions.ConnectionError as e:
        print(f"   ❌ CONNECTION ERROR: {e}")
    except Exception as e:
        print(f"   ❌ ERROR: {type(e).__name__}: {e}")

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
