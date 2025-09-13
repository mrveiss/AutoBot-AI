#!/usr/bin/env python3
"""
Quick API Endpoint Testing for AutoBot - Focus on High Priority
"""

import requests
import json
import time
from typing import Dict, List

class QuickAPITester:
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.timeout = 5  # Faster timeout
        
    def test_endpoint(self, path: str, method: str = "GET", data: Dict = None) -> Dict:
        """Test a single endpoint"""
        full_url = f"{self.base_url}{path}"
        start_time = time.time()
        
        try:
            if method.upper() == "GET":
                response = self.session.get(full_url)
            elif method.upper() == "POST":
                response = self.session.post(full_url, json=data)
                
            response_time = time.time() - start_time
            success = 200 <= response.status_code < 400
            
            return {
                "path": path,
                "method": method,
                "status": response.status_code,
                "time": f"{response_time:.3f}s",
                "success": success,
                "error": "" if success else response.text[:100]
            }
            
        except Exception as e:
            response_time = time.time() - start_time
            return {
                "path": path,
                "method": method,
                "status": 0,
                "time": f"{response_time:.3f}s",
                "success": False,
                "error": str(e)[:100]
            }

def main():
    tester = QuickAPITester()
    
    print("🚀 Quick AutoBot API Testing")
    print("=" * 50)
    
    # High Priority Tests - Previously failing endpoints
    priority_tests = [
        ("/api/health", "GET"),
        ("/api/knowledge_base/search", "POST", {"query": "test", "top_k": 5}),
        ("/api/files/stats", "GET"),
        ("/api/knowledge_base/detailed_stats", "GET"),
        ("/api/settings/", "GET"),
        ("/api/validation-dashboard/status", "GET"),
        ("/api/chat/chats/new", "POST"),
        ("/api/system/status", "GET"),
        ("/api/llm/status", "GET"),
        ("/api/monitoring/services", "GET"),
    ]
    
    print("\n🎯 HIGH PRIORITY ENDPOINTS")
    print("-" * 40)
    
    results = []
    success_count = 0
    
    for test_data in priority_tests:
        path = test_data[0]
        method = test_data[1]
        data = test_data[2] if len(test_data) > 2 else None
        
        result = tester.test_endpoint(path, method, data)
        results.append(result)
        
        status_icon = "✅" if result["success"] else "❌"
        print(f"{status_icon} {method:4} {path:35} {result['status']:3} {result['time']:>8}")
        
        if not result["success"] and result["error"]:
            print(f"    Error: {result['error']}")
            
        if result["success"]:
            success_count += 1
    
    # Additional Core Endpoints
    core_tests = [
        ("/api/system/info", "GET"),
        ("/api/chat/health", "GET"),
        ("/api/knowledge_base/stats", "GET"),
        ("/api/cache/stats", "GET"),
        ("/api/prompts/", "GET"),
        ("/api/files/recent", "GET"),
        ("/api/templates/", "GET"),
        ("/api/logs/recent", "GET"),
        ("/api/batch/status", "GET"),
    ]
    
    print(f"\n📋 ADDITIONAL CORE ENDPOINTS")
    print("-" * 40)
    
    for test_data in core_tests:
        path = test_data[0]
        method = test_data[1]
        
        result = tester.test_endpoint(path, method)
        results.append(result)
        
        status_icon = "✅" if result["success"] else "❌"
        print(f"{status_icon} {method:4} {path:35} {result['status']:3} {result['time']:>8}")
        
        if result["success"]:
            success_count += 1
    
    # Calculate success rate
    total_tests = len(results)
    success_rate = (success_count / total_tests * 100) if total_tests > 0 else 0
    
    print("\n" + "=" * 50)
    print(f"📊 QUICK TEST RESULTS")
    print(f"Success Rate: {success_rate:.1f}% ({success_count}/{total_tests})")
    
    if success_rate == 100:
        print("🎉 TARGET ACHIEVED: 100% endpoint success rate!")
    else:
        failures = [r for r in results if not r["success"]]
        print(f"🔧 {len(failures)} endpoints need fixes:")
        for failure in failures:
            print(f"   ❌ {failure['method']} {failure['path']} - Status {failure['status']}")
    
    # Save results
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    results_file = f"tests/results/quick_api_results_{timestamp}.json"
    with open(results_file, 'w') as f:
        json.dump({
            "timestamp": timestamp,
            "success_rate": success_rate,
            "total_tests": total_tests,
            "successful_tests": success_count,
            "results": results
        }, f, indent=2)
    
    print(f"💾 Results saved to: {results_file}")
    
    return success_rate

if __name__ == "__main__":
    success_rate = main()
    exit(0 if success_rate == 100 else 1)