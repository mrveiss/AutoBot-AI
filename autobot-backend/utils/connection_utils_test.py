# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Regression tests for connection_utils.py config-access AttributeError (#12069).

Same root cause as #11971 (worker_node.py): the module previously imported
the SSOT `AutoBotConfig` proxy (`from config import config`, attribute-access
only) under the name `global_config_manager`, then called `.get()` /
`.get_nested()` on it — both raise AttributeError because the SSOT proxy has
no such methods. Fixed by importing the legacy `config_manager` instance
instead (`from config import config_manager as global_config_manager`),
which does implement `.get()` / `.get_nested()` / `.get_llm_config()`
(backed by config.yaml + defaults.py).
"""

import pytest

from utils.connection_utils import ConnectionTester, ModelManager, global_config_manager


class TestGlobalConfigManagerApi:
    """Directly exercise every config lookup used by connection_utils.py."""

    def test_get_nested_backend_ollama_endpoint(self):
        """Line ~140 call site: global_config_manager.get_nested(...)."""
        result = global_config_manager.get_nested("backend.ollama_endpoint", "default-endpoint")
        assert result is not None

    def test_get_nested_backend_ollama_model(self):
        """Line ~145 call site: global_config_manager.get_nested(...)."""
        result = global_config_manager.get_nested("backend.ollama_model", "default-model")
        assert result is not None

    def test_get_task_transport(self):
        """Line ~232 call site: global_config_manager.get("task_transport", {})."""
        result = global_config_manager.get("task_transport", {})
        assert isinstance(result, dict)

    def test_get_backend_llm_nested_chain(self):
        """Line ~125 call site: global_config_manager.get("backend", {}).get("llm", {})."""
        llm_config = global_config_manager.get("backend", {}).get("llm", {})
        assert isinstance(llm_config, dict)

    def test_get_memory_config(self):
        """Line ~241 call site: global_config_manager.get("memory", {})."""
        result = global_config_manager.get("memory", {})
        assert isinstance(result, dict)

    def test_get_llm_config_method(self):
        """Line ~336 call site: global_config_manager.get_llm_config()."""
        result = global_config_manager.get_llm_config()
        assert isinstance(result, dict)

    def test_get_llm_config_key(self):
        """Line ~444 call site: global_config_manager.get("llm_config", {})."""
        result = global_config_manager.get("llm_config", {})
        assert isinstance(result, dict)

    def test_get_nested_llm_config_ollama(self):
        """Line ~491 call site: global_config_manager.get_nested("llm_config.ollama", {})."""
        result = global_config_manager.get_nested("llm_config.ollama", {})
        assert isinstance(result, dict)


class TestConnectionTesterConfigCallSites:
    """Exercise the actual ConnectionTester helpers that read config."""

    def test_get_ollama_config_from_new_structure(self):
        endpoint, model = ConnectionTester._get_ollama_config_from_new_structure()
        assert endpoint is None or isinstance(endpoint, str)
        assert model is None or isinstance(model, str)

    def test_get_ollama_config_fallback(self):
        endpoint, model = ConnectionTester._get_ollama_config_fallback(None, None)
        assert isinstance(endpoint, str)
        assert isinstance(model, str)

    def test_get_redis_config_values(self):
        host, port, error = ConnectionTester._get_redis_config_values()
        assert error is None or isinstance(error, dict)
        if error is None:
            assert host is not None
            assert port is not None


@pytest.mark.asyncio
class TestConnectionTesterAsyncConfigCallSites:
    """Async helpers whose config lookups previously raised AttributeError."""

    async def test_get_embedding_status_no_attribute_error(self, caplog):
        # Network access to a real Ollama instance is not guaranteed in the
        # test sandbox, so this only asserts the config lookup itself
        # (llm_config.get("unified", {}).get("embedding", {})) never raises
        # AttributeError — any network failure surfaces as a distinct log
        # message, not "'AutoBotConfig' object has no attribute ...".
        status = await ConnectionTester._get_embedding_status()
        assert isinstance(status, dict)
        assert "has no attribute" not in caplog.text
        assert "AttributeError" not in caplog.text

    async def test_get_available_models_no_attribute_error(self):
        result = await ModelManager.get_available_models()
        assert result["status"] == "success"

    async def test_get_ollama_models_no_attribute_error(self):
        # Returns [] on connection failure, but must not raise/log AttributeError.
        models = await ModelManager._get_ollama_models()
        assert isinstance(models, list)
