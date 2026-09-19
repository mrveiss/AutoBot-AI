#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Follow-up to ssot_config_defaults_13264_test.py (#13264): the 22-field
gateway/SMTP/MCP-isolation/codebase-indexing/provider-vLLM batch. The
ssot_config.py size ratchet is down-only, so this class does not fit under
ssot_config_test.py either. See tools/lint/check_getenv_ssot_drift.py's
module docstring for the per-field evidence and pre-#7437 verification this
fix was drawn from.
"""

import os
from unittest.mock import patch


class TestGatewaySmtpMcpCodebaseProviderDefaultsRestored13264:
    """#13264 batch 2: 22 more defaults the #7437 migration silently dropped.

    Restored to the literal the pre-#7437 ``os.getenv(NAME, DEFAULT)`` call
    site actually shipped, re-verified against ``git show 122793bbf``'s
    pre-image (not carried over from the issue's table unchecked).
    """

    def test_gateway_defaults(self) -> None:
        from autobot_shared.ssot_config import MiscConfig

        with patch.dict(os.environ, {}, clear=True):
            cfg = MiscConfig(_env_file=None)
            assert cfg.gateway_rate_limit_user == 60
            assert cfg.gateway_rate_limit_channel == 100
            assert cfg.gateway_session_timeout == 1800
            assert cfg.gateway_max_message_size == 1024 * 1024
            assert cfg.gateway_max_sessions_user == "5"
            assert cfg.gateway_heartbeat_interval == "30"
            assert cfg.gateway_message_retention_hours == "24"

    def test_smtp_defaults(self) -> None:
        from autobot_shared.ssot_config import MiscConfig

        with patch.dict(os.environ, {}, clear=True):
            cfg = MiscConfig(_env_file=None)
            assert cfg.smtp_host == "localhost"
            assert cfg.smtp_port == 587
            assert cfg.smtp_from == "autobot@localhost"
            assert cfg.smtp_tls == "true"

    def test_mcp_defaults(self) -> None:
        from autobot_shared.ssot_config import MiscConfig

        with patch.dict(os.environ, {}, clear=True):
            cfg = MiscConfig(_env_file=None)
            assert cfg.mcp_isolation_mode == "inprocess"
            assert cfg.mcp_worker_log_level == "INFO"

    def test_codebase_indexing_defaults(self) -> None:
        from autobot_shared.ssot_config import MiscConfig

        with patch.dict(os.environ, {}, clear=True):
            cfg = MiscConfig(_env_file=None)
            assert cfg.codebase_index_embed_batch_size == 100
            assert cfg.codebase_index_parallel_files == "50"
            assert cfg.codebase_scan_parallel_files == "50"

    def test_provider_and_vllm_defaults(self) -> None:
        from autobot_shared.ssot_config import MiscConfig

        with patch.dict(os.environ, {}, clear=True):
            cfg = MiscConfig(_env_file=None)
            assert cfg.anthropic_api_base_url == "https://api.anthropic.com/v1"
            assert cfg.vllm_host == "http://127.0.0.1:8000"
            assert cfg.openrouter_default_model == "gpt-3.5-turbo"
            assert cfg.vllm_dtype == "auto"
            assert cfg.vllm_gpu_memory_utilization == "0.9"
            assert cfg.vllm_tensor_parallel_size == 1
