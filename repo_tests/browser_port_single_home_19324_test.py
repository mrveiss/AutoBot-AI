# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The browser-service port has ONE home, and 3000 is Grafana's (#19324).

``autobot_shared/ssot_config.py`` ``port.browser`` (``AUTOBOT_BROWSER_SERVICE_PORT``)
is the home. Python readers import it. A file that cannot import Python -- an
env template, an Ansible var, a shell script, a JS/TS config -- carries the
literal, and is listed in ``_PINNED`` below, which holds every one of those
literals equal to the home (owner ruling on #19343: a guarded pin satisfies
"derive").

Three rules, each its own test:

1. Every pinned copy still exists and equals the home.
2. A browser-port definition (``browser_port: N``, ``PLAYWRIGHT_PORT=N``,
   ``VITE_BROWSER_PORT || 'N'`` ...) anywhere else fails: it is a second home.
3. 3000 in a browser/Playwright port context fails. 3000 is Grafana's port; the
   live fleet runs ``autobot-playwright`` on 9001 with Grafana on loopback 3000.
   There is no Docker exception: the Playwright compose files and the hybrid
   playbook bind 9001 like the fleet, and so do their clients (#19418).

Shell ``${AUTOBOT_BROWSER_SERVICE_PORT:-N}`` fallbacks are not definitions here:
``tools/lint/check_port_fallbacks_match_ssot.py`` already holds them to the SSOT.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

_REPO_ROOT = repo_root()
_HOME = "autobot_shared/ssot_config.py"
_HOME_FIELD = re.compile(r'browser: int = Field\(default=(\d+), alias="AUTOBOT_BROWSER_SERVICE_PORT"\)')

# Where a browser-port copy can live. Every glob here is already in the python
# filter or the #15900 record; the two concrete JS files are named directly.
_SCAN = (
    "*.py",
    "*.sh",
    "*.yml",
    "*.yaml",
    "*.j2",
    "*.service",
    "*.ts",
    ".env*",
    "autobot-frontend/src/**",
    "autobot-infrastructure/**",
    "autobot-frontend/vite.config.js",
    "autobot-browser-worker/playwright-server.js",
)
_SKIP_PREFIXES = ("docs/", "changelog/")
#: Prose describes the port; it does not define one (stale prose: #19419).
_SKIP_SUFFIXES = (".md",)
_MIN_SCANNED = 3000

_NAMES = (
    "AUTOBOT_BROWSER_SERVICE_PORT|AUTOBOT_BROWSER_PORT|BROWSER_SERVICE_PORT|BROWSER_PORT|"
    "VITE_BROWSER_PORT|VITE_PLAYWRIGHT_PORT|PLAYWRIGHT_PORT|PLAYWRIGHT_SERVER_PORT|"
    "playwright_port|browser_port|browser_service_port|browser_worker_port|backend_browser_port"
)
#: NAME=N, NAME: N, NAME || 'N', "NAME", "N", and Jinja NAME | default(N).
_DEFINITION = re.compile(
    rf"(?<![A-Za-z0-9_])(?:{_NAMES})(?![A-Za-z0-9_])"
    r"(?:[\"']?\s*(?:[:=]|\|\||,)\s*[\"']?|\s*\|\s*default\(\s*)(\d{2,5})\b"
)
_NAME_HINT = re.compile(_NAMES)
_PORT_3000 = re.compile(
    r":3000\b|port\W{0,6}3000\b|\b3000/tcp|\[3000\]|['\"]3000['\"]|--port[ =]3000\b|[\[,]\s*3000\s*[,\]]", re.I
)
_BROWSER_CONTEXT = re.compile(r"browser|playwright", re.I)
#: A line that names Grafana or calls 3000 legacy is explaining the port, not using it.
_EXPLAINS_3000 = re.compile(r"grafana|legacy", re.I)

#: path -> patterns whose one group is a browser-port literal pinned to the home.
_PINNED: dict[str, tuple[str, ...]] = {
    ".env.base": (r"^AUTOBOT_BROWSER_SERVICE_PORT=(\d+)$",),
    ".env.example": (
        r"^AUTOBOT_BROWSER_SERVICE_PORT=(\d+)$",
        r"^VITE_BROWSER_PORT=(\d+)$",
        r"^AUTOBOT_BROWSER_SERVICE_URL=http://YOUR_BROWSER_VM_IP:(\d+)$",
    ),
    ".env.localhost": (r"^AUTOBOT_BROWSER_SERVICE_URL=http://127\.0\.0\.1:(\d+)$",),
    "autobot_shared/network_constants.py": (r'"BROWSER_SERVICE_PORT": \("port\.browser", "(\d+)", int\)',),
    "autobot_shared/env_registry_backend_services.py": (
        r'name="AUTOBOT_BROWSER_SERVICE_PORT",\n\s+type=int,\n\s+default=(\d+),',
    ),
    "autobot-frontend/src/config/ssot-config.ts": (r"^export const PORT_DEFAULTS = \{[^}]*?\n  browser: (\d+),",),
    "autobot-frontend/vite.config.js": (r"VITE_BROWSER_PORT \|\| '(\d+)'",),
    "autobot-browser-worker/playwright-server.js": (r"process\.env\.PLAYWRIGHT_PORT \|\| '(\d+)'",),
    "autobot-infrastructure/shared/mcp/tools/mcp-autobot-tracker/src/constants/network.ts": (
        r"process\.env\.BROWSER_SERVICE_PORT \|\| '(\d+)'",
    ),
    "autobot-infrastructure/shared/scripts/utilities/test_console_using_browser_vm.js": (
        r"process\.env\.AUTOBOT_BROWSER_SERVICE_PORT \|\| '(\d+)'",
    ),
    "autobot-infrastructure/shared/scripts/lib/ssot-config.sh": (r"AUTOBOT_BROWSER_SERVICE_PORT:=(\d+)\}",),
    "autobot-infrastructure/shared/config/complete.yaml": (r"^    browser_service: (\d+)$",),
    "autobot-infrastructure/shared/config/ufw-defaults.sh": (r"ufw allow (\d+)/tcp comment 'Browser Worker'",),
    "autobot-infrastructure/shared/scripts/infrastructure/browser-playwright.service": (
        r'Environment="PLAYWRIGHT_PORT=(\d+)"',
    ),
    "autobot-slm-backend/ansible/inventory/production.yml": (
        r"^    browser_port: (\d+)\b",
        r"^        playwright_port: (\d+)\b",
    ),
    "autobot-slm-backend/ansible/inventory/group_vars/infrastructure.yml": (r"^    browser: (\d+)\b",),
    "autobot-slm-backend/ansible/inventory/group_vars/browser.yml": (
        r"^      port: (\d+)  # #19324",
        r"^    port: (\d+)  # #19324",
        r'url: "http://127\.0\.0\.1:(\d+)/health"',
    ),
    "autobot-slm-backend/ansible/roles/common/defaults/main.yml": (r"^  browser: (\d+)$",),
    "autobot-slm-backend/ansible/roles/browser/defaults/main.yml": (r"^playwright_port: (\d+)$",),
    "autobot-slm-backend/ansible/roles/browser/vars/main.yml": (r"^playwright_port: (\d+)$",),
    "autobot-slm-backend/ansible/roles/backend/defaults/main.yml": (r"^backend_browser_port: (\d+)\b",),
    "autobot-slm-backend/ansible/roles/backend/templates/backend.env.j2": (r"browser_port \| default\((\d+)\)",),
    "autobot-slm-backend/ansible/roles/distributed_setup/defaults/main.yml": (r"^browser_service_port: (\d+)\b",),
    "autobot-slm-backend/ansible/setup-user-backend.yml": (r"browser_worker_port: (\d+)\b",),
    "autobot-slm-backend/ansible/setup-browser-worker.yml": (r"playwright_port \| default\((\d+)\)",),
    "autobot-slm-backend/ansible/playbooks/update-all-nodes.yml": (r"playwright_port \| default\((\d+)\)",),
    "autobot-infrastructure/shared/tests/frontend-test-via-playwright-api.js": (
        r"process\.env\.AUTOBOT_BROWSER_SERVICE_PORT \|\| '(\d+)'",
    ),
    "autobot-infrastructure/shared/tests/screenshots/test-browser-console-errors.js": (
        r"process\.env\.AUTOBOT_BROWSER_SERVICE_PORT \|\| '(\d+)'",
    ),
    "autobot-infrastructure/shared/tests/screenshots/test-frontend-edge-error.js": (
        r"process\.env\.AUTOBOT_BROWSER_SERVICE_PORT \|\| '(\d+)'",
    ),
    "autobot-infrastructure/shared/tests/screenshots/test-frontend-via-docker.js": (
        r"process\.env\.AUTOBOT_BROWSER_SERVICE_PORT \|\| '(\d+)'",
    ),
    "autobot-infrastructure/shared/tests/screenshots/test-silent-chat-deletion.js": (
        r"process\.env\.AUTOBOT_BROWSER_SERVICE_PORT \|\| '(\d+)'",
    ),
    "autobot-infrastructure/shared/tests/screenshots/test-visible-browser.js": (
        r"process\.env\.AUTOBOT_BROWSER_SERVICE_PORT \|\| '(\d+)'",
    ),
    "autobot-slm-backend/ansible/playbooks/deploy-hybrid-docker.yml": (
        r"playwright_port \| default\((\d+)\)",
    ),  # #19418
    "autobot-slm-backend/ansible/playbooks/health-check.yml": (
        r"browser_port \| default\((\d+)\)",
        r"127\.0\.0\.1:\{\{ browser_port \| default\((\d+)\) \}\}/health",  # #19432: the probe task
    ),
    "autobot-slm-backend/ansible/playbooks/enroll-node.yml": (r"ports: \[(\d+), 5900\]",),
    "autobot-slm-backend/ansible/roles/dependency_patching/vars/main.yml": (
        r"service_name: \"autobot-playwright\"\n\s+health_endpoint: \"/health\"\n\s+health_port: (\d+)",
    ),
    "autobot-infrastructure/shared/config/deployment/distributed.yml": (r"playwright-vnc:\n.*\n\s+port: (\d+)\n",),
    "autobot-infrastructure/shared/config/deployment/kubernetes.yml": (r"playwright-vnc:\n.*\n\s+port: (\d+)\n",),
    "autobot-infrastructure/shared/config/deployment/local.yml": (r"playwright-vnc:\n.*\n\s+port: (\d+)\n",),
    "autobot-infrastructure/shared/config/distributed.yaml": (r"    browser:\n.*\n\s+port: (\d+)\n",),
}

#: Files whose 3000 or browser-port literal is a test input or a rule ABOUT the port.
_NOT_A_COPY = frozenset(
    {
        "repo_tests/browser_port_single_home_19324_test.py",  # this guard's own fixtures
        "repo_tests/one_playwright_server_18549_test.py",  # compose port-mismatch fixtures
        "repo_tests/deploy_scripts_standalone_18132_test.py",  # an arbitrary 19001 override
        "tools/lint/check_port_fallbacks_match_ssot_test.py",  # the diverging-fallback fixture
        "tools/lint/check_port_fallbacks_match_ssot.py",  # its docstring quotes the #14198 defect
        ".pre-commit-config.yaml",  # the comment on that hook quotes it too
        "autobot-infrastructure/shared/tests/test_ssot_config_lib.sh",  # same, for the shell library
        "autobot-slm-backend/tests/test_updater_browser_port_and_backend_unit.py",  # asserts 3000 is absent
        "autobot-backend/tests/unit/api/test_browser_mcp_url_guard.py",  # an arbitrary localhost URL
        "autobot-backend/tests/unit/api/test_browser_url_guard.py",  # an arbitrary localhost URL
        "autobot-frontend/src/components/__tests__/VisualBrowserPanel.test.ts",  # URL normalisation input
        "autobot-infrastructure/shared/config/.eslintrc.js",  # the rule that bans the literal
        "autobot-frontend/src/config/__tests__/ssot-config.spec.ts",  # lines 60/72: asserts 3000 is absent
        "autobot-slm-backend/ansible/roles/browser/defaults/main.yml",  # playwright_ports_legacy cleanup list (#19419)
    }
)


def _home_port(root: Path) -> str:
    match = _HOME_FIELD.search((root / _HOME).read_text(encoding="utf-8"))
    assert match, f"{_HOME}: the port.browser field moved -- this guard cannot read its home"
    return match.group(1)


def _scanned(root: Path) -> list[str]:
    paths = tracked_paths(root, *_SCAN)
    return [p for p in paths if not p.startswith(_SKIP_PREFIXES) and not p.endswith(_SKIP_SUFFIXES)]


@lru_cache(maxsize=None)
def _read(root: Path, rel: str) -> str:
    try:
        return (root / rel).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def pinned_drift(root: Path, pinned: dict[str, tuple[str, ...]], home: str) -> list[str]:
    """Each pinned pattern must match, and every literal it captures must equal *home*."""
    problems = []
    for rel, patterns in pinned.items():
        text = _read(root, rel)
        for pattern in patterns:
            values = re.findall(pattern, text, re.M)
            if not values:
                problems.append(f"{rel}: pinned pattern {pattern!r} no longer matches")
            problems += [f"{rel}: {v} != home {home} ({pattern!r})" for v in values if v != home]
    return problems


def unpinned_definitions(root: Path, paths: list[str], pinned: set[str], home: str) -> list[str]:
    """Browser-port definitions outside the home and the pinned set, or pinned ones off the home."""
    found = []
    for rel in paths:
        if rel == _HOME or rel in _NOT_A_COPY:
            continue
        text = _read(root, rel)
        if not _NAME_HINT.search(text):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in _DEFINITION.finditer(line):
                if rel not in pinned or match.group(1) != home:
                    found.append(f"{rel}:{lineno}: {line.strip()[:120]}")
    return found


#: How far up a YAML/INI block the context search looks for the task name or parent key.
_CONTEXT_LOOKBACK = 12


def _ancestor_lines(lines: list[str], index: int) -> list[str]:
    """The task ``name:`` and parent keys above *index*: each strictly less indented than the last."""
    indent = len(lines[index]) - len(lines[index].lstrip())
    found = []
    for back in range(index - 1, max(index - 1 - _CONTEXT_LOOKBACK, -1), -1):
        line = lines[back]
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        lead = len(line) - len(stripped)
        if lead < indent:
            found.append(stripped)
            indent = lead
    return found


def browser_3000(root: Path, paths: list[str]) -> list[str]:
    """3000 in a browser/Playwright port context, outside the Docker 3000 paths."""
    found = []
    for rel in paths:
        if rel in _NOT_A_COPY:
            continue
        text = _read(root, rel)
        if "3000" not in text:
            continue
        lines = text.splitlines()
        for lineno, line in enumerate(lines, start=1):
            if not _PORT_3000.search(line) or _EXPLAINS_3000.search(line):
                continue
            if _BROWSER_CONTEXT.search(rel) or _BROWSER_CONTEXT.search(line):
                found.append(f"{rel}:{lineno}: {line.strip()[:120]}")
            elif rel.endswith((".yml", ".yaml", ".j2")):
                # An Ansible task names its browser context on `- name:`, not on the url/port line.
                above = _ancestor_lines(lines, lineno - 1)
                if any(_BROWSER_CONTEXT.search(a) and not _EXPLAINS_3000.search(a) for a in above):
                    found.append(f"{rel}:{lineno}: {line.strip()[:100]}  [under: {above[-1][:60]}]")
    return found


@pytest.fixture(scope="module")
def scanned() -> list[str]:
    paths = _scanned(_REPO_ROOT)
    assert len(paths) >= _MIN_SCANNED, f"only {len(paths)} files enumerated -- the scan, not the tree, is empty"
    return paths


def test_the_home_is_9001_not_grafanas_3000() -> None:
    assert _home_port(_REPO_ROOT) == "9001", "the browser service is 9001; 3000 is Grafana (#4052)"


def test_every_pinned_copy_equals_the_home() -> None:
    drift = pinned_drift(_REPO_ROOT, _PINNED, _home_port(_REPO_ROOT))
    assert not drift, "pinned browser-port copies disagree with ssot_config.port.browser:\n" + "\n".join(drift)


def test_no_browser_port_definition_outside_the_home_and_the_pinned_set(scanned: list[str]) -> None:
    found = unpinned_definitions(_REPO_ROOT, scanned, set(_PINNED), _home_port(_REPO_ROOT))
    assert not found, (
        "a second home for the browser port -- import autobot_shared.ssot_config.config.port.browser "
        "(Python) or add the literal to _PINNED (non-Python):\n" + "\n".join(found)
    )


def test_no_browser_context_carries_grafanas_3000(scanned: list[str]) -> None:
    found = browser_3000(_REPO_ROOT, scanned)
    assert not found, "3000 is Grafana's port, not the browser service's:\n" + "\n".join(found)


def test_every_exception_still_exists() -> None:
    missing = sorted(p for p in _NOT_A_COPY | set(_PINNED) if not (_REPO_ROOT / p).is_file())
    assert not missing, f"listed but gone -- shrink the list: {missing}"


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text, encoding="utf-8")
    return tmp_path


def test_a_deliberate_copy_fails_every_rule(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        {
            "roles/x/defaults/main.yml": "browser_port: 9001\n",
            "web/vite.config.js": "port: env.VITE_BROWSER_PORT || '3000'\n",
            "scripts/check.sh": 'curl "http://$BROWSER_HOST:3000/health"\n',
            ".env.pinned": "VITE_BROWSER_PORT=3000\n",
        },
    )
    paths = ["roles/x/defaults/main.yml", "web/vite.config.js", "scripts/check.sh"]
    assert len(unpinned_definitions(root, paths, set(), "9001")) == 2
    assert len(browser_3000(root, paths)) == 2
    assert pinned_drift(root, {".env.pinned": (r"^VITE_BROWSER_PORT=(\d+)$",)}, "9001")


def test_a_3000_named_only_by_its_ansible_task_fails(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        {
            "pb/health.yml": (
                "- name: Test Playwright API health (Browser)\n  uri:\n"
                '    url: "http://127.0.0.1:3000/health"\n'
                "- name: Test Grafana\n  uri:\n"
                '    url: "http://127.0.0.1:3000/api/health"\n'
            ),
            "pb/roles.yml": "browser:\n  services: [x]\n  ports: [3000, 5900]\n",
        },
    )
    assert len(browser_3000(root, ["pb/health.yml", "pb/roles.yml"])) == 2


def test_the_same_tree_passes_once_the_copy_follows_the_home(tmp_path: Path) -> None:
    root = _tree(
        tmp_path,
        {
            "roles/x/defaults/main.yml": "browser_port: 9001\n",
            "scripts/check.sh": 'curl "http://$BROWSER_HOST:${AUTOBOT_BROWSER_SERVICE_PORT}/health"\n',
            "ops/grafana.yml": "# 3000 is Grafana's port, not the browser service's\n",
        },
    )
    paths = ["roles/x/defaults/main.yml", "scripts/check.sh", "ops/grafana.yml"]
    assert unpinned_definitions(root, paths, {"roles/x/defaults/main.yml"}, "9001") == []
    assert browser_3000(root, paths) == []
