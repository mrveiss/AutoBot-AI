# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for services/step_up_auth.py — D2 (#10158).

Covers:
- fresh auth_time within max_age → allowed
- stale auth_time beyond max_age → 401 with X-Step-Up-Required header
- iat fallback when auth_time absent
- no timestamp claim → bypass (legacy tokens)
- max_age = 0 → bypass (step-up disabled)
- negative auth_time handled without crash
"""

import importlib.util
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_BACKEND = Path(__file__).parent.parent.parent
_ROOT = _BACKEND.parent
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_ROOT))

# Import real FastAPI if available; otherwise stub enough for the module to load.
try:
    import fastapi as _fastapi_real  # noqa: F401 — keep real if installed
except ImportError:
    for _m in ["fastapi", "fastapi.security"]:
        if _m not in sys.modules:
            sys.modules[_m] = MagicMock()

# Stub services.auth dependency
_auth_stub = MagicMock()
sys.modules.setdefault("services.auth", _auth_stub)

# ---------------------------------------------------------------------------
# Load module under test (direct file import to bypass full app init)
# ---------------------------------------------------------------------------
_SU_PY = _BACKEND / "services" / "step_up_auth.py"
_spec = importlib.util.spec_from_file_location("_step_up_auth", _SU_PY)
_su_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_su_mod)  # type: ignore[union-attr]

_is_auth_fresh = _su_mod._is_auth_fresh
STEP_UP_MAX_AGE_SECONDS = _su_mod.STEP_UP_MAX_AGE_SECONDS


# ---------------------------------------------------------------------------
# _is_auth_fresh
# ---------------------------------------------------------------------------


class TestIsAuthFresh:
    def _now(self) -> int:
        return int(time.time())

    def test_fresh_auth_time_allowed(self):
        claims = {"auth_time": self._now() - 60}  # 1 min ago
        assert _is_auth_fresh(claims, max_age=900) is True

    def test_stale_auth_time_denied(self):
        claims = {"auth_time": self._now() - 1800}  # 30 min ago
        assert _is_auth_fresh(claims, max_age=900) is False

    def test_exactly_at_boundary_allowed(self):
        claims = {"auth_time": self._now() - 900}
        # boundary case: age == max_age → allowed
        assert _is_auth_fresh(claims, max_age=900) is True

    def test_iat_fallback_when_no_auth_time(self):
        claims = {"iat": self._now() - 100}
        assert _is_auth_fresh(claims, max_age=900) is True

    def test_iat_stale_denied(self):
        claims = {"iat": self._now() - 1000}
        assert _is_auth_fresh(claims, max_age=900) is False

    def test_no_timestamp_bypasses_check(self):
        """Tokens without auth_time or iat must not be blocked (legacy HS256)."""
        claims = {"sub": "alice", "role": "admin"}
        assert _is_auth_fresh(claims, max_age=900) is True

    def test_max_age_zero_always_allowed(self):
        claims = {"auth_time": 0}  # epoch — extremely stale
        assert _is_auth_fresh(claims, max_age=0) is True

    def test_malformed_auth_time_falls_back_to_iat(self):
        claims = {"auth_time": "not-a-number", "iat": self._now() - 60}
        assert _is_auth_fresh(claims, max_age=900) is True

    def test_malformed_both_timestamps_bypass(self):
        claims = {"auth_time": "bad", "iat": "also-bad"}
        assert _is_auth_fresh(claims, max_age=900) is True


# ---------------------------------------------------------------------------
# require_step_up (as a dependency function — test _is_auth_fresh integration)
# ---------------------------------------------------------------------------


class TestRequireStepUpIntegration:
    @pytest.mark.asyncio
    async def test_fresh_claims_returns_user(self):
        """Fresh auth_time must return the user dict unchanged."""
        claims = {"sub": "alice", "auth_time": int(time.time()) - 60}

        # Simulate dependency: inject user without calling get_current_user
        with patch.object(_su_mod, "_is_auth_fresh", return_value=True):
            result = await _su_mod.require_step_up(current_user=claims)
        assert result is claims

    @pytest.mark.asyncio
    async def test_stale_claims_raises_401(self):
        """Stale auth_time must raise HTTP 401 with X-Step-Up-Required header."""
        claims = {"sub": "alice", "auth_time": 0}

        with patch.object(_su_mod, "_is_auth_fresh", return_value=False):
            with pytest.raises(Exception) as exc_info:
                await _su_mod.require_step_up(current_user=claims)

        exc = exc_info.value
        # The module raises HTTPException; check the status_code attribute.
        assert getattr(exc, "status_code", None) == 401
        # Confirm step-up header
        headers = getattr(exc, "headers", {}) or {}
        assert headers.get("X-Step-Up-Required") == "true"
