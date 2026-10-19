# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Clock-skew leeway of jwt_core.decode_jwt (#18792).

A backward wall-clock step between encode and decode (WSL2) or skew between
hosts put ``iat`` ahead of the verifier's clock; PyJWT rejected it at leeway 0.
Leeway applies to ``iat``/``nbf`` only; ``exp`` stays strict.
"""

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest

from autobot_shared.auth import jwt_core
from autobot_shared.auth.jwt_core import JWTDecodeError, JWTExpiredError, decode_jwt

_SECRET = "test-secret-key-for-unit-tests-only-32chars"  # pragma: allowlist secret
_ENV = "AUTOBOT_JWT_CLOCK_SKEW_LEEWAY_SECONDS"
_LEEWAY = 5


@pytest.fixture(autouse=True)
def _leeway(monkeypatch):
    monkeypatch.setattr(jwt_core, "CLOCK_SKEW_LEEWAY_SECONDS", _LEEWAY)


def _token(iat_offset: float = 0, exp_offset: float = 3600, **extra) -> str:
    now = datetime.now(tz=timezone.utc)
    claims = {
        "sub": "alice",
        "iat": now + timedelta(seconds=iat_offset),
        "exp": now + timedelta(seconds=exp_offset),
        **extra,
    }
    return jwt.encode(claims, _SECRET, algorithm="HS256")


def test_iat_slightly_in_future_is_accepted() -> None:
    assert decode_jwt(_token(iat_offset=2), secret=_SECRET)["sub"] == "alice"


def test_iat_slightly_in_future_is_accepted_on_audience_path() -> None:
    token = _token(iat_offset=2, aud="autobot-device")
    assert decode_jwt(token, secret=_SECRET, audience="autobot-device")["sub"] == "alice"


def test_iat_in_future_is_rejected_at_zero_leeway(monkeypatch) -> None:
    monkeypatch.setattr(jwt_core, "CLOCK_SKEW_LEEWAY_SECONDS", 0)
    with pytest.raises(JWTDecodeError):
        decode_jwt(_token(iat_offset=2), secret=_SECRET)


def test_iat_beyond_leeway_is_rejected() -> None:
    with pytest.raises(JWTDecodeError):
        decode_jwt(_token(iat_offset=_LEEWAY + 2), secret=_SECRET)


def _nbf(offset: float) -> datetime:
    return datetime.now(tz=timezone.utc) + timedelta(seconds=offset)


def test_nbf_slightly_in_future_is_accepted() -> None:
    assert decode_jwt(_token(nbf=_nbf(2)), secret=_SECRET)["sub"] == "alice"


def test_nbf_beyond_leeway_is_rejected() -> None:
    with pytest.raises(JWTDecodeError):
        decode_jwt(_token(nbf=_nbf(_LEEWAY + 2)), secret=_SECRET)


def test_exp_just_past_is_rejected_strictly() -> None:
    with pytest.raises(JWTExpiredError):
        decode_jwt(_token(iat_offset=-60, exp_offset=-1), secret=_SECRET)


@pytest.mark.parametrize("bad", ["soon", True, None])
def test_malformed_iat_is_rejected(bad) -> None:
    token = jwt.encode({"sub": "a", "iat": bad, "exp": _nbf(3600)}, _SECRET, algorithm="HS256")
    with pytest.raises(JWTDecodeError):
        decode_jwt(token, secret=_SECRET)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), 1e400, 10**30])
def test_non_finite_or_far_future_iat_is_rejected(bad) -> None:
    token = jwt.encode({"sub": "a", "iat": bad, "exp": _nbf(3600)}, _SECRET, algorithm="HS256")
    with pytest.raises(JWTDecodeError):
        decode_jwt(token, secret=_SECRET)


def test_malformed_nbf_is_rejected() -> None:
    token = jwt.encode({"sub": "a", "nbf": float("nan"), "exp": _nbf(3600)}, _SECRET, algorithm="HS256")
    with pytest.raises(JWTDecodeError):
        decode_jwt(token, secret=_SECRET)


def test_exp_just_past_is_rejected_strictly_on_the_audience_path() -> None:
    token = _token(iat_offset=-60, exp_offset=-1, aud="svc")
    with pytest.raises(JWTExpiredError):
        decode_jwt(token, secret=_SECRET, audience="svc")


def test_no_verify_exp_decoder_also_tolerates_iat_skew() -> None:
    claims = jwt_core.decode_jwt_no_verify_exp(_token(iat_offset=2), secret=_SECRET)
    assert claims["sub"] == "alice"


def _leeway_with_env(value: str | None) -> int:
    env = {k: v for k, v in os.environ.items() if k != _ENV}
    if value is not None:
        env[_ENV] = value
    root = Path(__file__).resolve().parents[2]
    env["PYTHONPATH"] = str(root)
    code = "from autobot_shared.auth import jwt_core; print(jwt_core.CLOCK_SKEW_LEEWAY_SECONDS)"
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=root, check=True)
    return int(out.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, 5), ("0", 0), ("30", 30), ("-3", 0), ("999", 60), ("junk", 5)],
)
def test_env_var_is_clamped_to_0_60(raw, expected) -> None:
    assert _leeway_with_env(raw) == expected
