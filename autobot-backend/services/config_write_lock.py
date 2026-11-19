# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one lock around ConfigService's read-modify-write config writers (#18478).

Held for the whole read-modify-write of ``ConfigService.update_llm_config``,
``update_redis_config``, ``save_full_config`` and ``update_backend_settings``,
the agent-config writes (model/provider update, enable, disable; #21742), and by
the config rollback across its live read, apply and read. Reentrant, so the inner
``_save_config_to_file`` takes it again on the same thread. It does not cover
writes made straight through ``config_manager`` by other routes (developer,
embeddings, auth), and is a threading lock: never hold it across an await.
"""

import functools
import threading

CONFIG_WRITE_LOCK = threading.RLock()


def locked_config_write(func):
    """Run *func* with the config write lock held for its whole body."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with CONFIG_WRITE_LOCK:
            return func(*args, **kwargs)

    return wrapper
