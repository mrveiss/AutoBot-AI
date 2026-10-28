# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Where the knowledge indexers keep their hash caches: the shared user cache, never the repo (#19553).

One location per checkout, shared by its worktrees (#16934). Resolved on first use, never at
import: resolving keys the cache by checkout with a git call, and importing a module must not
spawn a subprocess (repo_tests/import_hermeticity_test.py).
"""

from pathlib import Path

from autobot_shared.paths import shared_cache_path


def doc_index_hashes(override: Path | None = None) -> Path:
    """The doc indexer's hash cache, or *override* when a caller or a test pins one."""
    return override or shared_cache_path("autobot-doc-index", ".doc_index_hashes.json")


def code_index_hashes() -> Path:
    """The code indexer's hash cache."""
    return shared_cache_path("autobot-code-index", ".code_index_hashes.json")
