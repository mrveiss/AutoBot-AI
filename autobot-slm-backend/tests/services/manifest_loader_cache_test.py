# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for ManifestLoader cache behaviour (Issue #16026).

Two defects, failing in opposite directions. The TTL was a bare literal in a
repo that bans hardcoded TTLs, so it could not be tuned on the host that edits
the manifests. And the per-role bypass existed but was unreachable from
``load_all()``, which is the method ``services/reconciler.py`` actually calls --
an override a caller cannot get at is not an override.

These tests patch ``_load_from_disk`` rather than ``load``, so the real caching
condition in ``load`` executes and is counted. Patching ``load`` would replace
the code under test: the first version of this file did exactly that, and the
``_CACHE_TTL > 0`` clause -- the dev-mode bypass this issue is named for -- was
asserted by none of its seven tests.

The TTL *parsing* has no tests here on purpose: it is
``autobot_shared.env_utils.env_int``, which owns its own coverage. Testing it
again would be testing a dependency.

``tests/services/conftest.py`` registers ``services`` and ``models`` as
real-path packages, so this imports without executing ``services/__init__.py``.
"""

from services import manifest_loader
from services.manifest_loader import ManifestLoader

_SENTINEL = object()


def _counting_loader(tmp_path, monkeypatch):
    """A loader whose disk reads are counted; the cache logic in `load` is real."""
    (tmp_path / "autobot-example").mkdir()
    loader = ManifestLoader(infra_base=tmp_path)
    reads: list[str] = []

    def _from_disk(role_name: str):
        reads.append(role_name)
        return _SENTINEL

    monkeypatch.setattr(loader, "_load_from_disk", _from_disk)
    return loader, reads


class TestCachingHonoursTheTtl:
    """The `_CACHE_TTL > 0` clause is the dev-mode bypass (#16026)."""

    def test_a_positive_ttl_serves_the_second_read_from_cache(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(manifest_loader, "_CACHE_TTL", 300)
        loader, reads = _counting_loader(tmp_path, monkeypatch)

        loader.load("autobot-example")
        loader.load("autobot-example")

        assert reads == ["autobot-example"], "a positive TTL must serve the second read from cache"

    def test_a_zero_ttl_disables_caching_entirely(self, tmp_path, monkeypatch) -> None:
        """The bypass for editing a manifest on the SLM host."""
        monkeypatch.setattr(manifest_loader, "_CACHE_TTL", 0)
        loader, reads = _counting_loader(tmp_path, monkeypatch)

        loader.load("autobot-example")
        loader.load("autobot-example")

        assert reads == ["autobot-example", "autobot-example"], (
            "SLM_MANIFEST_CACHE_TTL=0 must re-read every time — this is the dev-mode "
            "bypass the issue is named for, and a cached hit here defeats it"
        )

    def test_a_negative_ttl_also_disables_caching(self, tmp_path, monkeypatch) -> None:
        """`<= 0`, not `== 0`: a misconfigured -1 must not re-enable the cache."""
        monkeypatch.setattr(manifest_loader, "_CACHE_TTL", -1)
        loader, reads = _counting_loader(tmp_path, monkeypatch)

        loader.load("autobot-example")
        loader.load("autobot-example")

        assert len(reads) == 2

    def test_force_reload_bypasses_a_live_cache(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(manifest_loader, "_CACHE_TTL", 300)
        loader, reads = _counting_loader(tmp_path, monkeypatch)

        loader.load("autobot-example")
        loader.load("autobot-example", force_reload=True)

        assert len(reads) == 2, "force_reload must re-read even inside a live TTL window"


class TestBypassIsReachableFromLoadAll:
    """`reconciler.py:2167` reads the whole set through `load_all` (#16026)."""

    def test_load_all_reaches_the_bypass(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(manifest_loader, "_CACHE_TTL", 300)
        loader, reads = _counting_loader(tmp_path, monkeypatch)

        loader.load_all()
        loader.load_all(force_reload=True)

        assert len(reads) == 2, (
            "load_all did not reach the bypass — the reconciler reads the whole set "
            "through this method, so a bypass it cannot reach does not exist for it"
        )

    def test_load_all_defaults_to_using_the_cache(self, tmp_path, monkeypatch) -> None:
        """The bypass is opt-in; the default must not quietly become no-caching."""
        monkeypatch.setattr(manifest_loader, "_CACHE_TTL", 300)
        loader, reads = _counting_loader(tmp_path, monkeypatch)

        loader.load_all()
        loader.load_all()

        assert len(reads) == 1
