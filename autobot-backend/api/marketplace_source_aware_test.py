# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#6524: regression tests for source-aware install + detail endpoints.

Pin the fix: ``install_plugin`` and ``get_catalog_entry`` must resolve
against the same catalog the user was browsing — they were both hard-wired
to the built-in catalog via ``_get_catalog()``, which made every install
from a user-added marketplace 404.
"""

import inspect


def test_install_request_has_source_id_field():
    """``InstallRequest`` must accept ``source_id`` so the API can route
    the install to the correct catalog.

    Default = ``BUILTIN_SOURCE_ID`` so existing builtin-only callers don't
    break — opt-in for custom-marketplace installs.
    """
    from api.schemas_workflows import InstallRequest

    fields = InstallRequest.model_fields
    assert (
        "source_id" in fields
    ), "#6524: InstallRequest.source_id missing — install endpoint cannot route to custom catalogs"
    # Default ensures backward compat: a body with only `plugin_name` still
    # validates and resolves against the built-in catalog.
    default = fields["source_id"].default
    assert default == "builtin", f"Expected builtin default; got {default!r}"


def test_resolve_catalog_helper_exists():
    """The shared resolver must exist so list/detail/install all share
    the same source-routing logic — preventing future drift like the
    original #6524 split-brain (list source-aware; install was not).
    """
    from api import marketplace as mod

    assert hasattr(mod, "_resolve_catalog"), "#6524: shared `_resolve_catalog` helper missing"
    assert inspect.iscoroutinefunction(mod._resolve_catalog), "_resolve_catalog must be async"


def test_get_catalog_entry_takes_source_id_query_param():
    """Detail endpoint must accept ``?source_id=`` so deep-links from a
    custom marketplace catalog work.
    """
    from api.marketplace import get_catalog_entry

    sig = inspect.signature(get_catalog_entry)
    assert "source_id" in sig.parameters, "#6524: get_catalog_entry must accept source_id Query param"


def test_install_plugin_takes_install_request_body():
    """``install_plugin`` body type must be ``InstallRequest`` so the new
    ``source_id`` field arrives. Pin against accidental signature drift
    (e.g. someone replacing it with a plain dict body).
    """
    from api.marketplace import install_plugin
    from api.schemas_workflows import InstallRequest

    sig = inspect.signature(install_plugin)
    body_param = sig.parameters.get("body")
    assert body_param is not None, "#6524: install_plugin must keep `body` parameter"
    assert (
        body_param.annotation is InstallRequest
    ), f"#6524: body annotation must be InstallRequest; got {body_param.annotation!r}"


def test_install_plugin_no_longer_hardcoded_to_builtin_catalog():
    """The bug shape was ``catalog = await _get_catalog()`` inside
    ``install_plugin`` (and ``get_catalog_entry``) — flat call against the
    built-in catalog regardless of which marketplace the user was browsing.

    Pin against re-introduction: install_plugin source must call
    ``_resolve_catalog`` (which routes by source_id), not ``_get_catalog``.
    """
    from api.marketplace import install_plugin

    src = inspect.getsource(install_plugin)
    assert "_resolve_catalog" in src, (
        "#6524 regression: install_plugin must call _resolve_catalog(source_id), "
        "not the legacy _get_catalog() that returned only the built-in catalog."
    )
    # Original bug shape: bare `_get_catalog()` call without arguments.
    assert "await _get_catalog()" not in src, (
        "#6524 regression: install_plugin must NOT use `await _get_catalog()` — "
        "that's the bug shape that hard-coded routing to the built-in catalog."
    )


def test_get_catalog_entry_no_longer_hardcoded_to_builtin_catalog():
    """Same regression guard for the detail endpoint."""
    from api.marketplace import get_catalog_entry

    src = inspect.getsource(get_catalog_entry)
    assert "_resolve_catalog" in src, "#6524: get_catalog_entry must call _resolve_catalog"
    assert "await _get_catalog()" not in src, "#6524: get_catalog_entry must NOT use bare _get_catalog()"
