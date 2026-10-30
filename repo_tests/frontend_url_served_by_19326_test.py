# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``AUTOBOT_FRONTEND_PORT`` is the Vite dev port; the served URL has its own homes (#19326).

It used to carry four meanings (Vite 5173, native nginx 80, nginx HTTPS 443, and the URL
``config.frontend_url`` was built from). Owner decision 2026-10-24, option B: ``port.frontend`` stays
the dev port, the served URL comes from ``tls.frontend_tls_port`` or ``port.frontend_http``, and
``AUTOBOT_FRONTEND_SERVED_BY=vite|nginx`` says which. Python readers import the homes; every copy
that cannot (shell, Ansible, j2, ``.env``) is held equal to its home here, which counts as derived
(owner ruling, #19343).

1. ``PINNED``: each copy states its home's value at every site its pattern finds, and finds at least
   ``floor`` sites, so a reworded file cannot pass by matching nothing.
2. ``FORBIDDEN``: ``AUTOBOT_FRONTEND_PORT`` / ``frontend_port`` assigned 80 or 443 -- the served ports
   under the dev port's name -- anywhere in production sources.
3. ``frontend_url`` resolves for vite, nginx with TLS, nginx with HTTP, derives unset from the environment, and raises for invalid.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.deployment_profile import FRONTEND_SERVED_BY_VALUES, FrontendServedByError, try_frontend_url
from autobot_shared.ssot_config import AutoBotConfig, PortConfig
from autobot_shared.ssot_tls import TLSConfig
from tools.lint import check_getenv_ssot_drift  # noqa: F401 -- puts tools/lint on sys.path for the sibling import

from tools.lint import _env_fork_scan as scan_mod  # isort: skip
from tools.lint._scan_helpers import EmptyEnumeration  # isort: skip

_ROOT = repo_root()
_ANSIBLE = "autobot-slm-backend/ansible"
_SHELL_SSOT = "autobot-infrastructure/shared/scripts/lib/ssot-config.sh"
_ORCH = "autobot-slm-backend/services/service_orchestrator.py"
_HOMES = {
    "dev": lambda: str(PortConfig.model_fields["frontend"].default),
    "http": lambda: str(PortConfig.model_fields["frontend_http"].default),
    "tls": lambda: str(TLSConfig.model_fields["frontend_tls_port"].default),
    "vite": lambda: "vite",
    "nginx": lambda: "nginx",
    "tls_env": lambda: "AUTOBOT_FRONTEND_TLS_PORT",
    "dev_env": lambda: "AUTOBOT_FRONTEND_PORT",
}


class Pin(NamedTuple):
    """One non-importing copy: the home it restates, where, how to find each site, and how many."""

    home: str
    rel: str
    pattern: str
    floor: int


#: Every copy that cannot import its home. Each pattern has ONE capture group: the stated value.
PINNED: tuple[Pin, ...] = (
    Pin("dev", ".env.example", r"^AUTOBOT_FRONTEND_PORT=(\d+)$", 1),
    Pin("dev", ".env.base", r"^AUTOBOT_FRONTEND_PORT=(\d+)$", 1),
    Pin("dev", _SHELL_SSOT, r"AUTOBOT_FRONTEND_PORT:=(\d+)", 1),
    Pin("dev", f"{_ANSIBLE}/deploy-hybrid.sh", r"^AUTOBOT_FRONTEND_PORT=(\d+)$", 1),
    Pin("http", ".env.example", r"^AUTOBOT_FRONTEND_HTTP_PORT=(\d+)$", 1),
    Pin("http", _SHELL_SSOT, r"AUTOBOT_FRONTEND_HTTP_PORT:=(\d+)", 1),
    Pin("http", f"{_ANSIBLE}/deploy-native.sh", r"^AUTOBOT_FRONTEND_HTTP_PORT=(\d+)$", 1),
    Pin("tls", _SHELL_SSOT, r"AUTOBOT_FRONTEND_TLS_PORT:=(\d+)", 1),
    Pin("tls", f"{_ANSIBLE}/fix-slm-env-ports.yml", r'^    frontend_tls_port: "(\d+)"$', 1),
    Pin("tls", f"{_ANSIBLE}/setup-user-frontend.yml", r"^    frontend_tls_port: (\d+)$", 1),
    Pin("tls", f"{_ANSIBLE}/enable-tls.yml", r"^    frontend_tls_port: (\d+)$", 1),
    Pin("tls", f"{_ANSIBLE}/roles/distributed_setup/defaults/main.yml", r"^frontend_tls_port: (\d+)$", 1),
    Pin("tls", f"{_ANSIBLE}/roles/frontend/defaults/main.yml", r"^frontend_tls_port: (\d+)$", 1),
    Pin("tls", f"{_ANSIBLE}/roles/backend/defaults/main.yml", r"^frontend_tls_port: (\d+)$", 1),
    Pin("tls", "autobot-slm-backend/api/infrastructure.py", r'"frontend_tls_port": (\d+)', 1),
    Pin("nginx", f"{_ANSIBLE}/deploy-native.sh", r"^AUTOBOT_FRONTEND_SERVED_BY=(\w+)$", 1),
    Pin("nginx", f"{_ANSIBLE}/fix-slm-env-ports.yml", r'line: "AUTOBOT_FRONTEND_SERVED_BY=(\w+)"', 1),
    Pin(
        "nginx",
        f"{_ANSIBLE}/roles/distributed_setup/templates/distributed.env.j2",
        r"^AUTOBOT_FRONTEND_SERVED_BY=(\w+)$",
        1,
    ),
    Pin("nginx", f"{_ANSIBLE}/roles/backend/templates/backend.env.j2", r"^AUTOBOT_FRONTEND_SERVED_BY=(\w+)$", 1),
    Pin("vite", ".env.example", r"^AUTOBOT_FRONTEND_SERVED_BY=(\w+)$", 1),
    Pin("vite", f"{_ANSIBLE}/deploy-hybrid.sh", r"^AUTOBOT_FRONTEND_SERVED_BY=(\w+)$", 1),
    Pin("vite", "conftest.py", r'setdefault\("AUTOBOT_FRONTEND_SERVED_BY", "(\w+)"\)', 1),
    Pin("tls_env", _ORCH, r'"frontend": ServiceDefinition\((?:.*\n)*?\s+default_port_env="(\w+)"', 1),
    Pin("dev_env", _ORCH, r'"frontend-dev": ServiceDefinition\((?:.*\n)*?\s+default_port_env="(\w+)"', 1),
)
#: nginx writers also write the TLS switch and port together with the served-by key (no host switches URL).
PAIRED: tuple[tuple[str, str], ...] = (
    (f"{_ANSIBLE}/fix-slm-env-ports.yml", "AUTOBOT_FRONTEND_TLS_PORT="),
    (f"{_ANSIBLE}/roles/distributed_setup/templates/distributed.env.j2", "AUTOBOT_FRONTEND_TLS_PORT="),
    (f"{_ANSIBLE}/roles/backend/templates/backend.env.j2", "AUTOBOT_FRONTEND_TLS_PORT="),
    (f"{_ANSIBLE}/deploy-native.sh", "AUTOBOT_FRONTEND_HTTP_PORT="),
)

#: The served ports written under the dev port's name: the shapes this issue retired.
FORBIDDEN: tuple[re.Pattern[str], ...] = (
    re.compile(r"AUTOBOT_FRONTEND_PORT(?:=|:=|:-|[\"']?\s*[:=]\s*[\"']?)(80|443)\b"),
    re.compile(r"^\s*[\"']?frontend_port[\"']?\s*[:=]\s*[\"']?(80|443)\b", re.MULTILINE),
    re.compile(r"VITE_FRONTEND_PORT(?:=|:=|:-)(?:80\b|443\b|\{\{ *frontend_tls_port)"),
)
#: file -> how many sites of a FORBIDDEN shape stay; shrink-only (empty: none remain).
#: The one left: the SPA builds its OAuth callback from this port on a nginx host, so it cannot go
#: until the SPA has a served-URL input (#20058).
KNOWN: dict[str, int] = {f"{_ANSIBLE}/fix-slm-env-ports.yml": 1}

_SUFFIXES = (".py", ".sh", ".yml", ".yaml", ".j2", ".env", ".service")
_SCAN_ROOTS = (*scan_mod.SCAN_ROOTS,)
_NOT_PRODUCTION = re.compile(r"(_test\.py$|(^|/)test_[^/]*\.py$|/tests?/|/__tests__/|\.spec\.|/generated/)")


def _production(rel: str) -> bool:
    return rel.split("/")[0] in _SCAN_ROOTS and not _NOT_PRODUCTION.search(rel)


def _scanned_files(root: Path) -> list[str]:
    """Tracked production sources and the root ``.env*`` profiles; ``[]`` on an empty tree."""
    try:
        paths = scan_mod.tracked_paths(root, *(f"*{s}" for s in _SUFFIXES), ".env*")
    except EmptyEnumeration:
        return []
    return sorted(rel for rel in paths if _production(rel) or rel.startswith(".env"))


FILES = declare(
    "frontend-url-served-by-scan",
    discover=_scanned_files,
    floor=4308,  # mid-window: population 4358, window (4258, 4358)
    growth=100,
    what="production sources and env profiles",
    roots=_SCAN_ROOTS,
)


def pin_violations(pin: Pin, text: str, value: str) -> list[str]:
    """Each site in *text* that states other than *value*, or a shortfall below the floor."""
    found = list(re.finditer(pin.pattern, text, re.MULTILINE))
    out = [
        f"{pin.rel}:{text.count(chr(10), 0, m.start(1)) + 1}: states {m.group(1)}, home '{pin.home}' says {value}"
        for m in found
        if m.group(1) != value
    ]
    if len(found) < pin.floor:
        out.append(f"{pin.rel}: pattern found {len(found)} site(s), floor {pin.floor} -- reworded or moved?")
    return out


def forbidden_sites(rel: str, text: str) -> list[str]:
    """Each statement in *text* of a served port under the dev port's name."""
    return [
        f"{rel}:{text.count(chr(10), 0, m.start()) + 1}: {m.group(0).strip()} -- the dev port is "
        "AUTOBOT_FRONTEND_PORT; the served ports are AUTOBOT_FRONTEND_TLS_PORT / AUTOBOT_FRONTEND_HTTP_PORT"
        for pattern in FORBIDDEN
        for m in pattern.finditer(text)
    ]


def _read(rel: str) -> str:
    try:
        return (_ROOT / rel).read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


def test_every_pinned_copy_states_its_home() -> None:
    bad = [v for pin in PINNED for v in pin_violations(pin, _read(pin.rel), _HOMES[pin.home]())]
    assert bad == [], "\n".join(bad)


def test_every_nginx_writer_writes_the_served_port_with_it() -> None:
    missing = [f"{rel}: writes SERVED_BY=nginx but not {key}" for rel, key in PAIRED if key not in _read(rel)]
    assert missing == [], "\n".join(missing)


def test_no_served_port_is_written_under_the_dev_ports_name() -> None:
    files = FILES.examined(_ROOT)
    assert len(files) >= 1000, f"the sweep read {len(files)} files -- a clean result would be blind"
    found = []
    for rel in files:
        sites = forbidden_sites(rel, _read(rel))
        if len(sites) > KNOWN.get(rel, 0):
            found += sites
    assert found == [], f"checked {len(files)} files:\n" + "\n".join(found)


def test_the_known_counts_only_shrink() -> None:
    stale = [rel for rel, n in KNOWN.items() if len(forbidden_sites(rel, _read(rel))) < n]
    assert stale == [], f"{stale} -- lower the KNOWN count, or delete the entry at zero"


def test_a_drifted_pin_is_caught() -> None:
    pin = Pin("http", "x.sh", r"^AUTOBOT_FRONTEND_HTTP_PORT=(\d+)$", 1)
    assert pin_violations(pin, "AUTOBOT_FRONTEND_HTTP_PORT=80\n", "80") == []
    assert pin_violations(pin, "AUTOBOT_FRONTEND_HTTP_PORT=8080\n", "80") == [
        "x.sh:1: states 8080, home 'http' says 80"
    ]
    assert pin_violations(pin, "FRONTEND_HTTP_PORT=80\n", "80"), "a reworded site must fail the floor"


@pytest.mark.parametrize(
    "text",
    [
        "AUTOBOT_FRONTEND_PORT=80\n",
        "AUTOBOT_FRONTEND_PORT=443",
        "${AUTOBOT_FRONTEND_PORT:-443}",
        "frontend_port: 443\n",
        '"frontend_port": 80',
        'AUTOBOT_FRONTEND_PORT: "443"',
    ],
)
def test_a_served_port_under_the_dev_ports_name_is_caught(text: str) -> None:
    assert forbidden_sites("a.sh", text), text


@pytest.mark.parametrize(
    "text",
    [
        "AUTOBOT_FRONTEND_PORT=5173\n",
        "AUTOBOT_FRONTEND_PORT=15173",
        "AUTOBOT_FRONTEND_PORT=8443",
        "frontend_tls_port: 443\n",
        "AUTOBOT_FRONTEND_TLS_PORT=443",
        "frontend_port: 5173\n",
    ],
)
def test_the_dev_port_and_the_served_ports_under_their_own_names_pass(text: str) -> None:
    assert forbidden_sites("a.sh", text) == [], text


_ENV = (
    "AUTOBOT_ENVIRONMENT",
    "AUTOBOT_ENV",
    "AUTOBOT_FRONTEND_HOST",
    "AUTOBOT_FRONTEND_PORT",
    "AUTOBOT_FRONTEND_HTTP_PORT",
    "AUTOBOT_FRONTEND_TLS_PORT",
    "AUTOBOT_FRONTEND_TLS_ENABLED",
    "AUTOBOT_FRONTEND_SERVED_BY",
)


def _config(monkeypatch: pytest.MonkeyPatch, **env: str) -> AutoBotConfig:
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AUTOBOT_FRONTEND_HOST", "ui.example.test")
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return AutoBotConfig(_env_file=None)


@pytest.mark.parametrize(
    ("env", "url"),
    [
        ({"AUTOBOT_FRONTEND_SERVED_BY": "vite"}, "http://ui.example.test:5173"),
        ({"AUTOBOT_FRONTEND_SERVED_BY": "vite", "AUTOBOT_FRONTEND_PORT": "15173"}, "http://ui.example.test:15173"),
        (
            {"AUTOBOT_FRONTEND_SERVED_BY": "nginx", "AUTOBOT_FRONTEND_TLS_ENABLED": "true"},
            "https://ui.example.test:443",
        ),
        (
            {
                "AUTOBOT_FRONTEND_SERVED_BY": "nginx",
                "AUTOBOT_FRONTEND_TLS_ENABLED": "true",
                "AUTOBOT_FRONTEND_TLS_PORT": "8444",
            },
            "https://ui.example.test:8444",
        ),
        ({"AUTOBOT_FRONTEND_SERVED_BY": "nginx"}, "http://ui.example.test:80"),
        ({"AUTOBOT_FRONTEND_SERVED_BY": "NGINX", "AUTOBOT_FRONTEND_HTTP_PORT": "8080"}, "http://ui.example.test:8080"),
        # nginx ignores the dev port: the Vite value must not leak into the served URL.
        ({"AUTOBOT_FRONTEND_SERVED_BY": "nginx", "AUTOBOT_FRONTEND_PORT": "5173"}, "http://ui.example.test:80"),
    ],
)
def test_frontend_url_follows_the_served_by_profile(monkeypatch: pytest.MonkeyPatch, env: dict, url: str) -> None:
    assert _config(monkeypatch, **env).frontend_url == url


@pytest.mark.parametrize(
    ("environment", "url"),
    [
        ("development", "http://ui.example.test:5173"),
        ("test", "http://ui.example.test:5173"),
        ("production", "http://ui.example.test:80"),
        ("staging", "http://ui.example.test:80"),
    ],
)
def test_an_unset_served_by_follows_the_environment(
    monkeypatch: pytest.MonkeyPatch, environment: str, url: str
) -> None:
    assert _config(monkeypatch, AUTOBOT_ENVIRONMENT=environment).frontend_url == url


def test_an_explicit_served_by_overrides_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _config(monkeypatch, AUTOBOT_ENVIRONMENT="production", AUTOBOT_FRONTEND_SERVED_BY="vite")
    assert cfg.frontend_url == "http://ui.example.test:5173"


@pytest.mark.parametrize("value", ["apache", "vite,nginx", "5173", "true"])
def test_an_unknown_served_by_raises_rather_than_picking_a_port(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    with pytest.raises(FrontendServedByError, match="expected one of"):
        _config(monkeypatch, AUTOBOT_FRONTEND_SERVED_BY=value).frontend_url  # noqa: B018


def test_an_empty_served_by_is_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _config(monkeypatch, AUTOBOT_ENVIRONMENT="production", AUTOBOT_FRONTEND_SERVED_BY="  ")
    assert cfg.frontend_url == "http://ui.example.test:80"


def test_the_valid_values_are_the_two_the_profile_documents() -> None:
    assert FRONTEND_SERVED_BY_VALUES == ("vite", "nginx")


def test_try_frontend_url_leaves_the_frontend_out_when_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    assert try_frontend_url(_config(monkeypatch, AUTOBOT_FRONTEND_SERVED_BY="apache")) is None
    assert try_frontend_url(_config(monkeypatch, AUTOBOT_FRONTEND_SERVED_BY="vite")) == "http://ui.example.test:5173"


def test_get_service_url_does_not_evaluate_the_frontend_for_other_services(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _config(monkeypatch, AUTOBOT_FRONTEND_SERVED_BY="apache")
    assert cfg.get_service_url("backend") is not None and cfg.get_service_url("nope") is None
    with pytest.raises(FrontendServedByError):
        cfg.get_service_url("frontend")
