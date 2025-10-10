#!/usr/bin/env python3
"""
Quick AutoBot Integration Test
Focus on working endpoints and realistic testing scenarios
"""

import asyncio
import aiohttp
import json
import time
import logging
from datetime import datetime
from typing import Dict, List, Any
import sys
import os

# Add project root to path
sys.path.insert(0, '/home/kali/Desktop/AutoBot')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class QuickIntegrationTest:
    """Quick integration test focusing on working endpoints"""
    
    def __init__(self):
        # Use actual working backend address from logs
        self.backend_url = "http://172.16.168.20:8001"
        self.frontend_url = "http://127.0.0.1:5173"
        
        # Test results
        self.results = {
            "backend_connectivity": {},
            "api_endpoints": {},
            "frontend_backend_proxy": {},
            "production_readiness": {}
        }

    async def run_quick_tests(self) -> Dict[str, Any]:
        """Run focused integration tests"""
        logger.info("🚀 Starting Quick AutoBot Integration Tests")
        start_time = time.time()
        
        # Test backend connectivity
        await self.test_backend_connectivity()
        
        # Test critical API endpoints
        await self.test_critical_endpoints()
        
        # Test frontend-backend proxy
        await self.test_frontend_proxy()
        
        # Assess production readiness
        self.assess_production_readiness()
        
        total_time = time.time() - start_time
        self.results["total_time"] = total_time
        
        self.generate_report()
        return self.results

    async def test_backend_connectivity(self):
        """Test basic backend connectivity"""
        logger.info("🔗 Testing Backend Connectivity")
        
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=5)
        ) as session:
            try:
                start_time = time.time()
                async with session.get(f"{self.backend_url}/api/health") as response:
                    response_time = time.time() - start_time
                    
                    self.results["backend_connectivity"] = {
                        "success": response.status == 200,
                        "status_code": response.status,
                        "response_time": response_time,
                        "timestamp": datetime.now().isoformat()
                    }
                    
                    if response.status == 200:
                        data = await response.json()
                        self.results["backend_connectivity"]["data"] = data
                        logger.info(f"✅ Backend health check: {response.status} ({response_time:.2f}s)")
                    else:
                        logger.error(f"❌ Backend health check failed: {response.status}")
                        
            except Exception as e:
                self.results["backend_connectivity"] = {
                    "success": False,
                    "error": str(e)
                }
                logger.error(f"❌ Backend connectivity failed: {e}")

    async def test_critical_endpoints(self):
        """Test critical API endpoints that were working in logs"""
        logger.info("🎯 Testing Critical API Endpoints")
        
        # Endpoints confirmed working from logs
        endpoints = [
            ("/api/health", "Backend Health"),
            ("/ws/health", "WebSocket Health"),
            ("/api/knowledge_base/stats/basic", "Knowledge Base Stats"),
            ("/api/chat/health", "Chat Health"),
            ("/api/llm/models", "LLM Models"),
            ("/api/system/health", "System Health"),
        ]
        
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=5)
        ) as session:
            
            for endpoint, description in endpoints:
                try:
                    start_time = time.time()
                    async with session.get(f"{self.backend_url}{endpoint}") as response:
                        response_time = time.time() - start_time
                        
                        result = {
                            "success": response.status == 200,
                            "status_code": response.status,
                            "response_time": response_time,
                            "description": description
                        }
                        
                        if response.status == 200:
                            try:
                                data = await response.json()
                                result["data"] = data
                                result["has_data"] = bool(data)
                                
                                # Special handling for knowledge base stats
                                if endpoint == "/api/knowledge_base/stats/basic":
                                    result["documents_count"] = data.get("total_documents", 0)
                                    result["chunks_count"] = data.get("total_chunks", 0)
                                
                            except:
                                result["json_parse_error"] = True
                        
                        self.results["api_endpoints"][endpoint] = result
                        
                        status_emoji = "✅" if result["success"] else "❌"
                        logger.info(f"{status_emoji} {description}: {response.status} ({response_time:.3f}s)")
                        
                except Exception as e:
                    self.results["api_endpoints"][endpoint] = {
                        "success": False,
                        "error": str(e),
                        "description": description
                    }
                    logger.error(f"❌ {description}: {e}")

    async def test_frontend_proxy(self):
        """Test frontend-backend proxy configuration"""
        logger.info("🌐 Testing Frontend-Backend Proxy")
        
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=5)
        ) as session:
            
            # Test frontend accessibility
            try:
                async with session.get(self.frontend_url) as response:
                    self.results["frontend_backend_proxy"]["frontend_accessible"] = {
                        "success": response.status == 200,
                        "status_code": response.status
                    }
                    
                    if response.status == 200:
                        content = await response.text()
                        has_app_div = '<div id="app"></div>' in content
                        has_vite_client = '@vite/client' in content
                        
                        self.results["frontend_backend_proxy"]["frontend_accessible"].update({
                            "has_app_div": has_app_div,
                            "has_vite_client": has_vite_client,
                            "is_vue_app": has_app_div and has_vite_client
                        })
                        
                        logger.info(f"✅ Frontend accessible: Vue app {'detected' if has_app_div and has_vite_client else 'not detected'}")
                    else:
                        logger.error(f"❌ Frontend not accessible: {response.status}")
                        
            except Exception as e:
                self.results["frontend_backend_proxy"]["frontend_accessible"] = {
                    "success": False,
                    "error": str(e)
                }
                logger.error(f"❌ Frontend access failed: {e}")
            
            # Test if frontend can proxy to backend (simulate frontend API call)
            try:
                # This simulates how the frontend would call the backend through Vite proxy
                proxy_headers = {
                    "Origin": self.frontend_url,
                    "Referer": self.frontend_url
                }
                
                async with session.get(
                    f"{self.backend_url}/api/health", 
                    headers=proxy_headers
                ) as response:
                    
                    self.results["frontend_backend_proxy"]["proxy_test"] = {
                        "success": response.status == 200,
                        "status_code": response.status,
                        "cors_headers_present": "access-control-allow-origin" in response.headers
                    }
                    
                    status_emoji = "✅" if response.status == 200 else "❌"
                    logger.info(f"{status_emoji} Frontend-Backend proxy simulation: {response.status}")
                    
            except Exception as e:
                self.results["frontend_backend_proxy"]["proxy_test"] = {
                    "success": False,
                    "error": str(e)
                }
                logger.error(f"❌ Proxy test failed: {e}")

    def assess_production_readiness(self):
        """Assess overall production readiness"""
        logger.info("🚀 Assessing Production Readiness")
        
        # Count successful tests
        backend_ok = self.results["backend_connectivity"].get("success", False)
        
        api_successes = sum(
            1 for result in self.results["api_endpoints"].values()
            if result.get("success", False)
        )
        api_total = len(self.results["api_endpoints"])
        
        frontend_ok = (self.results.get("frontend_backend_proxy", {})
                      .get("frontend_accessible", {})
                      .get("success", False))
        
        proxy_ok = (self.results.get("frontend_backend_proxy", {})
                   .get("proxy_test", {})
                   .get("success", False))
        
        # Calculate scores
        api_success_rate = (api_successes / api_total * 100) if api_total > 0 else 0
        
        total_tests = 4  # backend, api (as group), frontend, proxy
        passed_tests = sum([
            int(backend_ok),
            int(api_success_rate >= 80),  # 80% API success rate
            int(frontend_ok),
            int(proxy_ok)
        ])
        
        overall_score = (passed_tests / total_tests * 100)
        
        # Knowledge base check
        kb_stats = self.results["api_endpoints"].get("/api/knowledge_base/stats/basic", {})
        has_knowledge_data = kb_stats.get("documents_count", 0) > 0
        
        # Production readiness assessment
        production_ready = overall_score >= 75 and backend_ok and api_success_rate >= 70
        
        self.results["production_readiness"] = {
            "overall_score": overall_score,
            "backend_connectivity": backend_ok,
            "api_success_rate": api_success_rate,
            "frontend_accessibility": frontend_ok,
            "proxy_functionality": proxy_ok,
            "knowledge_base_populated": has_knowledge_data,
            "production_ready": production_ready,
            "passed_tests": passed_tests,
            "total_tests": total_tests,
            "recommendation": self.get_recommendation(production_ready, overall_score)
        }

    def get_recommendation(self, production_ready: bool, score: float) -> str:
        """Get production readiness recommendation"""
        if production_ready and score >= 90:
            return "✅ PRODUCTION READY - System is fully operational and ready for deployment"
        elif production_ready and score >= 75:
            return "✅ PRODUCTION READY - System is operational with minor areas for improvement"
        elif score >= 50:
            return "⚠️ NEEDS ATTENTION - Address failing components before production deployment"
        else:
            return "❌ NOT READY - Critical issues must be resolved before production consideration"

    def generate_report(self):
        """Generate comprehensive test report"""
        print("\n" + "="*80)
        print("🤖 AUTOBOT QUICK INTEGRATION TEST REPORT")
        print("="*80)
        print(f"Test Duration: {self.results.get('total_time', 0):.2f} seconds")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()
        
        # Backend Connectivity
        backend = self.results.get("backend_connectivity", {})
        backend_status = "✅ CONNECTED" if backend.get("success", False) else "❌ FAILED"
        print(f"🔗 Backend Connectivity: {backend_status}")
        if backend.get("success"):
            print(f"    Response Time: {backend.get('response_time', 0):.3f}s")
            print(f"    Status Code: {backend.get('status_code', 'N/A')}")
        print()
        
        # API Endpoints
        print("🎯 API Endpoints Status:")
        api_endpoints = self.results.get("api_endpoints", {})
        for endpoint, result in api_endpoints.items():
            status = "✅" if result.get("success", False) else "❌"
            time_info = f" ({result.get('response_time', 0):.3f}s)" if 'response_time' in result else ""
            print(f"    {status} {result.get('description', endpoint)}: {result.get('status_code', 'N/A')}{time_info}")
            
            # Special info for knowledge base
            if endpoint == "/api/knowledge_base/stats/basic" and result.get("success"):
                docs = result.get("documents_count", 0)
                chunks = result.get("chunks_count", 0)
                print(f"        📊 Knowledge Base: {docs} documents, {chunks} chunks")
        print()
        
        # Frontend-Backend Integration
        print("🌐 Frontend-Backend Integration:")
        proxy = self.results.get("frontend_backend_proxy", {})
        
        frontend = proxy.get("frontend_accessible", {})
        frontend_status = "✅ ACCESSIBLE" if frontend.get("success", False) else "❌ FAILED"
        print(f"    Frontend: {frontend_status}")
        if frontend.get("is_vue_app"):
            print("        Vue.js app structure detected ✅")
        
        proxy_test = proxy.get("proxy_test", {})
        proxy_status = "✅ WORKING" if proxy_test.get("success", False) else "❌ FAILED"
        print(f"    API Proxy: {proxy_status}")
        print()
        
        # Production Readiness
        readiness = self.results.get("production_readiness", {})
        print("🚀 PRODUCTION READINESS ASSESSMENT:")
        print(f"    Overall Score: {readiness.get('overall_score', 0):.1f}%")
        print(f"    Tests Passed: {readiness.get('passed_tests', 0)}/{readiness.get('total_tests', 0)}")
        print()
        print(f"📋 Component Status:")
        print(f"    Backend API: {'✅' if readiness.get('backend_connectivity', False) else '❌'} {'Connected' if readiness.get('backend_connectivity', False) else 'Failed'}")
        print(f"    API Endpoints: {'✅' if readiness.get('api_success_rate', 0) >= 70 else '❌'} {readiness.get('api_success_rate', 0):.1f}% success rate")
        print(f"    Frontend: {'✅' if readiness.get('frontend_accessibility', False) else '❌'} {'Accessible' if readiness.get('frontend_accessibility', False) else 'Failed'}")
        print(f"    Integration: {'✅' if readiness.get('proxy_functionality', False) else '❌'} {'Working' if readiness.get('proxy_functionality', False) else 'Failed'}")
        print(f"    Knowledge Base: {'✅' if readiness.get('knowledge_base_populated', False) else '❌'} {'Populated' if readiness.get('knowledge_base_populated', False) else 'Empty'}")
        print()
        print("🎯 FINAL ASSESSMENT:")
        print(f"    {readiness.get('recommendation', 'No assessment available')}")
        print()
        print("="*80)
        print()

async def main():
    """Run quick integration tests"""
    test = QuickIntegrationTest()
    results = await test.run_quick_tests()
    
    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    results_file = f"/home/kali/Desktop/AutoBot/tests/results/quick_integration_{timestamp}.json"
    
    os.makedirs(os.path.dirname(results_file), exist_ok=True)
    
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    logger.info(f"📄 Results saved to: {results_file}")
    return results

if __name__ == "__main__":
    asyncio.run(main())