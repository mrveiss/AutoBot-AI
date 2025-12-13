#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Native VM Deployment Validation Script

Tests connectivity and health of all services across 6 machines:
- 5 Hyper-V VMs (172.16.168.21-25)
- 1 WSL machine (172.16.168.20) running backend + terminal + noVNC
All services run natively (no Docker containers).
"""

import asyncio
import aiohttp
import redis
import sys
import json
import time
import os
from typing import Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class ServiceStatus(Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNREACHABLE = "unreachable"


@dataclass
class ServiceCheck:
    name: str
    host: str
    port: int
    check_type: str
    endpoint: Optional[str] = None
    expected_response: Optional[str] = None
    timeout: int = 10


class DeploymentValidator:
    def __init__(self):
        """Initialize deployment validator with service definitions."""
        self.services = [
            ServiceCheck("WSL Backend", "172.16.168.20", 8001, "http", "/api/health", None, 10),
            ServiceCheck("WSL Terminal", "172.16.168.20", 7681, "http", "/", None, 10),
            ServiceCheck("WSL noVNC", "172.16.168.20", 6080, "http", "/", None, 10),
            ServiceCheck("Frontend", "172.16.168.21", 80, "http", "/", None, 10),
            ServiceCheck("NPU Worker", "172.16.168.22", 8081, "http", "/health", None, 15),
            ServiceCheck("Redis Stack", "172.16.168.23", 6379, "redis", None, "PONG", 5),
            ServiceCheck("RedisInsight", "172.16.168.23", 8002, "http", "/", None, 10),
            ServiceCheck("AI Stack", "172.16.168.24", 8080, "http", "/health", None, 15),
            ServiceCheck("Ollama", "172.16.168.24", 11434, "http", "/api/tags", None, 20),
            ServiceCheck("Browser Service", "172.16.168.25", 3000, "http", "/health", None, 10),
        ]
        self.results: Dict[str, Dict] = {}

    async def check_http_service(self, service: ServiceCheck) -> Tuple[ServiceStatus, str]:
        """Check HTTP-based service health"""
        url = f"http://{service.host}:{service.port}{service.endpoint or ''}"

        try:
            timeout = aiohttp.ClientTimeout(total=service.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        text = await response.text()
                        return ServiceStatus.HEALTHY, f"HTTP {response.status} - {text[:100]}"
                    else:
                        return ServiceStatus.UNHEALTHY, f"HTTP {response.status}"
        except aiohttp.ClientError as e:
            return ServiceStatus.UNREACHABLE, f"Connection failed: {str(e)}"
        except asyncio.TimeoutError:
            return ServiceStatus.UNREACHABLE, f"Timeout after {service.timeout}s"
        except Exception as e:
            return ServiceStatus.UNREACHABLE, f"Unexpected error: {str(e)}"

    def check_redis_service(self, service: ServiceCheck) -> Tuple[ServiceStatus, str]:
        """Check Redis service health"""
        try:
            r = redis.Redis(
                host=service.host,
                port=service.port,
                password=os.environ.get('REDIS_PASSWORD', os.environ.get('AUTOBOT_REDIS_PASSWORD', '')),
                socket_timeout=service.timeout,
                decode_responses=True
            )

            response = r.ping()
            if response:
                info = r.info('server')
                version = info.get('redis_version', 'unknown')
                return ServiceStatus.HEALTHY, f"Redis {version} - PONG received"
            else:
                return ServiceStatus.UNHEALTHY, "No PONG response"

        except redis.ConnectionError as e:
            return ServiceStatus.UNREACHABLE, f"Redis connection failed: {str(e)}"
        except redis.TimeoutError:
            return ServiceStatus.UNREACHABLE, f"Redis timeout after {service.timeout}s"
        except Exception as e:
            return ServiceStatus.UNREACHABLE, f"Redis error: {str(e)}"

    async def check_service(self, service: ServiceCheck) -> Dict:
        """Check individual service health"""
        print(f"🔍 Checking {service.name} at {service.host}:{service.port}...")

        start_time = time.time()

        if service.check_type == "http":
            status, message = await self.check_http_service(service)
        elif service.check_type == "redis":
            status, message = self.check_redis_service(service)
        else:
            status, message = ServiceStatus.UNREACHABLE, "Unknown check type"

        response_time = (time.time() - start_time) * 1000  # milliseconds

        result = {
            "name": service.name,
            "host": service.host,
            "port": service.port,
            "status": status.value,
            "message": message,
            "response_time_ms": round(response_time, 2),
            "timestamp": time.time()
        }

        # Print result with color coding
        if status == ServiceStatus.HEALTHY:
            print(f"✅ {service.name}: {message} ({response_time:.0f}ms)")
        elif status == ServiceStatus.UNHEALTHY:
            print(f"⚠️  {service.name}: {message} ({response_time:.0f}ms)")
        else:
            print(f"❌ {service.name}: {message} ({response_time:.0f}ms)")

        return result

    async def validate_deployment(self) -> Dict:
        """Validate entire native deployment"""
        print("🚀 AutoBot Native VM Deployment Validation")
        print("=" * 50)

        # Check all services concurrently
        tasks = [self.check_service(service) for service in self.services]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        healthy_count = 0
        unhealthy_count = 0
        unreachable_count = 0

        for result in results:
            if isinstance(result, Exception):
                print(f"❌ Service check failed: {result}")
                continue

            self.results[result["name"]] = result

            if result["status"] == "healthy":
                healthy_count += 1
            elif result["status"] == "unhealthy":
                unhealthy_count += 1
            else:
                unreachable_count += 1

        # Summary
        total_services = len(self.services)
        print("\n" + "=" * 50)
        print("📊 VALIDATION SUMMARY")
        print("=" * 50)
        print(f"✅ Healthy Services:     {healthy_count}/{total_services}")
        print(f"⚠️  Unhealthy Services:   {unhealthy_count}/{total_services}")
        print(f"❌ Unreachable Services: {unreachable_count}/{total_services}")

        # Overall status
        if healthy_count == total_services:
            print("\n🎉 SUCCESS: All services are healthy!")
            overall_status = "success"
        elif healthy_count >= total_services * 0.8:  # 80% healthy
            print("\n⚠️  WARNING: Some services need attention")
            overall_status = "warning"
        else:
            print("\n❌ FAILURE: Multiple services are down")
            overall_status = "failure"

        return {
            "overall_status": overall_status,
            "healthy_count": healthy_count,
            "unhealthy_count": unhealthy_count,
            "unreachable_count": unreachable_count,
            "total_services": total_services,
            "results": self.results,
            "validation_timestamp": time.time()
        }

    async def test_backend_vm_connectivity(self) -> Dict:
        """Test backend's ability to connect to VM services"""
        print("\n🔗 Testing Backend → VM Service Connectivity")
        print("=" * 50)

        connectivity_tests = []

        # Test Redis connection from backend perspective
        try:
            r = redis.Redis(host='172.16.168.23', port=6379, password=os.environ.get('REDIS_PASSWORD', os.environ.get('AUTOBOT_REDIS_PASSWORD', '')), decode_responses=True)
            r.ping()
            connectivity_tests.append({"test": "Backend → Redis", "status": "success", "message": "Connection successful"})
            print("✅ Backend → Redis: Connection successful")
        except Exception as e:
            connectivity_tests.append({"test": "Backend → Redis", "status": "failure", "message": str(e)})
            print(f"❌ Backend → Redis: {str(e)}")

        # Test HTTP services from backend perspective
        http_services = [
            ("AI Stack", "172.16.168.24", 8080, "/health"),
            ("NPU Worker", "172.16.168.24", 8081, "/health"),
            ("Ollama", "172.16.168.24", 11434, "/api/tags"),
            ("Browser Service", "172.16.168.25", 3000, "/health")
        ]

        for service_name, host, port, endpoint in http_services:
            try:
                url = f"http://{host}:{port}{endpoint}"
                timeout = aiohttp.ClientTimeout(total=10)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url) as response:
                        if response.status == 200:
                            connectivity_tests.append({
                                "test": f"Backend → {service_name}",
                                "status": "success",
                                "message": f"HTTP {response.status}"
                            })
                            print(f"✅ Backend → {service_name}: HTTP {response.status}")
                        else:
                            connectivity_tests.append({
                                "test": f"Backend → {service_name}",
                                "status": "failure",
                                "message": f"HTTP {response.status}"
                            })
                            print(f"❌ Backend → {service_name}: HTTP {response.status}")
            except Exception as e:
                connectivity_tests.append({
                    "test": f"Backend → {service_name}",
                    "status": "failure",
                    "message": str(e)
                })
                print(f"❌ Backend → {service_name}: {str(e)}")

        return {"connectivity_tests": connectivity_tests}

    def save_results(self, results: Dict, filename: str = None):
        """Save validation results to JSON file"""
        if filename is None:
            filename = f"/tmp/autobot-validation-{int(time.time())}.json"

        with open(filename, 'w') as f:
            json.dump(results, f, indent=2, default=str)

        print(f"\n📁 Results saved to: {filename}")


async def main():
    """Entry point for native VM deployment validation."""
    validator = DeploymentValidator()

    # Run validation
    validation_results = await validator.validate_deployment()
    connectivity_results = await validator.test_backend_vm_connectivity()

    # Combine results
    full_results = {
        **validation_results,
        **connectivity_results
    }

    # Save results
    validator.save_results(full_results)

    # Exit with appropriate code
    if validation_results["overall_status"] == "success":
        print("\n🎉 Native deployment validation PASSED!")
        sys.exit(0)
    elif validation_results["overall_status"] == "warning":
        print("\n⚠️  Native deployment validation completed with WARNINGS!")
        sys.exit(1)
    else:
        print("\n❌ Native deployment validation FAILED!")
        sys.exit(2)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Validation interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Validation failed with error: {e}")
        sys.exit(1)
