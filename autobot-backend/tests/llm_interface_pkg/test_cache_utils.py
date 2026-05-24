# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for llm_shared.providers.cache_utils (#7368)."""

import json
import random

import pytest

from llm_shared.providers.cache_utils import sorted_for_cache


def _serialise(payload: dict) -> str:
    return json.dumps(payload, default=str)


class TestSortedForCache:
    def test_tool_list_sorted_by_name(self):
        tools = [
            {"name": "web_search", "description": "search the web"},
            {"name": "calculator", "description": "do math"},
            {"name": "file_read", "description": "read a file"},
        ]
        shuffled = list(tools)
        random.shuffle(shuffled)
        result = sorted_for_cache({"tools": shuffled})
        names = [t["name"] for t in result["tools"]]
        assert names == sorted(names)

    def test_tool_list_byte_identical_from_shuffled_inputs(self):
        tools = [{"name": f"tool_{i}", "description": f"desc {i}"} for i in range(10)]
        shuffled_a = sorted(tools, key=lambda x: x["name"], reverse=True)
        shuffled_b = sorted(tools, key=lambda x: x["name"])

        payload_a = sorted_for_cache({"tools": shuffled_a, "model": "gpt-4o"})
        payload_b = sorted_for_cache({"tools": shuffled_b, "model": "gpt-4o"})
        assert _serialise(payload_a) == _serialise(payload_b)

    def test_functions_list_sorted_by_name(self):
        functions = [
            {"name": "send_email", "parameters": {}},
            {"name": "get_weather", "parameters": {}},
        ]
        result = sorted_for_cache({"functions": list(reversed(functions))})
        assert result["functions"][0]["name"] == "get_weather"
        assert result["functions"][1]["name"] == "send_email"

    def test_system_blocks_sorted_by_id(self):
        blocks = [
            {"id": "block_z", "type": "text", "text": "Z"},
            {"id": "block_a", "type": "text", "text": "A"},
        ]
        result = sorted_for_cache({"system": list(reversed(blocks))})
        assert result["system"][0]["id"] == "block_a"
        assert result["system"][1]["id"] == "block_z"

    def test_nested_dict_keys_sorted(self):
        payload = {"z_key": {"b": 2, "a": 1}, "a_key": "value"}
        result = sorted_for_cache(payload)
        assert list(result.keys()) == ["a_key", "z_key"]
        assert list(result["z_key"].keys()) == ["a", "b"]

    def test_set_raises_type_error(self):
        with pytest.raises(TypeError, match="set\\(\\)"):
            sorted_for_cache({"plugins": {"alpha", "beta"}})

    def test_plain_list_of_messages_preserved_in_order(self):
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "how are you"},
        ]
        result = sorted_for_cache({"messages": list(messages), "model": "claude-3"})
        assert result["messages"] == messages

    def test_original_payload_not_mutated(self):
        tools = [{"name": "b"}, {"name": "a"}]
        payload = {"tools": tools}
        sorted_for_cache(payload)
        assert payload["tools"][0]["name"] == "b"

    def test_empty_payload(self):
        assert sorted_for_cache({}) == {}

    def test_payload_without_sortable_lists(self):
        payload = {"model": "gpt-4o", "temperature": 0.7, "max_tokens": 1024}
        result = sorted_for_cache(payload)
        assert result["model"] == "gpt-4o"
        assert result["temperature"] == 0.7
