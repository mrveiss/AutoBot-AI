# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The awareness middleware must match paths the app actually serves (#15120).

``enable_for_paths`` defaulted to ``/api/intelligent-agent``. The router is
mounted at ``/api/intelligent_agent``, so ``_should_inject_context`` — a
``startswith`` over that list — returned ``False`` for every request to it, and
the middleware silently did nothing for a router it names explicitly. Nothing
errored: a path filter that matches nothing looks exactly like a path filter
whose paths were not requested.

The hyphen was copied from ``api/registry.py``, which advertised
``/api/intelligent-agent`` while the app mounted the underscore — the "wrong
path gets copied into new client code" failure #15120 was filed about, landing
inside the backend rather than in a client.

These assert the *served* paths, cross-checked against the generated OpenAPI
schema, so a future rename that moves the router reddens this file
instead of quietly disabling the middleware again.
"""

from __future__ import annotations

import pytest

from middleware.llm_awareness_middleware import LLMAwarenessMiddleware


def _middleware() -> LLMAwarenessMiddleware:
    """The middleware as ``initialization/middleware.py`` installs it: no arguments.

    Constructing it with an explicit path list would test the argument rather
    than the default, and the default is what production runs.
    """
    return LLMAwarenessMiddleware.__new__(LLMAwarenessMiddleware)


def _configure(mw: LLMAwarenessMiddleware) -> LLMAwarenessMiddleware:
    LLMAwarenessMiddleware.__init__(mw, app=None)
    return mw


class _Request:
    """The two attributes ``_should_inject_context`` reads."""

    def __init__(self, path: str, method: str = "POST") -> None:
        self.method = method
        self.url = type("_Url", (), {"path": path})()


#: Real POST paths, taken from the mounted prefixes in
#: ``initialization/router_registry/`` and present in the generated OpenAPI
#: schema. Every one of these must reach the middleware.
SERVED_PATHS = [
    "/api/intelligent_agent/process",
    "/api/intelligent_agent/reload",
    "/api/chat/message",
    "/api/llm/generate",
]

#: Paths no router answers on — the shape of the defect. Matching one of these
#: means the filter is keyed on something the app does not serve.
UNSERVED_PATHS = [
    "/api/intelligent-agent/process",
    "/api/agent-config/agents",
]


def test_the_path_list_is_populated():
    """Non-vacuity: an empty default would make every case below trivially true."""
    paths = _configure(_middleware()).enable_for_paths

    assert len(paths) >= 4, f"enable_for_paths holds {paths!r}; the cases below range over nothing"


@pytest.mark.parametrize("path", SERVED_PATHS)
def test_a_served_path_reaches_the_middleware(path):
    mw = _configure(_middleware())

    assert mw._should_inject_context(_Request(path)), (
        f"{path} is mounted and serves POST, but the awareness filter skips it; "
        f"enable_for_paths={mw.enable_for_paths!r}"
    )


@pytest.mark.parametrize("path", UNSERVED_PATHS)
def test_a_path_nothing_serves_is_not_what_the_filter_is_keyed_on(path):
    """The contrast. Without it, a list holding *both* spellings would pass above."""
    mw = _configure(_middleware())

    assert not mw._should_inject_context(_Request(path)), (
        f"the awareness filter matches {path}, which no router answers on — "
        f"it is keyed on a path that does not exist; enable_for_paths={mw.enable_for_paths!r}"
    )


def test_only_post_requests_are_considered():
    """Guards the method check the two lists above would otherwise not exercise."""
    mw = _configure(_middleware())

    assert not mw._should_inject_context(_Request("/api/intelligent_agent/process", method="GET"))
