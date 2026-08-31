# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``route_query_params``, shared by ``sdk_request_url_test.py`` and
``sdk_request_signature_params_test.py`` (#15187).

Lives here rather than in ``sdk_request_shared.py`` alongside the plain
constants and functions those two files import: pytest finds a fixture by
scanning ``conftest.py``, not by an import being referenced elsewhere as an
expression, and the local ``autoflake`` pre-commit hook
(``.pre-commit-config.yaml``, unscoped to ``repo_tests/``) removes any import
it cannot see used that way. Importing a fixture by name into a second test
module for reuse -- the usual way to share one without a ``conftest.py`` --
would be stripped on the next commit; a fixture defined here needs no import
in either test module at all.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from autobot_shared.api_routing import router_prefixes as routing
from repo_tests.sdk_request_shared import _BACKEND, _BACKEND_API_ROOT

#: Backend modules serving the paths ``SDK_REQUESTS`` (``sdk_request_shared.py``)
#: names. Only these are imported, so the oracle costs one small app rather
#: than the whole backend.
#:
#: This list cannot go stale unnoticed: the app built from it is asked for every
#: path in ``SDK_REQUESTS``, so a module missing here shows up as a path the spec
#: does not contain, and ``test_every_sdk_request_path_is_in_the_query_oracle``
#: (``sdk_request_url_test.py``) fails naming it.
SERVING_MODULES: tuple[str, ...] = (
    "api.agent",
    "api.agent_config",
    "api.analytics",
    "api.chat_sessions",
    "api.knowledge",
    "api.knowledge_search",
)


@pytest.fixture(scope="module")
def route_query_params() -> dict[tuple[str, str], frozenset[str]]:
    """``(METHOD, path template) -> declared query parameter names``.

    Built through ``fastapi.openapi.utils.get_openapi`` on an app that mounts the
    modules above exactly as ``app_factory`` mounts them -- ``/api`` + the prefix
    ``initialization/router_registry`` gives that module. Deliberately **not** a
    walk over ``router.routes``: from ``fastapi>=0.139`` ``include_router`` records
    an opaque wrapper instead of copying the child's routes onto the parent, so a
    flat walk finds almost nothing and every assertion over it passes vacuously.
    CI pins 0.141.1 and a development checkout may resolve below 0.139, so a local
    pass would prove nothing about the runner (#15091, #15093). ``get_openapi`` is
    the view FastAPI itself serves ``/openapi.json`` from and answers the same on
    both shapes.

    The mount prefixes are read from the registry rather than written here, so a
    router that moves is followed rather than silently mismatched.

    ``scope="module"``: each test module that requests this fixture builds its
    own copy (this file is now shared by two), rather than the one build the
    single original file used to get -- a small, deliberate cost of the split.
    """
    registry = dict(routing.registry_entries(_BACKEND / "initialization" / "router_registry"))
    assert registry, "the router registry parsed no entries -- the oracle below would have nothing to mount"

    app = FastAPI()
    for module_path in SERVING_MODULES:
        assert module_path in registry, f"{module_path} is not mounted by initialization/router_registry"
        app.include_router(
            importlib.import_module(module_path).router, prefix=f"{_BACKEND_API_ROOT}{registry[module_path]}"
        )

    spec = get_openapi(title="sdk-request-oracle", version="1", routes=app.routes)
    declared: dict[tuple[str, str], frozenset[str]] = {}
    for path, operations in spec.get("paths", {}).items():
        for verb, operation in operations.items():
            names = {p["name"] for p in operation.get("parameters", []) if p.get("in") == "query"}
            declared[(verb.upper(), path)] = frozenset(names)

    assert declared, "the oracle enumerated no routes at all; every assertion below would pass vacuously"
    assert any(names for names in declared.values()), (
        "no route in the oracle declares a single query parameter. Either the mounted set is wrong or "
        "the parameter extraction is -- an oracle where everything accepts nothing cannot detect a wrong name."
    )
    return declared
