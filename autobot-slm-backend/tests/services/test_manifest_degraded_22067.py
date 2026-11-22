# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Stale or missing role manifests degrade the SLM, they never stop it importing (#22067).

#16025 made a manifest-backed role with no loaded manifest raise at import of ``services.role_registry``.
An install whose manifest directory predates ``sync_target`` then could not start its SLM, the one service that
can update it. These tests pin: the import survives, the cause is recorded for /api/health and the deploy
refusals, the strict mode still raises, and the loader reads the git code source rather than the stale copy.
"""

import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

from services import manifest_loader as ml
from services import role_manifest_shape as rms
from services.manifest_loader import ManifestLoader
from services.role_manifest_errors import MANIFEST_ERRORS, manifest_errors, no_manifest_preflight

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_STALE = "role: autobot-backend\ndescription: x\ndeploy:\n  source: autobot-backend/\n  destination: /x/\n"
_FRESH = _STALE + '  sync_target: "{base_dir}"\n'
_STATIC = [{"name": "backend", "systemd_service": "autobot-backend"}]
_PLACEHOLDERS = {"base_dir": "/b", "agent_dir": "/a"}


def _write(infra: Path, text: str) -> Path:
    (infra / "autobot-backend").mkdir(parents=True)
    (infra / "autobot-backend" / "manifest.yml").write_text(text, encoding="utf-8")
    return infra


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    rms._default_roles_cache.clear()
    saved = dict(MANIFEST_ERRORS)
    MANIFEST_ERRORS.clear()
    yield
    MANIFEST_ERRORS.clear()
    MANIFEST_ERRORS.update(saved)
    rms._default_roles_cache.clear()


def _use_loader(monkeypatch, infra: Path) -> None:
    monkeypatch.setattr(ml, "get_manifest_loader", lambda: ManifestLoader(infra_base=infra))


@pytest.mark.parametrize("text", [_STALE, None], ids=["stale-without-sync_target", "empty-manifest-set"])
def test_a_role_without_a_usable_manifest_is_left_out_and_reported(monkeypatch, tmp_path, text):
    infra = _write(tmp_path / "infra", text) if text else tmp_path
    _use_loader(monkeypatch, infra)
    assert rms.default_roles_for(_STATIC, _PLACEHOLDERS, degrade=True) == []
    assert "autobot-backend" in manifest_errors()["backend"]
    assert not rms._default_roles_cache, "a degraded build must be retried, not cached"


def test_the_strict_mode_still_raises_and_records_nothing(monkeypatch, tmp_path):
    _use_loader(monkeypatch, _write(tmp_path / "infra", _STALE))
    with pytest.raises(rms.RoleManifestMissingError):
        rms.default_roles_for(_STATIC, _PLACEHOLDERS)
    assert manifest_errors() == {}


def test_a_fresh_manifest_leaves_no_error_and_is_cached(monkeypatch, tmp_path):
    _use_loader(monkeypatch, _write(tmp_path / "infra", _FRESH))
    roles = rms.default_roles_for(_STATIC, _PLACEHOLDERS, degrade=True)
    assert [r["name"] for r in roles] == ["backend"] and manifest_errors() == {}


def test_the_registry_imports_against_stale_manifests_and_names_the_roles(tmp_path):
    """The real import, in a fresh interpreter: what the failing install ran."""
    infra = tmp_path / "infra"
    for role in ("autobot-backend", "autobot-slm-backend"):
        (infra / role).mkdir(parents=True)
        (infra / role / "manifest.yml").write_text(_STALE.replace("autobot-backend", role), encoding="utf-8")
    env = {
        **os.environ,
        "SLM_INFRA_BASE_DIR": str(infra),
        "PYTHONPATH": os.pathsep.join([str(_BACKEND_ROOT), str(_BACKEND_ROOT.parent)]),
    }
    code = (
        "import services.role_registry as r; from services.role_manifest_errors import manifest_errors; "
        "print(sorted(manifest_errors())); print(len(r.DEFAULT_ROLES))"
    )
    done = subprocess.run(
        [sys.executable, "-c", code], cwd=_BACKEND_ROOT, env=env, capture_output=True, text=True, timeout=120
    )
    assert done.returncode == 0, done.stderr[-2000:]
    assert "slm-backend" in done.stdout


def test_an_affected_role_is_refused_in_the_preflight_and_an_unaffected_one_is_not_blamed(monkeypatch):
    fake = types.SimpleNamespace(PreflightResult=lambda **kw: kw, PreflightConflict=lambda **kw: kw)
    monkeypatch.setitem(sys.modules, "models.schemas", fake)
    MANIFEST_ERRORS["backend"] = "no manifest"
    refused = no_manifest_preflight("n1", "backend")
    assert refused["allowed"] is False and refused["conflicts"][0]["detail"] == "no manifest"
    assert no_manifest_preflight("n1", "tts-worker")["allowed"] is True


def test_the_git_code_source_beats_the_installs_stale_copy_when_the_unit_leaves_code_source_unset(tmp_path):
    """AUTOBOT_CODE_SOURCE unset: code_source resolves to the base dir itself, whose own copy is stale."""
    base = tmp_path
    _write(base / "autobot-infrastructure", _STALE)
    _write(base / "code_source" / "autobot-infrastructure", _FRESH)
    git_copy = base / "code_source" / "autobot-infrastructure"
    assert ml.resolve_infra_base(override="", code_source=base, base_dir=base) == git_copy
    assert ml.candidate_infra_roots(override="", code_source=base, base_dir=base)[0] == git_copy


def test_an_explicit_code_source_and_a_checkout_are_unchanged(tmp_path):
    _write(tmp_path / "cs" / "autobot-infrastructure", _FRESH)
    _write(tmp_path / "base" / "autobot-infrastructure", _STALE)
    cs, base = tmp_path / "cs", tmp_path / "base"
    assert ml.resolve_infra_base(override="", code_source=cs, base_dir=base) == cs / "autobot-infrastructure"
    # a checkout: no code_source directory beside the root, so the root's own copy stands
    assert ml.resolve_infra_base(override="", code_source=base, base_dir=base) == base / "autobot-infrastructure"
