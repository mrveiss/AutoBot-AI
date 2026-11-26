# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A service reports its release or says "unknown"; it never carries an invented version literal (#17821).

The repo declares no version (the release is a git tag), so ``"version": "1.0.0"`` / ``version="1.5.0"`` on an info
endpoint, an MCP bridge manifest or an app factory default is a made-up number that reads as a fact. Such a site says
``"unknown"``. A literal that is genuinely a protocol, format, catalog or API-spec version stays, with a comment on the
same line naming it (``# export format version: ...``).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._comment_syntax import strip_trailing_comment

_ROOT = repo_root()
_ROOTS = (
    "autobot-backend/api/",
    "autobot-backend/mcp_server/",
    "autobot-backend/a2a/",
    "autobot-backend/app_factory.py",
    "autobot-backend/llm_self_awareness.py",
    "autobot_shared/tracing.py",
    "autobot_shared/ssot_tracing_settings.py",
)
_TEST = re.compile(r"(_test\.py$|/test_[^/]*\.py$|/tests/)")
_NUM = r"[\"']\d+(?:\.\d+)+[\"']"
#: Each shape that states a version: a dict key, a keyword argument or default, a ``.get`` fallback, a constant.
_SITE = re.compile(
    rf"[\"']version[\"']\s*:\s*{_NUM}"
    rf"|\b\w*version\w*\s*(?::\s*str\s*)?=\s*(?:Field\(\s*default\s*=\s*)?{_NUM}"
    rf"|\.get\(\s*[\"']version[\"']\s*,\s*{_NUM}"
    rf"|\b(?:AUTOBOT|SERVICE|APP|PRODUCT)_VERSION\s*=\s*{_NUM}"
)
#: The comment that declares a literal to be a protocol / format / catalog / API-spec version.
_GENUINE = re.compile(r"\b(?:protocol|format|catalog|schema|api-spec)\s+version\b")


def _sources(root: Path) -> list[Path]:
    found: list[Path] = []
    for top in _ROOTS:
        base = root / top
        if base.is_dir():
            found += [p for p in sorted(base.rglob("*.py")) if not _TEST.search(p.relative_to(root).as_posix())]
        elif base.is_file():
            found.append(base)
    return found


#: 579 modules measured (2026-11-26); growth 60 puts the pin mid-window (579 - 30).
REACH = declare(
    "service-version-literals-17821",
    discover=_sources,
    floor=549,
    growth=60,
    roots=_ROOTS,
    what="non-test API, MCP, A2A, app-factory, self-awareness and tracing modules scanned for version literals",
)


def _is_invented(line: str) -> bool:
    """A version-stating code part whose trailing comment (quote-aware split) does not declare it genuine."""
    code = strip_trailing_comment(line, ("#",))
    return bool(_SITE.search(code)) and not _GENUINE.search(line[len(code) :])


def invented_versions(text: str) -> list[int]:
    """Line numbers of version literals that carry no comment declaring them a protocol/format/catalog version."""
    return [number for number, line in enumerate(text.splitlines(), 1) if _is_invented(line)]


def test_no_service_reports_an_invented_version() -> None:
    files = REACH.examined(_ROOT)
    found = {p.relative_to(_ROOT).as_posix(): invented_versions(p.read_text(encoding="utf-8")) for p in files}
    REACH.completed(files)
    bad = {rel: lines for rel, lines in found.items() if lines}
    assert (
        not bad
    ), f"an invented version literal: report 'unknown', or comment the literal as a protocol/format version: {bad}"


@pytest.mark.parametrize(
    "line",
    [
        '    "version": "1.0.0",',
        '    version="1.5.0",',
        '        version: str = "1.5.0",',
        '    value = cfg.get("version", "1.0.0")',
        '    SERVICE_VERSION = "2.0.0"',
        '    "version": "1.0",  # a release number nobody declared',
        '    otel_service_version: str = Field(default="1.5.0", alias="AUTOBOT_OTEL_SERVICE_VERSION")',
        '    service_version = Field(default="2.0.0")',
        '    otel_service_version = "1.5.0"',
    ],
)
def test_each_invented_shape_is_caught(line: str) -> None:
    assert invented_versions(line) == [1]


@pytest.mark.parametrize(
    "line",
    [
        '    "version": "unknown",',
        '    "version": "1.0",  # export format version: the layout of this payload',
        '    "version": "1.0.0",  # catalog version: the plugin\'s own',
        '    version = os.environ["VERSION"]',
        '    "protocolVersion": "2024-11-05",',
        '    otel_service_version: str = Field(default="", alias="AUTOBOT_OTEL_SERVICE_VERSION")',
    ],
)
def test_declared_unknown_and_commented_literals_pass(line: str) -> None:
    assert invented_versions(line) == []
