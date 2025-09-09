#!/usr/bin/env python3
"""
Comprehensive API Endpoint Testing for AutoBot
Tests all 25 mounted API routers for 100% endpoint success rate
"""

import asyncio
import json
import time
import requests
import aiohttp
from typing import Dict, List, Tuple, Any
from dataclasses import dataclass
from datetime import datetime

@dataclass
class EndpointResult:
    """Result of an individual endpoint test"""
    path: str
    method: str
    status_code: int
    response_time: float
    success: bool
    error: str = ""
    response_data: Any = None

class AutoBotAPITester:
    """Comprehensive API endpoint tester"""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.results: List[EndpointResult] = []
        self.session = requests.Session()
        self.session.timeout = 10
        
    def test_endpoint(self, path: str, method: str = "GET", 
                     data: Dict = None, files: Dict = None,
                     headers: Dict = None) -> EndpointResult:
        """Test a single endpoint and return result"""
        full_url = f"{self.base_url}{path}"
        start_time = time.time()
        
        try:
            if method.upper() == "GET":
                response = self.session.get(full_url, headers=headers)
            elif method.upper() == "POST":
                if files:
                    response = self.session.post(full_url, data=data, files=files, headers=headers)
                else:
                    response = self.session.post(full_url, json=data, headers=headers)
            elif method.upper() == "PUT":
                response = self.session.put(full_url, json=data, headers=headers)
            elif method.upper() == "DELETE":
                response = self.session.delete(full_url, headers=headers)
            else:
                raise ValueError(f"Unsupported method: {method}")
                
            response_time = time.time() - start_time
            
            # Consider 200-299 as success, some 4xx might be expected for invalid requests
            success = 200 <= response.status_code < 400
            
            try:
                response_data = response.json() if response.content else None
            except:
                response_data = response.text[:200] if response.text else None
                
            return EndpointResult(
                path=path,
                method=method,
                status_code=response.status_code,
                response_time=response_time,
                success=success,
                response_data=response_data
            )
            
        except Exception as e:
            response_time = time.time() - start_time
            return EndpointResult(
                path=path,
                method=method,
                status_code=0,
                response_time=response_time,
                success=False,
                error=str(e)
            )
    
    def run_comprehensive_tests(self) -> Dict[str, Any]:
        """Run comprehensive tests on all API endpoints"""
        
        print("🚀 Starting Comprehensive AutoBot API Endpoint Testing")
        print("=" * 80)
        
        # Test categories based on mounted routers
        test_categories = {
            "System & Health": [
                ("/api/health", "GET"),
                ("/api/system/status", "GET"),
                ("/api/system/info", "GET"),
                ("/api/system/resources", "GET"),
            ],
            
            "Chat & Messaging": [
                ("/api/chat/chats/new", "POST"),
                ("/api/chat/chats", "GET"),
                ("/api/chat/health", "GET"),
            ],
            
            "Settings & Configuration": [
                ("/api/settings/", "GET"),  # Corrected from /get_all
                ("/api/settings/llm", "GET"),
                ("/api/agent-config/", "GET"),
                ("/api/agent-config/agents", "GET"),
            ],
            
            "Knowledge Base (High Priority)": [
                ("/api/knowledge_base/stats", "GET"),
                ("/api/knowledge_base/detailed_stats", "GET"),
                ("/api/knowledge_base/search", "POST", {"query": "test search", "top_k": 5}),
                ("/api/knowledge", "GET"),
            ],
            
            "File Operations (High Priority)": [
                ("/api/files/stats", "GET"),  # Previously 403 error
                ("/api/files/recent", "GET"),
                ("/api/files/search", "GET"),
            ],
            
            "LLM & AI Operations": [
                ("/api/llm/status", "GET"),
                ("/api/llm/models", "GET"),
                ("/api/llm/health", "GET"),
                ("/api/prompts/", "GET"),
                ("/api/prompts/categories", "GET"),
            ],
            
            "Monitoring & Analytics": [
                ("/api/cache/stats", "GET"),
                ("/api/rum/dashboard", "GET"),
                ("/api/monitoring/services", "GET"),
                ("/api/infrastructure/health", "GET"),
                ("/api/validation-dashboard/status", "GET"),  # Corrected URL
            ],
            
            "Development & Tools": [
                ("/api/developer/", "GET"),
                ("/api/templates/", "GET"),
                ("/api/secrets/status", "GET"),
                ("/api/logs/recent", "GET"),
            ],
            
            "Automation & Control": [
                ("/api/playwright/health", "GET"),
                ("/api/terminal/sessions", "GET"),
                ("/api/batch/status", "GET"),
                ("/api/research/health", "GET"),
            ]
        }
        
        # Run tests by category
        category_results = {}
        total_tests = 0
        total_success = 0
        
        for category, endpoints in test_categories.items():
            print(f"\n📂 Testing Category: {category}")
            print("-" * 60)
            
            category_success = 0
            category_total = 0
            
            for endpoint_data in endpoints:
                path = endpoint_data[0]
                method = endpoint_data[1]
                data = endpoint_data[2] if len(endpoint_data) > 2 else None
                
                print(f"  Testing: {method} {path}")
                
                result = self.test_endpoint(path, method, data)
                self.results.append(result)
                
                total_tests += 1
                category_total += 1
                
                if result.success:
                    total_success += 1
                    category_success += 1
                    print(f"    ✅ {result.status_code} ({result.response_time:.3f}s)")
                else:
                    print(f"    ❌ {result.status_code} ({result.response_time:.3f}s) - {result.error}")
                    if result.response_data:
                        print(f"      Response: {str(result.response_data)[:100]}...")
            
            success_rate = (category_success / category_total * 100) if category_total > 0 else 0
            category_results[category] = {
                "success": category_success,
                "total": category_total,
                "success_rate": success_rate
            }
            print(f"  📊 Category Success Rate: {success_rate:.1f}% ({category_success}/{category_total})")
        
        # Calculate overall results
        overall_success_rate = (total_success / total_tests * 100) if total_tests > 0 else 0
        
        # Print summary
        print("\n" + "=" * 80)
        print("📋 COMPREHENSIVE API TESTING SUMMARY")
        print("=" * 80)
        
        for category, stats in category_results.items():
            status_icon = "✅" if stats["success_rate"] == 100 else "⚠️" if stats["success_rate"] >= 80 else "❌"
            print(f"{status_icon} {category}: {stats['success_rate']:.1f}% ({stats['success']}/{stats['total']})")
        
        print(f"\n🎯 OVERALL SUCCESS RATE: {overall_success_rate:.1f}% ({total_success}/{total_tests})")
        
        if overall_success_rate == 100:
            print("🎉 TARGET ACHIEVED: 100% endpoint success rate!")
        else:
            print(f"🔧 {total_tests - total_success} endpoints need fixes to reach 100%")
        
        # Detailed failure analysis
        failures = [r for r in self.results if not r.success]
        if failures:
            print(f"\n🔍 DETAILED FAILURE ANALYSIS ({len(failures)} failures)")
            print("-" * 60)
            for failure in failures:
                print(f"❌ {failure.method} {failure.path}")
                print(f"   Status: {failure.status_code}")
                print(f"   Error: {failure.error}")
                if failure.response_data:
                    print(f"   Response: {str(failure.response_data)[:150]}...")
                print()
        
        return {
            "overall_success_rate": overall_success_rate,
            "total_tests": total_tests,
            "total_success": total_success,
            "category_results": category_results,
            "failures": [
                {
                    "path": f.path,
                    "method": f.method,
                    "status": f.status_code,
                    "error": f.error,
                    "response": str(f.response_data)[:200] if f.response_data else None
                }
                for f in failures
            ]
        }
    
    def test_specific_fixes(self) -> Dict[str, Any]:
        """Test the specific endpoints mentioned as previously failing"""
        
        print("\n🔧 TESTING SPECIFIC PREVIOUSLY FAILING ENDPOINTS")
        print("=" * 60)
        
        high_priority_tests = [
            # Previously failing endpoints
            ("/api/knowledge_base/search", "POST", {"query": "test search", "top_k": 5}),
            ("/api/files/stats", "GET"),
            ("/api/knowledge_base/detailed_stats", "GET"),
            
            # URL mismatch corrections
            ("/api/settings/", "GET"),
            ("/api/validation-dashboard/status", "GET"),
            ("/api/chat/chats/new", "POST"),
        ]
        
        results = []
        for endpoint_data in high_priority_tests:
            path = endpoint_data[0]
            method = endpoint_data[1]
            data = endpoint_data[2] if len(endpoint_data) > 2 else None
            
            print(f"🎯 Testing: {method} {path}")
            result = self.test_endpoint(path, method, data)
            results.append(result)
            
            if result.success:
                print(f"   ✅ SUCCESS: {result.status_code} ({result.response_time:.3f}s)")
            else:
                print(f"   ❌ FAILED: {result.status_code} - {result.error}")
                if result.response_data:
                    print(f"   Response: {str(result.response_data)[:150]}...")
        
        success_count = sum(1 for r in results if r.success)
        success_rate = (success_count / len(results) * 100) if results else 0
        
        print(f"\n🎯 HIGH PRIORITY SUCCESS RATE: {success_rate:.1f}% ({success_count}/{len(results)})")
        
        return {
            "high_priority_success_rate": success_rate,
            "results": results
        }

def main():
    """Run comprehensive API endpoint testing"""
    tester = AutoBotAPITester()
    
    # Test specific fixes first
    specific_results = tester.test_specific_fixes()
    
    # Run comprehensive tests
    overall_results = tester.run_comprehensive_tests()
    
    # Save detailed results to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = f"/home/kali/Desktop/AutoBot/api_test_results_{timestamp}.json"
    
    with open(results_file, 'w') as f:
        json.dump({
            "timestamp": timestamp,
            "specific_fixes": specific_results,
            "comprehensive": overall_results,
            "detailed_results": [
                {
                    "path": r.path,
                    "method": r.method,
                    "status_code": r.status_code,
                    "response_time": r.response_time,
                    "success": r.success,
                    "error": r.error,
                    "response_data": str(r.response_data)[:500] if r.response_data else None
                }
                for r in tester.results
            ]
        }, f, indent=2)
    
    print(f"\n💾 Detailed results saved to: {results_file}")
    
    return overall_results["overall_success_rate"]

if __name__ == "__main__":
    success_rate = main()
    exit(0 if success_rate == 100 else 1)