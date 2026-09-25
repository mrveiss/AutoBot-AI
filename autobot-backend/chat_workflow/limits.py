# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One home for the chat workflow's iteration cap (#17468).

The cap had two truths. `ChatWorkflowManager.MAX_CONTINUATION_ITERATIONS = 5`
was the named one, and `graph.py`'s routing decision hardcoded `< 5` beside it.
Both said five, so nothing failed and nothing logged -- the defect only appeared
the day someone raised the constant and observed no effect on the LangGraph
path, because that path never read it.

A duplicated value is invisible precisely while it is still correct. This module
exists so there is one place to change, and both readers reach it here.

Read as a module ATTRIBUTE at the point of use (`limits.MAX_CONTINUATION_ITERATIONS`),
not bound into each caller's namespace at import. Binding the value at import
recreates the problem in a smaller form: each importer would hold its own copy,
a test could patch one and not the other, and the two would agree only by
accident of ordering.
"""

from __future__ import annotations

from autobot_shared.env_utils import env_int

#: Maximum multi-step continuation iterations for one turn (#352, #17468).
#: Env-backed per the project's configuration rule -- a budget written as a bare
#: literal cannot be changed without a deploy, and this one is a safety limit.
MAX_CONTINUATION_ITERATIONS: int = env_int("AUTOBOT_MAX_CONTINUATION_ITERATIONS", default=5)
