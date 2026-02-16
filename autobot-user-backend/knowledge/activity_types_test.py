# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Activity Entity Types

Issue #871 - Activity Entity Types (#608 Phase 4)

Tests cover:
- Entity instantiation and validation
- User attribution requirements
- Secret usage tracking
- Metadata handling
- Timestamp generation
"""

import uuid
from datetime import datetime

import pytest
from pydantic import ValidationError

from backend.knowledge.activity_types import (
    BrowserActivity,
    DesktopActivity,
    FileActivity,
    SecretUsage,
    TerminalActivity,
)


class TestTerminalActivity:
    """Tests for TerminalActivity entity type."""

    def test_terminal_activity_creation(self):
        """Test creating a terminal activity with all fields."""
        user_id = uuid.uuid4()
        secret_id = uuid.uuid4()

        activity = TerminalActivity(
            user_id=user_id,
            session_id="chat_abc123",
            command="git push origin main",
            working_directory="/home/user/project",
            exit_code=0,
            output="Everything up-to-date",
            secrets_used=[secret_id],
            metadata={"shell": "bash", "duration_ms": 1250},
        )

        assert activity.user_id == user_id
        assert activity.session_id == "chat_abc123"
        assert activity.command == "git push origin main"
        assert activity.working_directory == "/home/user/project"
        assert activity.exit_code == 0
        assert activity.output == "Everything up-to-date"
        assert activity.secrets_used == [secret_id]
        assert activity.metadata["shell"] == "bash"
        assert isinstance(activity.timestamp, datetime)

    def test_terminal_activity_minimal(self):
        """Test terminal activity with only required fields."""
        user_id = uuid.uuid4()

        activity = TerminalActivity(user_id=user_id, command="ls -la")

        assert activity.user_id == user_id
        assert activity.command == "ls -la"
        assert activity.session_id is None
        assert activity.working_directory is None
        assert activity.exit_code is None
        assert activity.output is None
        assert activity.secrets_used == []
        assert activity.metadata == {}

    def test_terminal_activity_user_id_required(self):
        """Test that user_id is required."""
        with pytest.raises(ValidationError) as exc_info:
            TerminalActivity(command="ls -la")

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("user_id",) for e in errors)

    def test_terminal_activity_command_required(self):
        """Test that command is required."""
        with pytest.raises(ValidationError) as exc_info:
            TerminalActivity(user_id=uuid.uuid4())

        errors = exc_info.value.errors()
        assert any(e["loc"] == ("command",) for e in errors)


class TestFileActivity:
    """Tests for FileActivity entity type."""

    def test_file_activity_creation(self):
        """Test creating a file activity with all fields."""
        user_id = uuid.uuid4()

        activity = FileActivity(
            user_id=user_id,
            session_id="chat_abc123",
            operation="create",
            path="/home/user/document.txt",
            file_type="text/plain",
            size_bytes=1024,
            metadata={"permissions": "0644", "encoding": "utf-8"},
        )

        assert activity.user_id == user_id
        assert activity.session_id == "chat_abc123"
        assert activity.operation == "create"
        assert activity.path == "/home/user/document.txt"
        assert activity.file_type == "text/plain"
        assert activity.size_bytes == 1024
        assert activity.metadata["permissions"] == "0644"

    def test_file_activity_rename(self):
        """Test file activity with rename operation."""
        user_id = uuid.uuid4()

        activity = FileActivity(
            user_id=user_id,
            operation="rename",
            path="/home/user/old.txt",
            new_path="/home/user/new.txt",
        )

        assert activity.operation == "rename"
        assert activity.path == "/home/user/old.txt"
        assert activity.new_path == "/home/user/new.txt"

    def test_file_activity_required_fields(self):
        """Test that user_id, operation, and path are required."""
        with pytest.raises(ValidationError) as exc_info:
            FileActivity()

        errors = exc_info.value.errors()
        field_names = {e["loc"][0] for e in errors}
        assert "user_id" in field_names
        assert "operation" in field_names
        assert "path" in field_names


class TestBrowserActivity:
    """Tests for BrowserActivity entity type."""

    def test_browser_activity_creation(self):
        """Test creating a browser activity with all fields."""
        user_id = uuid.uuid4()
        secret_id = uuid.uuid4()

        activity = BrowserActivity(
            user_id=user_id,
            session_id="chat_abc123",
            url="https://example.com/login",
            action="submit",
            selector="#login-form",
            input_value="username@example.com",
            secrets_used=[secret_id],
            metadata={"status_code": 200, "redirect_url": "/dashboard"},
        )

        assert activity.user_id == user_id
        assert activity.url == "https://example.com/login"
        assert activity.action == "submit"
        assert activity.selector == "#login-form"
        assert activity.secrets_used == [secret_id]
        assert activity.metadata["status_code"] == 200

    def test_browser_activity_navigate(self):
        """Test browser activity with navigation action."""
        user_id = uuid.uuid4()

        activity = BrowserActivity(
            user_id=user_id,
            url="https://example.com",
            action="navigate",
        )

        assert activity.action == "navigate"
        assert activity.url == "https://example.com"
        assert activity.selector is None
        assert activity.input_value is None
        assert activity.secrets_used == []

    def test_browser_activity_required_fields(self):
        """Test that user_id, url, and action are required."""
        with pytest.raises(ValidationError) as exc_info:
            BrowserActivity()

        errors = exc_info.value.errors()
        field_names = {e["loc"][0] for e in errors}
        assert "user_id" in field_names
        assert "url" in field_names
        assert "action" in field_names


class TestDesktopActivity:
    """Tests for DesktopActivity entity type."""

    def test_desktop_activity_creation(self):
        """Test creating a desktop activity with all fields."""
        user_id = uuid.uuid4()

        activity = DesktopActivity(
            user_id=user_id,
            session_id="chat_abc123",
            action="click",
            coordinates=(500, 300),
            window_title="Visual Studio Code",
            metadata={"app": "code", "ocr_text": "Save File"},
        )

        assert activity.user_id == user_id
        assert activity.action == "click"
        assert activity.coordinates == (500, 300)
        assert activity.window_title == "Visual Studio Code"
        assert activity.metadata["app"] == "code"

    def test_desktop_activity_type(self):
        """Test desktop activity with keyboard input."""
        user_id = uuid.uuid4()

        activity = DesktopActivity(
            user_id=user_id,
            action="type",
            input_text="Hello, world!",
            window_title="Notepad",
        )

        assert activity.action == "type"
        assert activity.input_text == "Hello, world!"
        assert activity.coordinates is None

    def test_desktop_activity_screenshot(self):
        """Test desktop activity with screenshot capture."""
        user_id = uuid.uuid4()

        activity = DesktopActivity(
            user_id=user_id,
            action="screenshot",
            screenshot_path="/tmp/screenshot_123.png",
            metadata={"width": 1920, "height": 1080},
        )

        assert activity.action == "screenshot"
        assert activity.screenshot_path == "/tmp/screenshot_123.png"
        assert activity.metadata["width"] == 1920

    def test_desktop_activity_required_fields(self):
        """Test that user_id and action are required."""
        with pytest.raises(ValidationError) as exc_info:
            DesktopActivity()

        errors = exc_info.value.errors()
        field_names = {e["loc"][0] for e in errors}
        assert "user_id" in field_names
        assert "action" in field_names


class TestSecretUsage:
    """Tests for SecretUsage audit trail entity."""

    def test_secret_usage_creation(self):
        """Test creating a secret usage audit entry with all fields."""
        secret_id = uuid.uuid4()
        user_id = uuid.uuid4()
        activity_id = uuid.uuid4()

        usage = SecretUsage(
            secret_id=secret_id,
            user_id=user_id,
            activity_type="terminal",
            activity_id=activity_id,
            session_id="chat_abc123",
            access_granted=True,
            metadata={"ip": "192.168.1.10", "location": "office"},
        )

        assert usage.secret_id == secret_id
        assert usage.user_id == user_id
        assert usage.activity_type == "terminal"
        assert usage.activity_id == activity_id
        assert usage.session_id == "chat_abc123"
        assert usage.access_granted is True
        assert usage.denial_reason is None
        assert usage.metadata["ip"] == "192.168.1.10"

    def test_secret_usage_denied(self):
        """Test secret usage with denied access."""
        secret_id = uuid.uuid4()
        user_id = uuid.uuid4()
        activity_id = uuid.uuid4()

        usage = SecretUsage(
            secret_id=secret_id,
            user_id=user_id,
            activity_type="browser",
            activity_id=activity_id,
            access_granted=False,
            denial_reason="Insufficient permissions",
        )

        assert usage.access_granted is False
        assert usage.denial_reason == "Insufficient permissions"

    def test_secret_usage_required_fields(self):
        """Test that all key fields are required for audit trail."""
        with pytest.raises(ValidationError) as exc_info:
            SecretUsage()

        errors = exc_info.value.errors()
        field_names = {e["loc"][0] for e in errors}
        assert "secret_id" in field_names
        assert "user_id" in field_names
        assert "activity_type" in field_names
        assert "activity_id" in field_names
        assert "access_granted" in field_names


class TestActivityEntityIntegration:
    """Integration tests across multiple activity entity types."""

    def test_terminal_with_secret_usage(self):
        """Test creating terminal activity and corresponding secret usage."""
        user_id = uuid.uuid4()
        secret_id = uuid.uuid4()

        # Create terminal activity
        terminal = TerminalActivity(
            user_id=user_id,
            command="git push",
            secrets_used=[secret_id],
        )

        # Create corresponding secret usage audit entry
        usage = SecretUsage(
            secret_id=secret_id,
            user_id=user_id,
            activity_type="terminal",
            activity_id=terminal.id,
            access_granted=True,
        )

        assert usage.activity_id == terminal.id
        assert usage.secret_id == secret_id
        assert usage.user_id == user_id

    def test_browser_with_secret_usage(self):
        """Test creating browser activity and corresponding secret usage."""
        user_id = uuid.uuid4()
        secret_id = uuid.uuid4()

        # Create browser activity
        browser = BrowserActivity(
            user_id=user_id,
            url="https://api.example.com",
            action="submit",
            secrets_used=[secret_id],
        )

        # Create corresponding secret usage audit entry
        usage = SecretUsage(
            secret_id=secret_id,
            user_id=user_id,
            activity_type="browser",
            activity_id=browser.id,
            access_granted=True,
        )

        assert usage.activity_id == browser.id
        assert usage.activity_type == "browser"

    def test_multiple_secrets_in_terminal(self):
        """Test terminal activity using multiple secrets."""
        user_id = uuid.uuid4()
        secret1 = uuid.uuid4()
        secret2 = uuid.uuid4()

        terminal = TerminalActivity(
            user_id=user_id,
            command="ansible-playbook deploy.yml",
            secrets_used=[secret1, secret2],
        )

        # Create audit entries for each secret
        usage1 = SecretUsage(
            secret_id=secret1,
            user_id=user_id,
            activity_type="terminal",
            activity_id=terminal.id,
            access_granted=True,
        )

        usage2 = SecretUsage(
            secret_id=secret2,
            user_id=user_id,
            activity_type="terminal",
            activity_id=terminal.id,
            access_granted=True,
        )

        assert len(terminal.secrets_used) == 2
        assert usage1.secret_id in terminal.secrets_used
        assert usage2.secret_id in terminal.secrets_used

    def test_session_context_across_activities(self):
        """Test that session_id is preserved across different activity types."""
        user_id = uuid.uuid4()
        session_id = "chat_xyz789"

        terminal = TerminalActivity(
            user_id=user_id,
            session_id=session_id,
            command="ls",
        )

        file = FileActivity(
            user_id=user_id,
            session_id=session_id,
            operation="read",
            path="/etc/hosts",
        )

        browser = BrowserActivity(
            user_id=user_id,
            session_id=session_id,
            url="https://example.com",
            action="navigate",
        )

        desktop = DesktopActivity(
            user_id=user_id,
            session_id=session_id,
            action="click",
            coordinates=(100, 200),
        )

        assert terminal.session_id == session_id
        assert file.session_id == session_id
        assert browser.session_id == session_id
        assert desktop.session_id == session_id
