# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Behaviour pins for the slice-2 shared cores of #18557 (structural guard: the sibling test).

Light loading only. The terminal methods are read from ``api/terminal_handlers.py`` by syntax tree and
executed against the real ``command_assessor`` (``security.py`` loaded by path, so the
``services.terminal_websocket`` package and its heavy chat stack are never imported). The sanitizers
are loaded by path with ``auto-tools`` on ``sys.path``, exactly as the scripts themselves run.
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest
from repo_tests._paths import repo_root  # noqa: E402

ROOT = repo_root()
BACKEND = ROOT / "autobot-backend"
AUTO_TOOLS = BACKEND / "code_analysis" / "auto-tools"
for _p in (str(ROOT), str(BACKEND)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from api.schemas_terminal import SecurityLevel  # noqa: E402
from autobot_shared.status_enums import CommandRisk  # noqa: E402


def _load_by_path(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _terminal_methods() -> dict:
    """The real delegating methods of ``TerminalWebSocket``, bound to the real assessor."""
    security = _load_by_path("_slice2_terminal_security", BACKEND / "services/terminal_websocket/security.py")
    source = (BACKEND / "api/terminal_handlers.py").read_text(encoding="utf-8")
    namespace = {"CommandRisk": CommandRisk, "command_assessor": security.command_assessor}
    wanted = {"_assess_command_risk", "_should_block_command"}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ClassDef) and node.name == "TerminalWebSocket":
            for fn in node.body:
                if getattr(fn, "name", None) in wanted:
                    exec(textwrap.dedent(ast.get_source_segment(source, fn)), namespace)
    return namespace


class _Session:
    def __init__(self, level: SecurityLevel) -> None:
        self.security_level = level


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("rm -rf /", CommandRisk.DANGEROUS),
        ("sudo ls", CommandRisk.MODERATE),
        ("a | b", CommandRisk.HIGH),
        ("x > f", CommandRisk.HIGH),
        ("ls", CommandRisk.SAFE),
    ],
)
def test_terminal_handlers_assess_command_risk(command, expected):
    assert _terminal_methods()["_assess_command_risk"](None, command) is expected


@pytest.mark.parametrize(
    ("level", "risk", "blocked"),
    [
        (SecurityLevel.RESTRICTED, CommandRisk.HIGH, True),  # strict blocks HIGH ...
        (SecurityLevel.STANDARD, CommandRisk.HIGH, False),  # ... the permissive level allows it
        (SecurityLevel.RESTRICTED, CommandRisk.DANGEROUS, True),
        (SecurityLevel.ELEVATED, CommandRisk.DANGEROUS, True),
        (SecurityLevel.STANDARD, CommandRisk.DANGEROUS, False),
        (SecurityLevel.ELEVATED, CommandRisk.HIGH, False),
        (SecurityLevel.RESTRICTED, CommandRisk.SAFE, False),
        (SecurityLevel.RESTRICTED, CommandRisk.MODERATE, False),
    ],
)
def test_terminal_handlers_should_block_command(level, risk, blocked):
    verdict = asyncio.run(_terminal_methods()["_should_block_command"](_Session(level), "cmd", risk))
    assert verdict is blocked


def _sanitizer(module: str, cls: str):
    # The script imports ``tool_base`` by bare name; whatever held those keys before is put back
    # afterwards, so no test file after this one sees this load's copy (sys.modules leak guard).
    saved = {key: sys.modules.pop(key, None) for key in ("tool_base", module)}
    sys.path.insert(0, str(AUTO_TOOLS))
    try:
        return getattr(_load_by_path(module + "_slice2", AUTO_TOOLS / f"{module}.py"), cls)()
    finally:
        sys.path.remove(str(AUTO_TOOLS))
        for key, previous in saved.items():
            if previous is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = previous


TOOLS = [
    ("security_sanitizer", "SecurityFixAgent"),
    ("security_deep_sanitizer", "DeepSecurityFixAgent"),
]
MINIFIED = "a.b.c(" + "x,y," * 80 + "react)"  # long, minified property access, many commas
PLAIN = "let total = 1;\nlet next = total + 1;\n"
HTML = "<!DOCTYPE html><html><head></head><body><script>\nel.innerHTML = x;\n</script></body></html>"


@pytest.mark.parametrize(("module", "cls"), TOOLS)
@pytest.mark.parametrize(("code", "expected"), [(MINIFIED, True), (PLAIN, False)])
def test_is_minified_library_code_returns_a_bool_and_never_raises(module, cls, code, expected):
    # The deep sanitizer used ``sum(indicators)`` over Match/None and always raised TypeError.
    assert _sanitizer(module, cls).is_minified_library_code(code) is expected


@pytest.mark.parametrize(("module", "cls"), TOOLS)
def test_innerhtml_assignment_is_still_reported(module, cls):
    found = _sanitizer(module, cls).scan_for_vulnerabilities(HTML, "page.html")
    assert any("innerHTML" in v["type"] and "innerHTML" in v["match"] for v in found)


@pytest.mark.parametrize(("module", "cls"), TOOLS)
def test_plain_html_without_sinks_reports_nothing(module, cls):
    clean = "<!DOCTYPE html><html><head></head><body><script>let a = 1;</script></body></html>"
    assert _sanitizer(module, cls).scan_for_vulnerabilities(clean, "page.html") == []
