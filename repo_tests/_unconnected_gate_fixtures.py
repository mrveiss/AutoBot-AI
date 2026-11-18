# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Planted-tree fixtures shared by the unconnected-code gate tests (#20512, #20910).

Each test plants files under ``tmp_path`` and judges them with the real detectors, the scripts loaded from the
repository. Everything that is not the subject sits outside the judged backend trees, or it would itself be an
unconnected module.
"""

from __future__ import annotations

import functools
from pathlib import Path

from repo_tests import _unconnected_code as uc
from repo_tests import _unconnected_routes as routes
from repo_tests._paths import repo_root
from repo_tests._unconnected_common import Tree


@functools.lru_cache(maxsize=2)
def _state(root: Path) -> tuple[Tree, routes.Audit]:
    return Tree.of_repo(root), routes.Audit(root, scripts_root=repo_root())


def _plant(tmp_path: Path, files: dict[str, str]) -> tuple[Tree, routes.Audit]:
    for rel, body in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(body, encoding="utf-8")
    tree = Tree(list(files), lambda rel: (tmp_path / rel).read_text(encoding="utf-8"))
    return tree, routes.Audit(tmp_path, scripts_root=repo_root())


def _fired(tmp_path: Path, files: dict[str, str]) -> set[str]:
    tree, audit = _plant(tmp_path, files)
    return uc.detected(tree, audit)


_ROUTER = (
    'from fastapi import APIRouter\nrouter = APIRouter(prefix="/{prefix}")\n\n\n'
    '@router.{verb}("/{path}")\nasync def h():\n    return {{}}\n'
)
_ROUTE = {"autobot-backend/api/planted_route.py": _ROUTER.format(prefix="planted", verb="get", path="orphan")}
#: Imports every planted module, so the subject under test is the route, queue or table and not its file.
_WIRED = {"scripts/wire.py": "import api.planted_route\nimport api.planted_hook\nimport services.planted_queue\n"}
