"""
AutoBot Access Control Penetration Testing Suite
CVSS 9.1 Vulnerability Validation - Comprehensive Security Assessment

This test suite validates the access control implementation across AutoBot's
distributed 6-VM infrastructure. It tests both protected and unprotected
endpoints to identify authorization bypass vulnerabilities.

**CRITICAL FINDINGS FROM RESEARCH PHASE:**
1. Session ownership validator exists but NOT deployed to main chat endpoints
2. Only conversation_files endpoints are protected
3. Auth bypass mode allows complete security circumvention
4. Legacy session auto-migration creates hijacking vulnerability
5. Silent audit failures due to non-blocking async logging

Test Approach:
- Attack simulations against protected and unprotected endpoints
- Session hijacking and manipulation attempts
- Cross-user unauthorized access testing
- Distributed environment security validation
- Audit logging verification for all attacks
- Performance testing under attack scenarios

Author: Security Auditor Agent
Date: 2025-10-06
Task: Week 3, Task 3.5 - Penetration Testing
"""

import asyncio
import httpx
import pytest
import json
import uuid
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path

# Test configuration
BACKEND_URL = "http://172.16.168.20:8001"
REDIS_HOST = "172.16.168.23"
REDIS_PORT = 6379

# Test users and sessions
TEST_USER_ALICE = {"username": "alice", "user_id": "user_alice"}
TEST_USER_BOB = {"username": "bob", "user_id": "user_bob"}
TEST_USER_ATTACKER = {"username": "attacker", "user_id": "user_attacker"}


class PenetrationTestResults:
    """Track penetration test results and findings"""

    def __init__(self):
        self.total_tests = 0
        self.vulnerabilities_found = []
        self.bypasses_successful = []
        self.audit_failures = []
        self.false_positives = []
        self.performance_issues = []

    def add_vulnerability(self, test_name: str, severity: str, description: str, evidence: Dict):
        """Record a discovered vulnerability"""
        self.vulnerabilities_found.append({
            "test": test_name,
            "severity": severity,
            "description": description,
            "evidence": evidence,
            "timestamp": datetime.now().isoformat()
        })

    def add_bypass(self, test_name: str, endpoint: str, method: str, details: Dict):
        """Record a successful authorization bypass"""
        self.bypasses_successful.append({
            "test": test_name,
            "endpoint": endpoint,
            "method": method,
            "details": details,
            "timestamp": datetime.now().isoformat()
        })

    def add_audit_failure(self, test_name: str, reason: str, details: Dict):
        """Record an audit logging failure"""
        self.audit_failures.append({
            "test": test_name,
            "reason": reason,
            "details": details,
            "timestamp": datetime.now().isoformat()
        })

    def add_false_positive(self, test_name: str, description: str):
        """Record a false positive (legitimate user blocked)"""
        self.false_positives.append({
            "test": test_name,
            "description": description,
            "timestamp": datetime.now().isoformat()
        })

    def generate_report(self) -> Dict:
        """Generate comprehensive test report"""
        return {
            "summary": {
                "total_tests": self.total_tests,
                "vulnerabilities_count": len(self.vulnerabilities_found),
                "bypasses_count": len(self.bypasses_successful),
                "audit_failures_count": len(self.audit_failures),
                "false_positives_count": len(self.false_positives),
                "performance_issues_count": len(self.performance_issues)
            },
            "vulnerabilities": self.vulnerabilities_found,
            "bypasses": self.bypasses_successful,
            "audit_failures": self.audit_failures,
            "false_positives": self.false_positives,
            "performance_issues": self.performance_issues,
            "test_timestamp": datetime.now().isoformat()
        }


@pytest.fixture(scope="session")
def test_results():
    """Global test results tracker"""
    return PenetrationTestResults()


@pytest.fixture
async def http_client():
    """Async HTTP client for API testing"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        yield client


@pytest.fixture
async def setup_test_sessions(http_client):
    """Create test chat sessions for Alice and Bob"""
    alice_session_id = str(uuid.uuid4())
    bob_session_id = str(uuid.uuid4())

    # Create Alice's session
    alice_response = await http_client.post(
        f"{BACKEND_URL}/api/chat/sessions",
        json={
            "session_id": alice_session_id,
            "title": "Alice's Private Session",
            "context": "Private conversation for Alice"
        },
        headers={"X-Username": TEST_USER_ALICE["username"]}
    )

    # Create Bob's session
    bob_response = await http_client.post(
        f"{BACKEND_URL}/api/chat/sessions",
        json={
            "session_id": bob_session_id,
            "title": "Bob's Private Session",
            "context": "Private conversation for Bob"
        },
        headers={"X-Username": TEST_USER_BOB["username"]}
    )

    return {
        "alice": {
            "session_id": alice_session_id,
            "username": TEST_USER_ALICE["username"],
            "response": alice_response
        },
        "bob": {
            "session_id": bob_session_id,
            "username": TEST_USER_BOB["username"],
            "response": bob_response
        }
    }


# ============================================================================
# CRITICAL TEST 1: Unauthorized Conversation Access (CVSS 9.1)
# ============================================================================

@pytest.mark.asyncio
async def test_unauthorized_session_access(http_client, setup_test_sessions, test_results):
    """
    **CRITICAL VULNERABILITY TEST**

    Attempt: Attacker tries to access Alice's private chat session
    Expected: 403 Forbidden + audit log entry
    Reality: Will likely succeed due to missing endpoint protection

    This is the PRIMARY CVSS 9.1 vulnerability being tested.
    """
    test_results.total_tests += 1
    sessions = await setup_test_sessions
    alice_session_id = sessions["alice"]["session_id"]

    # Attacker attempts to access Alice's session
    response = await http_client.get(
        f"{BACKEND_URL}/api/chat/sessions/{alice_session_id}",
        headers={"X-Username": TEST_USER_ATTACKER["username"]}
    )

    # Analyze result
    if response.status_code == 200:
        # VULNERABILITY: Unauthorized access succeeded
        test_results.add_vulnerability(
            test_name="unauthorized_session_access",
            severity="CRITICAL",
            description="Attacker successfully accessed another user's chat session without authorization",
            evidence={
                "endpoint": f"/api/chat/sessions/{alice_session_id}",
                "attacker": TEST_USER_ATTACKER["username"],
                "victim": TEST_USER_ALICE["username"],
                "response_code": 200,
                "response_data": response.json() if response.status_code == 200 else None
            }
        )
        test_results.add_bypass(
            test_name="unauthorized_session_access",
            endpoint=f"/api/chat/sessions/{alice_session_id}",
            method="GET",
            details={
                "vulnerability": "Missing session ownership validation on GET /api/chat/sessions/{session_id}",
                "impact": "Complete access to private conversations across all users"
            }
        )
        pytest.fail("CRITICAL: Unauthorized session access succeeded - CVSS 9.1 vulnerability CONFIRMED")

    elif response.status_code == 403:
        # Expected behavior - access denied
        print("✅ Unauthorized access properly blocked (403 Forbidden)")

    elif response.status_code == 401:
        # Authentication required
        print("✅ Authentication required (401 Unauthorized)")

    else:
        # Unexpected response
        test_results.add_vulnerability(
            test_name="unauthorized_session_access",
            severity="HIGH",
            description=f"Unexpected response code: {response.status_code}",
            evidence={"response_code": response.status_code, "response": response.text}
        )


@pytest.mark.asyncio
async def test_unauthorized_session_deletion(http_client, setup_test_sessions, test_results):
    """
    **CRITICAL VULNERABILITY TEST**

    Attempt: Attacker tries to delete Bob's chat session
    Expected: 403 Forbidden + audit log entry
    Reality: Will likely succeed due to missing endpoint protection
    """
    test_results.total_tests += 1
    sessions = await setup_test_sessions
    bob_session_id = sessions["bob"]["session_id"]

    # Attacker attempts to delete Bob's session
    response = await http_client.delete(
        f"{BACKEND_URL}/api/chat/sessions/{bob_session_id}",
        headers={"X-Username": TEST_USER_ATTACKER["username"]}
    )

    if response.status_code in [200, 204]:
        # VULNERABILITY: Unauthorized deletion succeeded
        test_results.add_vulnerability(
            test_name="unauthorized_session_deletion",
            severity="CRITICAL",
            description="Attacker successfully deleted another user's chat session without authorization",
            evidence={
                "endpoint": f"/api/chat/sessions/{bob_session_id}",
                "attacker": TEST_USER_ATTACKER["username"],
                "victim": TEST_USER_BOB["username"],
                "response_code": response.status_code
            }
        )
        test_results.add_bypass(
            test_name="unauthorized_session_deletion",
            endpoint=f"/api/chat/sessions/{bob_session_id}",
            method="DELETE",
            details={
                "vulnerability": "Missing session ownership validation on DELETE /api/chat/sessions/{session_id}",
                "impact": "Attackers can delete any user's conversation history"
            }
        )
        pytest.fail("CRITICAL: Unauthorized session deletion succeeded - CVSS 9.1 vulnerability CONFIRMED")

    elif response.status_code == 403:
        print("✅ Unauthorized deletion properly blocked (403 Forbidden)")

    elif response.status_code == 401:
        print("✅ Authentication required (401 Unauthorized)")


@pytest.mark.asyncio
async def test_unauthorized_session_export(http_client, setup_test_sessions, test_results):
    """
    Attempt: Attacker tries to export Alice's conversation data
    Expected: 403 Forbidden
    Impact: Data exfiltration if successful
    """
    test_results.total_tests += 1
    sessions = await setup_test_sessions
    alice_session_id = sessions["alice"]["session_id"]

    # Attacker attempts to export Alice's session
    response = await http_client.get(
        f"{BACKEND_URL}/api/chat/sessions/{alice_session_id}/export",
        headers={"X-Username": TEST_USER_ATTACKER["username"]},
        params={"format": "json"}
    )

    if response.status_code == 200:
        test_results.add_vulnerability(
            test_name="unauthorized_session_export",
            severity="CRITICAL",
            description="Attacker successfully exported another user's conversation data",
            evidence={
                "endpoint": f"/api/chat/sessions/{alice_session_id}/export",
                "attacker": TEST_USER_ATTACKER["username"],
                "victim": TEST_USER_ALICE["username"],
                "data_size_bytes": len(response.content)
            }
        )
        pytest.fail("CRITICAL: Unauthorized data export succeeded")

    elif response.status_code in [401, 403]:
        print("✅ Unauthorized export properly blocked")


# ============================================================================
# TEST 2: Session Token Manipulation
# ============================================================================

@pytest.mark.asyncio
async def test_session_id_tampering(http_client, setup_test_sessions, test_results):
    """
    Attempt: Modify session ID to access other conversations
    Expected: Validation failure
    """
    test_results.total_tests += 1
    sessions = await setup_test_sessions
    alice_session_id = sessions["alice"]["session_id"]

    # Try various session ID manipulations
    manipulations = [
        alice_session_id[:-4] + "0000",  # Change last 4 chars
        alice_session_id.upper(),  # Case manipulation
        alice_session_id.replace("-", ""),  # Remove hyphens
        "../../" + alice_session_id,  # Path traversal
        alice_session_id + "' OR '1'='1",  # SQL injection attempt
    ]

    for manipulated_id in manipulations:
        response = await http_client.get(
            f"{BACKEND_URL}/api/chat/sessions/{manipulated_id}",
            headers={"X-Username": TEST_USER_ATTACKER["username"]}
        )

        if response.status_code == 200:
            test_results.add_vulnerability(
                test_name="session_id_tampering",
                severity="HIGH",
                description=f"Session ID manipulation succeeded: {manipulated_id}",
                evidence={"original": alice_session_id, "manipulated": manipulated_id}
            )


@pytest.mark.asyncio
async def test_missing_authentication(http_client, setup_test_sessions, test_results):
    """
    Attempt: Access protected endpoints without authentication headers
    Expected: 401 Unauthorized
    """
    test_results.total_tests += 1
    sessions = await setup_test_sessions
    alice_session_id = sessions["alice"]["session_id"]

    # Try to access without any authentication
    response = await http_client.get(
        f"{BACKEND_URL}/api/chat/sessions/{alice_session_id}"
        # No headers provided
    )

    if response.status_code == 200:
        test_results.add_vulnerability(
            test_name="missing_authentication",
            severity="CRITICAL",
            description="Endpoint accessible without any authentication",
            evidence={"endpoint": f"/api/chat/sessions/{alice_session_id}", "response_code": 200}
        )
        pytest.fail("CRITICAL: No authentication required for sensitive endpoint")

    elif response.status_code == 401:
        print("✅ Authentication properly required")


# ============================================================================
# TEST 3: Legacy Session Auto-Migration Vulnerability
# ============================================================================

@pytest.mark.asyncio
async def test_orphaned_session_hijacking(http_client, test_results):
    """
    **VULNERABILITY: Legacy Session Auto-Migration**

    Test the auto-migration feature that assigns orphaned sessions
    to the requesting user. This could enable session hijacking.

    Scenario:
    1. Create a session without owner assignment
    2. Attacker requests the orphaned session
    3. System auto-assigns it to attacker (vulnerability)
    """
    test_results.total_tests += 1

    # Create an orphaned session (session exists but no owner in Redis)
    orphaned_session_id = str(uuid.uuid4())

    # Note: This test requires direct Redis manipulation to create orphaned state
    # In production, this scenario could occur from:
    # - Redis key expiration while session data persists
    # - Database inconsistencies
    # - Legacy sessions from before ownership tracking

    # Attacker attempts to access the orphaned session
    response = await http_client.get(
        f"{BACKEND_URL}/api/chat/sessions/{orphaned_session_id}",
        headers={"X-Username": TEST_USER_ATTACKER["username"]}
    )

    # If the session is auto-assigned to the attacker, this is a vulnerability
    # Check if session now belongs to attacker via subsequent requests

    print("⚠️  Legacy session migration vulnerability requires manual validation")
    print("    See session_ownership.py lines 126-134 for auto-assignment logic")


# ============================================================================
# TEST 4: Cross-VM Unauthorized Access
# ============================================================================

@pytest.mark.asyncio
async def test_cross_vm_session_access(http_client, setup_test_sessions, test_results):
    """
    Test distributed environment security across 6 VMs

    Scenario: Session created on Frontend VM, accessed from different VMs
    Expected: Consistent authorization enforcement across all VMs
    """
    test_results.total_tests += 1
    sessions = await setup_test_sessions
    alice_session_id = sessions["alice"]["session_id"]

    # Test from different VM IPs (simulated via headers)
    vm_sources = [
        "172.16.168.21",  # Frontend VM
        "172.16.168.22",  # NPU Worker VM
        "172.16.168.24",  # AI Stack VM
        "172.16.168.25",  # Browser VM
    ]

    for vm_ip in vm_sources:
        response = await http_client.get(
            f"{BACKEND_URL}/api/chat/sessions/{alice_session_id}",
            headers={
                "X-Username": TEST_USER_ATTACKER["username"],
                "X-Forwarded-For": vm_ip
            }
        )

        if response.status_code == 200:
            test_results.add_vulnerability(
                test_name="cross_vm_unauthorized_access",
                severity="CRITICAL",
                description=f"Unauthorized access from VM {vm_ip}",
                evidence={"vm_source": vm_ip, "session_id": alice_session_id}
            )


# ============================================================================
# TEST 5: Audit Logging Verification
# ============================================================================

@pytest.mark.asyncio
async def test_audit_logging_coverage(http_client, setup_test_sessions, test_results):
    """
    Verify that all unauthorized access attempts are logged

    This test validates:
    1. Unauthorized attempts create audit log entries
    2. Audit logs contain required OWASP fields
    3. Logs are searchable and retrievable
    4. Redis failures trigger file-based fallback
    """
    test_results.total_tests += 1
    sessions = await setup_test_sessions
    alice_session_id = sessions["alice"]["session_id"]

    # Make unauthorized access attempt
    attack_timestamp = datetime.now()
    response = await http_client.get(
        f"{BACKEND_URL}/api/chat/sessions/{alice_session_id}",
        headers={"X-Username": TEST_USER_ATTACKER["username"]}
    )

    # Wait for audit logging (async batch processing)
    await asyncio.sleep(2)

    # Query audit logs for this event
    audit_response = await http_client.get(
        f"{BACKEND_URL}/api/audit/logs",
        params={
            "operation": "conversation.access",
            "user_id": TEST_USER_ATTACKER["username"],
            "result": "denied",
            "start_time": (attack_timestamp - timedelta(minutes=1)).isoformat(),
            "end_time": (attack_timestamp + timedelta(minutes=1)).isoformat()
        }
    )

    if audit_response.status_code == 200:
        audit_logs = audit_response.json()

        if not audit_logs or len(audit_logs) == 0:
            test_results.add_audit_failure(
                test_name="audit_logging_coverage",
                reason="Unauthorized access not logged",
                details={
                    "attack_timestamp": attack_timestamp.isoformat(),
                    "session_id": alice_session_id,
                    "attacker": TEST_USER_ATTACKER["username"]
                }
            )
            print("❌ AUDIT FAILURE: Unauthorized access not logged")
        else:
            print(f"✅ Audit log captured: {len(audit_logs)} entries")

            # Validate log structure
            for log_entry in audit_logs:
                required_fields = ["timestamp", "operation", "result", "user_id", "ip_address"]
                missing_fields = [f for f in required_fields if f not in log_entry]

                if missing_fields:
                    test_results.add_audit_failure(
                        test_name="audit_logging_coverage",
                        reason="Missing required OWASP fields",
                        details={"missing_fields": missing_fields, "log_entry": log_entry}
                    )
    else:
        test_results.add_audit_failure(
            test_name="audit_logging_coverage",
            reason=f"Audit query failed with status {audit_response.status_code}",
            details={"response": audit_response.text}
        )


@pytest.mark.asyncio
async def test_audit_log_tampering_resistance(http_client, test_results):
    """
    Test if audit logs can be modified or deleted
    Expected: Append-only, tamper-resistant storage
    """
    test_results.total_tests += 1

    # Attempt to delete audit logs via API (if endpoint exists)
    response = await http_client.delete(f"{BACKEND_URL}/api/audit/logs")

    if response.status_code in [200, 204]:
        test_results.add_vulnerability(
            test_name="audit_log_tampering",
            severity="CRITICAL",
            description="Audit logs can be deleted via API",
            evidence={"endpoint": "/api/audit/logs", "method": "DELETE"}
        )
        pytest.fail("CRITICAL: Audit logs are not tamper-resistant")

    # Attempt to modify audit logs
    response = await http_client.put(
        f"{BACKEND_URL}/api/audit/logs/some-id",
        json={"result": "success"}  # Try to change denied to success
    )

    if response.status_code in [200, 204]:
        test_results.add_vulnerability(
            test_name="audit_log_tampering",
            severity="CRITICAL",
            description="Audit logs can be modified via API",
            evidence={"endpoint": "/api/audit/logs/some-id", "method": "PUT"}
        )


# ============================================================================
# TEST 6: Race Conditions and Concurrent Access
# ============================================================================

@pytest.mark.asyncio
async def test_concurrent_ownership_change(http_client, setup_test_sessions, test_results):
    """
    Test race conditions during ownership validation

    Scenario:
    1. Alice owns session
    2. Concurrent requests: Alice accesses + Ownership changes + Bob accesses
    3. Validate atomic ownership checks prevent race condition bypass
    """
    test_results.total_tests += 1
    sessions = await setup_test_sessions
    alice_session_id = sessions["alice"]["session_id"]

    async def alice_access():
        return await http_client.get(
            f"{BACKEND_URL}/api/chat/sessions/{alice_session_id}",
            headers={"X-Username": TEST_USER_ALICE["username"]}
        )

    async def bob_access():
        return await http_client.get(
            f"{BACKEND_URL}/api/chat/sessions/{alice_session_id}",
            headers={"X-Username": TEST_USER_BOB["username"]}
        )

    # Execute concurrent requests
    results = await asyncio.gather(
        alice_access(),
        bob_access(),
        alice_access(),
        bob_access(),
        return_exceptions=True
    )

    # Analyze race condition results
    bob_successful_accesses = sum(1 for r in results if hasattr(r, 'status_code') and r.status_code == 200 and "bob" in str(r))

    if bob_successful_accesses > 0:
        test_results.add_vulnerability(
            test_name="race_condition_ownership",
            severity="HIGH",
            description="Race condition allowed unauthorized access during concurrent requests",
            evidence={"bob_successful_accesses": bob_successful_accesses}
        )


# ============================================================================
# TEST 7: Session ID Enumeration and Brute Force
# ============================================================================

@pytest.mark.asyncio
async def test_session_id_enumeration(http_client, test_results):
    """
    Test if session IDs can be enumerated/brute-forced
    Expected: Rate limiting or timing-safe comparisons
    """
    test_results.total_tests += 1

    # Generate random session IDs and try to access them
    attempted_ids = [str(uuid.uuid4()) for _ in range(100)]

    start_time = datetime.now()
    valid_sessions_found = 0

    for session_id in attempted_ids:
        response = await http_client.get(
            f"{BACKEND_URL}/api/chat/sessions/{session_id}",
            headers={"X-Username": TEST_USER_ATTACKER["username"]}
        )

        if response.status_code == 200:
            valid_sessions_found += 1

        # Check for rate limiting
        if response.status_code == 429:
            print("✅ Rate limiting active")
            return

    elapsed_time = (datetime.now() - start_time).total_seconds()

    if valid_sessions_found > 0:
        test_results.add_vulnerability(
            test_name="session_enumeration",
            severity="MEDIUM",
            description=f"Found {valid_sessions_found} valid sessions via enumeration",
            evidence={
                "attempts": 100,
                "found": valid_sessions_found,
                "elapsed_seconds": elapsed_time
            }
        )

    if elapsed_time < 5:  # 100 requests in < 5 seconds
        test_results.add_vulnerability(
            test_name="missing_rate_limiting",
            severity="MEDIUM",
            description="No rate limiting detected on session access",
            evidence={"requests": 100, "elapsed_seconds": elapsed_time}
        )


# ============================================================================
# TEST 8: Performance Under Attack
# ============================================================================

@pytest.mark.asyncio
async def test_dos_via_ownership_validation(http_client, setup_test_sessions, test_results):
    """
    Test if excessive validation requests cause DoS
    Expected: <10ms per validation, no resource exhaustion
    """
    test_results.total_tests += 1
    sessions = await setup_test_sessions
    alice_session_id = sessions["alice"]["session_id"]

    # Rapid-fire validation requests
    num_requests = 1000
    start_time = datetime.now()

    tasks = [
        http_client.get(
            f"{BACKEND_URL}/api/chat/sessions/{alice_session_id}",
            headers={"X-Username": TEST_USER_ATTACKER["username"]}
        )
        for _ in range(num_requests)
    ]

    responses = await asyncio.gather(*tasks, return_exceptions=True)
    elapsed_time = (datetime.now() - start_time).total_seconds()

    avg_time_per_request = (elapsed_time / num_requests) * 1000  # ms

    if avg_time_per_request > 10:
        test_results.performance_issues.append({
            "test": "dos_via_ownership_validation",
            "avg_response_time_ms": avg_time_per_request,
            "target_ms": 10,
            "requests": num_requests,
            "total_time_seconds": elapsed_time
        })
        print(f"⚠️  Performance degradation: {avg_time_per_request:.2f}ms per request (target: <10ms)")
    else:
        print(f"✅ Performance acceptable: {avg_time_per_request:.2f}ms per request")


# ============================================================================
# TEST 9: Auth Bypass Mode Validation
# ============================================================================

@pytest.mark.asyncio
async def test_auth_disabled_mode(http_client, test_results):
    """
    **VULNERABILITY: Development Auth Bypass Mode**

    Test if auth_disabled=True or enable_auth=False allows
    complete security bypass.

    This is a CRITICAL issue if enabled in production.
    """
    test_results.total_tests += 1

    # Check current auth status
    response = await http_client.get(f"{BACKEND_URL}/api/security/status")

    if response.status_code == 200:
        status = response.json()

        if not status.get("security_enabled", True):
            test_results.add_vulnerability(
                test_name="auth_disabled_mode",
                severity="CRITICAL",
                description="Authentication is DISABLED - complete security bypass active",
                evidence={"security_status": status}
            )
            pytest.fail("CRITICAL: Authentication disabled in current deployment")
        else:
            print("✅ Authentication is enabled")


# ============================================================================
# TEST 10: File Operations Protection (Should be Protected)
# ============================================================================

@pytest.mark.asyncio
async def test_file_operations_protected(http_client, setup_test_sessions, test_results):
    """
    Verify that conversation file operations ARE protected
    (These should have session ownership validation)

    This is a POSITIVE test - we expect these to be blocked.
    """
    test_results.total_tests += 1
    sessions = await setup_test_sessions
    alice_session_id = sessions["alice"]["session_id"]

    # Attempt unauthorized file listing
    response = await http_client.get(
        f"{BACKEND_URL}/api/conversation-files/{alice_session_id}/files",
        headers={"X-Username": TEST_USER_ATTACKER["username"]}
    )

    if response.status_code == 200:
        test_results.add_vulnerability(
            test_name="file_operations_unprotected",
            severity="CRITICAL",
            description="File operations accessible without authorization (expected to be protected)",
            evidence={"endpoint": f"/api/conversation-files/{alice_session_id}/files"}
        )
        pytest.fail("File operations should be protected but are not")

    elif response.status_code in [401, 403]:
        print("✅ File operations properly protected (403 Forbidden)")
        # This is EXPECTED and CORRECT behavior

    else:
        print(f"⚠️  Unexpected response: {response.status_code}")


# ============================================================================
# Test Reporting and Summary
# ============================================================================

@pytest.mark.asyncio
async def test_generate_security_report(test_results):
    """
    Generate comprehensive security penetration test report
    """
    report = test_results.generate_report()

    # Save report to file
    report_path = Path("/home/kali/Desktop/AutoBot/reports/security/PENETRATION_TEST_RESULTS.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with open(report_path, 'w') as f:
        json.dump(report, indent=2, fp=f)

    # Print summary
    print("\n" + "="*80)
    print("SECURITY PENETRATION TEST SUMMARY")
    print("="*80)
    print(f"Total Tests: {report['summary']['total_tests']}")
    print(f"Vulnerabilities Found: {report['summary']['vulnerabilities_count']}")
    print(f"Authorization Bypasses: {report['summary']['bypasses_count']}")
    print(f"Audit Failures: {report['summary']['audit_failures_count']}")
    print(f"False Positives: {report['summary']['false_positives_count']}")
    print(f"Performance Issues: {report['summary']['performance_issues_count']}")
    print("="*80)

    if report['summary']['vulnerabilities_count'] > 0:
        print("\n⚠️  VULNERABILITIES DISCOVERED:")
        for vuln in report['vulnerabilities']:
            print(f"  [{vuln['severity']}] {vuln['test']}: {vuln['description']}")

    if report['summary']['bypasses_count'] > 0:
        print("\n❌ AUTHORIZATION BYPASSES:")
        for bypass in report['bypasses']:
            print(f"  {bypass['endpoint']} ({bypass['method']}): {bypass['details']['vulnerability']}")

    if report['summary']['audit_failures_count'] > 0:
        print("\n🚨 AUDIT LOGGING FAILURES:")
        for failure in report['audit_failures']:
            print(f"  {failure['test']}: {failure['reason']}")

    print(f"\nFull report saved to: {report_path}")

    # FAIL the test suite if critical vulnerabilities found
    if report['summary']['vulnerabilities_count'] > 0:
        critical_vulns = [v for v in report['vulnerabilities'] if v['severity'] == 'CRITICAL']
        if critical_vulns:
            pytest.fail(f"CRITICAL VULNERABILITIES FOUND: {len(critical_vulns)} issues require immediate remediation")


if __name__ == "__main__":
    # Run penetration tests
    pytest.main([__file__, "-v", "-s", "--tb=short"])
