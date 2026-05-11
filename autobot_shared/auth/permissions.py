# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Canonical Permission/Role definitions for AutoBot (#6511).

Single source of truth for all permission names and role-to-permission mappings
shared by autobot-backend and autobot-slm-backend.  Before this module existed,
``Permission`` and ``Role`` lived only in ``autobot-backend/auth_rbac.py``; the
SLM backend used bare permission strings from the database that were never
cross-checked against the main backend's enum values, creating security drift.

Adding a new permission
-----------------------
1. Add a member to ``Permission`` here.
2. Grant it to the appropriate roles in ``ROLE_PERMISSIONS``.
3. Both backends automatically see the change on next deploy — no second edit.

Removing or renaming a permission
----------------------------------
Search for callers of the old name across both backends before deleting.
"""

from enum import Enum
from typing import Dict, List


class Permission(str, Enum):
    """All API permissions in the system.

    Naming convention: CATEGORY_RESOURCE_ACTION
    - CATEGORY: functional area (API, KNOWLEDGE, ANALYTICS, …)
    - RESOURCE: specific resource being accessed
    - ACTION: READ, WRITE, EXECUTE, DELETE, MANAGE
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

    # === Agent ===
    AGENT_VIEW = "agent.view"
    AGENT_EXECUTE = "agent.execute"
    AGENT_MANAGE = "agent.manage"
    AGENT_TERMINAL = "agent.terminal"

    # === Workflow ===
    WORKFLOW_VIEW = "workflow.view"
    WORKFLOW_CREATE = "workflow.create"
    WORKFLOW_EXECUTE = "workflow.execute"
    WORKFLOW_MANAGE = "workflow.manage"

    # === File Operations ===
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

    # === Shell Execution (dangerous — no single-user bypass allowed) ===
    SHELL_EXECUTE = "allow_shell_execute"


class Role(str, Enum):
    """Standard roles in the AutoBot system."""

    ADMIN = "admin"
    OPERATOR = "operator"
    ANALYST = "analyst"
    EDITOR = "editor"
    USER = "user"
    READONLY = "readonly"


# Canonical role-to-permission mappings.
# Both autobot-backend (auth_rbac.py) and autobot-slm-backend import this dict
# so that a permission added here is enforced by both services automatically.
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
    ],
    Role.USER: [
        Permission.API_READ,
        Permission.KNOWLEDGE_READ,
        Permission.ANALYTICS_VIEW,
        Permission.AGENT_VIEW,
        Permission.WORKFLOW_VIEW,
        Permission.FILES_VIEW,
        Permission.FILES_DOWNLOAD,
        Permission.MCP_READ,
        Permission.BATCH_VIEW,
    ],
    Role.READONLY: [
        Permission.API_READ,
        Permission.KNOWLEDGE_READ,
        Permission.ANALYTICS_VIEW,
        Permission.AGENT_VIEW,
        Permission.WORKFLOW_VIEW,
        Permission.FILES_VIEW,
    ],
}
