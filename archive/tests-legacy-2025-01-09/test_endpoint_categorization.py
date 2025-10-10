#!/usr/bin/env python3
"""
Test Endpoint Categorization Logic
Week 3 Phase 2: Verify endpoint exemption and service-only path matching
"""

import sys
import os

# Add backend to path
sys.path.insert(0, '/home/kali/Desktop/AutoBot')

from backend.middleware.service_auth_enforcement import (
    is_path_exempt,
    requires_service_auth,
    EXEMPT_PATHS,
    SERVICE_ONLY_PATHS,
    get_endpoint_categories
)


def test_frontend_accessible_paths():
    """Test that frontend-accessible paths are correctly identified as exempt"""
    print("=" * 80)
    print("TEST 1: Frontend-Accessible Paths (Should be EXEMPT)")
    print("=" * 80)

    frontend_paths = [
        "/api/chat",
        "/api/chats/session-123",
        "/api/conversations/list",
        "/api/knowledge/search",
        "/api/knowledge_base/stats",
        "/api/terminal/create",
        "/api/agent_terminal/connect",
        "/api/settings/llm",
        "/api/frontend_config",
        "/api/system/health",
        "/api/monitoring/services/health",
        "/api/services/status",
        "/api/files/upload",
        "/api/llm/models",
        "/api/prompts/system",
        "/api/memory/graph",
        "/api/monitoring/metrics",
        "/api/metrics/performance",
        "/api/analytics/usage",
        "/ws",
        "/ws/terminal",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/api/developer/tools",
        "/api/validation_dashboard",
        "/api/rum/events",
        "/api/infrastructure/status",
        "/api/orchestration/workflows",
        "/api/workflow/execute",
        "/api/embeddings/generate",
        "/api/voice/synthesize",
        "/api/multimodal/analyze"
    ]

    passed = 0
    failed = 0

    for path in frontend_paths:
        is_exempt = is_path_exempt(path)
        requires_auth = requires_service_auth(path)

        if is_exempt and not requires_auth:
            print(f"✅ {path:50s} → EXEMPT (correct)")
            passed += 1
        else:
            print(f"❌ {path:50s} → NOT EXEMPT (WRONG!)")
            print(f"   is_exempt={is_exempt}, requires_auth={requires_auth}")
            failed += 1

    print(f"\nFrontend Paths: {passed} passed, {failed} failed")
    return failed == 0


def test_service_only_paths():
    """Test that service-only paths require authentication"""
    print("\n" + "=" * 80)
    print("TEST 2: Service-Only Paths (Should REQUIRE AUTH)")
    print("=" * 80)

    service_paths = [
        "/api/npu/results",
        "/api/npu/results/task-123",
        "/api/npu/heartbeat",
        "/api/npu/status",
        "/api/npu/internal/metrics",
        "/api/ai-stack/results",
        "/api/ai-stack/results/req-456",
        "/api/ai-stack/heartbeat",
        "/api/ai-stack/models",
        "/api/ai-stack/internal/health",
        "/api/browser/results",
        "/api/browser/results/task-789",
        "/api/browser/screenshots",
        "/api/browser/screenshots/upload",
        "/api/browser/logs",
        "/api/browser/heartbeat",
        "/api/browser/internal/status",
        "/api/internal/service-registry",
        "/api/registry/internal/services",
        "/api/audit/internal/logs"
    ]

    passed = 0
    failed = 0

    for path in service_paths:
        is_exempt = is_path_exempt(path)
        requires_auth = requires_service_auth(path)

        if requires_auth and not is_exempt:
            print(f"✅ {path:50s} → REQUIRES AUTH (correct)")
            passed += 1
        else:
            print(f"❌ {path:50s} → DOES NOT REQUIRE AUTH (WRONG!)")
            print(f"   is_exempt={is_exempt}, requires_auth={requires_auth}")
            failed += 1

    print(f"\nService-Only Paths: {passed} passed, {failed} failed")
    return failed == 0


def test_unlisted_paths():
    """Test behavior of paths not in either list (should default to allowed)"""
    print("\n" + "=" * 80)
    print("TEST 3: Unlisted Paths (Should default to ALLOWED - neither exempt nor required)")
    print("=" * 80)

    unlisted_paths = [
        "/api/unknown/endpoint",
        "/api/future/feature",
        "/api/custom/integration",
        "/health",
        "/status",
        "/api/v2/chat"
    ]

    passed = 0
    failed = 0

    for path in unlisted_paths:
        is_exempt = is_path_exempt(path)
        requires_auth = requires_service_auth(path)

        if not is_exempt and not requires_auth:
            print(f"✅ {path:50s} → DEFAULT ALLOW (correct)")
            passed += 1
        else:
            print(f"⚠️  {path:50s} → is_exempt={is_exempt}, requires_auth={requires_auth}")
            print(f"   (Unexpected categorization)")
            failed += 1

    print(f"\nUnlisted Paths: {passed} passed, {failed} failed")
    return failed == 0


def test_edge_cases():
    """Test edge cases and boundary conditions"""
    print("\n" + "=" * 80)
    print("TEST 4: Edge Cases and Boundary Conditions")
    print("=" * 80)

    test_cases = [
        # Path, Expected is_exempt, Expected requires_auth, Description
        ("/api/chat", True, False, "Exact match - chat"),
        ("/api/chat/", True, False, "Trailing slash - chat"),
        ("/api/npu/results", False, True, "Exact match - npu results"),
        ("/api/npu/results/", False, True, "Trailing slash - npu results"),
        ("/api", False, False, "Root API path"),
        ("/", False, False, "Root path"),
        ("", False, False, "Empty path"),
        ("/api/knowledge_base/search?query=test", True, False, "Query parameters"),
        ("/api/browser/results?format=json", False, True, "Service path with query"),
    ]

    passed = 0
    failed = 0

    for path, expected_exempt, expected_auth, description in test_cases:
        is_exempt = is_path_exempt(path)
        requires_auth = requires_service_auth(path)

        if is_exempt == expected_exempt and requires_auth == expected_auth:
            print(f"✅ {description:40s} → CORRECT")
            print(f"   Path: {path}")
            print(f"   is_exempt={is_exempt}, requires_auth={requires_auth}")
            passed += 1
        else:
            print(f"❌ {description:40s} → WRONG")
            print(f"   Path: {path}")
            print(f"   Expected: is_exempt={expected_exempt}, requires_auth={expected_auth}")
            print(f"   Actual:   is_exempt={is_exempt}, requires_auth={requires_auth}")
            failed += 1

    print(f"\nEdge Cases: {passed} passed, {failed} failed")
    return failed == 0


def test_summary():
    """Display endpoint categorization summary"""
    print("\n" + "=" * 80)
    print("ENDPOINT CATEGORIZATION SUMMARY")
    print("=" * 80)

    categories = get_endpoint_categories()

    print(f"\nEnforcement Mode: {categories['enforcement_mode']}")
    print(f"Total Exempt Paths: {categories['total_exempt']}")
    print(f"Total Service-Only Paths: {categories['total_service_only']}")

    print("\n--- Frontend-Accessible Paths (First 10) ---")
    for path in categories['exempt_paths'][:10]:
        print(f"  • {path}")
    if categories['total_exempt'] > 10:
        print(f"  ... and {categories['total_exempt'] - 10} more")

    print("\n--- Service-Only Paths ---")
    for path in categories['service_only_paths']:
        print(f"  • {path}")


def main():
    """Run all tests"""
    print("🧪 Testing Endpoint Categorization Logic")
    print("Week 3 Phase 2: Verify path matching before enforcement activation\n")

    # Run all tests
    test1_passed = test_frontend_accessible_paths()
    test2_passed = test_service_only_paths()
    test3_passed = test_unlisted_paths()
    test4_passed = test_edge_cases()

    # Display summary
    test_summary()

    # Overall result
    print("\n" + "=" * 80)
    print("OVERALL TEST RESULTS")
    print("=" * 80)

    all_passed = test1_passed and test2_passed and test3_passed and test4_passed

    if all_passed:
        print("✅ ALL TESTS PASSED")
        print("\nEndpoint categorization logic is working correctly.")
        print("Ready to proceed with Phase 3: Gradual Enforcement Rollout")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        print("\nEndpoint categorization has issues that must be fixed before enforcement.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
