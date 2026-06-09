# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
DEPRECATED — conversation.py (Issue #3831)

This module has been removed. All session management is now handled by:

  - Session persistence (create/load/save/delete/update):
        from chat_history import ChatHistoryManager

  - Session orchestration and conversation history:
        from chat_workflow import ChatWorkflowManager, get_chat_workflow_manager

  - Conversation history mixin (Redis-backed):
        from chat_workflow.conversation import ConversationHandlerMixin

  - Active workflow session data model:
        from chat_workflow.models import WorkflowSession

The former ConversationManager and Conversation classes have no active callers.
The conversation processing pipeline (classify → KB search → research → LLM
response) is now fully owned by chat_workflow.manager.ChatWorkflowManager.

Do NOT import from this file. It will be deleted in a future cleanup pass
once all dependants confirm they have been migrated.
"""

raise ImportError(
    "conversation.py has been deprecated (Issue #3831). "
    "Use 'from chat_history import ChatHistoryManager' for session persistence "
    "or 'from chat_workflow import get_chat_workflow_manager' for orchestration."
)
