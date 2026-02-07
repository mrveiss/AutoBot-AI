#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Backend Status Checker - Quick diagnostic tool to verify backend API availability
"""

import json
import sys
import time
from urllib.parse import urljoin

import requests
from src.constants import ServiceURLs


class BackendStatusChecker:
    def __init__(self, base_url=ServiceURLs.BACKEND_LOCAL):
        self.base_url = base_url
        self.timeout = 5

    def check_endpoint(self, endpoint, method="GET", data=None):
        """Check a specific endpoint"""
        url = urljoin(self.base_url, endpoint)

        try:
            start_time = time.time()

            if method.upper() == "GET":
                response = requests.get(url, timeout=self.timeout)
            elif method.upper() == "POST":
                response = requests.post(url, json=data, timeout=self.timeout)
            else:
                return {"error": f"Unsupported method: {method}"}

            response_time = round((time.time() - start_time) * 1000, 2)

            return {
                "endpoint": endpoint,
                "url": url,
                "status_code": response.status_code,
                "success": response.ok,
                "response_time_ms": response_time,
                "content_length": len(response.content),
                "content_type": response.headers.get("content-type", ""),
                "error": None,
            }

        except requests.exceptions.ConnectionError:
            return {
                "endpoint": endpoint,
                "url": url,
                "error": "Connection refused - backend may not be running",
                "success": False,
            }
        except requests.exceptions.Timeout:
            return {
                "endpoint": endpoint,
                "url": url,
                "error": f"Request timeout after {self.timeout}s",
                "success": False,
            }
        except Exception as e:
            return {"endpoint": endpoint, "url": url, "error": str(e), "success": False}

    def run_comprehensive_check(self):
        """Run comprehensive backend status check"""
        print(f"🔍 Checking backend status at {self.base_url}")
        print("=" * 60)

        # Define critical endpoints to test
        critical_endpoints = [
            "/api/hello",
            "/api/system/health",
            "/api/chats",
            "/api/settings/",
            "/api/prompts/",
            "/api/knowledge_base/search",
            "/api/llm/models",
            "/api/files/list",
        ]

        results = []
        successful = 0
        failed = 0

        for endpoint in critical_endpoints:
            print(f"Testing {endpoint}...", end=" ")
            result = self.check_endpoint(endpoint)
            results.append(result)

            if result["success"]:
                print(
                    f"✅ {result['status_code']} ({result.get('response_time_ms', 'N/A')}ms)"
                )
                successful += 1
            else:
                print(f"❌ {result['error']}")
                failed += 1

        print("\n" + "=" * 60)
        print(f"📊 Results: {successful} successful, {failed} failed")

        # Overall assessment
        if successful == len(critical_endpoints):
            print("🟢 Backend Status: HEALTHY")
            status = "healthy"
        elif successful >= len(critical_endpoints) * 0.7:
            print("🟡 Backend Status: DEGRADED")
            status = "degraded"
        else:
            print("🔴 Backend Status: UNHEALTHY")
            status = "unhealthy"

        # Generate recommendations
        print("\n📋 Recommendations:")
        if failed > 0:
            if any(
                result.get("error", "").startswith("Connection refused")
                for result in results
            ):
                print("  • Start the backend server: ./run_agent.sh")

            timeout_failures = [
                r for r in results if "timeout" in r.get("error", "").lower()
            ]
            if timeout_failures:
                print(
                    f"  • {len(timeout_failures)} endpoints timing out - check server performance"
                )

            not_found_failures = [r for r in results if r.get("status_code") == 404]
            if not_found_failures:
                print(
                    f"  • {len(not_found_failures)} endpoints not found - verify API routes"
                )

        if successful > 0:
            print("  • Some endpoints working - partial functionality available")

        return {
            "status": status,
            "successful": successful,
            "failed": failed,
            "total": len(critical_endpoints),
            "results": results,
        }

    def quick_health_check(self):
        """Quick health check - just test if backend is running"""
        print("⚡ Quick health check...", end=" ")

        # Try the simplest endpoint first
        result = self.check_endpoint("/api/hello")
        if result["success"]:
            print(f"✅ Backend is running ({result.get('response_time_ms', 'N/A')}ms)")
            return True

        # Try health endpoint as fallback
        result = self.check_endpoint("/api/system/health")
        if result["success"]:
            print(f"✅ Backend is running ({result.get('response_time_ms', 'N/A')}ms)")
            return True

        print(f"❌ Backend not responding: {result['error']}")
        return False


def main():
    """Main function for command line usage"""
    import argparse

    from src.constants import ServiceURLs

    parser = argparse.ArgumentParser(description="Check AutoBot backend API status")
    parser.add_argument(
        "--url",
        default=ServiceURLs.BACKEND_LOCAL,
        help="Backend base URL (default: ServiceURLs.BACKEND_LOCAL)",
    )
    parser.add_argument(
        "--quick", action="store_true", help="Run quick health check only"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output results in JSON format"
    )

    args = parser.parse_args()

    checker = BackendStatusChecker(args.url)

    if args.quick:
        result = checker.quick_health_check()
        if args.json:
            print(json.dumps({"healthy": result}))
        sys.exit(0 if result else 1)
    else:
        results = checker.run_comprehensive_check()
        if args.json:
            print(json.dumps(results, indent=2))
        sys.exit(0 if results["status"] != "unhealthy" else 1)


if __name__ == "__main__":
    main()
