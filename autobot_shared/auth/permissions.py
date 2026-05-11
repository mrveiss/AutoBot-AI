# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Canonical Permission and Role enums shared across all AutoBot services (GH #6511).

Both autobot-backend and autobot-slm-backend must import from this module so
that a permission added here is automatically enforced by every service.

Naming convention: CATEGORY_RESOURCE_ACTION  →  "category.resource.action"
"""

from enum import Enum
from typing import Dict, List


class Permission(str, Enum):
    """All API permissions in the AutoBot system.

    Adding a permission here registers it for both the main backend and the SLM
    backend.  Do NOT define permissions in service-local files; that is the
    security drift pattern this module was created to eliminate.
    """

    # === API Core ===
    API_READ = "api.read"
    API_WRITE = "api.write"
    API_ADMIN = "api.admin"

    # === Knowledge Base ===
    KNOWLEDGE_READ = "knowledge.read"
    KNOWLEDGE_WRITE = "knowledge.write"
    KNOWLEDGE_DELETE = "knowledge.delete"
    KNOWLEDGE_MANAGE = "knowledge.manage"

    # === Analytics ===
    ANALYTICS_VIEW = "analytics.view"
    ANALYTICS_EXPORT = "analytics.export"
    ANALYTICS_MANAGE = "analytics.manage"
    ANALYTICS_LOGS = "analytics.logs"

    # === Agents ===
    AGENT_VIEW = "agent.view"
    AGENT_EXECUTE = "agent.execute"
    AGENT_MANAGE = "agent.manage"
    AGENT_TERMINAL = "agent.terminal"

    # === Workflows ===
    WORKFLOW_VIEW = "workflow.view"
    WORKFLOW_CREATE = "workflow.create"
    WORKFLOW_EXECUTE = "workflow.execute"
    WORKFLOW_MANAGE = "workflow.manage"

    # === Files ===
    FILES_VIEW = "files.view"
    FILES_DOWNLOAD = "files.download"
    FILES_UPLOAD = "files.upload"
    FILES_DELETE = "files.delete"
    FILES_MANAGE = "files.manage"

    # === Security ===
    SECURITY_VIEW = "security.view"
    SECURITY_AUDIT = "security.audit"
    SECURITY_MANAGE = "security.manage"

    # === System Administration ===
    ADMIN_USERS_READ = "admin.users.read"
    ADMIN_USERS_WRITE = "admin.users.write"
    ADMIN_CONFIG_READ = "admin.config.read"
    ADMIN_CONFIG_WRITE = "admin.config.write"
    ADMIN_SYSTEM = "admin.system"

    # === MCP (Model Context Protocol) ===
    MCP_READ = "mcp.read"
    MCP_EXECUTE = "mcp.execute"
    MCP_MANAGE = "mcp.manage"

    # === Batch Jobs ===
    BATCH_VIEW = "batch.view"
    BATCH_CREATE = "batch.create"
    BATCH_EXECUTE = "batch.execute"
    BATCH_MANAGE = "batch.manage"

    # === Sandbox ===
    SANDBOX_VIEW = "sandbox.view"
    SANDBOX_EXECUTE = "sandbox.execute"
    SANDBOX_MANAGE = "sandbox.manage"

    # === Chat ===
    CHAT_USE = "chat.use"
    CHAT_HISTORY = "chat.history"

    # === Teams / Organisations ===
    TEAMS_READ = "teams.read"
    TEAMS_CREATE = "teams.create"
    TEAMS_MANAGE = "teams.manage"
    TEAMS_DELETE = "teams.delete"

    # === Audit ===
    AUDIT_READ = "audit.read"
    AUDIT_WRITE = "audit.write"

    # === Settings ===
    SETTINGS_READ = "settings.read"
    SETTINGS_WRITE = "settings.write"

    # === Shell Execution (dangerous — no single-user bypass) ===
    SHELL_EXECUTE = "allow_shell_execute"


class Role(str, Enum):
    """Standard roles in the AutoBot system."""

    ADMIN = "admin"
    OPERATOR = "operator"
    ANALYST = "analyst"
    EDITOR = "editor"
    USER = "user"
    READONLY = "readonly"


# Canonical role-to-permission mapping.
# Both backends derive their permission sets from this dict.
# SLM system-role seeding also reads from here — see
# autobot-slm-backend/user_management/models/role.py.
ROLE_PERMISSIONS: Dict[Role, List[Permission]] = {
    Role.ADMIN: [
        Permission.API_READ,
        Permission.API_WRITE,
        Permission.API_ADMIN,
        Permission.KNOWLEDGE_READ,
        Permission.KNOWLEDGE_WRITE,
        Permission.KNOWLEDGE_DELETE,
        Permission.KNOWLEDGE_MANAGE,
        Permission.ANALYTICS_VIEW,
        Permission.ANALYTICS_EXPORT,
        Permission.ANALYTICS_MANAGE,
        Permission.ANALYTICS_LOGS,
        Permission.AGENT_VIEW,
        Permission.AGENT_EXECUTE,
        Permission.AGENT_MANAGE,
        Permission.AGENT_TERMINAL,
        Permission.WORKFLOW_VIEW,
        Permission.WORKFLOW_CREATE,
        Permission.WORKFLOW_EXECUTE,
        Permission.WORKFLOW_MANAGE,
        Permission.FILES_VIEW,
        Permission.FILES_DOWNLOAD,
        Permission.FILES_UPLOAD,
        Permission.FILES_DELETE,
        Permission.FILES_MANAGE,
        Permission.SECURITY_VIEW,
        Permission.SECURITY_AUDIT,
        Permission.SECURITY_MANAGE,
        Permission.ADMIN_USERS_READ,
        Permission.ADMIN_USERS_WRITE,
        Permission.ADMIN_CONFIG_READ,
        Permission.ADMIN_CONFIG_WRITE,
        Permission.ADMIN_SYSTEM,
        Permission.MCP_READ,
        Permission.MCP_EXECUTE,
        Permission.MCP_MANAGE,
        Permission.BATCH_VIEW,
        Permission.BATCH_CREATE,
        Permission.BATCH_EXECUTE,
        Permission.BATCH_MANAGE,
        Permission.SANDBOX_VIEW,
        Permission.SANDBOX_EXECUTE,
        Permission.SANDBOX_MANAGE,
        Permission.CHAT_USE,
        Permission.CHAT_HISTORY,
        Permission.TEAMS_READ,
        Permission.TEAMS_CREATE,
        Permission.TEAMS_MANAGE,
        Permission.TEAMS_DELETE,
        Permission.AUDIT_READ,
        Permission.AUDIT_WRITE,
        Permission.SETTINGS_READ,
        Permission.SETTINGS_WRITE,
        Permission.SHELL_EXECUTE,
    ],
    Role.OPERATOR: [
        Permission.API_READ,
        Permission.API_WRITE,
        Permission.KNOWLEDGE_READ,
        Permission.KNOWLEDGE_WRITE,
        Permission.ANALYTICS_VIEW,
        Permission.ANALYTICS_EXPORT,
        Permission.AGENT_VIEW,
        Permission.AGENT_EXECUTE,
        Permission.WORKFLOW_VIEW,
        Permission.WORKFLOW_CREATE,
        Permission.WORKFLOW_EXECUTE,
        Permission.FILES_VIEW,
        Permission.FILES_DOWNLOAD,
        Permission.FILES_UPLOAD,
        Permission.MCP_READ,
        Permission.MCP_EXECUTE,
        Permission.BATCH_VIEW,
        Permission.BATCH_CREATE,
        Permission.BATCH_EXECUTE,
        Permission.SANDBOX_VIEW,
        Permission.SANDBOX_EXECUTE,
        Permission.CHAT_USE,
        Permission.CHAT_HISTORY,
        Permission.TEAMS_READ,
        Permission.SETTINGS_READ,
    ],
    Role.ANALYST: [
        Permission.API_READ,
        Permission.KNOWLEDGE_READ,
        Permission.ANALYTICS_VIEW,
        Permission.ANALYTICS_EXPORT,
        Permission.ANALYTICS_LOGS,
        Permission.AGENT_VIEW,
        Permission.WORKFLOW_VIEW,
        Permission.FILES_VIEW,
        Permission.FILES_DOWNLOAD,
        Permission.SECURITY_VIEW,
        Permission.MCP_READ,
        Permission.BATCH_VIEW,
        Permission.CHAT_HISTORY,
        Permission.AUDIT_READ,
        Permission.SETTINGS_READ,
    ],
    Role.EDITOR: [
        Permission.API_READ,
        Permission.API_WRITE,
        Permission.KNOWLEDGE_READ,
        Permission.KNOWLEDGE_WRITE,
        Permission.ANALYTICS_VIEW,
        Permission.AGENT_VIEW,
        Permission.WORKFLOW_VIEW,
        Permission.WORKFLOW_CREATE,
        Permission.FILES_VIEW,
        Permission.FILES_DOWNLOAD,
        Permission.FILES_UPLOAD,
        Permission.MCP_READ,
        Permission.BATCH_VIEW,
        Permission.BATCH_CREATE,
        Permission.CHAT_USE,
        Permission.CHAT_HISTORY,
        Permission.SETTINGS_READ,
    ],
    Role.USER: [
        Permission.API_READ,
        Permission.KNOWLEDGE_READ,
        Permission.KNOWLEDGE_WRITE,
        Permission.ANALYTICS_VIEW,
        Permission.AGENT_VIEW,
        Permission.WORKFLOW_VIEW,
        Permission.FILES_VIEW,
        Permission.FILES_DOWNLOAD,
        Permission.FILES_UPLOAD,
        Permission.MCP_READ,
        Permission.BATCH_VIEW,
        Permission.CHAT_USE,
        Permission.CHAT_HISTORY,
        Permission.TEAMS_READ,
        Permission.SETTINGS_READ,
    ],
    Role.READONLY: [
        Permission.API_READ,
        Permission.KNOWLEDGE_READ,
        Permission.ANALYTICS_VIEW,
        Permission.AGENT_VIEW,
        Permission.WORKFLOW_VIEW,
        Permission.FILES_VIEW,
        Permission.FILES_DOWNLOAD,
        Permission.CHAT_HISTORY,
        Permission.TEAMS_READ,
        Permission.SETTINGS_READ,
    ],
}
