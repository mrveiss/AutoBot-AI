#!/usr/bin/env python3
"""Quick backend diagnostic script"""

import requests
import time

print("🔍 Checking backend health...")

# Test endpoints
endpoints = [
    ("http://localhost:8001/api/hello", "Basic API"),
    ("http://localhost:8001/api/system/health", "Health Check"),
    ("http://localhost:8001/api/chat/list", "Chat List"),
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
    response = requests.get("http://localhost:11434/api/tags", timeout=5)
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
print("   - If all endpoints timeout, the backend is likely stuck during initialization")
print("   - Check the backend logs for LLM initialization errors")
print("   - Try restarting the backend with: pkill -f uvicorn && ./run_agent.sh")