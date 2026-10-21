# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Written audit action spellings that are not yet canonical, each with its reason (#18716).

SHRINK-ONLY. ``audit_action_vocabulary_18716_test.py`` fails on an entry no writer passes any
more (delete it) and on a writer spelling that is neither an ``AuditAction`` member, an
open-ended family, nor listed here. Adding an entry is not the way to land a new action: add the
member to ``AuditAction`` (``services/audit/taxonomy.py``) and write that.

These are all outside the concepts #18716 normalises (login, logout, config change, file
delete/create/upload, user create/delete/update, role change, password change, api_key
create/revoke). Every spelling of those resolves to one member through
``autobot_shared.audit_actions``.
"""

from __future__ import annotations

_DOTTED_REASON = (
    "already `<resource>.<verb>` shaped, but a vocabulary outside the #18716 concepts (login, "
    "logout, config, file, user, role, password, api_key); it needs an AuditAction member when "
    "its owner promotes it"
)
_DOTTED = (
    "agent.budget_paused",
    "agent.budget_resumed",
    "approval.post_action_failed",
    "budget.threshold_breach",
    "collection.stamp_embedding_space",
    "knowledge.source_liveness.sweep",
    "legacy_transcript.delete",
    "mcp.external_server.tool_call",
    "memory.privacy.amend",
    "memory.privacy.export",
    "memory.privacy.forget",
    "memory.privacy.forget_everywhere",
    "memory.privacy.list",
    "oauth_bundle.strip_app_credentials",
    "orphan_storage.delete",
    "resource.repair_orphan",
    "secret.bulk_delete",
    "secret.create",
    "secret.delete",
    "secret.list",
    "secret.transfer",
    "secret.update",
    "voice.realtime.tool_call",
)

_IDENTITY_REASON = (
    "team / organization / RBAC-denial identity action: `IdentityAuditAction` is a public "
    "constant set of the shared user-management package and audit_row (the one boundary) stores "
    "it unchanged until the follow-up vocabulary expansion"
)
_IDENTITY = (
    "org_created",
    "org_deleted",
    "org_updated",
    "permission_denied",
    "team_created",
    "team_deleted",
    "team_member_added",
    "team_member_removed",
    "team_member_role_changed",
    "team_updated",
)

_COMMAND_REASON = (
    "security-layer command, approval, service-control or lockout event: an operation record "
    "outside the #18716 concepts, still underscore-spelled; rename belongs to the vocabulary "
    "expansion"
)
_COMMAND = (
    "account_locked",
    "command_approval",
    "command_approval_decision",
    "command_approval_request",
    "command_approval_response",
    "command_approval_timeout",
    "command_auto_approved",
    "command_execution",
    "command_execution_attempt",
    "command_execution_complete",
    "command_execution_denied",
    "deprecated_role_usage",
    "execute_command",
    "execute_shell_command",
    "file_access_denied",
    "file_access_granted",
    "intelligent_agent_command_execution",
    "password_change_failed",
    "password_change_rate_limited",
    "redis_service_restart_attempt",
    "redis_service_restart_completed",
    "redis_service_restart_failed",
    "redis_service_start_attempt",
    "redis_service_start_completed",
    "redis_service_start_failed",
    "redis_service_stop_attempt",
    "redis_service_stop_completed",
    "redis_service_stop_failed",
    "role_denied",
)

_HANDLER_REASON = (
    "task-handler, voice, GUI, KB or SSO-callback operation name: an operation record outside "
    "the #18716 concepts, still underscore-spelled; rename belongs to the vocabulary expansion"
)
_HANDLER = (
    "agent_pause",
    "agent_resume",
    "ask_user_command_approval",
    "ask_user_for_manual",
    "audit_log_retention_purge",
    "conversation_accessed",
    "gui_bring_window_to_front",
    "gui_click_element",
    "gui_move_mouse",
    "gui_read_text_from_region",
    "gui_type_text",
    "kb_add_file",
    "kb_search",
    "kb_store_fact",
    "llm_chat_completion",
    "mfa_challenge_issued",
    "respond_conversationally",
    "retention_purge",
    "slo_callback",
    "slo_callback_failed",
    "submit_goal",
    "system_execute_command",
    "system_get_process_info",
    "system_list_services",
    "system_manage_service",
    "system_query_info",
    "system_terminate_process",
    "unauthorized_conversation_access",
    "voice_bundle_assignment_changed",
    "voice_clone",
    "voice_listen",
    "voice_speak",
    "voice_synthesize",
    "voice_transcribe",
    "web_fetch",
)

_REST_REASON = (
    "file-adjacent or workflow-permission verb outside the #18716 concepts (no "
    "create/delete/upload/download); needs its own member and, for the bare verbs, a resource "
    "prefix"
)
_REST = (
    "directory_create",
    "file_rename",
    "grant",
    "revoke",
    "view",
)

LEGACY_SPELLINGS: dict[str, str] = {
    **dict.fromkeys(_DOTTED, _DOTTED_REASON),
    **dict.fromkeys(_IDENTITY, _IDENTITY_REASON),
    **dict.fromkeys(_COMMAND, _COMMAND_REASON),
    **dict.fromkeys(_HANDLER, _HANDLER_REASON),
    **dict.fromkeys(_REST, _REST_REASON),
}

#: Open-ended families: the suffix is data, so no finite member list can name them.
OPEN_ENDED_PREFIXES = ("llm_command_parser:", "ai_line.", "execute_task_")
