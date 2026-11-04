# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The GUI's backend protocol and port have one home (#19821).

The root and frontend env templates used to disagree (http/8001 against https/8443),
and call sites across the GUI read or rebuilt the backend origin themselves. The value
lives in ``ssot-config.ts`` ``PORT_DEFAULTS`` (held to ``autobot_shared/ssot_config.py``
by ``ssot-parity.spec.ts``), and the origin is decided by ``getBackendUrl()`` /
``getBackendWsUrl()``. The templates must state the value, and nothing under
``autobot-frontend/src`` except ``ssot-config.ts`` may read the variables, fall back to a
literal, or build an absolute ``host:port`` backend origin.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOT = repo_root()
_SSOT = "autobot-frontend/src/config/ssot-config.ts"
_TEMPLATES = (".env.example", "autobot-frontend/.env.example")
_SRC = "autobot-frontend/src"
_TEST_FILE = re.compile(r"(\.spec\.|\.test\.|/__tests__/|/test/)")


def _read(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def _template_value(rel: str, name: str) -> str:
    found = re.findall(rf"^{name}=(\S+)\s*$", _read(rel), re.MULTILINE)
    assert len(found) == 1, f"{rel} must set {name} exactly once (uncommented); found {found}"
    return found[0]


def _ssot_backend_port() -> str:
    match = re.search(r"^export const PORT_DEFAULTS = \{\s*\n\s*backend: (\d+),", _read(_SSOT), re.MULTILINE)
    assert match, f"PORT_DEFAULTS.backend not found in {_SSOT}"
    return match.group(1)


@pytest.mark.parametrize("template", _TEMPLATES)
def test_each_template_states_the_ssot_backend_port(template):
    assert _template_value(template, "VITE_BACKEND_PORT") == _ssot_backend_port()


def test_the_templates_agree_on_the_protocol():
    values = {t: _template_value(t, "VITE_HTTP_PROTOCOL") for t in _TEMPLATES}
    assert len(set(values.values())) == 1, f"templates disagree: {values}"


_OWN_READ = re.compile(
    r"(import\.meta\.env\.|import\.meta\.env\[\s*['\"]|getEnv\(\s*['\"])VITE_(BACKEND_HOST|BACKEND_PORT|HTTP_PROTOCOL)\b"
)
_LITERAL_FALLBACK = re.compile(r"\|\|\s*['\"](8001|8443)['\"]")
_ABSOLUTE_ORIGIN = re.compile(r"\$\{[^}]*\}:\$\{[^}]*(port\.backend|BACKEND_PORT)\}")

#: The canonical home reads the variables; that is what it is for.
_CANONICAL = frozenset({_SSOT})

#: Files allowed one specific shape, each with its reason. Nothing else may.
_ALLOWED_ABSOLUTE_ORIGIN = {
    # Localhost origins read only by the test mocks (src/test/mocks, src/test/config) under jsdom;
    # its NetworkConfig class and networkConfig instance have no importer at all.
    "autobot-frontend/src/constants/network.ts": "localhost test-mock origins; NetworkConfig unused",
    # Story text shown to a reader, not a URL anything requests.
    "autobot-frontend/src/components/browser/BrowserSessionManager.stories.ts": "display text",
}


def _source_files(root: Path) -> list[str]:
    try:
        paths = tracked_paths(root, _SRC)
    except EmptyEnumeration:
        return []
    return [p for p in paths if p.endswith((".ts", ".js", ".vue")) and not _TEST_FILE.search(p)]


def _all_files(root: Path) -> int:
    try:
        return len(tracked_paths(root, _SRC))
    except EmptyEnumeration:
        return 0


#: Measured 2026-11-03: 1177 of 1699 tracked files under src are non-test source (69%); 0.5 leaves room.
REACH = declare(
    "frontend-backend-origin",
    discover=_source_files,
    reference=_all_files,
    min_fraction=0.5,
    what="non-test GUI source",
    roots=(_SRC,),
)


def _offences(rel: str, source: str) -> list[str]:
    """Own reads, literal fallbacks and absolute backend origins this file is not allowed."""
    found: list[str] = []
    if rel not in _CANONICAL:
        found += [m.group(0) for m in _OWN_READ.finditer(source)]
        found += [m.group(0) for m in _LITERAL_FALLBACK.finditer(source)]
    if rel not in _ALLOWED_ABSOLUTE_ORIGIN:
        found += [m.group(0) for m in _ABSOLUTE_ORIGIN.finditer(source)]
    return found


def _scan() -> dict[str, list[str]]:
    examined = REACH.examined(_ROOT)
    offences = {rel: hits for rel in examined if (hits := _offences(rel, _read(rel)))}
    REACH.completed(len(examined), _ROOT)
    return offences


def test_nothing_in_the_gui_builds_the_backend_origin_itself():
    offences = _scan()
    assert not offences, (
        "these read the backend host/port/protocol, fall back to a literal, or build an absolute "
        f"host:port backend origin: {offences}. Use getConfig() / getBackendUrl() / getBackendWsUrl() "
        f"from {_SSOT} (#19821, #12339)."
    )


def test_every_allowance_is_still_needed():
    stale = [rel for rel in _ALLOWED_ABSOLUTE_ORIGIN if not _ABSOLUTE_ORIGIN.search(_read(rel))]
    assert not stale, f"{stale} no longer build that shape; delete their allowance"


@pytest.mark.parametrize(
    "planted",
    [
        "port: import.meta.env.VITE_BACKEND_PORT || '8001',",
        "const p = getEnv('VITE_HTTP_PROTOCOL', 'http')",
        "const host = import.meta.env['VITE_BACKEND_HOST']",
        'const port = import.meta.env["VITE_BACKEND_PORT"]',
        "return `ws://${cfg.vm.main}:${cfg.port.backend}/api/ws`",
        "return `ws://${NetworkConstants.MAIN_MACHINE_IP}:${NetworkConstants.BACKEND_PORT}/api/terminal/ws`",
        "const port = env.PORT || '8443'",
    ],
)
def test_the_detector_catches_each_planted_shape(planted):
    assert _offences("autobot-frontend/src/x.ts", planted), planted


def test_the_detector_passes_the_canonical_shape():
    assert not _offences("autobot-frontend/src/x.ts", "port: String(getConfig().port.backend), url: getBackendUrl()")
