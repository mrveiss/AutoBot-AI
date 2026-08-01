# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The shared TeamService is the single implementation (#12647).

`team_service.py` was byte-identical across both backends — 701 duplicated
lines, so a fix reached one service or the other but never both by accident.

These pin the property that matters: both backends resolve to the SAME class
objects, not merely equivalent ones. Two same-named classes are not
interchangeable (the trap #12913 fixed for CircuitState), so identity is the
assertion, not behaviour.
"""

import importlib.util
import pathlib
import sys

import pytest

from autobot_shared.user_management.team_service import (
    DuplicateTeamError,
    MembershipError,
    TeamNotFoundError,
    TeamService,
    TeamServiceError,
)

# parents: [0] user_management, [1] autobot_shared, [2] repo root.
_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SHIMS = {
    "backend": _ROOT / "autobot-backend/user_management/services/team_service.py",
    "slm": _ROOT / "autobot-slm-backend/user_management/services/team_service.py",
}
_EXPORTS = (
    "TeamService",
    "TeamServiceError",
    "TeamNotFoundError",
    "DuplicateTeamError",
    "MembershipError",
)


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("backend", sorted(_SHIMS))
def test_shim_exists(backend):
    assert _SHIMS[backend].is_file(), f"{backend} shim missing"


@pytest.mark.parametrize("backend", sorted(_SHIMS))
def test_shim_resolves_to_the_shared_classes(backend):
    """Same objects, not same-named twins — see #12913."""
    module = _load(_SHIMS[backend], f"team_shim_{backend}")

    assert module.TeamService is TeamService
    assert module.TeamServiceError is TeamServiceError
    assert module.TeamNotFoundError is TeamNotFoundError
    assert module.DuplicateTeamError is DuplicateTeamError
    assert module.MembershipError is MembershipError


def test_both_backends_share_one_implementation():
    a = _load(_SHIMS["backend"], "team_shim_a")
    b = _load(_SHIMS["slm"], "team_shim_b")

    for name in _EXPORTS:
        assert getattr(a, name) is getattr(b, name), f"{name} diverged"


@pytest.mark.parametrize("backend", sorted(_SHIMS))
def test_shim_reexports_the_whole_public_surface(backend):
    """A missing name would break an importer that the move promised not to."""
    module = _load(_SHIMS[backend], f"team_surface_{backend}")

    assert sorted(module.__all__) == sorted(_EXPORTS)
    for name in _EXPORTS:
        assert hasattr(module, name), f"{backend} shim drops {name}"


def test_error_hierarchy_survived_the_move():
    """Callers catch TeamServiceError to cover all three — keep that true."""
    for error in (TeamNotFoundError, DuplicateTeamError, MembershipError):
        assert issubclass(error, TeamServiceError)


def test_service_still_derives_from_the_shared_base():
    """TeamService(BaseService) — the base moved in #12972, this must follow."""
    from autobot_shared.user_management.base_service import BaseService

    assert issubclass(TeamService, BaseService)


def test_membership_roles_are_unchanged():
    """The role vocabulary is persisted data — a rename would be a migration."""
    assert TeamService.ROLE_OWNER == "owner"
    assert TeamService.ROLE_ADMIN == "admin"
    assert TeamService.ROLE_MEMBER == "member"
    assert TeamService.VALID_ROLES == {"owner", "admin", "member"}
