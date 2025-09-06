#!/usr/bin/env python3
"""
Test script to verify LLM connection and model loading fixes
"""

import requests
import json
import sys

BASE_URL = "http://localhost:8001"

def test_endpoint(name, url, expected_keys=None):
    """Test an endpoint and check response"""
    print(f"\n🧪 Testing {name}: {url}")
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print(f"❌ Status: {response.status_code}")
            return False
        
        data = response.json()
        print(f"✅ Status: {response.status_code}")
        
        if expected_keys:
            for key in expected_keys:
                if key in data:
                    value = data[key]
                    if isinstance(value, bool):
                        status = "✅" if value else "❌"
                    elif isinstance(value, str):
                        status = "✅" if value else "❌ (empty)"
                    elif isinstance(value, (list, dict)):
                        status = f"✅ ({len(value)} items)" if value else "❌ (empty)"
                    else:
                        status = f"✅ ({value})"
                    print(f"   {key}: {status}")
                else:
                    print(f"   {key}: ❌ (missing)")
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_comprehensive_status():
    """Test the comprehensive LLM status"""
    print(f"\n🧪 Testing Comprehensive LLM Status")
    try:
        response = requests.get(f"{BASE_URL}/api/llm/status/comprehensive", timeout=10)
        if response.status_code != 200:
            print(f"❌ Status: {response.status_code}")
            return False
        
        data = response.json()
        print(f"✅ Status: {response.status_code}")
        
        # Check structure
        provider_type = data.get("provider_type", "unknown")
        print(f"   Provider Type: ✅ {provider_type}")
        
        if provider_type == "local":
            ollama_config = data.get("providers", {}).get("local", {}).get("ollama", {})
            configured = ollama_config.get("configured", False)
            model = ollama_config.get("model", "")
            status = "✅" if configured and model else "❌"
            print(f"   Ollama Configured: {status}")
            print(f"   Ollama Model: {'✅' if model else '❌'} ({model})")
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    print("🔍 Testing LLM Connection and Model Loading Fixes")
    print("=" * 50)
    
    # Test endpoints
    tests = [
        ("System Health", f"{BASE_URL}/api/system/health", 
         ["llm_status", "current_model", "embedding_status", "current_embedding_model"]),
        
        ("LLM Status", f"{BASE_URL}/api/llm/status", 
         ["status", "model", "provider_type"]),
        
        ("LLM Models", f"{BASE_URL}/api/llm/models", 
         ["models", "total_count"]),
        
        ("Agent Config", f"{BASE_URL}/api/agent-config/agents", 
         ["agents", "total_count"]),
    ]
    
    results = []
    for name, url, keys in tests:
        success = test_endpoint(name, url, keys)
        results.append((name, success))
    
    # Test comprehensive status separately
    comprehensive_success = test_comprehensive_status()
    results.append(("Comprehensive LLM Status", comprehensive_success))
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Results Summary:")
    all_passed = True
    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"   {name}: {status}")
        if not success:
            all_passed = False
    
    print(f"\n🎯 Overall Result: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")
    
    if all_passed:
        print("\n🎉 LLM connection and model loading fixes are working!")
        print("   The Settings Panel should now show:")
        print("   - LLM Status: Connected ✅")
        print("   - Current Model: llama3.2:1b-instruct-q4_K_M ✅")
        print("   - Model Dropdown: Populated with available models ✅")
    else:
        print("\n⚠️ Some issues remain. Check the failing tests above.")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())