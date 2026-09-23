# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A code-source repo_path may only name a path inside an allowed root (#17300).

CodeQL alerts 452 and 453. `repo_path` arrives from a POST body (default
`/opt/autobot`) and reached `Path(...).is_dir()` and `.iterdir()` with no
confinement, so any authenticated user could test whether an arbitrary path
exists on the host and — via the typo suggestion, before it was removed — learn
one real filename from any directory.

These routes are gated by `get_current_user` only, **not** by an admin role.
That is what made this worth confining rather than accepting: the capability is
not restricted to operators today.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from api._code_source_paths import _ALLOWED_ROOTS_ENV, _allowed_repo_roots, _confined_repo_path


@pytest.fixture(autouse=True)
def _default_roots(monkeypatch):
    monkeypatch.delenv(_ALLOWED_ROOTS_ENV, raising=False)


def test_unset_defers_to_the_path_validators_own_default():
    """No second copy of the default root here. `path_validator` owns it, and a
    restated literal is a value that can drift from the one enforced."""
    from autobot_shared.security import path_validator

    assert _allowed_repo_roots() is None
    assert "/opt/autobot" in path_validator._DEFAULT_ALLOWED_ROOTS


def test_a_path_inside_the_allowed_root_is_accepted():
    """The contrast. Without it, a confinement that rejected everything passes."""
    assert str(_confined_repo_path("/opt/autobot")) == "/opt/autobot"


@pytest.mark.parametrize(
    "probe",
    ["/etc", "/root", "/home", "/opt", "/opt/autobot/../../etc", "../../etc", ""],
    ids=["etc", "root", "home", "parent-of-root", "traversal", "relative", "empty"],
)
def test_a_path_outside_the_allowed_roots_is_refused(probe):
    with pytest.raises(HTTPException) as exc:
        _confined_repo_path(probe)
    assert exc.value.status_code == 400


def test_the_refusal_does_not_echo_the_probed_path():
    """A caller who supplied the path knows it; one probing does not need
    confirmation that it was understood."""
    with pytest.raises(HTTPException) as exc:
        _confined_repo_path("/etc/shadow")
    assert "/etc/shadow" not in str(exc.value.detail)


def test_an_operator_can_widen_the_roots(monkeypatch):
    """The escape hatch has to work, or a checkout outside /opt/autobot is
    unusable and somebody deletes the confinement instead."""
    monkeypatch.setenv(_ALLOWED_ROOTS_ENV, "/opt/autobot,/srv/code")
    assert _allowed_repo_roots() == ["/opt/autobot", "/srv/code"]
    assert str(_confined_repo_path("/srv/code")) == "/srv/code"


def test_widening_does_not_allow_everything(monkeypatch):
    monkeypatch.setenv(_ALLOWED_ROOTS_ENV, "/srv/code")
    with pytest.raises(HTTPException):
        _confined_repo_path("/opt/autobot")
