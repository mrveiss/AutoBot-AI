# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Frozen allowlist of the hand-rolled Redis pipeline doubles that exist today (#18991).

Each key is `<repo path>::<enclosing function>::<class>` (`<module>` at module level; `#2` for a
second same-named class in one function); the value is why it is still hand-rolled. The list may
only SHRINK: a new match fails the guard, and an entry whose class was migrated to
`testkit.fake_redis_pipeline` (or left the tree) fails it too until the line is deleted.
`FROZEN_TOTAL` caps the length.

It is EMPTY: the 18 doubles the #18883 guard had frozen as `NOT-A-SESSION: Redis pipeline double`
all moved onto `FakePipeline` / `FakeAsyncPipeline`, so none needs a recorded reason. A double that
genuinely cannot be expressed by the canonical fake is added here WITH that reason, never skipped.
"""

from __future__ import annotations

ALLOWLIST: dict[str, str] = {}

#: The ceiling. Lower it with the list; never raise it.
FROZEN_TOTAL = 0
