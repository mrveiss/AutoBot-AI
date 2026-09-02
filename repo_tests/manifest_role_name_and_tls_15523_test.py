# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15523 — the reconciler errored every 60 seconds on two schema mismatches.

Both were caught, logged, and retried forever, so nothing ever went red:

1. ``Failed to load manifest for autobot-shared: Role name must start with
   'autobot-': 'autobot_shared'`` — a validator requiring a hyphen against an
   underscored ``role:``. #15523 settles the spelling once rather than
   spot-fixing each site: manifest/Ansible ROLE names are hyphenated, and only
   the Python PACKAGE keeps the underscore, because an import name cannot
   contain a hyphen. Path -> underscore, role -> hyphen, nothing else.
2. ``'ManifestTLS' object has no attribute 'cert'`` — ``reconciler``'s
   cert-expiry check has always read ``tls.cert``, a field the model never
   declared, so the check had never once run on any ``auto_rotate: true`` role.

Guarding the shipped manifests against the real model is what makes either
regression fail here instead of in a log nobody reads.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
INFRA_ROOT = REPO_ROOT / "autobot-infrastructure"
RECONCILER = REPO_ROOT / "autobot-slm-backend/services/reconciler.py"

# Floor. Evaluated before every substantive assertion so a sweep that stopped
# finding manifests fails by name rather than passing on an empty set.
MIN_MANIFESTS = 13


def _manifest_paths() -> list[Path]:
    return sorted(INFRA_ROOT.glob("autobot-*/manifest.yml"))


def _model():
    """Load ``models/manifest.py`` by path — it needs only pydantic."""
    spec = importlib.util.spec_from_file_location(
        "_manifest_15523", REPO_ROOT / "autobot-slm-backend/models/manifest.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_sweep_reaches_the_manifests_it_claims():
    paths = _manifest_paths()
    assert len(paths) >= MIN_MANIFESTS, f"FIX THE SWEEP: only {len(paths)} manifests found under autobot-infrastructure"


def test_every_shipped_manifest_validates_against_the_model():
    """The reconciler's 1105-per-cycle load failure, asserted at the source."""
    paths = _manifest_paths()
    assert len(paths) >= MIN_MANIFESTS, f"FIX THE SWEEP: only {len(paths)} manifests found"
    role_manifest = _model().RoleManifest

    failures: dict[str, str] = {}
    for path in paths:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        try:
            role_manifest.model_validate(raw)
        except Exception as exc:  # noqa: BLE001 — the loader swallows this exact class
            failures[path.parent.name] = str(exc).splitlines()[-1]
    assert failures == {}, f"manifests the reconciler cannot load: {failures}"


def test_role_names_are_hyphenated_everywhere_they_are_referenced():
    """One canonical spelling, decided in #15523 — including dependency edges."""
    paths = _manifest_paths()
    assert len(paths) >= MIN_MANIFESTS, f"FIX THE SWEEP: only {len(paths)} manifests found"

    offenders: dict[str, list[str]] = {}
    for path in paths:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        names = [raw.get("role", "")] + list((raw.get("dependencies") or {}).get("requires") or [])
        bad = [n for n in names if n.startswith("autobot_") or (n.startswith("autobot") and "_" in n)]
        if bad:
            offenders[path.parent.name] = bad
    assert offenders == {}, f"underscored role names (roles use hyphens; only the python package does not): {offenders}"


def test_the_python_package_keeps_its_underscore():
    """The other half of the rule — a path is not a role name."""
    assert (REPO_ROOT / "autobot_shared" / "__init__.py").is_file()
    shared = yaml.safe_load((INFRA_ROOT / "autobot-shared" / "manifest.yml").read_text(encoding="utf-8"))
    assert shared["role"] == "autobot-shared"
    assert shared["deploy"]["source"].rstrip("/") == "autobot_shared"


def test_the_cert_expiry_check_can_read_the_field_it_reads():
    """``ManifestTLS.cert`` was never declared, so this raised every cycle."""
    assert "cert_path = manifest.tls.cert" in RECONCILER.read_text(encoding="utf-8"), (
        "FIX THE SWEEP: the cert-expiry read this guard anchors to has moved"
    )
    tls = _model().ManifestTLS(auto_rotate=True)
    assert tls.cert is None, "an undeclared cert must read as absent, not raise"
    assert _model().ManifestTLS(cert="/etc/ssl/x.pem").cert == "/etc/ssl/x.pem"


def test_an_underscored_role_is_still_rejected_by_the_validator():
    """The validator stays the enforcement point; #15523 fixed the data, not it."""
    with pytest.raises(Exception, match="must start with 'autobot-'"):
        _model().RoleManifest.model_validate(
            {"role": "autobot_shared", "description": "x", "deploy": {"source": "a", "destination": "b"}}
        )
