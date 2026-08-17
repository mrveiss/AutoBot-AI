# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``autobot_shared.auth`` submodule imports must not drag in jwt_core (#14397).

``permissions.py`` has no bcrypt/JWT dependency of its own (just ``enum``/
``typing``), but ``autobot_shared/auth/__init__.py`` used to eagerly
``from autobot_shared.auth.jwt_core import (...)`` at module load time — and
because Python always fully executes a package's ``__init__.py`` before any
of its submodules, *every* consumer of any ``autobot_shared.auth.*``
submodule (including one that only wants ``SYSTEM_PERMISSIONS``/
``SYSTEM_ROLES``) was forced to import ``bcrypt``/``PyJWT`` too. This is what
broke the #14300 SLM migration gate with ``ModuleNotFoundError: No module
named 'bcrypt'``.

Each case below runs in its own subprocess with a ``sys.meta_path`` finder
that raises for ``bcrypt``/``jwt`` — the only way to prove the import graph
itself is clean rather than merely that bcrypt/jwt happen to be installed in
this environment.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_ENV = dict(os.environ, PYTHONPATH=str(_ROOT))

_BLOCK_BCRYPT_JWT = textwrap.dedent("""
    import sys

    _BLOCKED = {"bcrypt", "jwt"}

    class _BlockFinder:
        def find_spec(self, name, path=None, target=None):
            root = name.split(".", 1)[0]
            if root in _BLOCKED:
                raise ModuleNotFoundError(f"blocked for test: {name!r}")
            return None

    sys.meta_path.insert(0, _BlockFinder())
    """)


def _run_in_subprocess(body: str) -> subprocess.CompletedProcess:
    """Execute ``body`` in a fresh interpreter with bcrypt/jwt import-blocked."""
    script = _BLOCK_BCRYPT_JWT + "\n" + textwrap.dedent(body)
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=str(_ROOT),
        env=_ENV,
    )


def test_importing_permissions_alone_does_not_pull_jwt_core():
    """The #14397 regression: this import must succeed with bcrypt/jwt blocked."""
    result = _run_in_subprocess("""
        from autobot_shared.auth.permissions import SYSTEM_PERMISSIONS, SYSTEM_ROLES

        assert SYSTEM_PERMISSIONS, "SYSTEM_PERMISSIONS must be non-empty"
        assert SYSTEM_ROLES, "SYSTEM_ROLES must be non-empty"

        # Assert the invariant (#14397), not today's spelling: jwt_core must
        # never have been imported as a side effect of importing permissions.
        assert "autobot_shared.auth.jwt_core" not in sys.modules
        assert "bcrypt" not in sys.modules
        assert "jwt" not in sys.modules
        print("OK")
        """)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert result.stdout.strip() == "OK"


def test_importing_connector_auth_alone_does_not_pull_jwt_core():
    """connector_auth.py also has no bcrypt/JWT dependency of its own."""
    result = _run_in_subprocess("""
        from autobot_shared.auth.connector_auth import BearerAuth

        assert BearerAuth is not None
        assert "autobot_shared.auth.jwt_core" not in sys.modules
        assert "bcrypt" not in sys.modules
        print("OK")
        """)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert result.stdout.strip() == "OK"


def test_package_level_reexports_still_work_for_every_public_name():
    """``from autobot_shared.auth import X`` must keep working for callers (#14397).

    jwt_core-backed names are still expected to pull bcrypt/jwt — they are not
    blocked here — this only proves the lazy re-export resolves correctly.
    """
    result = _run_in_subprocess("""
        from autobot_shared.auth import (
            ApiKeyAuth,
            BasicAuth,
            BearerAuth,
            JWTDecodeError,
            JWTExpiredError,
            OAuthRefreshAuth,
            Permission,
            ROLE_PERMISSIONS,
            Role,
            SYSTEM_PERMISSIONS,
            SYSTEM_ROLES,
            validate_config_against_schema,
        )

        for value in (
            ApiKeyAuth, BasicAuth, BearerAuth, JWTDecodeError, JWTExpiredError,
            OAuthRefreshAuth, Permission, ROLE_PERMISSIONS, Role,
            SYSTEM_PERMISSIONS, SYSTEM_ROLES, validate_config_against_schema,
        ):
            assert value is not None
        print("OK")
        """)
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert result.stdout.strip() == "OK"


def test_package_level_jwt_reexport_still_works_when_jwt_core_is_allowed():
    """``from autobot_shared.auth import encode_jwt`` must still resolve (#14397).

    Unlike the tests above, this one does NOT block bcrypt/jwt — a caller that
    actually wants a jwt_core symbol must still get it lazily.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            textwrap.dedent("""
                from autobot_shared.auth import decode_jwt, encode_jwt, hash_password, verify_password

                for value in (decode_jwt, encode_jwt, hash_password, verify_password):
                    assert callable(value)

                import sys
                assert "autobot_shared.auth.jwt_core" in sys.modules
                print("OK")
                """),
        ],
        capture_output=True,
        text=True,
        cwd=str(_ROOT),
        env=_ENV,
    )
    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert result.stdout.strip() == "OK"
