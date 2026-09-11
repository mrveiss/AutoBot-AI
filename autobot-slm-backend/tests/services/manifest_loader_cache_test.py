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


def _switchable_loader(tmp_path, monkeypatch):
    """Like `_counting_loader`, but the disk read can be made to fail on demand."""
    (tmp_path / "autobot-example").mkdir()
    loader = ManifestLoader(infra_base=tmp_path)
    state = {"fail": False, "reads": 0}

    def _from_disk(role_name: str):
        state["reads"] += 1
        return None if state["fail"] else _SENTINEL

    monkeypatch.setattr(loader, "_load_from_disk", _from_disk)
    return loader, state


class TestAFailedReadLeavesNoStaleEntry:
    """A failed disk read evicts rather than retains (#16204).

    Each of these fails against the code before #16204, which only wrote the
    cache on success and never removed an entry when a read failed.
    """

    def test_a_failed_forced_reload_does_not_leave_the_old_manifest_serving(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(manifest_loader, "_CACHE_TTL", 300)
        loader, state = _switchable_loader(tmp_path, monkeypatch)

        assert loader.load("autobot-example") is _SENTINEL
        state["fail"] = True
        assert loader.load("autobot-example", force_reload=True) is None

        assert loader.load("autobot-example") is not _SENTINEL, (
            "a plain load() after a failed forced reload served the pre-reload manifest "
            "from cache — the caller that forced the reload was told it failed, and "
            "every later caller inside the TTL is told the old answer"
        )

    def test_an_expired_entry_whose_reload_fails_is_removed(self, tmp_path, monkeypatch) -> None:
        """Asserted on cache state, because this case has no other observable effect.

        An expired entry is never served, so retaining it changes no return value —
        it only leaves `_cache` holding a manifest the disk no longer backs.
        """
        monkeypatch.setattr(manifest_loader, "_CACHE_TTL", 300)
        loader, state = _switchable_loader(tmp_path, monkeypatch)
        role = "autobot-example"

        loader.load(role)
        manifest, loaded_at = loader._cache[role]
        loader._cache[role] = (manifest, loaded_at - 10_000)
        state["fail"] = True

        assert loader.load(role) is None
        assert role not in loader._cache, "an expired entry whose reload failed was retained"

    def test_a_successful_read_after_a_failure_caches_again(self, tmp_path, monkeypatch) -> None:
        """The success path is unchanged: it caches, and a fresh entry is served without disk."""
        monkeypatch.setattr(manifest_loader, "_CACHE_TTL", 300)
        loader, state = _switchable_loader(tmp_path, monkeypatch)
        role = "autobot-example"

        loader.load(role)
        state["fail"] = True
        loader.load(role, force_reload=True)
        state["fail"] = False

        assert loader.load(role) is _SENTINEL
        assert loader.load(role) is _SENTINEL
        assert state["reads"] == 3, "the recovered entry must be served from cache, not re-read"


class TestLoadAllTellsAbsentFromFailed:
    """`load_all` must not signal a failed read only by a shorter dict (#16204 AC3).

    Pins behaviour already present in `_load_from_disk`: a missing manifest logs at
    DEBUG, a manifest that fails to parse or validate logs a WARNING naming the role.
    Uses real files, because patching `_load_from_disk` would remove the logging
    under test.
    """

    def test_a_broken_manifest_warns_by_name_and_a_missing_one_does_not(self, tmp_path, caplog) -> None:
        (tmp_path / "autobot-broken").mkdir()
        (tmp_path / "autobot-broken" / "manifest.yml").write_text("role: [unclosed\n", encoding="utf-8")
        (tmp_path / "autobot-empty").mkdir()
        loader = ManifestLoader(infra_base=tmp_path)

        caplog.set_level("DEBUG")
        result = loader.load_all()

        assert "autobot-broken" not in result and "autobot-empty" not in result
        warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
        debugs = [r.getMessage() for r in caplog.records if r.levelname == "DEBUG"]
        assert any(
            "autobot-broken" in m for m in warnings
        ), f"a manifest that failed to load produced no WARNING naming its role: {warnings}"
        assert not any("autobot-empty" in m for m in warnings), "an absent manifest must not read as a failure"
        assert any("autobot-empty" in m for m in debugs), "an absent manifest must still be recorded, at DEBUG"
