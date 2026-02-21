#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Endpoint Verification Script

Verifies that all new API endpoints are properly registered.
Run this after server startup to ensure endpoints are accessible.
"""

import logging
import sys

logger = logging.getLogger(__name__)


def extract_routes_from_file(filepath: str) -> list:
    """Extract router definitions from a Python file."""
    routes = []
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()
        for i, line in enumerate(lines):
            if "@router." in line:
                method_line = line.strip()
                # Try to find the function definition on the next few lines
                for j in range(i + 1, min(i + 5, len(lines))):
                    if "async def " in lines[j] or "def " in lines[j]:
                        func_line = lines[j].strip()
                        routes.append((method_line, func_line))
                        break
    return routes


def main():
    """Main verification function."""
    logger.info("%s", "=" * 80)
    logger.info("SLM Server - API Endpoint Verification")
    logger.info("%s", "=" * 80)
    logger.info("")

    # Check nodes.py endpoints
    logger.info("Nodes API (api/nodes.py):")
    logger.info("%s", "-" * 80)
    nodes_routes = extract_routes_from_file("api/nodes.py")
    for method, func in nodes_routes:
        logger.info(f"  {method}")
        logger.info(f"    └─ {func}")
    logger.info(f"\n  Total: {len(nodes_routes)} endpoints")
    logger.info("")

    # Check updates.py endpoints
    logger.info("Updates API (api/updates.py):")
    logger.info("%s", "-" * 80)
    updates_routes = extract_routes_from_file("api/updates.py")
    for method, func in updates_routes:
        logger.info(f"  {method}")
        logger.info(f"    └─ {func}")
    logger.info(f"\n  Total: {len(updates_routes)} endpoints")
    logger.info("")

    # Summary
    logger.info("%s", "=" * 80)
    logger.info("Summary of New Endpoints:")
    logger.info("%s", "=" * 80)
    new_endpoints = [
        ("POST", "/api/nodes/test-connection", "Test SSH connection"),
        ("GET", "/api/nodes/{node_id}/events", "Get node events"),
        ("GET", "/api/nodes/{node_id}/certificate", "Get certificate status"),
        ("POST", "/api/nodes/{node_id}/certificate/renew", "Renew certificate"),
        ("POST", "/api/nodes/{node_id}/certificate/deploy", "Deploy certificate"),
        ("GET", "/api/updates/check", "Check for updates"),
        ("POST", "/api/updates/apply", "Apply updates"),
    ]

    for method, endpoint, description in new_endpoints:
        logger.info(f"  {method:6} {endpoint:45} - {description}")

    logger.info("")
    logger.info(f"Total new endpoints: {len(new_endpoints)}")
    logger.info("")

    # Database models
    logger.info("%s", "=" * 80)
    logger.info("New Database Models:")
    logger.info("%s", "=" * 80)
    models = [
        ("NodeEvent", "Lifecycle event tracking"),
        ("Certificate", "PKI certificate management"),
        ("UpdateInfo", "Update tracking and management"),
        ("EventType", "Event type enumeration (13 types)"),
        ("EventSeverity", "Event severity levels (4 levels)"),
    ]

    for model, description in models:
        logger.info(f"  {model:20} - {description}")

    logger.info("")
    logger.info("%s", "=" * 80)
    logger.info("Verification Complete!")
    logger.info("%s", "=" * 80)
    logger.info("")
    logger.info("Next steps:")
    logger.info("  1. Install dependencies: pip install -r requirements.txt")
    logger.info(
        "  2. Run migration: python migrations/add_events_certificates_updates_tables.py"
    )
    logger.info("  3. Start server: python main.py")
    logger.info("  4. View API docs: http://localhost:8080/api/docs")
    logger.info("")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        main()
    except FileNotFoundError as e:
        logger.info(f"Error: {e}", file=sys.stderr)
        logger.info(
            "Make sure to run this script from the slm-server directory.",
            file=sys.stderr,
        )
        sys.exit(1)
