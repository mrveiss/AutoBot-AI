# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The route classes the two #20513 guards share, declared once.

``autobot-backend/api/codebase_analytics/endpoints/routes_require_source_20513_test.py``
reads the REGISTERED routes; ``repo_tests/analytics_callers_scope_to_source_20513_test.py``
reads the frontend callers. Both must agree on which paths are not about one source,
so the lists live here and neither test carries a private copy.

A path leaves a list only when its route starts requiring a source; a path joins one
only with a stated reason, because each list is a place a route may legitimately be
sourceless and so a place a defect can hide.
"""

from __future__ import annotations

#: Results that are not about one source. Each carries ``openapi_extra={"x-source-scope":
#: "cross-source"}`` on its route, so the route says so itself.
CROSS_SOURCE_PATHS: frozenset[str] = frozenset(
    {
        "/sources",
        "/sources/summary",
        "/index/queue",
        "/embedding-stats",
        "/env-analysis/default-model",
        "/patterns/tasks",
        # The code-graph collection is not tagged with a code source (#20513); the
        # route states that in every response (`source_scope`).
        "/impact",
    }
)

#: Operations on process-wide or task state, or that create the source itself. ``(method, path)``
#: or a path suffix. A source id cannot be required of "create a source".
OPS_EXACT: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/sources"),
        ("POST", "/embedding-stats/reset"),
        ("POST", "/patterns/tasks/clear-all"),
    }
)
OPS_SUFFIXES: tuple[str, ...] = ("/tasks/clear-stuck",)

#: Routes addressed by a task id: the id was minted for one source's run, and no source can be
#: re-asserted by the caller. Decision recorded on #20513.
TASK_MARKER = "{task_id}"

#: Indexing job controls whose scoping is the second #20513 PR (needs #20491's changes to
#: ``useIndexingJob`` first). Named, with the reason, so they are a tracked gap and not a hole.
DEFERRED_TO_PR2: frozenset[str] = frozenset({"/index/current", "/index/cancel"})

#: Takes EXACTLY ONE of ``source_id`` and ``root_path`` in its body (dev mode keeps ``root_path``).
EXACTLY_ONE_BODY: frozenset[tuple[str, str]] = frozenset({("POST", "/index")})
