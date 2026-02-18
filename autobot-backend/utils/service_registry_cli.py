#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Service Registry CLI Tool
=========================

Command-line interface for debugging and managing the AutoBot service registry.
Useful for troubleshooting service discovery issues and validating deployments.

Usage:
    python -m src.utils.service_registry_cli status
    python -m src.utils.service_registry_cli health
    python -m src.utils.service_registry_cli url redis
    python -m src.utils.service_registry_cli test-all
"""

import argparse
import asyncio
import json
import sys
import time

from .service_registry import ServiceStatus, get_service_registry, get_service_url


def print_header(title: str):
    """Print a formatted header"""
    print(f"\n{'=' * len(title)}")
    print(title)
    print("=" * len(title))


def print_status(status: str, message: str):
    """Print a status message with emoji"""
    status_emojis = {"success": "✅", "error": "❌", "warning": "⚠️", "info": "ℹ️"}
    emoji = status_emojis.get(status, "•")
    print(f"{emoji} {message}")


def cmd_status(args):
    """Show service registry status"""
    print_header("AutoBot Service Registry Status")

    try:
        registry = get_service_registry(args.config)
        info = registry.get_deployment_info()

        print_status("success", "Registry initialized successfully")
        print(f"   Mode: {info['deployment_mode']}")
        print(f"   Domain: {info['domain']}")
        print(f"   Services: {info['services_count']}")

        print_header("Service URLs")
        for service, details in info["services"].items():
            print_status("info", f"{service:15} → {details['url']}")

    except Exception as e:
        print_status("error", f"Failed to get registry status: {e}")
        return 1

    return 0


async def cmd_health(args):
    """Check health of all services"""
    print_header("Service Health Check")

    try:
        registry = get_service_registry(args.config)
        health_results = await registry.check_all_services_health()

        healthy_count = 0
        total_count = len(health_results)

        for service, health in health_results.items():
            if health.status == ServiceStatus.HEALTHY:
                print_status("success", f"{service:15} → {health.status.value}")
                if hasattr(health, "response_time") and health.response_time > 0:
                    print(f"{'':18}Response time: {health.response_time:.3f}s")
                healthy_count += 1
            elif health.status == ServiceStatus.CIRCUIT_OPEN:
                print_status("error", f"{service:15} → Circuit breaker OPEN")
            else:
                print_status("error", f"{service:15} → {health.status.value}")

        print_header("Health Summary")
        print_status("info", f"Services healthy: {healthy_count}/{total_count}")

        if healthy_count == total_count:
            print_status("success", "All services are healthy!")
            return 0
        else:
            print_status(
                "warning", f"{total_count - healthy_count} services have issues"
            )
            return 1

    except Exception as e:
        print_status("error", f"Health check failed: {e}")
        return 1


def cmd_url(args):
    """Get URL for a specific service"""
    print_header(f"Service URL: {args.service}")

    try:
        url = get_service_url(args.service, args.path)
        print_status("success", f"URL: {url}")
        return 0
    except Exception as e:
        print_status("error", f"Failed to resolve URL: {e}")
        return 1


def cmd_config(args):
    """Show service configuration"""
    print_header(f"Service Configuration: {args.service}")

    try:
        registry = get_service_registry(args.config)
        config = registry.get_service_config(args.service)

        if config:
            print_status("success", "Configuration found")
            print(f"   Name: {config.name}")
            print(f"   Host: {config.host}")
            print(f"   Port: {config.port}")
            print(f"   Scheme: {config.scheme}")
            print(f"   Health Endpoint: {config.health_endpoint}")
            print(f"   Timeout: {config.timeout}s")
            print(f"   Circuit Breaker Threshold: {config.circuit_breaker_threshold}")
        else:
            print_status("error", "Service not found")
            return 1

    except Exception as e:
        print_status("error", f"Failed to get configuration: {e}")
        return 1

    return 0


async def cmd_test_service(args):
    """Test connectivity to a specific service"""
    print_header(f"Testing Service: {args.service}")

    try:
        registry = get_service_registry(args.config)

        # Get service URL
        url = get_service_url(args.service)
        print_status("info", f"Testing URL: {url}")

        # Check health
        health = await registry.check_service_health(args.service)

        if health.status == ServiceStatus.HEALTHY:
            print_status("success", "Service is healthy")
            if hasattr(health, "response_time") and health.response_time > 0:
                print(f"   Response time: {health.response_time:.3f}s")
        else:
            print_status("error", f"Service is {health.status.value}")

        return 0 if health.status == ServiceStatus.HEALTHY else 1

    except Exception as e:
        print_status("error", f"Test failed: {e}")
        return 1


async def _test_services(registry, services: list) -> dict:
    """Test each service and collect results.

    Args:
        registry: Service registry instance.
        services: List of service names to test.

    Returns:
        Dictionary mapping service names to test results.

    Issue #620.
    """
    results = {}
    for service in services:
        print(f"🔄 Testing {service}...")
        try:
            health = await registry.check_service_health(service)
            results[service] = {
                "status": health.status.value,
                "response_time": getattr(health, "response_time", 0),
                "url": get_service_url(service),
            }
        except Exception as e:
            results[service] = {"status": "error", "error": str(e), "url": "unknown"}
    return results


def _display_test_results(results: dict) -> tuple:
    """Display test results and categorize services.

    Args:
        results: Dictionary of test results by service.

    Returns:
        Tuple of (healthy_services, unhealthy_services) lists.

    Issue #620.
    """
    print_header("Test Results")
    healthy_services = []
    unhealthy_services = []

    for service, result in results.items():
        if result["status"] == "healthy":
            print_status("success", f"{service:15} → {result['url']}")
            if result.get("response_time", 0) > 0:
                print(f"{'':18}Response: {result['response_time']:.3f}s")
            healthy_services.append(service)
        else:
            print_status("error", f"{service:15} → {result['status']}")
            if "error" in result:
                print(f"{'':18}Error: {result['error']}")
            unhealthy_services.append(service)

    return healthy_services, unhealthy_services


def _print_test_summary(services: list, healthy: list, unhealthy: list) -> None:
    """Print test summary statistics.

    Args:
        services: All services tested.
        healthy: List of healthy service names.
        unhealthy: List of unhealthy service names.

    Issue #620.
    """
    print_header("Summary")
    print_status("info", f"Total services: {len(services)}")
    print_status("success", f"Healthy: {len(healthy)}")
    if unhealthy:
        print_status("error", f"Unhealthy: {len(unhealthy)}")
        print(f"   Issues: {', '.join(unhealthy)}")


async def cmd_test_all(args):
    """Test all services and generate report."""
    print_header("Testing All Services")

    try:
        registry = get_service_registry(args.config)
        services = registry.list_services()

        results = await _test_services(registry, services)
        healthy, unhealthy = _display_test_results(results)
        _print_test_summary(services, healthy, unhealthy)

        if args.json:
            json_output = {
                "timestamp": time.time(),
                "deployment_mode": registry.deployment_mode.value,
                "results": results,
            }
            print_header("JSON Output")
            print(json.dumps(json_output, indent=2))

        return 0 if len(unhealthy) == 0 else 1

    except Exception as e:
        print_status("error", f"Test failed: {e}")
        return 1


def cmd_deploy_info(args):
    """Show deployment information"""
    print_header("Deployment Information")

    try:
        registry = get_service_registry(args.config)
        info = registry.get_deployment_info()

        print_status("success", "Deployment information:")
        print(f"   Mode: {info['deployment_mode']}")
        print(f"   Domain: {info['domain']}")
        print(f"   Services: {info['services_count']}")

        if args.verbose:
            print_header("Detailed Service Information")
            for service, details in info["services"].items():
                print(f"📦 {service}")
                print(f"   URL: {details['url']}")
                print(f"   Health: {details['health']}")

        return 0

    except Exception as e:
        print_status("error", f"Failed to get deployment info: {e}")
        return 1


def _create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser with all subcommands.

    Returns:
        Configured ArgumentParser instance.

    Issue #620.
    """
    parser = argparse.ArgumentParser(
        description="AutoBot Service Registry CLI Tool",
        epilog="Use this tool to debug service discovery issues and validate deployments.",
    )

    parser.add_argument("--config", "-c", help="Configuration file path", default=None)
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Simple commands (no arguments needed)
    subparsers.add_parser("status", help="Show registry status")
    subparsers.add_parser("health", help="Check service health")
    subparsers.add_parser("deploy", help="Show deployment info")

    # URL command
    url_parser = subparsers.add_parser("url", help="Get service URL")
    url_parser.add_argument("service", help="Service name")
    url_parser.add_argument("--path", help="URL path", default="")

    # Config command
    config_parser = subparsers.add_parser("config", help="Show service configuration")
    config_parser.add_argument("service", help="Service name")

    # Test service command
    test_parser = subparsers.add_parser("test", help="Test specific service")
    test_parser.add_argument("service", help="Service name")

    # Test all command
    test_all_parser = subparsers.add_parser("test-all", help="Test all services")
    test_all_parser.add_argument("--json", action="store_true", help="JSON output")

    return parser


def _dispatch_command(args: argparse.Namespace) -> int:
    """Dispatch command to appropriate handler.

    Args:
        args: Parsed command-line arguments.

    Returns:
        Exit code (0 for success, 1 for failure).

    Issue #620.
    """
    # Command dispatch table (Issue #315 - reduced nesting)
    sync_commands = {
        "status": cmd_status,
        "url": cmd_url,
        "config": cmd_config,
        "deploy": cmd_deploy_info,
    }
    async_commands = {
        "health": cmd_health,
        "test": cmd_test_service,
        "test-all": cmd_test_all,
    }

    if args.command in sync_commands:
        return sync_commands[args.command](args)
    elif args.command in async_commands:
        return asyncio.run(async_commands[args.command](args))
    else:
        print_status("error", f"Unknown command: {args.command}")
        return 1


def main():
    """Main CLI entry point."""
    parser = _create_argument_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    try:
        return _dispatch_command(args)
    except KeyboardInterrupt:
        print_status("warning", "Operation cancelled by user")
        return 1
    except Exception as e:
        print_status("error", f"Unexpected error: {e}")
        import traceback

        if args.verbose:
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
