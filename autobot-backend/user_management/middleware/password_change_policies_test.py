# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Each password-change surface gets the policy intended for it (#15757).

Two classes named ``PasswordChangeRateLimiter`` existed in different modules with
different policies -- 5 attempts per 300s on the session auth surface, 3 per 1800s
on the user-management surface. Both were reachable by that one name, so a reader
at the call site could not tell which they had, and an edit to "the" limiter's
policy could land on the wrong surface entirely.

The names now say which surface they guard. This pins the policies so that a
future edit to one cannot silently apply to the other -- which is the failure the
shared name made invisible rather than merely confusing.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _import_with_env(env_var: str, value: str, attribute: str) -> int:
    """Read the attribute from a FRESH interpreter with *env_var* set.

    Reloading in-process was tried first and poisoned the suite twice:
    `sys.modules` is process-global, so the module reloaded under a patched env
    stayed installed for every later test -- `rate_limit_test` failed asserting
    `expire(..., 1800)` against the 900 set here, and then failed differently
    when the reloaded instance replaced shared state. `monkeypatch.setitem` put
    the module object back and still did not help, because the damage is the
    reload itself, not the mapping entry.

    A subprocess has its own `sys.modules`. Nothing this test does can reach the
    one running it.
    """
    source = (
        "import sys; sys.path[:0] = [%r, %r]\n"
        "from user_management.middleware.rate_limit import TargetedPasswordChangeRateLimiter as L\n"
        "print(getattr(L, %r))" % (str(BACKEND), str(REPO_ROOT), attribute)
    )
    result = subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        env={**os.environ, env_var: value},
        cwd=str(BACKEND),
        timeout=60,
    )
    assert result.returncode == 0, f"import failed: {result.stderr[-400:]}"
    return int(result.stdout.strip())


def test_the_two_surfaces_have_distinct_limiter_names() -> None:
    """The defect itself: one name, two policies, no way to tell them apart.

    Asserted by NAME rather than by policy value, because the values are meant to
    be tunable and the distinguishability is not.
    """
    from user_management.middleware.rate_limit import TargetedPasswordChangeRateLimiter

    assert TargetedPasswordChangeRateLimiter.__name__ == "TargetedPasswordChangeRateLimiter"
    assert not hasattr(
        __import__("user_management.middleware.rate_limit", fromlist=["*"]),
        "PasswordChangeRateLimiter",
    ), "the ambiguous name is back -- a call site can no longer tell which surface it is limiting"


def test_the_targeted_surface_is_stricter_than_the_session_surface() -> None:
    """The policies differ ON PURPOSE, and the direction is the load-bearing part.

    The targeted limiter covers an admin resetting another user's password, where
    repeated attempts against one victim is the threat. The session limiter guards
    a self-service form where a mistyped current password is the common case.

    If a future edit makes the targeted surface *looser* than the session one, the
    higher-value path has become the easier one to brute-force -- so this asserts
    the ORDERING, not the literals, and keeps failing however the values are tuned.
    """
    from user_management.middleware.rate_limit import TargetedPasswordChangeRateLimiter

    session_attempts = int(os.environ.get("AUTOBOT_PASSWORD_CHANGE_SESSION_MAX_ATTEMPTS", "5"))
    session_window = int(os.environ.get("AUTOBOT_PASSWORD_CHANGE_SESSION_WINDOW_SECONDS", "300"))

    assert TargetedPasswordChangeRateLimiter.MAX_ATTEMPTS <= session_attempts, (
        f"the targeted surface now allows {TargetedPasswordChangeRateLimiter.MAX_ATTEMPTS} attempts against the "
        f"session surface's {session_attempts}. Admin reset of another user's password must not be easier to "
        "brute-force than a self-service change."
    )
    assert TargetedPasswordChangeRateLimiter.WINDOW_SECONDS >= session_window, (
        f"the targeted window is now {TargetedPasswordChangeRateLimiter.WINDOW_SECONDS}s against the session "
        f"surface's {session_window}s. A shorter window means attempts refill faster on the higher-value path."
    )


@pytest.mark.parametrize(
    ("env_var", "attribute", "value"),
    [
        ("AUTOBOT_PASSWORD_CHANGE_TARGETED_MAX_ATTEMPTS", "MAX_ATTEMPTS", "7"),
        ("AUTOBOT_PASSWORD_CHANGE_TARGETED_WINDOW_SECONDS", "WINDOW_SECONDS", "900"),
    ],
)
def test_the_targeted_policy_is_env_backed_not_a_literal(env_var: str, attribute: str, value: str) -> None:
    """AC3, proven by CHANGING the value rather than by reading the source.

    A test that greps for `os.environ` proves the call was written. Setting the
    variable and importing proves it is read -- the distinction between a config
    knob and a literal with a comment next to it.
    """
    assert _import_with_env(env_var, value, attribute) == int(
        value
    ), f"{attribute} ignored {env_var} -- the value is still effectively a literal"
