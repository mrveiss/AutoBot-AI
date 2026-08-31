#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Split out of ssot_config_test.py (#13264): the size ratchet on that file
is down-only, and this class does not fit under it. See
tools/lint/check_getenv_ssot_drift.py for the systemic guard and the #13264
issue comment for the full measured comparison this fix was drawn from.
"""

import os
from unittest.mock import patch


class TestMemoryAndCacheDefaultsRestored13264:
    """#13264: the #7437 migration silently dropped these ten defaults too.

    All ten are read unguarded at their live call site (no ``or``/``is not
    None`` fallback rescues them — two of the bool fields sit behind an
    ``is not None`` guard in config/defaults.py that can never fire for a
    field whose own default is False, not None, which is documented at each
    Field declaration in ssot_config.py). Restored to the literal the
    pre-#7437 ``os.getenv(NAME, DEFAULT)`` call site actually shipped,
    verified against ``git show 122793bbf``.
    """

    def test_memory_optimization_defaults(self) -> None:
        from autobot_shared.ssot_config import MiscConfig

        with patch.dict(os.environ, {}, clear=True):
            cfg = MiscConfig(_env_file=None)
            assert cfg.log_max_bytes == 52428800
            assert cfg.log_backup_count == 5
            assert cfg.memory_pool_size == 100
            assert cfg.weak_cache_size == 128
            assert cfg.cache_size == 128
            assert cfg.memory_threshold_mb == 500
            assert cfg.memory_log_threshold_mb == 1

    def test_chat_timeout_default(self) -> None:
        from autobot_shared.ssot_config import MiscConfig

        with patch.dict(os.environ, {}, clear=True):
            assert MiscConfig(_env_file=None).chat_timeout == 30

    def test_cache_and_vllm_bool_defaults(self) -> None:
        from autobot_shared.ssot_config import MiscConfig

        with patch.dict(os.environ, {}, clear=True):
            cfg = MiscConfig(_env_file=None)
            assert cfg.cache_enabled is True
            assert cfg.vllm_async_output is True
            assert cfg.vllm_prefix_caching == "true"
