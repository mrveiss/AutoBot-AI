# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
The husk repair is reachable from ansible provisioning (#17339).

#17332 wired `clear_provenance_husks` into `api/venv_reconcile._run_pip_install`
— the builtin updater's path. A host reached only by ansible never runs it, so
its husks survive and every pip step that must upgrade a husked package aborts
with `uninstall-no-record-file`.

What these pin, in the order the failure happens:

1. The module imports with **stdlib only**, because ansible stages this one
   file onto a node and runs it with the target venv's interpreter, where
   `autobot_shared` is not importable.
2. The CLI clears a husked venv and leaves everything else alone — the same
   `is_provenance_husk` rule, not a second copy of it.
3. The repair runs with the **venv's own interpreter**, which is the property
   nobody had established: `autobot-slm-backend/venv` runs the builtin updater,
   so a husk there can block its own repair unless the fix works from inside.
4. The ansible task exists, stages the module, and is included by both roles
   that own a venv able to carry a marker — before their pip steps, since after
   them the failure has already happened.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

SLM_ROOT = Path(__file__).resolve().parents[1]
ANSIBLE_ROOT = SLM_ROOT / "ansible"
MODULE_PATH = SLM_ROOT / "venv_provenance.py"
TASK_FILE = ANSIBLE_ROOT / "roles" / "_shared" / "tasks" / "clear_venv_husks.yml"

sys.path.insert(0, str(SLM_ROOT))

import venv_provenance as provenance  # noqa: E402  -- after the sys.path insert above


def _fake_venv(tmp_path: Path, *, python_tag: str = "python3.14") -> Path:
    """A venv-shaped tree: an interpreter dir and one versioned site-packages."""
    venv_dir = tmp_path / "venv"
    (venv_dir / "bin").mkdir(parents=True)
    (venv_dir / "lib" / python_tag / "site-packages").mkdir(parents=True)
    return venv_dir


def _plant_husk(site_packages: Path, name: str) -> Path:
    """A dist-info whose sole content is this tool's marker — the #17332 shape."""
    dist_info = site_packages / f"{name}.dist-info"
    dist_info.mkdir()
    (dist_info / provenance.PROVENANCE_MARKER_FILENAME).write_text("{}", encoding="utf-8")
    return dist_info


def _plant_real_install(site_packages: Path, name: str) -> Path:
    """A dist-info that describes an installed distribution. Never ours to remove."""
    dist_info = site_packages / f"{name}.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text("Name: real\n", encoding="utf-8")
    (dist_info / "RECORD").write_text("", encoding="utf-8")
    return dist_info


# --------------------------------------------------------------- stdlib only


def test_the_staged_module_imports_on_stdlib_alone():
    """Ansible stages this file alone; a node's venv has no `autobot_shared`.

    Run in a subprocess with an interpreter that cannot see this repo, so an
    `autobot_shared` import at module scope fails the test rather than being
    satisfied by the test runner's own path.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; sys.path=[{str(MODULE_PATH.parent)!r}]+sys.path[1:]; import venv_provenance",
        ],
        capture_output=True,
        text=True,
        cwd=str(MODULE_PATH.parent),
    )

    assert result.returncode == 0, result.stderr
    assert "autobot_shared" not in result.stderr


def test_the_marker_writer_still_has_its_timestamp():
    """The lazy import must not have removed the dependency, only deferred it."""
    source = MODULE_PATH.read_text(encoding="utf-8")

    assert "from autobot_shared.time_utils import utc_timestamp" in source
    assert "utc_timestamp()" in source


# ------------------------------------------------------------------ the CLI


def test_cli_clears_a_husked_venv(tmp_path, capsys):
    venv_dir = _fake_venv(tmp_path)
    site_packages = next(venv_dir.glob("lib/python*/site-packages"))
    husk = _plant_husk(site_packages, "psycopg2_binary-2.9.12")

    assert provenance.main([str(venv_dir)]) == 0

    assert not husk.exists()
    assert "cleared 1 husk" in capsys.readouterr().out


def test_cli_leaves_a_real_installation_alone(tmp_path, capsys):
    """The narrow-deletion property, at the entry point ansible actually calls."""
    venv_dir = _fake_venv(tmp_path)
    site_packages = next(venv_dir.glob("lib/python*/site-packages"))
    real = _plant_real_install(site_packages, "requests-2.32.0")
    husk = _plant_husk(site_packages, "psycopg2_binary-2.9.12")

    provenance.main([str(venv_dir)])

    assert real.is_dir() and (real / "METADATA").exists()
    assert not husk.exists()


def test_cli_leaves_another_tools_leftovers_alone(tmp_path):
    """A dist-info with content this module did not write is not ours to classify."""
    venv_dir = _fake_venv(tmp_path)
    site_packages = next(venv_dir.glob("lib/python*/site-packages"))
    foreign = site_packages / "something-1.0.dist-info"
    foreign.mkdir()
    (foreign / "INSTALLER").write_text("pip\n", encoding="utf-8")

    provenance.main([str(venv_dir)])

    assert foreign.is_dir()


def test_cli_is_success_on_an_absent_venv(tmp_path, capsys):
    """First provisioning has no venv yet; that is not a failure."""
    assert provenance.main([str(tmp_path / "nope")]) == 0
    assert "nothing to clear" in capsys.readouterr().out


def test_cli_is_success_on_a_healthy_venv(tmp_path, capsys):
    venv_dir = _fake_venv(tmp_path)

    assert provenance.main([str(venv_dir)]) == 0
    assert "no husks" in capsys.readouterr().out


def test_cli_clears_every_site_packages_in_the_venv(tmp_path):
    """The glob is by `python*`, so an interpreter bump does not hide a husk."""
    venv_dir = _fake_venv(tmp_path)
    second = venv_dir / "lib" / "python3.15" / "site-packages"
    second.mkdir(parents=True)
    first_husk = _plant_husk(next(venv_dir.glob("lib/python3.14/site-packages")), "a-1.0")
    second_husk = _plant_husk(second, "b-2.0")

    provenance.main([str(venv_dir)])

    assert not first_husk.exists() and not second_husk.exists()


# ------------------------------------------- the bootstrap property (#17339)


def test_a_husked_venv_can_repair_itself_with_its_own_interpreter(tmp_path):
    """The question nobody had established: can the broken venv run the repair?

    `autobot-slm-backend/venv` runs the builtin updater, the only other path to
    this repair, so a husk there could block its own fix. A husk is a dist-info
    directory rather than a broken interpreter, so it cannot — and this asserts
    that by running the module as a script against a husked tree, the way the
    ansible task does, rather than by arguing it.
    """
    venv_dir = _fake_venv(tmp_path)
    site_packages = next(venv_dir.glob("lib/python*/site-packages"))
    husk = _plant_husk(site_packages, "psycopg2_binary-2.9.12")

    result = subprocess.run(
        [sys.executable, str(MODULE_PATH), str(venv_dir)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert not husk.exists()
    assert "cleared 1 husk" in result.stdout


# ----------------------------------------------------- the ansible reachability


def _tasks(path: Path) -> list:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or []


def test_the_shared_task_stages_the_module_and_runs_it():
    tasks = _tasks(TASK_FILE)
    rendered = TASK_FILE.read_text(encoding="utf-8")

    assert any("copy" in str(task.get("ansible.builtin.copy", "")) or "ansible.builtin.copy" in task for task in tasks)
    assert "venv_provenance.py" in rendered
    assert "{{ husk_venv_dir }}/bin/python" in rendered, "must run with the TARGET venv's interpreter"


def test_the_shared_task_does_not_re_express_the_classification():
    """A `find -name '*.dist-info'` step here would fork the rule that deletes."""
    rendered = TASK_FILE.read_text(encoding="utf-8")

    for forked in ("dist-info", "METADATA", "RECORD"):
        assert f"-name '*{forked}" not in rendered
    assert "rm -rf" not in rendered
    assert "shell:" not in rendered, "a shell step here would fork the rule that decides a deletion"


@pytest.mark.parametrize(
    ("role_tasks", "venv_var"),
    [
        ("roles/backend/tasks/main.yml", "backend_code_dir"),
        ("roles/slm_manager/tasks/main.yml", "slm_backend_dir"),
    ],
)
def test_both_marker_capable_roles_include_the_repair(role_tasks, venv_var):
    """`_COMPONENT_PIP_PATHS` names exactly these two venvs; nothing else can husk."""
    rendered = (ANSIBLE_ROOT / role_tasks).read_text(encoding="utf-8")

    assert "_shared/tasks/clear_venv_husks.yml" in rendered
    assert f'husk_venv_dir: "{{{{ {venv_var} }}}}/venv"' in rendered


@pytest.mark.parametrize(
    "role_tasks",
    ["roles/backend/tasks/main.yml", "roles/slm_manager/tasks/main.yml"],
)
def test_the_repair_precedes_the_first_pip_step(role_tasks):
    """After the pip step the deploy has already aborted, so order is the fix."""
    rendered = (ANSIBLE_ROOT / role_tasks).read_text(encoding="utf-8")

    include_at = rendered.index("_shared/tasks/clear_venv_husks.yml")
    first_pip_at = rendered.index("ansible.builtin.pip:")

    assert include_at < first_pip_at, "the husk repair must run before the first pip task"
