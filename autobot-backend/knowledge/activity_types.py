# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Activity Entity Types with User Attribution

Issue #871 - Activity Entity Types (#608 Phase 4)

Defines entity types for tracking user activities across UI components:
- TerminalActivity: Command execution with secret usage tracking
- FileActivity: File operations (read, write, delete, rename)
- BrowserActivity: Web navigation and interactions with secret usage
- DesktopActivity: Desktop automation actions (click, type, etc.)
- SecretUsage: Audit trail for secret access across all activity types
"""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class TerminalActivity(BaseModel):
    """
    Terminal command execution activity.

    Tracks shell commands executed by users, including:
    - Command text and exit code
    - Secret usage (environment variables, credentials)
    - Output capture for knowledge extraction
    - User attribution and session context
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: uuid.UUID = Field(..., description="User who executed the command")
    session_id: Optional[str] = Field(
        None, description="Chat session ID if executed via chat"
    )
    command: str = Field(..., description="The shell command executed")
    working_directory: Optional[str] = Field(
        None, description="Directory where command was executed"
    )
    exit_code: Optional[int] = Field(
        None, description="Command exit code (0 = success)"
    )
    output: Optional[str] = Field(None, description="Command output (stdout + stderr)")
    secrets_used: list[uuid.UUID] = Field(
        default_factory=list,
        description="IDs of secrets used in this command",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (shell type, env vars, etc.)",
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "session_id": "chat_abc123",
                "command": "git push origin main",
                "working_directory": "/home/user/project",
                "exit_code": 0,
                "output": "Everything up-to-date",
                "secrets_used": ["660e8400-e29b-41d4-a716-446655440001"],
                "metadata": {"shell": "bash", "duration_ms": 1250},
            }
        }


class FileActivity(BaseModel):
    """
    File system operation activity.

    Tracks file operations performed by users:
    - CRUD operations (create, read, update, delete)
    - File renames and moves
    - User attribution for access control
    - Path tracking for security auditing
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: uuid.UUID = Field(..., description="User who performed the operation")
    session_id: Optional[str] = Field(
        None, description="Chat session ID if performed via chat"
    )
    operation: str = Field(
        ...,
        description="Operation type: create, read, update, delete, rename, move",
    )
    path: str = Field(..., description="File or directory path")
    new_path: Optional[str] = Field(
        None, description="New path for rename/move operations"
    )
    file_type: Optional[str] = Field(None, description="File MIME type or extension")
    size_bytes: Optional[int] = Field(None, description="File size in bytes")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (permissions, owner, etc.)",
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "session_id": "chat_abc123",
                "operation": "create",
                "path": "/home/user/document.txt",
                "file_type": "text/plain",
                "size_bytes": 1024,
                "metadata": {"permissions": "0644", "encoding": "utf-8"},
            }
        }


class BrowserActivity(BaseModel):
    """
    Browser automation activity.

    Tracks web navigation and interactions:
    - URL navigation and page loads
    - Form submissions with secret usage
    - Click and scroll actions
    - User attribution for audit trails
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: uuid.UUID = Field(..., description="User who performed the action")
    session_id: Optional[str] = Field(
        None, description="Chat session ID if performed via chat"
    )
    url: str = Field(..., description="Target URL")
    action: str = Field(
        ...,
        description="Action type: navigate, click, type, submit, scroll",
    )
    selector: Optional[str] = Field(
        None, description="CSS selector for targeted element"
    )
    input_value: Optional[str] = Field(
        None, description="Value entered (for type/submit actions)"
    )
    secrets_used: list[uuid.UUID] = Field(
        default_factory=list,
        description="IDs of secrets used (credentials, API keys)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (status code, cookies, etc.)",
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "session_id": "chat_abc123",
                "url": "https://example.com/login",
                "action": "submit",
                "selector": "#login-form",
                "secrets_used": ["660e8400-e29b-41d4-a716-446655440001"],
                "metadata": {"status_code": 200, "redirect_url": "/dashboard"},
            }
        }


class DesktopActivity(BaseModel):
    """
    Desktop automation activity.

    Tracks GUI automation actions:
    - Mouse clicks and movements
    - Keyboard input
    - Window management
    - User attribution for security auditing
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    user_id: uuid.UUID = Field(..., description="User who performed the action")
    session_id: Optional[str] = Field(
        None, description="Chat session ID if performed via chat"
    )
    action: str = Field(
        ...,
        description="Action type: click, type, move, screenshot, window_focus",
    )
    coordinates: Optional[tuple[int, int]] = Field(
        None, description="Screen coordinates (x, y) for click/move"
    )
    window_title: Optional[str] = Field(None, description="Target window title")
    input_text: Optional[str] = Field(None, description="Text typed (for type actions)")
    screenshot_path: Optional[str] = Field(
        None, description="Path to captured screenshot"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (app name, OCR results, etc.)",
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "session_id": "chat_abc123",
                "action": "click",
                "coordinates": (500, 300),
                "window_title": "Visual Studio Code",
                "metadata": {"app": "code", "ocr_text": "Save File"},
            }
        }


class SecretUsage(BaseModel):
    """
    Secret access audit trail.

    Provides comprehensive audit trail for secret usage:
    - Which secret was accessed
    - Who accessed it
    - What activity triggered the access
    - When it was accessed

    This entity enables:
    - Security auditing and compliance
    - Secret lifecycle tracking
    - Access pattern analysis
    - Anomaly detection
    """

    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    secret_id: uuid.UUID = Field(..., description="ID of the secret accessed")
    user_id: uuid.UUID = Field(..., description="User who accessed the secret")
    activity_type: str = Field(
        ...,
        description="Type of activity: terminal, browser, file, desktop, api",
    )
    activity_id: uuid.UUID = Field(..., description="ID of the parent activity entity")
    session_id: Optional[str] = Field(
        None, description="Chat session ID if accessed via chat"
    )
    access_granted: bool = Field(
        ..., description="Whether access was granted or denied"
    )
    denial_reason: Optional[str] = Field(
        None, description="Reason for denial (if access_granted=False)"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (IP, user agent, etc.)",
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_schema_extra = {
            "example": {
                "secret_id": "660e8400-e29b-41d4-a716-446655440001",
                "user_id": "550e8400-e29b-41d4-a716-446655440000",
                "activity_type": "terminal",
                "activity_id": "770e8400-e29b-41d4-a716-446655440002",
                "session_id": "chat_abc123",
                "access_granted": True,
                "metadata": {"ip": "192.168.1.10", "location": "office"},
            }
        }
