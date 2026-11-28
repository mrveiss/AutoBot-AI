# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#17856 row 6: the frontend API timeout is declared once and every copy agrees.

The value lives in ``TimeoutConfig.api`` (``AUTOBOT_API_TIMEOUT``). Before this
guard it had six homes holding four answers: 60000 in ``ssot-config.ts`` and the
root ``.env.example``, 30000 in ``autobot-frontend/.env.example`` and both
``AppConfig.js`` fallbacks, 10000 in the Python field, and ``"30.0000"`` (30 ms)
from ``generate-env-files.py``, which appended ``"000"`` to a float of seconds.

Each reader and writer is checked against the field default. The literal
mirrors (the TS default, ``ssot-config.sh``, both ``.env.example`` files) must
equal it; the code writers (``AppConfig.js``, ``generate-env-files.py``'s
frontend file) must hold no literal at all. The generator's ``AUTOBOT_API_TIMEOUT``
lines are #18565.
"""

from __future__ import annotations

import re

import pytest
from repo_tests._paths import repo_root

_ROOT = repo_root()
_SSOT_TS = _ROOT / "autobot-frontend" / "src" / "config" / "ssot-config.ts"
_APP_CONFIG = _ROOT / "autobot-frontend" / "src" / "config" / "AppConfig.js"
_FRONTEND_ENV_EXAMPLE = _ROOT / "autobot-frontend" / ".env.example"
_ROOT_ENV_EXAMPLE = _ROOT / ".env.example"
_SHELL_SSOT = _ROOT / "autobot-infrastructure" / "shared" / "scripts" / "lib" / "ssot-config.sh"
_GENERATOR = _ROOT / "autobot-infrastructure" / "shared" / "scripts" / "generate-env-files.py"
_SYNC_ENV = _ROOT / "autobot-infrastructure" / "shared" / "scripts" / "sync-env.sh"


def _ssot_value() -> int:
    from autobot_shared.ssot_config import TimeoutConfig

    return TimeoutConfig.model_fields["api"].default


def _one(pattern: str, text: str, where: str) -> str:
    found = re.findall(pattern, text, re.MULTILINE)
    assert len(found) == 1, f"{where}: expected exactly one match for {pattern!r}, found {found}"
    return found[0]


def _mirrors() -> dict[str, str]:
    """Every place that restates the number, as the string it restates."""
    read = lambda p: p.read_text(encoding="utf-8")  # noqa: E731
    return {
        "ssot-config.ts default": _one(
            r"getEnvPositiveInt\(import\.meta\.env, 'VITE_API_TIMEOUT', (\d+)\)", read(_SSOT_TS), "ssot-config.ts"
        ),
        "autobot-frontend/.env.example": _one(
            r"^VITE_API_TIMEOUT=(\S+)$", read(_FRONTEND_ENV_EXAMPLE), "frontend .env.example"
        ),
        "root .env.example VITE_": _one(r"^VITE_API_TIMEOUT=(\S+)$", read(_ROOT_ENV_EXAMPLE), "root .env.example"),
        "root .env.example AUTOBOT_": _one(
            r"^AUTOBOT_API_TIMEOUT=(\S+)$", read(_ROOT_ENV_EXAMPLE), "root .env.example"
        ),
        "ssot-config.sh": _one(r'^: "\$\{AUTOBOT_API_TIMEOUT:=(\S+)\}"$', read(_SHELL_SSOT), "ssot-config.sh"),
    }


def test_the_ssot_holds_the_owner_value():
    """60000 ms is the owner's decision on #17856; a silent edit fails here first."""
    assert _ssot_value() == 60000


@pytest.mark.parametrize("where", sorted(_mirrors()))
def test_every_mirror_restates_the_ssot(where):
    assert _mirrors()[where] == str(_ssot_value()), f"{where} disagrees with TimeoutConfig.api"


#: The env overlays and profile files (#19333): each may omit the key -- an overlay carries only
#: keys that differ from the base -- but never restate a different number. 10000 sat in two of
#: them with no recorded reason, aborting long LLM-backed calls after 10 s on those profiles.
_ENV_OVERLAYS = (
    ".env.base",
    ".env.example",
    ".env.localhost",
    ".env.native-vm",
    ".env.network",
    ".env.network-template",
    "docker/.env.docker",
)
#: Reads active AND commented-out (``# KEY=...``) assignments, indented or ``export``-prefixed, with
#: quotes stripped: a commented 10000 in an overlay is a copy that misleads the next reader too.
_API_TIMEOUT_LINE = re.compile(
    r"""^\s*(?:#\s*)?(?:export\s+)?(?:AUTOBOT|VITE)_API_TIMEOUT=["']?([^\s#"']+)["']?\s*(?:#.*)?$""", re.MULTILINE
)


def _overlay_values(text: str) -> list[str]:
    return _API_TIMEOUT_LINE.findall(text)


@pytest.mark.parametrize("rel", _ENV_OVERLAYS)
def test_no_env_overlay_restates_a_different_api_timeout(rel):
    path = _ROOT / rel
    assert path.is_file(), f"{rel} moved; update _ENV_OVERLAYS (#19333)"
    wrong = [v for v in _overlay_values(path.read_text(encoding="utf-8")) if v != str(_ssot_value())]
    assert not wrong, f"{rel} restates the API timeout as {wrong}; drop the line, the base carries {_ssot_value()}"


def test_a_different_overlay_value_is_caught():
    assert _overlay_values("AUTOBOT_API_TIMEOUT=10000\n") == ["10000"]
    assert _overlay_values("export VITE_API_TIMEOUT=10000  # profile\n") == ["10000"]
    assert _overlay_values("# AUTOBOT_API_TIMEOUT=10000\n") == ["10000"], "a commented copy is still a copy"
    assert _overlay_values("    AUTOBOT_API_TIMEOUT='10000'\n") == ["10000"], "indented and quoted"


def test_a_disagreeing_mirror_is_caught():
    """Contrast: the comparison above fails on a wrong value, so a pass is not vacuous."""
    sample = "VITE_API_TIMEOUT=30000\n"
    assert _one(r"^VITE_API_TIMEOUT=(\S+)$", sample, "fixture") != str(_ssot_value())


def test_appconfig_reads_the_ssot_getter_with_no_literal_fallback():
    text = _APP_CONFIG.read_text(encoding="utf-8")
    assert "VITE_API_TIMEOUT" not in text, "AppConfig.js reads the env var itself instead of getApiTimeout()"
    assert text.count("getApiTimeout()") >= 2, "AppConfig.js timeout and timeouts.default must both use getApiTimeout()"


def test_generator_derives_the_frontend_key_from_the_field():
    """The frontend writer only; its AUTOBOT_API_TIMEOUT lines are #18565."""
    text = _GENERATOR.read_text(encoding="utf-8")
    assert 'TimeoutConfig.model_fields["api"].default' in text
    line = _one(r"^.*VITE_API_TIMEOUT=.*$", text, "generate-env-files.py")
    assert "{API_TIMEOUT_MS}" in line, f"generate-env-files.py writes a non-derived VITE_API_TIMEOUT: {line.strip()}"


def test_sync_env_maps_the_ssot_key():
    text = _SYNC_ENV.read_text(encoding="utf-8")
    mapping = re.search(r"AUTOBOT_API_TIMEOUT\)\s*\n\s*echo \"VITE_API_TIMEOUT=\$value\"", text)
    assert mapping, "sync-env.sh must map VITE_API_TIMEOUT from AUTOBOT_API_TIMEOUT, not a literal"
