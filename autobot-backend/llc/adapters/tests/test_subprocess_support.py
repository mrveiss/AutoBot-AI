# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for shared subprocess-adapter helpers (GH#9789, GH#9769, GH#9777)."""

import json

from llc.adapters.subprocess_support import (
    AGENT_API_KEY_PLACEHOLDER,
    inject_agent_credentials,
    render_context_markdown,
    serialize_invoke_context,
)


class TestRenderContextMarkdown:
    def test_rag_brief_and_task_id(self) -> None:
        p = render_context_markdown({"rag_brief": "# Policy\nDo X.", "task_id": "t1"})
        assert "# Policy" in p
        assert "Task ID: t1" in p

    def test_fat_context_structured(self) -> None:
        p = render_context_markdown(
            {
                "work_item_detail": {
                    "title": "Fix login",
                    "status": "in_progress",
                    "priority": "high",
                    "acceptance_criteria": "Works.",
                },
                "goal_ancestry": [{"title": "Improve auth"}],
                "company_context": {"chunks": ["Uses OAuth."], "sources": []},
            }
        )
        assert "# Work Item: Fix login" in p
        assert "**Status:** in_progress" in p
        assert "## Goal Ancestry" in p
        assert "Uses OAuth." in p

    def test_never_raw_json(self) -> None:
        p = render_context_markdown({"foo": "bar", "nested": {"a": 1}})
        assert "- foo: bar" in p
        assert '"a": 1' not in p  # dict-valued key not dumped

    def test_empty_context_nonempty(self) -> None:
        assert render_context_markdown({})


class TestSerializeInvokeContext:
    def test_redacts_real_key(self) -> None:
        blob = serialize_invoke_context({"agent_api_key": "llc_real", "x": 1})
        assert "llc_real" not in blob
        assert AGENT_API_KEY_PLACEHOLDER in blob
        assert json.loads(blob)["x"] == 1

    def test_passes_through_placeholder(self) -> None:
        blob = serialize_invoke_context({"agent_api_key": AGENT_API_KEY_PLACEHOLDER})
        assert AGENT_API_KEY_PLACEHOLDER in blob

    def test_no_key_unaffected(self) -> None:
        assert json.loads(serialize_invoke_context({"y": 2}))["y"] == 2


class TestInjectAgentCredentials:
    def test_forwards_real_key(self) -> None:
        env: dict = {}
        inject_agent_credentials(env, {"agent_api_key": "llc_real", "api_base": "http://api"})
        assert env["AUTOBOT_LLC_API_KEY"] == "llc_real"
        assert env["AUTOBOT_LLC_API_BASE"] == "http://api"

    def test_skips_placeholder(self) -> None:
        env: dict = {}
        inject_agent_credentials(env, {"agent_api_key": AGENT_API_KEY_PLACEHOLDER})
        assert "AUTOBOT_LLC_API_KEY" not in env

    def test_skips_empty_key(self) -> None:
        env: dict = {}
        inject_agent_credentials(env, {})
        assert "AUTOBOT_LLC_API_KEY" not in env
        # api_base falls back to the module default
        assert env.get("AUTOBOT_LLC_API_BASE")
