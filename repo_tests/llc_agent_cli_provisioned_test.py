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
passes whether or not anything ever installs the binary — which is exactly how
this stayed invisible.

Deliberately no `shutil.which("claude")` gate anywhere: a test skipped for a
missing binary is indistinguishable from a pass (#14550).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "docker/backend/Dockerfile"
ANSIBLE_TASKS = REPO_ROOT / "autobot-slm-backend/ansible/roles/backend/tasks/main.yml"

# The adapters that shell out to a CLI, and the binary each one resolves.
AGENT_CLIS = ["claude", "gh"]


@pytest.mark.parametrize("path", [DOCKERFILE, ANSIBLE_TASKS], ids=["image", "ansible"])
@pytest.mark.parametrize("binary", AGENT_CLIS)
def test_every_deployment_path_installs_the_agent_cli(path: Path, binary: str) -> None:
    assert path.is_file(), f"{path} missing — this guard would otherwise pass vacuously"
    text = path.read_text(encoding="utf-8")
    package = "claude-code" if binary == "claude" else binary
    assert package in text, (
        f"{path.name} does not install '{package}'. A deployment that runs LLC "
        f"agents without {binary} on PATH hires agents that cannot dispatch (#12681)."
    )


@pytest.mark.parametrize("path", [DOCKERFILE, ANSIBLE_TASKS], ids=["image", "ansible"])
def test_every_deployment_path_proves_the_cli_resolves(path: Path) -> None:
    """Installing without checking lets a broken PATH look like a clean provision."""
    text = path.read_text(encoding="utf-8")
    assert re.search(r"claude\s+--version", text), (
        f"{path.name} installs the CLI but never resolves it; an install regression "
        "would be silent (#12681)"
    )


def test_the_signing_keys_are_fetched_not_piped_to_a_shell() -> None:
    """Both repos are signed; neither CLI may be installed by curl|bash."""
    text = ANSIBLE_TASKS.read_text(encoding="utf-8")
    assert "/etc/apt/keyrings/claude-code.asc" in text
    assert "/etc/apt/keyrings/githubcli-archive-keyring.gpg" in text
    # A pipe-to-shell install of either CLI would defeat the signed-repo choice.
    assert not re.search(r"curl[^\n|]*\|\s*(sudo\s+)?(ba)?sh", text), (
        "an agent CLI must not be installed by piping a download into a shell"
    )


def test_the_version_pin_is_optional_and_renders_both_ways() -> None:
    """An empty pin must yield a bare package name, not a trailing '='."""
    jinja2 = pytest.importorskip("jinja2")

    text = ANSIBLE_TASKS.read_text(encoding="utf-8")
    match = re.search(r"name:\s*\"(\{\{ \['gh'\].*?\}\})\"", text, re.DOTALL)
    assert match, "could not locate the CLI package-name expression to check"

    env = jinja2.Environment()  # nosec B701  # compiling a repo-owned expression, never rendering user input
    template = env.from_string(match.group(1))
    assert template.render(backend_claude_cli_version="") == "['gh', 'claude-code']"
    assert template.render(backend_claude_cli_version="2.1.89") == "['gh', 'claude-code=2.1.89']"
