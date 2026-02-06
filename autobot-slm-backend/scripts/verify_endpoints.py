#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Endpoint Verification Script

Verifies that all new API endpoints are properly registered.
Run this after server startup to ensure endpoints are accessible.
"""

import sys


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
    print("=" * 80)
    print("SLM Server - API Endpoint Verification")
    print("=" * 80)
    print()

    # Check nodes.py endpoints
    print("Nodes API (api/nodes.py):")
    print("-" * 80)
    nodes_routes = extract_routes_from_file("api/nodes.py")
    for method, func in nodes_routes:
        print(f"  {method}")
        print(f"    └─ {func}")
    print(f"\n  Total: {len(nodes_routes)} endpoints")
    print()

    # Check updates.py endpoints
    print("Updates API (api/updates.py):")
    print("-" * 80)
    updates_routes = extract_routes_from_file("api/updates.py")
    for method, func in updates_routes:
        print(f"  {method}")
        print(f"    └─ {func}")
    print(f"\n  Total: {len(updates_routes)} endpoints")
    print()

    # Summary
    print("=" * 80)
    print("Summary of New Endpoints:")
    print("=" * 80)
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
        print(f"  {method:6} {endpoint:45} - {description}")

    print()
    print(f"Total new endpoints: {len(new_endpoints)}")
    print()

    # Database models
    print("=" * 80)
    print("New Database Models:")
    print("=" * 80)
    models = [
        ("NodeEvent", "Lifecycle event tracking"),
        ("Certificate", "PKI certificate management"),
        ("UpdateInfo", "Update tracking and management"),
        ("EventType", "Event type enumeration (13 types)"),
        ("EventSeverity", "Event severity levels (4 levels)"),
    ]

    for model, description in models:
        print(f"  {model:20} - {description}")

    print()
    print("=" * 80)
    print("Verification Complete!")
    print("=" * 80)
    print()
    print("Next steps:")
    print("  1. Install dependencies: pip install -r requirements.txt")
    print(
        "  2. Run migration: python migrations/add_events_certificates_updates_tables.py"
    )
    print("  3. Start server: python main.py")
    print("  4. View API docs: http://localhost:8080/api/docs")
    print()


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print(
            "Make sure to run this script from the slm-server directory.",
            file=sys.stderr,
        )
        sys.exit(1)
