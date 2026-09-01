# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A broken secrets store is observable everywhere it matters (#14126).

The defect was uniform silence. Three surfaces each answered a store fault with
a value that reads as "everything is fine, there is simply nothing here":

* ``_load_secrets_hosts`` returned ``[]`` - identical to "no hosts configured"
* ``_resolve_token`` returned ``None`` - which sent the caller to
  ``_build_clone_url``, downgrading an authenticated clone to an anonymous one
* the health surface said nothing at all, because no probe watched the store

Each test below breaks the store deliberately and asserts the caller can *tell* -
the property the issue asks for. Structured as three explicit failure modes
rather than one, because they fail differently in production: a missing file is
a fresh install, a permission error is a misconfigured deployment, and a decrypt
failure is a rotated or corrupted key.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest


class _BrokenStore(RuntimeError):
    """Stands in for whatever the store raises; the callers must not care."""


def _exploding(*_args: Any, **_kwargs: Any) -> Any:
    raise _BrokenStore("simulated store fault")


# ---------------------------------------------------------------------------
# The hosts path
# ---------------------------------------------------------------------------


def test_the_hosts_loader_raises_rather_than_returning_an_empty_list(monkeypatch) -> None:
    """`[]` and "the store is broken" must not be the same answer."""
    from security.secrets_store_errors import SecretsStoreUnavailable

    import api.secrets as secrets_module
    import api.infrastructure as infra

    monkeypatch.setattr(secrets_module.secrets_manager, "list_secrets", _exploding)

    with pytest.raises(SecretsStoreUnavailable) as excinfo:
        infra._load_secrets_hosts()

    # The original fault is preserved for the logs, not swallowed.
    assert isinstance(excinfo.value.__cause__, _BrokenStore)
    assert excinfo.value.what == "infrastructure host secrets"


def test_a_healthy_but_empty_store_still_returns_an_empty_list(monkeypatch) -> None:
    """The other direction, and the reason the fix is not simply 'raise more'.

    A fresh install genuinely has no hosts. If this had been collapsed into the
    failure case, every new deployment would report a broken secrets store.
    """
    import api.secrets as secrets_module
    import api.infrastructure as infra

    monkeypatch.setattr(secrets_module.secrets_manager, "list_secrets", lambda *a, **k: [])

    assert infra._load_secrets_hosts() == []


def test_only_infrastructure_host_secrets_become_hosts(monkeypatch) -> None:
    """Guard the guard: a loader that returned [] for everything would pass the
    empty-store test above while being just as broken as the original."""
    import api.secrets as secrets_module
    import api.infrastructure as infra

    monkeypatch.setattr(
        secrets_module.secrets_manager,
        "list_secrets",
        lambda *a, **k: [
            {"id": "s1", "type": "api_key", "name": "not a host"},
            {"id": "s2", "type": "infrastructure_host", "name": "a host", "metadata": {}},
        ],
    )

    hosts = infra._load_secrets_hosts()

    assert [h["id"] for h in hosts] == ["s2"]


# ---------------------------------------------------------------------------
# The clone path
# ---------------------------------------------------------------------------


def test_a_clone_needing_a_token_fails_rather_than_going_anonymous(monkeypatch) -> None:
    from security.secrets_store_errors import SecretsStoreUnavailable

    import api.secrets as secrets_module
    from api.codebase_analytics.endpoints import sources

    monkeypatch.setattr(secrets_module.secrets_manager, "get_secret", _exploding)

    with pytest.raises(SecretsStoreUnavailable):
        asyncio.run(sources._resolve_token("some-credential"))


def test_a_missing_credential_is_still_a_token_less_clone(monkeypatch) -> None:
    """Absent is not broken.

    ``get_secret`` returning ``None`` means the credential was never configured,
    and an anonymous clone of a public repo is the correct behaviour. Only a
    *fault* must raise - otherwise the fix would break every public clone.
    """
    import api.secrets as secrets_module
    from api.codebase_analytics.endpoints import sources

    monkeypatch.setattr(secrets_module.secrets_manager, "get_secret", lambda *a, **k: None)

    assert asyncio.run(sources._resolve_token("never-configured")) is None


def test_the_clone_url_carries_no_credential_when_there_is_no_token() -> None:
    from api.codebase_analytics.endpoints import sources

    assert "@" not in sources._build_clone_url("owner/repo", None)


# ---------------------------------------------------------------------------
# The health surface
# ---------------------------------------------------------------------------


def test_the_health_probe_reports_degraded_when_the_store_is_unreadable(monkeypatch) -> None:
    """The gap the earlier fix left: the two callers above only speak when
    something calls them. An operator reading the health page while nobody
    happens to be listing hosts saw a fully healthy system."""
    import api.secrets as secrets_module
    from api.secrets_store_health import _secrets_store_health_probe

    monkeypatch.setattr(secrets_module.secrets_manager, "list_secrets", _exploding)

    component = asyncio.run(_secrets_store_health_probe(None))

    assert component.status == "degraded"
    assert component.detail is not None
    # Not "down": the platform is up, and conflating the two is how a health
    # page stops being read.
    assert component.status != "down"


def test_the_probe_detail_leaks_no_store_internals(monkeypatch) -> None:
    """The payload is served to anyone who can reach the health endpoint."""
    import api.secrets as secrets_module
    from api.secrets_store_health import _secrets_store_health_probe

    def _leaky(*_a: Any, **_k: Any) -> Any:
        raise _BrokenStore("cannot decrypt /some/internal/path/secrets.enc with key kid-4718")

    monkeypatch.setattr(secrets_module.secrets_manager, "list_secrets", _leaky)

    detail = asyncio.run(_secrets_store_health_probe(None)).detail or ""

    assert "/some/internal/path" not in detail
    assert "kid-4718" not in detail
    assert "_BrokenStore" in detail  # the type name is enough to reach the logs


def test_the_probe_reports_ok_for_a_readable_store(monkeypatch) -> None:
    import api.secrets as secrets_module
    from api.secrets_store_health import _secrets_store_health_probe

    monkeypatch.setattr(secrets_module.secrets_manager, "list_secrets", lambda *a, **k: [])

    assert asyncio.run(_secrets_store_health_probe(None)).status == "ok"


def test_the_probe_module_is_imported_at_startup() -> None:
    """A probe nobody imports reports nothing, and would pass every test above.

    Registration is an import side effect, so importing the module inside a test
    proves only that the decorator runs - it says nothing about the running
    application. This asserts the startup import exists, statically, without
    booting the backend. Same technique as test_router_load_visibility_14207.
    """
    from pathlib import Path

    registry = (
        Path(__file__).resolve().parents[2]
        / "autobot-backend/initialization/router_registry/core_routers.py"
    )
    source = registry.read_text(encoding="utf-8")

    assert "import api.secrets_store_health" in source, (
        "core_routers.py does not import api.secrets_store_health, so the probe "
        "never registers in the running app and the health surface stays silent "
        "about a broken store - the exact gap this issue is about."
    )


def test_the_probe_registers_under_the_canonical_name() -> None:
    import api.secrets_store_health  # noqa: F401 - registration is an import side effect
    from api.system_health import KnownProbes, list_registered_probes

    assert KnownProbes.SECRETS_STORE.value in list_registered_probes()
