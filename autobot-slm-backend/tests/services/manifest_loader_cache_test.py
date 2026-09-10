# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for ManifestLoader cache configuration (Issue #16026).

Two defects, and they fail in opposite directions. The TTL was a bare literal
in a repo that bans hardcoded TTLs, so it could not be tuned on the host that
edits the manifests. And the per-role bypass existed but was unreachable from
``load_all()``, which is the method ``services/reconciler.py`` actually calls —
an override a caller cannot get at is not an override, so the reconciler was
stuck behind the cache regardless of what ``load()`` supported.

``tests/services/conftest.py`` registers ``services`` and ``models`` as
real-path packages, so ``services.manifest_loader`` imports without executing
the heavy ``services/__init__.py`` chain.
"""

from services.manifest_loader import ManifestLoader, _resolve_manifest_cache_ttl

_ENV = "SLM_MANIFEST_CACHE_TTL"


class TestTtlResolution:
    """The TTL comes from the environment, and a bad value never takes the service down."""

    def test_unset_uses_the_documented_default(self, monkeypatch) -> None:
        monkeypatch.delenv(_ENV, raising=False)
        assert _resolve_manifest_cache_ttl() == 300

    def test_blank_is_treated_as_unset(self, monkeypatch) -> None:
        """ssot-style knobs arrive as "" when declared but not set, and int("") raises."""
        monkeypatch.setenv(_ENV, "")
        assert _resolve_manifest_cache_ttl() == 300

    def test_an_integer_is_honoured(self, monkeypatch) -> None:
        monkeypatch.setenv(_ENV, "60")
        assert _resolve_manifest_cache_ttl() == 60

    def test_zero_is_honoured_rather_than_falling_back(self, monkeypatch) -> None:
        """0 is the dev-mode bypass, so it must survive as 0 and not read as unset."""
        monkeypatch.setenv(_ENV, "0")
        assert _resolve_manifest_cache_ttl() == 0

    def test_a_non_integer_warns_and_falls_back(self, monkeypatch, caplog) -> None:
        """A typo in a tuning knob must not crash the import of the loader."""
        monkeypatch.setenv(_ENV, "5 minutes")
        with caplog.at_level("WARNING"):
            assert _resolve_manifest_cache_ttl() == 300
        assert _ENV in caplog.text, "a rejected value must say so; silently defaulting hides the typo"


class TestBypassIsReachable:
    """`load_all` must be able to reach the bypass `load` already had (#16026)."""

    def test_load_all_threads_force_reload_through(self, tmp_path, monkeypatch) -> None:
        (tmp_path / "autobot-example").mkdir()
        loader = ManifestLoader(infra_base=tmp_path)

        seen: list[bool] = []

        def _record(role_name: str, *, force_reload: bool = False):
            seen.append(force_reload)
            return None

        monkeypatch.setattr(loader, "load", _record)

        loader.load_all(force_reload=True)
        assert seen == [True], (
            "load_all did not pass force_reload down — reconciler.py reads the whole "
            "set through this method, so a bypass it cannot reach does not exist for it"
        )

    def test_load_all_defaults_to_using_the_cache(self, tmp_path, monkeypatch) -> None:
        """The default must stay cached; the bypass is opt-in, not the new normal."""
        (tmp_path / "autobot-example").mkdir()
        loader = ManifestLoader(infra_base=tmp_path)

        seen: list[bool] = []

        def _record(role_name: str, *, force_reload: bool = False):
            seen.append(force_reload)
            return None

        monkeypatch.setattr(loader, "load", _record)

        loader.load_all()
        assert seen == [False]
