# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One gateway adapter package (#15024).

`services/gateway/` carried two adapter packages, `adapters/` and `channel_adapters/`, one
base class and one concrete adapter in each. `adapters/` is canonical (it holds the nine
platform normalizers `GatewayManager` registers); the transport base and the WebSocket
adapter were folded into it. The guard reads the syntax tree and the tracked paths, never
prose, and checks two things:

* no tracked file lives in a second package under `services/gateway/` that holds adapter modules;
* no adapter class name is defined in more than one module.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_GATEWAY = "autobot-backend/services/gateway/"
_CANONICAL = _GATEWAY + "adapters/"


def _adapter_package(rel: str) -> str | None:
    """The gateway sub-package `rel` is an adapter module of, or None.

    An adapter module is a non-test `*adapter*.py` or `base.py` inside a sub-package of
    the gateway directory.
    """
    if not (rel.startswith(_GATEWAY) and rel.endswith(".py")):
        return None
    parts = rel[len(_GATEWAY) :].split("/")
    if len(parts) != 2 or parts[1].endswith("_test.py") or parts[1] == "__init__.py":
        return None
    if "adapter" in parts[1] or parts[1] in ("base.py", "transport_base.py"):
        return parts[0]
    return None


@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        (_GATEWAY + "adapters/whatsapp_adapter.py", "adapters"),
        (_GATEWAY + "channel_adapters/websocket_adapter.py", "channel_adapters"),
        (_GATEWAY + "channel_adapters/base.py", "channel_adapters"),
        (_GATEWAY + "adapters/websocket_adapter_test.py", None),
        (_GATEWAY + "gateway.py", None),
        (_GATEWAY + "adapters/__init__.py", None),
        ("autobot-backend/knowledge/adapters/okf_adapter.py", None),
    ],
)
def test_the_package_matcher_tells_an_adapter_module_from_the_rest(rel: str, expected: str | None) -> None:
    assert _adapter_package(rel) == expected


def _adapter_classes(source: str) -> list[str]:
    """Top-level class names that look like gateway adapters."""
    tree = ast.parse(source)
    return [n.name for n in tree.body if isinstance(n, ast.ClassDef) and n.name.endswith("Adapter")]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("class SlackAdapter(BaseAdapter): pass\n", ["SlackAdapter"]),
        ("class Helper: pass\n", []),
        ("def f():\n    class InnerAdapter: pass\n", []),
        ('# class CommentAdapter:\nx = "class StrAdapter:"\n', []),
    ],
)
def test_the_class_matcher_reads_definitions_not_prose(source: str, expected: list[str]) -> None:
    assert _adapter_classes(source) == expected


def _population(root: Path) -> list[str]:
    try:
        return [r for r in tracked_paths(root, "autobot-backend/services/gateway") if r.endswith(".py")]
    except EmptyEnumeration:
        return []


REACH = declare(
    "gateway-adapter-package-scan",
    discover=_population,
    # Mid-window, from REACH.window() = (-2, 28, 13).
    floor=13,
    what="gateway python files",
    roots=("autobot-backend/services/gateway",),
    growth=30,
)


@functools.lru_cache(maxsize=1)
def _scan() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """(adapter modules by sub-package, defining modules by adapter class name)."""
    packages: dict[str, list[str]] = {}
    classes: dict[str, list[str]] = {}
    for rel in REACH.examined(repo_root()):
        pkg = _adapter_package(rel)
        if pkg is not None:
            packages.setdefault(pkg, []).append(rel)
        if rel.startswith(_CANONICAL) and not rel.endswith("_test.py"):
            for name in _adapter_classes((repo_root() / rel).read_text(encoding="utf-8")):
                classes.setdefault(name, []).append(rel)
    return packages, classes


def test_the_scan_is_not_vacuous() -> None:
    packages, classes = _scan()
    assert len(packages.get("adapters", [])) >= 10, packages
    assert {"WhatsAppAdapter", "WebSocketAdapter"} <= set(classes), sorted(classes)


def test_adapters_live_in_one_package() -> None:
    packages, _ = _scan()
    assert set(packages) == {"adapters"}, (
        f"#15024: adapter modules found in {sorted(packages)}; services/gateway has ONE adapter "
        "package, adapters/. Add the new adapter there."
    )


def test_no_adapter_class_is_defined_twice() -> None:
    _, classes = _scan()
    dups = {name: mods for name, mods in classes.items() if len(mods) > 1}
    assert not dups, f"#15024: duplicate adapter classes {dups}"
