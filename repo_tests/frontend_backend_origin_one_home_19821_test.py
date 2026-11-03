# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The GUI's backend protocol and port have one home (#19821).

The root and frontend env templates used to disagree (http/8001 against https/8443),
and three call sites carried their own literal fallbacks. The value lives in
``ssot-config.ts`` ``PORT_DEFAULTS`` (held to ``autobot_shared/ssot_config.py`` by
``ssot-parity.spec.ts``). The templates must state it, and the call sites read it
through ``getConfig()`` / ``getBackendUrl()``.
"""

from __future__ import annotations

import re

import pytest
from repo_tests._paths import repo_root

_ROOT = repo_root()
_SSOT = "autobot-frontend/src/config/ssot-config.ts"
_TEMPLATES = (".env.example", "autobot-frontend/.env.example")
_CALL_SITES = (
    "autobot-frontend/src/config/AppConfig.js",
    "autobot-frontend/src/models/repositories/ApiRepository.ts",
    "autobot-frontend/src/utils/ApiClient.ts",
)


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


_OWN_READ = re.compile(r"import\.meta\.env\.VITE_(BACKEND_HOST|BACKEND_PORT|HTTP_PROTOCOL)\b")
_LITERAL_FALLBACK = re.compile(r"\|\|\s*['\"](8001|8443|https?)['\"]")

#: Each call site must reach the value through the canonical helper named here.
_MUST_USE = {
    "autobot-frontend/src/config/AppConfig.js": (
        "getConfig().vm.main",
        "getConfig().port.backend",
        "getConfig().httpProtocol",
    ),
    "autobot-frontend/src/models/repositories/ApiRepository.ts": ("getBackendUrl()",),
    "autobot-frontend/src/utils/ApiClient.ts": ("getBackendUrl()",),
}


def _offences(source: str) -> list[str]:
    """Own reads of the backend host/port/protocol, or a literal fallback for one."""
    return [m.group(0) for m in _OWN_READ.finditer(source)] + [m.group(0) for m in _LITERAL_FALLBACK.finditer(source)]


@pytest.mark.parametrize("rel", _CALL_SITES)
def test_no_call_site_builds_the_backend_origin_itself(rel):
    assert not _offences(_read(rel)), (
        f"{rel} reads the backend host/port/protocol or falls back to a literal: {_offences(_read(rel))}. "
        f"Use getConfig() / getBackendUrl() from {_SSOT} (#19821, #12339)."
    )


@pytest.mark.parametrize("rel", _CALL_SITES)
def test_each_call_site_uses_the_canonical_helper(rel):
    source = _read(rel)
    missing = [helper for helper in _MUST_USE[rel] if helper not in source]
    assert not missing, f"{rel} no longer calls {missing}"


@pytest.mark.parametrize(
    "planted",
    [
        "port: import.meta.env.VITE_BACKEND_PORT || '8001',",
        "return `${p}://${import.meta.env.VITE_BACKEND_HOST}:${port}`",
        "protocol: env.PROTO || 'http'",
    ],
)
def test_the_detector_catches_each_planted_shape(planted):
    assert _offences(planted), planted


def test_the_detector_passes_the_canonical_shape():
    assert not _offences("port: String(getConfig().port.backend), protocol: getConfig().httpProtocol")
