# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A user's OAuth credential bundle never carries the OAuth app's client secret (#13630).

`client_secret` identifies the operator-owned OAuth application. Copying it into every
user's stored credential made a rotation strand every connection and spread one secret
across N rows. Refresh now resolves it from provider config at use time.

The marker is a dict literal holding BOTH `access_token` and `client_secret`: the shape of
`ConnectorCredentialStore._oauth_bundle`. A token *request* payload also has `client_secret`
but no `access_token`, so it is not a bundle. The detector reads the syntax tree, so prose
naming the key is not a definition.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_SECRET_KEY = "client_secret"  # pragma: allowlist secret
_BUNDLE_KEY = "access_token"


def _dict_keys(node: ast.Dict) -> set[str]:
    return {k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}


def _bundle_with_app_secret(source: str) -> bool:
    """True when `source` builds a token-bundle dict that also holds the app client secret."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Dict):
            keys = _dict_keys(node)
            if _SECRET_KEY in keys and _BUNDLE_KEY in keys:
                return True
    return False


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


def _source_population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, "autobot-backend", "autobot_shared")
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "oauth-bundle-app-secret-scan",
    discover=_source_population,
    # Mid-window, from REACH.window() = (2430, 2730, 2580).
    floor=2948,  # re-pinned mid-window (train 81 on main)
    what="non-test python source",
    roots=("autobot-backend", "autobot_shared"),
    growth=300,
)


@functools.lru_cache(maxsize=1)
def _offenders() -> tuple[str, ...]:
    found = []
    for rel in REACH.examined(repo_root()):
        source = (repo_root() / rel).read_text(encoding="utf-8")
        if _SECRET_KEY in source and _bundle_with_app_secret(source):
            found.append(rel)
    return tuple(found)


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("the old bundle shape", 'b = {"provider": p, "access_token": a, "client_secret": s}\n', True),
        ("a bundle without the app secret", 'b = {"provider": p, "access_token": a, "token_url": u}\n', False),
        ("a token request payload", 'b = {"grant_type": "refresh_token", "client_secret": s}\n', False),
        ("a comment naming the key", '# {"access_token": 1, "client_secret": 2}\nx = 1\n', False),
    ],
)
def test_the_matcher_tells_a_bundle_from_a_request(label: str, source: str, expected: bool) -> None:
    assert _bundle_with_app_secret(source) is expected, label


def test_no_user_credential_bundle_carries_the_app_client_secret() -> None:
    assert _offenders() == (), (
        f"#13630: {list(_offenders())} write the OAuth app's client secret into a user credential bundle. "
        "Resolve it at use time with oauth_flow.resolve_client_credentials(provider)."
    )
