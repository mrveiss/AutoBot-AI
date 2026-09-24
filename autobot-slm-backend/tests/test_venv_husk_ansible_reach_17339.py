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

import ast
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


#: Spellings that would re-express the deletion rule in YAML instead of calling
#: it. `.dist-info` carries the DOT because real directories are
#: `pkg-1.0.dist-info` -- the first version of this list omitted it and let the
#: worked example from its own docstring straight through (#17339 review).
FORKED_RULE_MARKERS: tuple = (
    "-name '*.dist-info'",
    '-name "*.dist-info"',
    "rm -rf",
    "shell:",
    "METADATA",
    "RECORD",
)


def _forked_rule_hits(rendered: str) -> list:
    """Every re-expression marker present in *rendered*."""
    return [marker for marker in FORKED_RULE_MARKERS if marker in rendered]


def _task_content(path: Path) -> str:
    """The task file's CONTENT with comments dropped.

    Scanned after a YAML round-trip on purpose: this file's own header explains
    the rule it must not fork, so it names `find -name '*.dist-info'`,
    `METADATA` and `RECORD` in prose. A raw-text scan would flag the
    documentation and force the explanation out -- the #16750 shape, where a
    scan that reads comments makes the comment the defect.
    """
    return yaml.safe_dump(yaml.safe_load(path.read_text(encoding="utf-8")), default_flow_style=False)


def test_the_detector_catches_its_own_worked_example():
    """Positive control: a guard never shown to fire is not evidence.

    The task file is clean, so the check below reports a true negative either
    way -- which is exactly how a matcher that cannot match looks correct. This
    feeds it the reimplementation the guard exists to stop.
    """
    worked_example = "ansible.builtin.command: find {{ dir }} -name '*.dist-info' -delete"

    assert _forked_rule_hits(worked_example) == ["-name '*.dist-info'"]
    assert _forked_rule_hits("ansible.builtin.shell: rm -rf {{ dir }}") == ["rm -rf", "shell:"]


def test_the_shared_task_does_not_re_express_the_classification():
    """A `find -name '*.dist-info'` STEP here would fork the rule that deletes.

    Comments are exempt by construction (see `_task_content`): this file has to
    be able to explain what it forbids.
    """
    assert _forked_rule_hits(_task_content(TASK_FILE)) == []


#: Which ansible role provisions each marker-capable component's venv. The KEYS
#: are checked against the set DERIVED from source below, so a new
#: marker-capable component fails this file until someone maps it.
COMPONENT_ROLES: dict = {
    "autobot-backend": ("roles/backend/tasks/main.yml", "backend_code_dir"),
    "autobot-slm-backend": ("roles/slm_manager/tasks/main.yml", "slm_backend_dir"),
    "autobot-ai-stack": ("roles/ai-stack/tasks/main.yml", "ai_install_dir"),
}


def _assigned_value(module: Path, name: str):
    """The value node of a module-level assignment, read with ast rather than import."""
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    for node in ast.walk(tree):
        targets = getattr(node, "targets", []) or ([node.target] if getattr(node, "target", None) else [])
        if any(isinstance(t, ast.Name) and t.id == name for t in targets):
            return node.value
    raise AssertionError(f"{name} not found in {module} -- the derivation is broken, not the claim")


def _dict_keys_from_source(module: Path, name: str) -> set:
    value = _assigned_value(module, name)
    assert isinstance(value, ast.Dict), f"{name} is no longer a dict literal"
    return {key.value for key in value.keys if isinstance(key, ast.Constant)}


def _explicit_list_components() -> set:
    value = _assigned_value(SLM_ROOT / "api" / "venv_reconcile.py", "EXPLICIT_LIST_COMPONENTS")
    return {
        elt.value
        for node in ast.walk(value)
        if isinstance(node, (ast.Set, ast.List, ast.Tuple))
        for elt in node.elts
        if isinstance(elt, ast.Constant)
    }


def marker_capable_components() -> set:
    """Components whose venv `reconcile_component` can stamp with a marker.

    DERIVED from the source rather than restated: both dicts that reach
    `reconcile_component`, minus the components that take the explicit-list
    branch and never touch a requirements file. The first version of this PR
    hand-wrote the set, missed `autobot-ai-stack`, and the test could not
    notice -- because the claim was its own parametrisation.
    """
    code_sync = SLM_ROOT / "api" / "code_sync.py"
    return (
        _dict_keys_from_source(code_sync, "_COMPONENT_PIP_PATHS")
        | _dict_keys_from_source(code_sync, "_WORKER_COMPONENT_PIP")
    ) - _explicit_list_components()


def test_the_role_map_covers_every_marker_capable_component():
    """The falsifiable half: a new component in either dict fails here first."""
    assert set(COMPONENT_ROLES) == marker_capable_components()


def test_the_derivation_finds_the_component_the_first_version_missed():
    """Positive control on the derivation itself (#17339 review)."""
    capable = marker_capable_components()

    assert "autobot-ai-stack" in capable
    assert "autobot-npu-worker" not in capable


@pytest.mark.parametrize(("component", "mapping"), sorted(COMPONENT_ROLES.items()))
def test_every_marker_capable_role_includes_the_repair(component, mapping):
    role_tasks, venv_var = mapping
    rendered = (ANSIBLE_ROOT / role_tasks).read_text(encoding="utf-8")

    assert "_shared/tasks/clear_venv_husks.yml" in rendered, f"{component}'s role must include the repair"
    assert f'husk_venv_dir: "{{{{ {venv_var} }}}}/venv"' in rendered


#: Every shape a pip invocation takes in these role files. This guard first
#: looked for `ansible.builtin.pip:` alone, so `slm_manager`'s editable install
#: -- spelled `ansible.builtin.command:` with `.../venv/bin/pip install -e ...`
#: -- was invisible to it. The guard passed while the repair ran AFTER the first
#: real pip step, in the one venv this role's own comment calls the critical one
#: (it runs the builtin updater, so a husk there blocks its own repair). The
#: assertion was true of what it measured and false of what its name claims.
_PIP_INVOCATION_PATTERNS = (
    "ansible.builtin.pip:",
    "/bin/pip ",
    "pip install",
    "-m pip ",
)

#: ...and why the search runs on `_task_content`, not on the raw file. Widening
#: the patterns made the matcher hit PROSE: `roles/backend/tasks/main.yml:348`
#: describes its own deploy window as "apt/pip install, code sync, alembic
#: migrations", 24k characters before the first real pip task, which failed that
#: role for a sentence. Both offsets are therefore taken in the same
#: comment-stripped round-trip -- the #16750 shape again, where a scan that
#: reads comments makes the comment the defect.


def _first_pip_invocation(rendered: str) -> tuple[int, str]:
    """Offset of the earliest pip invocation of any shape, and the pattern that found it.

    Raises rather than returning a sentinel when nothing matches: a file with no
    pip invocation at all means the matcher has gone blind, which must not read
    the same as "pip comes later".
    """
    hits = [(rendered.index(p), p) for p in _PIP_INVOCATION_PATTERNS if p in rendered]
    if not hits:
        raise AssertionError("no pip invocation of any known shape -- the matcher is blind, not the file clean")
    return min(hits)


def test_the_matcher_sees_a_command_shaped_pip_invocation():
    """Positive control for the widening above.

    `slm_manager` really does invoke pip through `ansible.builtin.command`, and
    the original matcher scored that as "no pip here", so the ordering assertion
    below passed vacuously. Without this control, narrowing the matcher back to
    the module spelling would make the suite greener rather than redder -- which
    is how the gap survived the first review.
    """
    command_shaped = (
        '- name: "SLM | Install autobot_shared in venv (editable)"\n'
        "  ansible.builtin.command:\n"
        '    cmd: "{{ slm_backend_dir }}/venv/bin/pip install -e {{ slm_base_dir }}/autobot_shared"\n'
    )
    assert "ansible.builtin.pip:" not in command_shaped, "fixture must not use the module spelling"

    _at, pattern = _first_pip_invocation(command_shaped)
    assert pattern != "ansible.builtin.pip:", "the widened matcher found it by the module spelling"


@pytest.mark.parametrize("role_tasks", sorted(mapping[0] for mapping in COMPONENT_ROLES.values()))
def test_the_repair_precedes_the_first_pip_step(role_tasks):
    """After the pip step the deploy has already aborted, so order is the fix."""
    rendered = _task_content(ANSIBLE_ROOT / role_tasks)

    include_at = rendered.index("_shared/tasks/clear_venv_husks.yml")
    first_pip_at, pattern = _first_pip_invocation(rendered)

    assert include_at < first_pip_at, (
        f"the husk repair must run before the first pip task; {role_tasks} reaches "
        f"pip first via {pattern!r} at offset {first_pip_at}, repair at {include_at}"
    )
