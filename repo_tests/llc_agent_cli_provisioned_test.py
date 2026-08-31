# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss

"""#12681: every deployment path that runs LLC agents must provision their CLIs.

`resolve_cli_binary` returns None when the binary is absent, and a hired agent
then fails at dispatch rather than at hire time. The container image installed
`claude` and `gh` and proved they resolved at build time; the ansible path
installed neither, so an agent hired on a systemd deployment could never run.

These assert the PROVISIONING, not the resolver. A test over `resolve_cli_binary`
passes whether or not anything ever installs the binary — which is how this
stayed invisible.

The ansible assertions parse the task file and inspect the actual tasks. An
earlier version of this guard matched raw source text and was **vacuous**: `"gh"
in text` is satisfied by the word *Copyright* in the licence header, and a
`claude --version` regex matched an explanatory comment rather than the templated
`cmd`, so deleting the real verify task left the test green. Substring checks
against a whole file are not evidence.

Deliberately no `shutil.which(...)` gate anywhere: a test skipped for a missing
binary is indistinguishable from a pass (#14550).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

yaml = pytest.importorskip("yaml")

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "docker/backend/Dockerfile"
ANSIBLE_TASKS = REPO_ROOT / "autobot-slm-backend/ansible/roles/backend/tasks/main.yml"

AGENT_CLIS = ("gh", "claude")
PACKAGES = ("gh", "claude-code")


def _tasks() -> list[dict[str, Any]]:
    """Every task in the backend role, including those nested in block/rescue/always."""
    assert ANSIBLE_TASKS.is_file(), f"{ANSIBLE_TASKS} missing — this guard would pass vacuously"
    loaded = yaml.safe_load(ANSIBLE_TASKS.read_text(encoding="utf-8"))
    out: list[dict[str, Any]] = []

    def walk(items: Any) -> None:
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            out.append(item)
            for key in ("block", "rescue", "always"):
                walk(item.get(key))

    walk(loaded)
    assert out, "parsed no tasks — the guard would pass on an empty set"
    return out


def _install_task() -> dict[str, Any]:
    for task in _tasks():
        apt = task.get("ansible.builtin.apt")
        if isinstance(apt, dict) and "claude-code" in str(apt.get("name", "")):
            return task
    raise AssertionError("no apt task installs claude-code (#12681)")


def _verify_task() -> dict[str, Any]:
    for task in _tasks():
        cmd = task.get("ansible.builtin.command")
        cmd_str = cmd.get("cmd", "") if isinstance(cmd, dict) else str(cmd or "")
        if "--version" in cmd_str and task.get("loop"):
            return task
    raise AssertionError("no task resolves the agent CLIs with --version (#12681)")


@pytest.mark.parametrize("package", PACKAGES)
def test_ansible_installs_each_agent_cli(package: str) -> None:
    """Asserted against the apt task's package list, never against file text."""
    names = _install_task()["ansible.builtin.apt"]["name"]
    rendered = names if isinstance(names, str) else " ".join(map(str, names))
    assert re.search(rf"(?<![\w-]){re.escape(package)}(?![\w-])", rendered), (
        f"the apt task does not install '{package}'; it installs: {rendered!r}. "
        f"A deployment running LLC agents without it hires agents that cannot dispatch."
    )


@pytest.mark.parametrize("binary", AGENT_CLIS)
def test_ansible_proves_each_cli_resolves(binary: str) -> None:
    """Installing without resolving lets a broken PATH look like a clean provision."""
    task = _verify_task()
    loop = task.get("loop") or []
    assert binary in [str(x) for x in loop], (
        f"the verify task does not resolve '{binary}' (loop={loop!r}); an install "
        "regression for it would be silent"
    )


def test_the_cli_install_is_outside_the_restart_guarded_window() -> None:
    """#12139: a failure inside that block aborts the deploy with the service stopped.

    These tasks reach two third-party apt repos, so a transient outage there must
    not take down code sync, workers, nginx and the health check with it.
    """
    text = ANSIBLE_TASKS.read_text(encoding="utf-8")
    guarded = text.index("Restart-guarded env-update")
    first_cli = text.index("Ensure the apt keyring directory exists")
    assert first_cli < guarded, (
        "the agent-CLI tasks sit inside the restart-guarded window; a CLI-repo "
        "outage would abort the whole backend deploy after the service was stopped"
    )


@pytest.mark.parametrize("binary", AGENT_CLIS)
def test_the_image_installs_and_resolves_each_cli(binary: str) -> None:
    assert DOCKERFILE.is_file(), f"{DOCKERFILE} missing — this guard would pass vacuously"
    text = DOCKERFILE.read_text(encoding="utf-8")
    package = "claude-code" if binary == "claude" else binary
    assert re.search(rf"(?<![\w-]){re.escape(package)}(?![\w-])", text), (
        f"the image no longer installs '{package}' (#12681)"
    )
    assert re.search(rf"{re.escape(binary)}\s+--version", text), (
        f"the image installs '{package}' but never proves it resolves"
    )


def test_the_signing_keys_are_fetched_not_piped_to_a_shell() -> None:
    text = ANSIBLE_TASKS.read_text(encoding="utf-8")
    assert "/etc/apt/keyrings/claude-code.asc" in text
    assert "/etc/apt/keyrings/githubcli-archive-keyring.gpg" in text
    assert not re.search(r"curl[^\n|]*\|\s*(sudo\s+)?(ba)?sh", text), (
        "an agent CLI must not be installed by piping a download into a shell"
    )


def test_the_version_pin_is_optional_and_renders_both_ways() -> None:
    """An empty pin must yield a bare package name, not a trailing '='."""
    jinja2 = pytest.importorskip("jinja2")

    names = _install_task()["ansible.builtin.apt"]["name"]
    env = jinja2.Environment()  # nosec B701  # compiling a repo-owned expression, never user input
    template = env.from_string(names if isinstance(names, str) else str(names))
    assert template.render(backend_claude_cli_version="") == "['gh', 'claude-code']"
    assert template.render(backend_claude_cli_version="2.1.89") == "['gh', 'claude-code=2.1.89']"
