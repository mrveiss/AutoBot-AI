# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18451: the 'api' symbol-fork batch -- one MCPTool, homonyms named apart."""

import importlib

import pytest


def test_mcp_tool_is_one_class_for_every_mcp_router():
    from api.redis_mcp import tools
    from api.schemas_code import MCPTool

    assert tools.MCPTool is MCPTool
    tool = tools.get_all_tools()[0]
    assert type(tool) is MCPTool
    assert {"name", "description", "input_schema"} <= set(MCPTool.model_fields)


def test_dead_terminal_workflow_control_copy_is_gone():
    from api import schemas_terminal
    from services.workflow_automation.models import WorkflowControlRequest

    assert not hasattr(schemas_terminal, "WorkflowControlRequest")
    assert {"workflow_id", "action"} <= set(WorkflowControlRequest.model_fields)


@pytest.mark.parametrize(
    "module, names",
    [
        ("api.ide_integration", ["get_ide_integration_engine"]),
        ("api.analytics_continuous_learning", ["get_continuous_learning_engine"]),
        ("api.cache_management", ["get_cache_redis_connection"]),
        ("api.analytics_dfa", ["DFATaintVulnerability"]),
        ("api.developer", ["RuntimeEndpointRegistry"]),
        ("api.natural_language_search", ["CodeQueryIntent"]),
        ("api.schemas_realtime_session", ["RealtimeSessionSummary"]),
        ("api.schemas_chat_rows", ["ChatSessionSummary"]),
        ("llc.models.template", ["LLCTemplateSearchResponse"]),
        ("workflow_templates", ["WorkflowTemplateCategory"]),
        ("services.advanced_workflow", ["SmartWorkflowTemplate"]),
        ("tools.terminal_backend_client", ["fetch_terminal_sessions"]),
    ],
)
def test_homonyms_are_named_apart(module, names):
    mod = importlib.import_module(module)
    for name in names:
        assert hasattr(mod, name), f"{module}.{name}"


def test_formerly_shared_names_now_refer_to_one_concept_each():
    from api import developer, registry

    assert registry.APIRegistry is not getattr(developer, "APIRegistry", None)
    from tools import terminal_backend_client

    assert not hasattr(terminal_backend_client, "list_terminal_sessions")
