# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18558: the CI config fixture and the node credential registration each have one home.

The rows of the issue kept separate on purpose are in docs/developer/ARCHITECTURE_EXCEPTIONS.md.
"""

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
GITHUB_DIR = REPO_ROOT / ".github"
ANSIBLE_DIR = REPO_ROOT / "autobot-slm-backend" / "ansible"
FIXTURE = GITHUB_DIR / "actions" / "setup-python-suite" / "ci-config.yaml"
SHARED_TASK = ANSIBLE_DIR / "_shared" / "tasks" / "register_node_credentials.yml"

_READS_FIXTURE = re.compile(r"""ci-config\.yaml"? config/config\.yaml""")
_WRITES_CONFIG = re.compile(r"cat\s*>+\s*\S*config\.ya?ml\s*<<")
_CREDENTIAL_ROUTE = re.compile(r"""/api/nodes/[^"'\n]*-credentials""")


def _ci_files() -> list[Path]:
    return [*(GITHUB_DIR / "workflows").glob("*.y*ml"), *(GITHUB_DIR / "actions").glob("*/action.y*ml")]


def test_no_ci_file_writes_its_own_config_fixture() -> None:
    copies = [p.relative_to(REPO_ROOT).as_posix() for p in _ci_files() if _WRITES_CONFIG.search(p.read_text("utf-8"))]
    assert not copies, f"copy {FIXTURE.name} instead of writing config.yaml inline: {copies}"


@pytest.mark.parametrize(
    ("source", "flagged"),
    [
        ("cat > config/config.yaml << 'EOF'", True),
        ("cat >> ./config.yml <<EOF", True),
        ("cp fixture/ci-config.yaml config/config.yaml", False),
        ("cat config/config.yaml", False),
    ],
)
def test_the_config_detector_has_both_sides(source: str, flagged: bool) -> None:
    assert bool(_WRITES_CONFIG.search(source)) is flagged


def test_the_fixture_is_read_by_every_job_that_used_to_write_it() -> None:
    readers = {p.name for p in _ci_files() if _READS_FIXTURE.search(p.read_text("utf-8"))}
    assert readers == {"action.yml", "ci.yml", "marker-tests.yml", "phase_validation.yml"}
    assert yaml.safe_load(FIXTURE.read_text("utf-8"))["llm"]["orchestrator_llm"] == "mock"


def test_only_the_shared_task_calls_the_credential_routes() -> None:
    callers = [
        p.relative_to(REPO_ROOT).as_posix()
        for p in ANSIBLE_DIR.rglob("*.yml")
        if p != SHARED_TASK and _CREDENTIAL_ROUTE.search(p.read_text("utf-8"))
    ]
    assert not callers, f"include {SHARED_TASK.name} instead of calling the route: {callers}"


@pytest.mark.parametrize(
    ("source", "flagged"),
    [
        ('url: "{{ slm_api_url }}/api/nodes/{{ slm_node_id }}/vnc-credentials"', True),
        ('url: "{{ slm_api_url }}/api/nodes/{{ slm_node_id }}/{{ node_credentials_path }}"', False),
    ],
)
def test_the_route_detector_has_both_sides(source: str, flagged: bool) -> None:
    assert bool(_CREDENTIAL_ROUTE.search(source)) is flagged


@pytest.mark.parametrize(("role", "route"), [("vnc", "vnc-credentials"), ("xrdp", "rdp-credentials")])
def test_each_role_registers_through_the_shared_task(role: str, route: str) -> None:
    tasks = yaml.safe_load((ANSIBLE_DIR / "roles" / role / "tasks" / "register-credentials.yml").read_text("utf-8"))
    assert len(tasks) == 1
    assert tasks[0]["ansible.builtin.include_tasks"].endswith(f"_shared/tasks/{SHARED_TASK.name}")
    assert tasks[0]["vars"]["node_credentials_path"] == route
