# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The local self-update socket's permissions ARE its authentication (#15728).

``/self-update`` on the local admin app carries no auth dependency, deliberately:
reachability over the inherited fd is supposed to prove the caller is on the host
*and* allowed to open the socket. That second half is enforced by three lines in a
systemd unit -- ``SocketMode=``, ``SocketUser=``, ``SocketGroup=`` -- and by the
mode default they interpolate.

So a later edit widening that mode to ``0666``, or dropping ``SocketGroup=``, does
not break a test, does not fail a lint, and does not look wrong in review: it hands
an unauthenticated update trigger to every process on the box. This file is the
thing that fails.

It asserts the shipped configuration, and -- via ``test_a_world_accessible_mode_is
_rejected`` -- that the predicate doing the asserting actually rejects the bad
value. Without that contrast case, a predicate that accepted everything would pass
here and report the socket as safe.
"""

import re
from pathlib import Path

_ROLE = Path(__file__).resolve().parents[1] / "autobot-slm-backend/ansible/roles/slm_manager"
_DEFAULTS = _ROLE / "defaults/main.yml"
_UNIT = _ROLE / "templates/autobot-slm-self-update.socket.j2"

_MODE_KEY = "slm_self_update_socket_mode"


def _mode_is_world_accessible(mode: str) -> bool:
    """True when the "other" digit of an octal file mode grants anything.

    A Unix socket needs write to be usable, but read or execute bits set for
    "other" are equally a sign the mode was widened, so any non-zero digit fails.
    """
    digits = mode.strip().strip("\"'")
    if not re.fullmatch(r"0?[0-7]{3}", digits):
        raise AssertionError(f"{_MODE_KEY} is not a 3-digit octal mode: {mode!r}")
    return digits[-1] != "0"


def _defaults_mode() -> str:
    for line in _DEFAULTS.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{_MODE_KEY}:"):
            return line.split(":", 1)[1].strip()
    raise AssertionError(f"{_MODE_KEY} is not defined in {_DEFAULTS.name}")


def test_the_shipped_socket_mode_grants_nothing_to_other():
    """The default mode must not be readable or writable by "other"."""
    mode = _defaults_mode()
    assert not _mode_is_world_accessible(mode), (
        f"{_MODE_KEY} is {mode} -- the local self-update socket carries no "
        "authentication, so a world-accessible mode hands an unauthenticated "
        "update trigger to every process on the host (#15728)"
    )


def test_a_world_accessible_mode_is_rejected():
    """Contrast case: the predicate must actually reject a widened mode.

    Pairs with the test above. A predicate that returned False unconditionally
    would pass that one while reporting a wide-open socket as safe.
    """
    assert _mode_is_world_accessible("0666")
    assert _mode_is_world_accessible("0664")
    assert not _mode_is_world_accessible("0660")
    assert not _mode_is_world_accessible("0600")


def test_the_socket_unit_pins_owner_and_group():
    """Mode alone is meaningless without an owner and group to apply it to.

    ``SocketMode=0660`` on a socket systemd creates as ``root:root`` would lock
    the service's own user out; dropped entirely, the mode applies to whatever
    the default happens to be. Both directives must be present.
    """
    unit = _UNIT.read_text(encoding="utf-8")
    for directive in ("SocketMode=", "SocketUser=", "SocketGroup=", "ListenStream="):
        assert directive in unit, f"{_UNIT.name} is missing {directive} (#15728)"


def test_the_socket_unit_removes_a_stale_socket_on_stop():
    """``RemoveOnStop`` keeps a file from a previous boot from lingering.

    A leftover socket path is not merely untidy: the next start may bind beside
    it or inherit a file whose permissions were set by an older configuration.
    """
    assert "RemoveOnStop=true" in _UNIT.read_text(encoding="utf-8")
