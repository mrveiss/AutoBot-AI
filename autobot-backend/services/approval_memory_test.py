# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for ApprovalMemoryManager - Redis-backed per-project approval memory."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from services.approval_memory import (
    ApprovalMemoryManager,
    ApprovalRecord,
    get_approval_memory,
)

# =============================================================================
# ApprovalRecord Tests
# =============================================================================


class TestApprovalRecord:
    """Tests for ApprovalRecord dataclass."""

    def test_to_dict(self):
        """Convert record to dictionary."""
        record = ApprovalRecord(
            pattern="npm install *",
            tool="Bash",
            risk_level="moderate",
            user_id="user123",
            created_at=1000.0,
            original_command="npm install lodash",
            comment="Trusted package",
        )
        d = record.to_dict()
        assert d["pattern"] == "npm install *"
        assert d["tool"] == "Bash"
        assert d["risk_level"] == "moderate"
        assert d["comment"] == "Trusted package"

    def test_from_dict(self):
        """Create record from dictionary."""
        data = {
            "pattern": "git commit *",
            "tool": "Bash",
            "risk_level": "moderate",
            "user_id": "user456",
            "created_at": 2000.0,
            "original_command": "git commit -m 'test'",
            "comment": None,
        }
        record = ApprovalRecord.from_dict(data)
        assert record.pattern == "git commit *"
        assert record.user_id == "user456"
        assert record.comment is None

    def test_from_dict_defaults(self):
        """from_dict fills defaults for missing fields."""
        record = ApprovalRecord.from_dict({})
        assert record.pattern == ""
        assert record.tool == "Bash"
        assert record.risk_level == "moderate"
        assert record.user_id == ""

    def test_roundtrip(self):
        """to_dict -> from_dict roundtrip preserves data."""
        original = ApprovalRecord(
            pattern="pip install *",
            tool="Bash",
            risk_level="safe",
            user_id="admin",
            created_at=3000.0,
            original_command="pip install requests",
        )
        restored = ApprovalRecord.from_dict(original.to_dict())
        assert restored.pattern == original.pattern
        assert restored.tool == original.tool
        assert restored.risk_level == original.risk_level
        assert restored.user_id == original.user_id


# =============================================================================
# Pattern Extraction Tests
# =============================================================================


class TestExtractPattern:
    """Tests for ApprovalMemoryManager._extract_pattern()."""

    @pytest.fixture
    def manager(self):
        """Create manager with memory disabled (no Redis needed)."""
        with patch("services.approval_memory.config") as mock_config:
            mock_config.permission.approval_memory_ttl = 2592000
            mock_config.permission.approval_memory_enabled = False
            return ApprovalMemoryManager(enabled=False)

    def test_single_word_command(self, manager):
        """Single-word command is exact match."""
        assert manager._extract_pattern("pwd") == "pwd"

    def test_simple_command_with_args(self, manager):
        """Simple command with args becomes 'cmd *'."""
        assert manager._extract_pattern("ls -la") == "ls *"

    def test_git_subcommand_preserved(self, manager):
        """Git subcommand is preserved in pattern."""
        assert manager._extract_pattern("git commit -m 'test'") == "git commit *"
        assert manager._extract_pattern("git push origin main") == "git push *"

    def test_npm_subcommand_preserved(self, manager):
        """NPM subcommand is preserved in pattern."""
        assert manager._extract_pattern("npm install lodash") == "npm install *"
        assert manager._extract_pattern("npm run build") == "npm run *"

    def test_docker_subcommand_preserved(self, manager):
        """Docker subcommand is preserved in pattern."""
        assert manager._extract_pattern("docker build .") == "docker build *"
        assert manager._extract_pattern("docker run -it ubuntu") == "docker run *"

    def test_pip_subcommand_preserved(self, manager):
        """pip subcommand is preserved in pattern."""
        assert manager._extract_pattern("pip install requests") == "pip install *"

    def test_kubectl_subcommand_preserved(self, manager):
        """kubectl subcommand is preserved in pattern."""
        assert manager._extract_pattern("kubectl get pods") == "kubectl get *"

    def test_yarn_subcommand_preserved(self, manager):
        """yarn subcommand is preserved in pattern."""
        assert manager._extract_pattern("yarn add react") == "yarn add *"

    def test_non_subcommand_tool(self, manager):
        """Non-subcommand tool only preserves base command."""
        assert manager._extract_pattern("curl https://example.com") == "curl *"
        assert manager._extract_pattern("cat /etc/hosts") == "cat *"

    def test_empty_command(self, manager):
        """Empty command returns itself."""
        assert manager._extract_pattern("") == ""


# =============================================================================
# Project Hash Tests
# =============================================================================


class TestProjectHash:
    """Tests for project path hashing."""

    @pytest.fixture
    def manager(self):
        """Create manager with memory disabled."""
        with patch("services.approval_memory.config") as mock_config:
            mock_config.permission.approval_memory_ttl = 2592000
            mock_config.permission.approval_memory_enabled = False
            return ApprovalMemoryManager(enabled=False)

    def test_hash_deterministic(self, manager):
        """Same path produces same hash."""
        h1 = manager._get_project_hash("/home/user/project")
        h2 = manager._get_project_hash("/home/user/project")
        assert h1 == h2

    def test_hash_strips_trailing_slash(self, manager):
        """Trailing slash doesn't affect hash."""
        h1 = manager._get_project_hash("/home/user/project")
        h2 = manager._get_project_hash("/home/user/project/")
        assert h1 == h2

    def test_hash_case_insensitive(self, manager):
        """Path hashing is case-insensitive."""
        h1 = manager._get_project_hash("/Home/User/Project")
        h2 = manager._get_project_hash("/home/user/project")
        assert h1 == h2

    def test_different_paths_different_hashes(self, manager):
        """Different paths produce different hashes."""
        h1 = manager._get_project_hash("/home/user/project-a")
        h2 = manager._get_project_hash("/home/user/project-b")
        assert h1 != h2

    def test_hash_length(self, manager):
        """Hash is truncated to 16 characters."""
        h = manager._get_project_hash("/home/user/project")
        assert len(h) == 16


# =============================================================================
# Redis Key Tests
# =============================================================================


class TestRedisKey:
    """Tests for Redis key generation."""

    @pytest.fixture
    def manager(self):
        """Create manager with memory disabled."""
        with patch("services.approval_memory.config") as mock_config:
            mock_config.permission.approval_memory_ttl = 2592000
            mock_config.permission.approval_memory_enabled = False
            return ApprovalMemoryManager(enabled=False)

    def test_key_format(self, manager):
        """Key follows prefix:hash:user format."""
        key = manager._get_redis_key("/home/user/project", "user123")
        parts = key.split(":")
        assert parts[0] == "autobot"
        assert parts[1] == "approval_memory"
        assert len(parts[2]) == 16  # project hash
        assert parts[3] == "user123"


# =============================================================================
# Remember Approval Tests (async, mocked Redis)
# =============================================================================


class TestRememberApproval:
    """Tests for remember_approval()."""

    @pytest.fixture
    def manager(self):
        """Create enabled manager."""
        with patch("services.approval_memory.config") as mock_config:
            mock_config.permission.approval_memory_ttl = 2592000
            mock_config.permission.approval_memory_enabled = True
            return ApprovalMemoryManager(enabled=True, ttl=2592000)

    @pytest.mark.asyncio
    async def test_disabled_returns_false(self):
        """Disabled manager returns False."""
        with patch("services.approval_memory.config") as mock_config:
            mock_config.permission.approval_memory_ttl = 2592000
            mock_config.permission.approval_memory_enabled = False
            mgr = ApprovalMemoryManager(enabled=False)
        result = await mgr.remember_approval("/path", "ls", "user", "safe")
        assert result is False

    @pytest.mark.asyncio
    async def test_stores_approval_in_redis(self, manager):
        """Approval is stored in Redis with TTL."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        with patch(
            "services.approval_memory.get_redis_client", return_value=mock_redis
        ):
            result = await manager.remember_approval(
                project_path="/home/user/project",
                command="npm install lodash",
                user_id="user123",
                risk_level="moderate",
            )

        assert result is True
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == 2592000  # TTL
        stored_data = json.loads(call_args[0][2])
        assert len(stored_data) == 1
        assert stored_data[0]["pattern"] == "npm install *"

    @pytest.mark.asyncio
    async def test_updates_existing_record(self, manager):
        """Existing record for same pattern is updated."""
        existing = [
            {
                "pattern": "npm install *",
                "tool": "Bash",
                "risk_level": "safe",
                "user_id": "user123",
                "created_at": 1000.0,
                "original_command": "npm install old",
            }
        ]
        mock_redis = AsyncMock()
        mock_redis.get.return_value = json.dumps(existing)

        with patch(
            "services.approval_memory.get_redis_client", return_value=mock_redis
        ):
            await manager.remember_approval(
                project_path="/home/user/project",
                command="npm install new-pkg",
                user_id="user123",
                risk_level="moderate",
            )

        stored_data = json.loads(mock_redis.setex.call_args[0][2])
        assert len(stored_data) == 1  # Updated, not duplicated
        assert stored_data[0]["risk_level"] == "moderate"

    @pytest.mark.asyncio
    async def test_redis_unavailable_returns_false(self, manager):
        """Returns False when Redis is unavailable."""
        with patch("services.approval_memory.get_redis_client", return_value=None):
            result = await manager.remember_approval("/path", "ls", "user", "safe")
        assert result is False


# =============================================================================
# Check Remembered Tests (async, mocked Redis)
# =============================================================================


class TestCheckRemembered:
    """Tests for check_remembered()."""

    @pytest.fixture
    def manager(self):
        """Create enabled manager."""
        with patch("services.approval_memory.config") as mock_config:
            mock_config.permission.approval_memory_ttl = 2592000
            mock_config.permission.approval_memory_enabled = True
            return ApprovalMemoryManager(enabled=True, ttl=2592000)

    @pytest.mark.asyncio
    async def test_disabled_returns_false(self):
        """Disabled manager returns False."""
        with patch("services.approval_memory.config") as mock_config:
            mock_config.permission.approval_memory_ttl = 2592000
            mock_config.permission.approval_memory_enabled = False
            mgr = ApprovalMemoryManager(enabled=False)
        result = await mgr.check_remembered("/path", "ls", "user", "safe")
        assert result is False

    @pytest.mark.asyncio
    async def test_matching_pattern_auto_approves(self, manager):
        """Matching pattern at same risk level auto-approves."""
        records = [
            {
                "pattern": "npm install *",
                "tool": "Bash",
                "risk_level": "moderate",
                "user_id": "user123",
            }
        ]
        mock_redis = AsyncMock()
        mock_redis.get.return_value = json.dumps(records)

        with patch(
            "services.approval_memory.get_redis_client", return_value=mock_redis
        ):
            result = await manager.check_remembered(
                project_path="/home/user/project",
                command="npm install express",
                user_id="user123",
                risk_level="moderate",
            )
        assert result is True

    @pytest.mark.asyncio
    async def test_lower_risk_auto_approves(self, manager):
        """Lower risk than stored still auto-approves."""
        records = [
            {
                "pattern": "npm install *",
                "tool": "Bash",
                "risk_level": "high",
                "user_id": "user123",
            }
        ]
        mock_redis = AsyncMock()
        mock_redis.get.return_value = json.dumps(records)

        with patch(
            "services.approval_memory.get_redis_client", return_value=mock_redis
        ):
            result = await manager.check_remembered(
                project_path="/home/user/project",
                command="npm install express",
                user_id="user123",
                risk_level="moderate",
            )
        assert result is True

    @pytest.mark.asyncio
    async def test_higher_risk_denies_auto_approve(self, manager):
        """Higher risk than stored does NOT auto-approve."""
        records = [
            {
                "pattern": "npm install *",
                "tool": "Bash",
                "risk_level": "safe",
                "user_id": "user123",
            }
        ]
        mock_redis = AsyncMock()
        mock_redis.get.return_value = json.dumps(records)

        with patch(
            "services.approval_memory.get_redis_client", return_value=mock_redis
        ):
            result = await manager.check_remembered(
                project_path="/home/user/project",
                command="npm install express",
                user_id="user123",
                risk_level="high",
            )
        assert result is False

    @pytest.mark.asyncio
    async def test_no_stored_records(self, manager):
        """No stored records returns False."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        with patch(
            "services.approval_memory.get_redis_client", return_value=mock_redis
        ):
            result = await manager.check_remembered("/path", "ls", "user", "safe")
        assert result is False

    @pytest.mark.asyncio
    async def test_pattern_mismatch(self, manager):
        """Non-matching pattern returns False."""
        records = [
            {
                "pattern": "npm install *",
                "tool": "Bash",
                "risk_level": "moderate",
                "user_id": "user123",
            }
        ]
        mock_redis = AsyncMock()
        mock_redis.get.return_value = json.dumps(records)

        with patch(
            "services.approval_memory.get_redis_client", return_value=mock_redis
        ):
            result = await manager.check_remembered(
                project_path="/home/user/project",
                command="pip install requests",
                user_id="user123",
                risk_level="moderate",
            )
        assert result is False

    @pytest.mark.asyncio
    async def test_tool_mismatch(self, manager):
        """Different tool returns False."""
        records = [
            {
                "pattern": "npm install *",
                "tool": "Read",
                "risk_level": "moderate",
                "user_id": "user123",
            }
        ]
        mock_redis = AsyncMock()
        mock_redis.get.return_value = json.dumps(records)

        with patch(
            "services.approval_memory.get_redis_client", return_value=mock_redis
        ):
            result = await manager.check_remembered(
                project_path="/home/user/project",
                command="npm install express",
                user_id="user123",
                risk_level="moderate",
                tool="Bash",
            )
        assert result is False

    @pytest.mark.asyncio
    async def test_corrupt_json_returns_false(self, manager):
        """Corrupt JSON in Redis returns False."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "not valid json{"

        with patch(
            "services.approval_memory.get_redis_client", return_value=mock_redis
        ):
            result = await manager.check_remembered("/path", "ls", "user", "safe")
        assert result is False


# =============================================================================
# Helper Method Tests
# =============================================================================


class TestHelperMethods:
    """Tests for _load_existing_records and _update_or_add_record."""

    @pytest.fixture
    def manager(self):
        """Create manager with memory disabled."""
        with patch("services.approval_memory.config") as mock_config:
            mock_config.permission.approval_memory_ttl = 2592000
            mock_config.permission.approval_memory_enabled = False
            return ApprovalMemoryManager(enabled=False)

    @pytest.mark.asyncio
    async def test_load_existing_records_empty(self, manager):
        """No data returns empty list."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        result = await manager._load_existing_records(mock_redis, "key")
        assert result == []

    @pytest.mark.asyncio
    async def test_load_existing_records_valid_json(self, manager):
        """Valid JSON returns parsed list."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = json.dumps([{"pattern": "ls *"}])
        result = await manager._load_existing_records(mock_redis, "key")
        assert len(result) == 1
        assert result[0]["pattern"] == "ls *"

    @pytest.mark.asyncio
    async def test_load_existing_records_invalid_json(self, manager):
        """Invalid JSON returns empty list."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = "bad json"
        result = await manager._load_existing_records(mock_redis, "key")
        assert result == []

    def test_update_or_add_new_record(self, manager):
        """New record is appended."""
        records = []
        record = ApprovalRecord(
            pattern="ls *",
            tool="Bash",
            risk_level="safe",
            user_id="user",
            created_at=1000.0,
            original_command="ls",
        )
        result = manager._update_or_add_record(records, record, "ls *", "Bash")
        assert len(result) == 1

    def test_update_or_add_existing_record(self, manager):
        """Existing record with same pattern+tool is updated."""
        records = [{"pattern": "ls *", "tool": "Bash", "risk_level": "safe"}]
        record = ApprovalRecord(
            pattern="ls *",
            tool="Bash",
            risk_level="moderate",
            user_id="user",
            created_at=2000.0,
            original_command="ls -la",
        )
        result = manager._update_or_add_record(records, record, "ls *", "Bash")
        assert len(result) == 1
        assert result[0]["risk_level"] == "moderate"


# =============================================================================
# Singleton Tests
# =============================================================================


class TestGetApprovalMemorySingleton:
    """Tests for get_approval_memory factory."""

    def test_returns_instance(self):
        """Factory returns an ApprovalMemoryManager instance."""
        with patch("services.approval_memory.config") as mock_config:
            mock_config.permission.approval_memory_ttl = 2592000
            mock_config.permission.approval_memory_enabled = True
            import services.approval_memory as am_module

            am_module._memory_instance = None
            instance = get_approval_memory()
            assert isinstance(instance, ApprovalMemoryManager)
            am_module._memory_instance = None

    def test_returns_same_instance(self):
        """Factory returns singleton."""
        with patch("services.approval_memory.config") as mock_config:
            mock_config.permission.approval_memory_ttl = 2592000
            mock_config.permission.approval_memory_enabled = True
            import services.approval_memory as am_module

            am_module._memory_instance = None
            first = get_approval_memory()
            second = get_approval_memory()
            assert first is second
            am_module._memory_instance = None
