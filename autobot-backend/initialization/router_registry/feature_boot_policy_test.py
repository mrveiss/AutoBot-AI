# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The feature-router abort policy (#19319): security routers abort in any mode, the rest only when strict."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from initialization.router_registry.feature_boot_policy import REQUIRED_FEATURE_ROUTERS, enforce_feature_boot_policy

_FEATURE_ROUTERS = Path(__file__).with_name("feature_routers.py")


def _result(name: str, loaded: bool) -> dict:
    return {"name": name, "module": f"api.{name}", "loaded": loaded, "error": None if loaded else "ImportError: boom"}


def _configured_names() -> set[str]:
    tree = ast.parse(_FEATURE_ROUTERS.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "FEATURE_ROUTER_CONFIGS":
            return {ast.literal_eval(entry)[3] for entry in node.value.elts}
    raise AssertionError("FEATURE_ROUTER_CONFIGS not found")


def test_every_required_router_is_configured() -> None:
    """A rename in FEATURE_ROUTER_CONFIGS must not silently drop a router from the required set."""
    configured = _configured_names()
    assert len(configured) > 100, "the parser lost the config list"
    assert set(REQUIRED_FEATURE_ROUTERS) <= configured, sorted(set(REQUIRED_FEATURE_ROUTERS) - configured)


@pytest.mark.parametrize("strict", ["0", "1"])
def test_a_required_router_failure_aborts_in_either_mode(strict: str) -> None:
    with pytest.raises(RuntimeError, match=r"security \(api\.security\): ImportError: boom"):
        enforce_feature_boot_policy([_result("security", False), _result("marketplace", True)], strict)


def test_an_optional_router_failure_is_tolerated_when_lenient() -> None:
    enforce_feature_boot_policy([_result("marketplace", False), _result("security", True)], "0")


def test_an_optional_router_failure_aborts_when_strict() -> None:
    with pytest.raises(RuntimeError, match=r"AUTOBOT_FEATURE_ROUTERS_STRICT=1 .*marketplace \(api\.marketplace\)"):
        enforce_feature_boot_policy([_result("marketplace", False)], "1")


def test_a_clean_load_never_aborts() -> None:
    enforce_feature_boot_policy([_result("security", True), _result("marketplace", True)], "1")
