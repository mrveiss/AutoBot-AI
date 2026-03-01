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
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, Tuple

import aiohttp
import redis

logger = logging.getLogger(__name__)


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


def _build_service_definitions():
    """Build the list of services to validate (#1228)."""
    return [
        ServiceCheck("WSL Backend", "172.16.168.20", 8001, "http", "/api/health"),
        ServiceCheck("WSL Terminal", "172.16.168.20", 7681, "http", "/"),
        ServiceCheck("WSL noVNC", "172.16.168.20", 6080, "http", "/"),
        ServiceCheck("Frontend", "172.16.168.21", 80, "http", "/"),
        ServiceCheck("NPU Worker", "172.16.168.22", 8081, "http", "/health", None, 15),
        ServiceCheck("Redis Stack", "172.16.168.23", 6379, "redis", None, "PONG", 5),
        ServiceCheck("RedisInsight", "172.16.168.23", 8002, "http", "/"),
        ServiceCheck("AI Stack", "172.16.168.24", 8080, "http", "/health", None, 15),
        # Issue #1214: Ollama runs on .20 (autobot-llm-gpu), not .24
        ServiceCheck("Ollama", "172.16.168.20", 11434, "http", "/api/tags", None, 20),
        ServiceCheck("Browser Service", "172.16.168.25", 3000, "http", "/health"),
    ]


class DeploymentValidator:
    def __init__(self):
        """Initialize deployment validator with service definitions."""
        self.services = _build_service_definitions()
        self.results: Dict[str, Dict] = {}

    async def check_http_service(
        self, service: ServiceCheck
    ) -> Tuple[ServiceStatus, str]:
        """Check HTTP-based service health."""
        url = f"http://{service.host}:{service.port}{service.endpoint or ''}"

        try:
            timeout = aiohttp.ClientTimeout(total=service.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        text = await response.text()
                        return (
                            ServiceStatus.HEALTHY,
                            f"HTTP {response.status} - {text[:100]}",
                        )
                    else:
                        return ServiceStatus.UNHEALTHY, f"HTTP {response.status}"
        except aiohttp.ClientError as e:
            return ServiceStatus.UNREACHABLE, f"Connection failed: {str(e)}"
        except asyncio.TimeoutError:
            return ServiceStatus.UNREACHABLE, f"Timeout after {service.timeout}s"
        except Exception as e:
            return ServiceStatus.UNREACHABLE, f"Unexpected error: {str(e)}"

    def check_redis_service(self, service: ServiceCheck) -> Tuple[ServiceStatus, str]:
        """Check Redis service health."""
        try:
            r = redis.Redis(
                host=service.host,
                port=service.port,
                password=os.environ.get(
                    "REDIS_PASSWORD",
                    os.environ.get("AUTOBOT_REDIS_PASSWORD", ""),
                ),
                socket_timeout=service.timeout,
                decode_responses=True,
            )

            response = r.ping()
            if response:
                info = r.info("server")
                version = info.get("redis_version", "unknown")
                return ServiceStatus.HEALTHY, f"Redis {version} - PONG received"
            else:
                return ServiceStatus.UNHEALTHY, "No PONG response"

        except redis.ConnectionError as e:
            return ServiceStatus.UNREACHABLE, f"Redis connection failed: {str(e)}"
        except redis.TimeoutError:
            return (
                ServiceStatus.UNREACHABLE,
                f"Redis timeout after {service.timeout}s",
            )
        except Exception as e:
            return ServiceStatus.UNREACHABLE, f"Redis error: {str(e)}"

    async def check_service(self, service: ServiceCheck) -> Dict:
        """Check individual service health."""
        logger.info("Checking %s at %s:%d...", service.name, service.host, service.port)

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
            "timestamp": time.time(),
        }

        _log_service_result(service.name, status, message, response_time)

        return result

    async def validate_deployment(self) -> Dict:
        """Validate entire native deployment."""
        logger.info("AutoBot Native VM Deployment Validation")

        # Check all services concurrently
        tasks = [self.check_service(service) for service in self.services]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        healthy, unhealthy, unreachable = self._tally_results(results)
        total = len(self.services)

        _log_summary(healthy, unhealthy, unreachable, total)
        overall_status = _determine_overall_status(healthy, total)

        return {
            "overall_status": overall_status,
            "healthy_count": healthy,
            "unhealthy_count": unhealthy,
            "unreachable_count": unreachable,
            "total_services": total,
            "results": self.results,
            "validation_timestamp": time.time(),
        }

    def _tally_results(self, results) -> Tuple[int, int, int]:
        """Count healthy/unhealthy/unreachable from gathered results."""
        healthy = unhealthy = unreachable = 0
        for result in results:
            if isinstance(result, Exception):
                logger.error("Service check failed: %s", result)
                continue
            self.results[result["name"]] = result
            if result["status"] == "healthy":
                healthy += 1
            elif result["status"] == "unhealthy":
                unhealthy += 1
            else:
                unreachable += 1
        return healthy, unhealthy, unreachable

    async def test_backend_vm_connectivity(self) -> Dict:
        """Test backend's ability to connect to VM services."""
        logger.info("Testing Backend -> VM Service Connectivity")

        connectivity_tests = []

        redis_result = _test_redis_connectivity()
        connectivity_tests.append(redis_result)

        http_services = [
            ("AI Stack", "172.16.168.24", 8080, "/health"),
            ("NPU Worker", "172.16.168.22", 8081, "/health"),
            # Issue #1214: Ollama on .20 (autobot-llm-gpu)
            ("Ollama", "172.16.168.20", 11434, "/api/tags"),
            ("Browser Service", "172.16.168.25", 3000, "/health"),
        ]

        for name, host, port, endpoint in http_services:
            result = await _test_http_connectivity(name, host, port, endpoint)
            connectivity_tests.append(result)

        return {"connectivity_tests": connectivity_tests}

    def save_results(self, results: Dict, filename: str = None):
        """Save validation results to JSON file."""
        if filename is None:
            filename = f"/tmp/autobot-validation-{int(time.time())}.json"

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)

        logger.info("Results saved to: %s", filename)


def _log_service_result(
    name: str, status: ServiceStatus, message: str, response_time: float
):
    """Log a single service check result at appropriate level."""
    time_str = f"({response_time:.0f}ms)"
    if status == ServiceStatus.HEALTHY:
        logger.info("%s: %s %s", name, message, time_str)
    elif status == ServiceStatus.UNHEALTHY:
        logger.warning("%s: %s %s", name, message, time_str)
    else:
        logger.error("%s: %s %s", name, message, time_str)


def _log_summary(healthy: int, unhealthy: int, unreachable: int, total: int):
    """Log the validation summary counts."""
    logger.info("VALIDATION SUMMARY")
    logger.info("Healthy Services:     %d/%d", healthy, total)
    if unhealthy:
        logger.warning("Unhealthy Services:   %d/%d", unhealthy, total)
    if unreachable:
        logger.error("Unreachable Services: %d/%d", unreachable, total)


def _determine_overall_status(healthy: int, total: int) -> str:
    """Determine overall deployment status from health counts."""
    if healthy == total:
        logger.info("All services are healthy!")
        return "success"
    elif healthy >= total * 0.8:
        logger.warning("Some services need attention")
        return "warning"
    else:
        logger.error("Multiple services are down")
        return "failure"


def _test_redis_connectivity() -> Dict:
    """Test Redis connection from backend perspective (#1228)."""
    try:
        r = redis.Redis(
            host="172.16.168.23",
            port=6379,
            password=os.environ.get(
                "REDIS_PASSWORD",
                os.environ.get("AUTOBOT_REDIS_PASSWORD", ""),
            ),
            decode_responses=True,
        )
        r.ping()
        logger.info("Backend -> Redis: Connection successful")
        return {
            "test": "Backend -> Redis",
            "status": "success",
            "message": "Connection successful",
        }
    except Exception as e:
        logger.error("Backend -> Redis: %s", e)
        return {
            "test": "Backend -> Redis",
            "status": "failure",
            "message": str(e),
        }


async def _test_http_connectivity(
    name: str, host: str, port: int, endpoint: str
) -> Dict:
    """Test HTTP service connectivity from backend perspective (#1228)."""
    try:
        url = f"http://{host}:{port}{endpoint}"
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    logger.info("Backend -> %s: HTTP %d", name, response.status)
                    return {
                        "test": f"Backend -> {name}",
                        "status": "success",
                        "message": f"HTTP {response.status}",
                    }
                else:
                    logger.error("Backend -> %s: HTTP %d", name, response.status)
                    return {
                        "test": f"Backend -> {name}",
                        "status": "failure",
                        "message": f"HTTP {response.status}",
                    }
    except Exception as e:
        logger.error("Backend -> %s: %s", name, e)
        return {
            "test": f"Backend -> {name}",
            "status": "failure",
            "message": str(e),
        }


async def main():
    """Entry point for native VM deployment validation."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    validator = DeploymentValidator()

    # Run validation
    validation_results = await validator.validate_deployment()
    connectivity_results = await validator.test_backend_vm_connectivity()

    # Combine results
    full_results = {**validation_results, **connectivity_results}

    # Save results
    validator.save_results(full_results)

    # Exit with appropriate code
    if validation_results["overall_status"] == "success":
        logger.info("Native deployment validation PASSED!")
        sys.exit(0)
    elif validation_results["overall_status"] == "warning":
        logger.warning("Native deployment validation completed with WARNINGS!")
        sys.exit(1)
    else:
        logger.error("Native deployment validation FAILED!")
        sys.exit(2)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.warning("Validation interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error("Validation failed with error: %s", e)
        sys.exit(1)
