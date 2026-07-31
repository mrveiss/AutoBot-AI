# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Host-side guard for undelivered role-owned changes (#12959).

The companion test ``test_update_all_applies_roles_12959.py`` inspects the
playbook in CI. It cannot see a host, so it stays green while a box runs code
whose role-owned half never arrived — which is exactly how #12777, #12886 and
#12907 were closed on merge evidence while remaining absent from a live node.

These tests pin the probe that closes that half, and in particular the two
judgement calls it makes:

  * a **missing** artifact is skipped, not failed — a component that is not
    installed here has nothing to deliver, and reporting it would train
    operators to ignore the signal;
  * a **present but stale** artifact is failed — that is the real #12959 case.

Modules are loaded past the suite's session-global ``services`` stub, following
``test_self_update_log_reader.py``; without that every assertion here would pass
vacuously against MagicMock attributes.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _load(module_name: str, alias: str):
    """Load ``services/<module_name>.py`` for real, past the services stub."""
    saved = sys.modules.get("autobot_shared.logging_manager")
    sys.modules["autobot_shared.logging_manager"] = MagicMock()
    try:
        spec = importlib.util.spec_from_file_location(alias, _BACKEND_ROOT / "services" / f"{module_name}.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[alias] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        if saved is None:
            sys.modules.pop("autobot_shared.logging_manager", None)
        else:
            sys.modules["autobot_shared.logging_manager"] = saved


_probe = _load("role_delivery_probe", "_rdp_12959")
_reader = _load("self_update_log_reader", "_sulr_12959")

CONTAINS = _probe.CONTAINS
UNIQUE_KEY = _probe.UNIQUE_KEY
probe_role_delivery = _probe.probe_role_delivery
RoleInvariant = _probe.RoleInvariant
SelfUpdateVerdict = _reader.SelfUpdateVerdict

_PW_KEY = "AUTOBOT_DB" + "_PASSWORD"  # split so secret scanners ignore the literal


def _inv(artifact: Path, kind: str = CONTAINS, marker: str = "MARKER") -> RoleInvariant:
    return RoleInvariant(
        role="backend",
        issue="#12777",
        artifact=artifact,
        kind=kind,
        marker=marker,
        describes="artifact is missing the role-owned change",
    )


def test_present_and_satisfied_is_not_degraded(tmp_path: Path) -> None:
    artifact = tmp_path / "unit.service"
    artifact.write_text("Environment=MARKER=1\n", encoding="utf-8")

    verdict = probe_role_delivery([_inv(artifact)])

    assert verdict.checked == 1
    assert verdict.undelivered == []
    assert not verdict.degraded


def test_present_but_stale_is_reported_as_undelivered(tmp_path: Path) -> None:
    artifact = tmp_path / "unit.service"
    artifact.write_text("Environment=SOMETHING_ELSE=1\n", encoding="utf-8")

    verdict = probe_role_delivery([_inv(artifact)])

    assert verdict.degraded
    assert verdict.undelivered == ["backend (#12777): artifact is missing the role-owned change"]
    assert "#12959" in (verdict.reason or "")


def test_missing_artifact_is_skipped_not_failed(tmp_path: Path) -> None:
    """A component absent from this host must not read as a failed update."""
    verdict = probe_role_delivery([_inv(tmp_path / "never-installed.service")])

    assert verdict.skipped == 1
    assert verdict.checked == 0
    assert not verdict.degraded, "absence must not be reported as undelivered"


def test_duplicate_key_is_undelivered_but_single_key_is_not(tmp_path: Path) -> None:
    """The #12907 case: an append-only store keeps a stale first copy."""
    store = tmp_path / "db-credentials.env"
    store.write_text(f"{_PW_KEY}=stale\nAUTOBOT_DB_USER=app\n{_PW_KEY}=current\n", encoding="utf-8")
    dup = probe_role_delivery([_inv(store, UNIQUE_KEY, _PW_KEY)])
    assert dup.degraded, "duplicate keys must be reported"

    store.write_text(f"{_PW_KEY}=current\n", encoding="utf-8")
    single = probe_role_delivery([_inv(store, UNIQUE_KEY, _PW_KEY)])
    assert not single.degraded, "a consolidated store must pass"


def test_key_match_is_anchored_not_substring(tmp_path: Path) -> None:
    """A differently-prefixed key must not be counted as a duplicate."""
    store = tmp_path / "db-credentials.env"
    store.write_text(f"{_PW_KEY}=current\nSLM_{_PW_KEY}=other\n", encoding="utf-8")

    verdict = probe_role_delivery([_inv(store, UNIQUE_KEY, _PW_KEY)])

    assert not verdict.degraded, "only line-anchored keys count toward the duplicate check"


def test_unreadable_artifact_never_raises(tmp_path: Path) -> None:
    """A status endpoint must answer even when an artifact cannot be read."""
    directory = tmp_path / "a-directory"
    directory.mkdir()

    verdict = probe_role_delivery([_inv(directory)])

    assert verdict.skipped == 1
    assert not verdict.degraded


@pytest.mark.parametrize("log_complete", [True, False])
def test_undelivered_roles_degrade_even_a_clean_run(log_complete: bool) -> None:
    """The whole point: a playbook that finished cleanly can still deliver nothing."""
    verdict = SelfUpdateVerdict(log_present=True, complete=log_complete)
    assert verdict.degraded is not log_complete  # baseline before the flag

    verdict.role_delivery_incomplete = True

    assert verdict.degraded, "undelivered role changes must degrade regardless of the log"
