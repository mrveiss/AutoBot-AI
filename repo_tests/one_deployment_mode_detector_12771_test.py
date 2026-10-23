# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One deployment-mode decision, in the shared core (#12771 item 3).

`detect_deployment_mode` replaced two decision bodies: the backend's config-driven one and
the deploy scripts' env + `/.dockerenv` one. The table below encodes what EACH old detector
returned for every input combination and requires the shared function to agree with both.
Guard: no `_detect_deployment_mode` outside the shared function may decide a mode itself.
"""

from __future__ import annotations

import ast
import itertools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.service_registry_core import DeploymentMode as M
from autobot_shared.service_registry_core import detect_deployment_mode

_ROOT = repo_root()
_SCAN = ("autobot-backend", "autobot-infrastructure")
_EXPLICIT = (None, *M)


def _old_backend(explicit, in_container, kubernetes, distributed):
    """Old backend body: explicit valid mode; container -> k8s/distributed/docker; host -> local."""
    if explicit:
        return explicit
    if in_container:
        return M.KUBERNETES if kubernetes else (M.DISTRIBUTED if distributed else M.DOCKER_LOCAL)
    return M.LOCAL  # old host branch tested config == "distributed", already returned above as explicit


def _old_scripts(explicit, in_container):
    """Old scripts body: valid env mode, else DOCKER_LOCAL in a container, else LOCAL."""
    return explicit or (M.DOCKER_LOCAL if in_container else M.LOCAL)


@pytest.mark.parametrize(
    "explicit,in_container,kubernetes,distributed",
    itertools.product(_EXPLICIT, (False, True), (False, True), (False, True)),
)
def test_matches_old_backend_detector(explicit, in_container, kubernetes, distributed):
    got = detect_deployment_mode(explicit, in_container, kubernetes, distributed)
    assert got == _old_backend(explicit, in_container, kubernetes, distributed)


@pytest.mark.parametrize("explicit,in_container", itertools.product(_EXPLICIT, (False, True)))
def test_matches_old_scripts_detector(explicit, in_container):
    got = detect_deployment_mode(explicit, in_container, kubernetes=False, distributed=False)
    assert got == _old_scripts(explicit, in_container)


def test_literal_expectations() -> None:
    assert detect_deployment_mode(None, False, True, True) is M.LOCAL
    assert detect_deployment_mode(None, True, True, True) is M.KUBERNETES
    assert detect_deployment_mode(None, True, False, True) is M.DISTRIBUTED
    assert detect_deployment_mode(None, True, False, False) is M.DOCKER_LOCAL
    assert detect_deployment_mode(M.CLOUD, True, True, True) is M.CLOUD


#: The shared functions a thin ``_detect_deployment_mode`` may delegate to (#19372 added the resolver).
_DELEGATES = {"detect_deployment_mode", "resolve_deployment_mode"}


def _forking_detectors(source: str) -> list[str]:
    """`_detect_deployment_mode` defs that do not delegate, or that return a mode themselves."""
    bad = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.FunctionDef) and node.name == "_detect_deployment_mode"):
            continue
        calls = {c.func.id for c in ast.walk(node) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
        decides = any(
            isinstance(r, ast.Return)
            and r.value is not None
            and any(
                isinstance(a, ast.Attribute) and isinstance(a.value, ast.Name) and a.value.id == "DeploymentMode"
                for a in ast.walk(r.value)
            )
            for r in ast.walk(node)
        )
        if not calls & _DELEGATES or decides:
            bad.append(node.name)
    return bad


def _scanned_files(root: Path) -> list[str]:
    """Every .py file under the scanned trees; empty on a tree that lacks them."""
    return sorted(str(p.relative_to(root)) for r in _SCAN if (root / r).is_dir() for p in (root / r).rglob("*.py"))


#: Files the no-second-decision-body sweep reads -- a scan of ~0 files is a broken glob.
#: Migrated from a hand-rolled ``MIN_FILES_SCANNED = 300`` (#16147); pinned mid-window.
SCAN_REACH = declare(
    "deployment-mode-detector-scan",
    discover=_scanned_files,
    floor=5076,  # re-pinned mid-window (train 82 on main)
    growth=150,
    what="python files scanned for a second deployment-mode decision body",
    roots=("autobot-backend/", "autobot-infrastructure/"),
)
MIN_DETECTORS_SEEN = 2  # backend registry + scripts registry, each still defines the thin wrapper


def test_no_second_decision_body_in_tree() -> None:
    offenders, scanned, seen = [], 0, 0
    for root in _SCAN:
        for path in (_ROOT / root).rglob("*.py"):
            scanned += 1
            text = path.read_text(encoding="utf-8")
            if "_detect_deployment_mode" not in text:
                continue
            seen += 1
            if _forking_detectors(text):
                offenders.append(str(path.relative_to(_ROOT)))
    assert scanned >= SCAN_REACH.floor and len(SCAN_REACH.examined(_ROOT)) >= SCAN_REACH.floor, scanned
    assert seen >= MIN_DETECTORS_SEEN, seen
    assert not offenders, offenders


def test_guard_flags_a_forked_body() -> None:
    forked = "class R:\n    def _detect_deployment_mode(self):\n        return DeploymentMode.LOCAL\n"
    thin = "class R:\n    def _detect_deployment_mode(self):\n        return detect_deployment_mode(None, False, False, False)\n"
    assert _forking_detectors(forked) and not _forking_detectors(thin)
