# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""autobot_shared/pyproject.toml names what constraints/shared.txt versions, and restates no floor (#20092)."""

from __future__ import annotations

import tomllib

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from repo_tests._paths import repo_root


def _constrained(text: str) -> set[str]:
    lines = (line.split("#")[0].strip() for line in text.splitlines())
    return {canonicalize_name(Requirement(line).name) for line in lines if line}


def restated_floors(pyproject: str, constraints: str) -> list[str]:
    owned = _constrained(constraints)
    requirements = map(Requirement, tomllib.loads(pyproject)["project"]["dependencies"])
    return [str(r) for r in requirements if canonicalize_name(r.name) in owned and r.specifier]


def test_the_shared_package_restates_no_constrained_floor() -> None:
    root = repo_root()
    constraints = (root / "constraints/shared.txt").read_text(encoding="utf-8")
    assert len(_constrained(constraints)) >= 9, "constraints/shared.txt parsed to almost nothing"
    pyproject = (root / "autobot_shared/pyproject.toml").read_text(encoding="utf-8")
    assert restated_floors(pyproject, constraints) == []


def test_a_planted_restated_floor_is_flagged() -> None:
    pyproject = '[project]\ndependencies = ["Starlette>=0.27.0", "other>=1", "fastapi"]\n'
    assert restated_floors(pyproject, "# note\nstarlette>=1.10.0  # why\nfastapi>=0.1\n") == ["Starlette>=0.27.0"]
