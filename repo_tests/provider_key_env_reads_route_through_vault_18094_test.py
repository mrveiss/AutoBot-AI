# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No provider credential is read from the environment past the vault-first resolver (#18094).

Owner ruling 2026-10-12: a provider key resolves through
``services.provider_key_vault.resolve_provider_key`` -- the vault first; a key the vault holds
but cannot read is refused; the environment is used only for a key the vault does not hold. A
direct ``os.getenv("X_API_KEY")`` skips all three, so it is the one shape this guard forbids.

The marker is an env read (``os.getenv`` / ``os.environ.get`` / ``os.environ[...]``) whose
literal name is either registered in ``provider_key_vault`` (any ``*_KEY_NAMES`` frozenset) or
shaped like a provider credential (``*_API_KEY``, ``*_API_TOKEN``, ``*_BOT_TOKEN``,
``*_TOKEN_ID``, ``*_TOKEN_SECRET``, ``HF_TOKEN``; ``AUTOBOT_*`` platform names are not provider
keys). A read passed straight into ``resolve_provider_key(...)`` as its fallback is the
sanctioned shape and is not flagged. Reads by a variable name (a plugin's standalone path through
the SDK's ``CredentialSlot``) are out of reach of a literal-name scan; that is a stated boundary,
not a clean result.
"""

from __future__ import annotations

import ast
import functools
import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOTS = ("autobot-backend", "autobot_shared", "plugins")
_VAULT_MODULE = "autobot-backend/services/provider_key_vault.py"
_SHAPE = re.compile(r"^(?!AUTOBOT_)[A-Z0-9_]+_(API_KEY|API_TOKEN|BOT_TOKEN|TOKEN_ID|TOKEN_SECRET)$|^HF_TOKEN$")

_BYPASS_ISSUE = "reads past the resolver; the fix and its blocker are #18383"
#: ``file -> names`` still read directly, each with its reason. Shrink-only: a stale entry fails.
_ALLOWED: dict[str, tuple[frozenset[str], str]] = {
    "autobot-backend/services/execution/modal_backend.py": (
        frozenset({"MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET"}),
        f"the Modal SDK itself reads these from the environment; {_BYPASS_ISSUE}",
    ),
    "autobot_shared/paperclip_client.py": (
        frozenset({"PAPERCLIP_API_KEY"}),
        f"autobot_shared cannot import the backend resolver; {_BYPASS_ISSUE}",
    ),
}


def _terminal(node: ast.AST) -> str:
    return getattr(node, "attr", getattr(node, "id", ""))


def _env_read_name(node: ast.AST) -> str:
    """The literal variable name an env read asks for, or ``""``."""
    if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
        func, name = node.func, node.args[0].value
        is_getenv = _terminal(func) == "getenv"
        is_environ_get = isinstance(func, ast.Attribute) and func.attr == "get" and _terminal(func.value) == "environ"
        return name if isinstance(name, str) and (is_getenv or is_environ_get) else ""
    if isinstance(node, ast.Subscript) and _terminal(node.value) == "environ" and isinstance(node.slice, ast.Constant):
        return node.slice.value if isinstance(node.slice.value, str) else ""
    return ""


def _routed(tree: ast.AST) -> set[int]:
    """ids of env-read nodes passed directly as an argument of ``resolve_provider_key(...)``."""
    routed: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _terminal(node.func) == "resolve_provider_key":
            routed.update(id(arg) for arg in node.args)
    return routed


def bypassing_reads(source: str, registered: frozenset[str]) -> set[str]:
    """Credential names *source* reads from the environment without going through the resolver."""
    tree = ast.parse(source)
    routed = _routed(tree)
    found = set()
    for node in ast.walk(tree):
        name = _env_read_name(node)
        if name and id(node) not in routed and (name in registered or _SHAPE.match(name)):
            found.add(name)
    return found


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("getenv of a provider key", "k = os.getenv('TILDE_API_KEY')\n", {"TILDE_API_KEY"}),
        ("environ.get of a bot token", "k = os.environ.get('SLACK_BOT_TOKEN', '')\n", {"SLACK_BOT_TOKEN"}),
        ("environ subscript", "k = os.environ['RUNWAY_API_KEY']\n", {"RUNWAY_API_KEY"}),
        ("registered name of another shape", "k = os.getenv('SEARXNG_INSTANCE_URL')\n", {"SEARXNG_INSTANCE_URL"}),
        ("routed fallback", "k = resolve_provider_key('TILDE_API_KEY', os.getenv('TILDE_API_KEY', ''))\n", set()),
        ("a platform name", "k = os.getenv('AUTOBOT_INTERNAL_API_KEY')\n", set()),
        ("a non-credential var", "u = os.getenv('TILDE_API_URL')\n", set()),
        ("a variable name", "k = os.environ.get(name, '')\n", set()),
        ("a dict get", "k = headers.get('X_API_KEY')\n", set()),
        ("a docstring", '"""os.getenv("X_API_KEY")"""\n', set()),
    ],
)
def test_the_matcher_tells_a_bypass_from_a_routed_read(label: str, source: str, expected: set[str]) -> None:
    assert bypassing_reads(source, frozenset({"SEARXNG_INSTANCE_URL"})) == expected, label


def _registered_names(root: Path) -> frozenset[str]:
    """Every string constant in a ``*_KEY_NAMES`` assignment of the resolver module."""
    tree = ast.parse((root / _VAULT_MODULE).read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(_terminal(t).endswith("_KEY_NAMES") for t in targets):
                names.update(
                    c.value for c in ast.walk(node) if isinstance(c, ast.Constant) and isinstance(c.value, str)
                )
    return frozenset(names)


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    is_test = name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel or name == "conftest.py"
    return rel.endswith(".py") and not is_test


def _source_population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, *_ROOTS)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "provider-key-env-read-scan",
    discover=_source_population,
    floor=2617,
    # Mid-window, from REACH.window(): 2767 measured, growth 300 -> 150 of headroom each way.
    what="non-test python source",
    roots=_ROOTS,
    growth=300,
)


@functools.lru_cache(maxsize=1)
def _bypasses() -> dict[str, frozenset[str]]:
    root = repo_root()
    registered = _registered_names(root)
    assert len(registered) >= 20, f"FIX THE SWEEP: only {len(registered)} names parsed from {_VAULT_MODULE}"
    found = {}
    for rel in REACH.examined(root):
        source = (root / rel).read_text(encoding="utf-8")
        if "environ" in source or "getenv" in source:
            names = bypassing_reads(source, registered)
            if names:
                found[rel] = frozenset(names)
    return found


def test_no_provider_key_is_read_past_the_resolver() -> None:
    new = {rel: sorted(names - _ALLOWED.get(rel, (frozenset(), ""))[0]) for rel, names in _bypasses().items()}
    new = {rel: names for rel, names in new.items() if names}
    assert not new, (
        f"#18094: {new} read provider credentials from the environment directly. Use "
        "`resolve_provider_key(NAME, <env or ssot value>)` from services.provider_key_vault (a plugin: its "
        "CredentialSlot), so the vault wins and an unreadable vault key is refused."
    )


def test_every_allowance_still_matches_a_read() -> None:
    stale = sorted(rel for rel, (names, _why) in _ALLOWED.items() if not names <= _bypasses().get(rel, frozenset()))
    assert not stale, f"#18094: {stale} no longer read what they are allowed to; shrink _ALLOWED"
