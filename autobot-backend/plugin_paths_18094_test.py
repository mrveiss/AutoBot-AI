# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Both plugin hosts search the same dirs and trust only the built-in core roots (#18094)."""

from __future__ import annotations

import ast
from pathlib import Path

import plugin_paths
from autobot_shared.plugin_sdk.credential_binding import bound_resolver
from services.provider_key_vault import plugin_credential_resolvers

_BACKEND = Path(__file__).resolve().parent
_NAME = "image-generation-plugin"


def test_no_community_dir_is_trusted() -> None:
    trusted = plugin_paths.trusted_plugin_roots()
    assert trusted and all(root.name == "core-plugins" for root in trusted)
    assert all(root.is_absolute() for root in trusted), "a CWD-relative trust root moves with the CWD"


def test_search_order_is_core_first_so_core_wins_a_name_conflict() -> None:
    names = [p.name for p in plugin_paths.plugin_search_dirs()]
    assert names == ["core-plugins", "community-plugins", "core-plugins", "community-plugins"]


def test_a_cwd_plugins_dir_outside_the_checkout_is_not_trusted(tmp_path, monkeypatch) -> None:
    impostor = tmp_path / "plugins" / "core-plugins" / _NAME
    impostor.mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    resolvers = plugin_credential_resolvers()

    assert (
        bound_resolver(_NAME, Path("plugins/core-plugins") / _NAME, resolvers, plugin_paths.trusted_plugin_roots())
        is None
    )


def test_the_checkout_core_plugin_is_trusted() -> None:
    genuine = _BACKEND.parent / "plugins" / "core-plugins" / _NAME
    resolvers = plugin_credential_resolvers()

    assert bound_resolver(_NAME, genuine, resolvers, plugin_paths.trusted_plugin_roots()) is resolvers[_NAME]


def _host_call(rel: str, ctor: str) -> ast.Call:
    tree = ast.parse((_BACKEND / rel).read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == ctor]
    assert len(calls) == 1, f"{rel}: expected one {ctor}(...) call, found {len(calls)}"
    return calls[0]


def test_both_hosts_pass_the_shared_dirs_resolvers_and_trust() -> None:
    for rel, ctor in (("initialization/lifespan.py", "PluginManager"), ("plugin_manager.py", "PluginLoader")):
        call = _host_call(rel, ctor)
        passed = [getattr(arg.func, "id", "") for arg in call.args if isinstance(arg, ast.Call)]
        assert passed == ["plugin_search_dirs", "plugin_credential_resolvers", "trusted_plugin_roots"], rel
