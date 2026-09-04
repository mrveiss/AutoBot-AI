# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15557: every SLM-frontend entry point publishes through the SAME staged swap.

#15430 made ``playbooks/update-all-nodes.yml`` build into ``dist.staging`` and
promote it only once ``index.html`` was proven present. Three other entry points
kept the original shape -- ``npm run build`` straight into the served ``dist/``
with nothing failing the play -- and #15462 is what that costs: vite empties the
outDir before writing, nginx serves ``dist/`` with ``try_files`` and
``autoindex off``, so a failed build answered **403 for the whole /slm/ tree**
while ten services reported ``active (running)``. The repair UI is served by the
frontend that broke, so the sanctioned recovery path disappeared in exactly the
failure it exists for.

A fix applied to one of four copies is not applied to the other three. So the
logic now lives once, in
``roles/_shared/tasks/build_publish_slm_frontend.yml``, and this module asserts
two things that together make a silent divergence impossible:

1. each known entry point *delegates* to that file (and to the shared
   ``.deployed_commit`` writer beside it), resolving the include path for real
   rather than matching a string; and
2. **no** Ansible file in the tree still builds the SLM frontend inline -- which
   is what catches a fifth entry point being added with a fresh copy.

Every count has a floor. A sweep that finds nothing passes vacuously, and a
vacuous guard over a defect whose whole nature is "present in some places, absent
in others" is worse than none: ``test_the_sweep_is_not_vacuous`` fails when the
entry-point set shrinks or the file sweep collapses, and
``test_the_inline_build_detector_discriminates`` re-runs the detector over the
pre-#15557 task shape to prove a clean result means something.

Lives in ``repo_tests/`` because CI's shard command passes an explicit path list
and ``autobot-slm-backend/ansible`` is not on it -- a test placed beside the
playbooks is collected by a bare local pytest and by nothing that gates a merge.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ANSIBLE_ROOT = _REPO_ROOT / "autobot-slm-backend" / "ansible"

_SHARED_BUILD = _ANSIBLE_ROOT / "roles" / "_shared" / "tasks" / "build_publish_slm_frontend.yml"
_SHARED_MARKER = _ANSIBLE_ROOT / "roles" / "_shared" / "tasks" / "record_slm_deployed_commit.yml"

#: Every Ansible entry point that builds the SLM frontend, as named by #15557.
#: update-all-nodes.yml is the one that already had the staged publish; the other
#: three are the copies that never received it.
_ENTRY_POINTS: dict[str, Path] = {
    "update-all-nodes": _ANSIBLE_ROOT / "playbooks" / "update-all-nodes.yml",
    "slm_manager-role": _ANSIBLE_ROOT / "roles" / "slm_manager" / "tasks" / "main.yml",
    "update-node": _ANSIBLE_ROOT / "playbooks" / "update-node.yml",
    "provision-fleet-roles": _ANSIBLE_ROOT / "playbooks" / "provision-fleet-roles.yml",
}

#: The vacuity floor. Four entry points are known; a set that has shrunk means a
#: caller was dropped or renamed without this guard being told, not that the
#: defect is gone.
_EXPECTED_ENTRY_POINTS = 4

#: The Ansible tree is ~150 YAML files. Well below this and the sweep collapsed
#: (a moved directory, a broken glob) rather than the tree being clean.
_MIN_ANSIBLE_FILES_SWEPT = 60

#: The pre-#15557 shape of the task in roles/slm_manager/tasks/main.yml, kept
#: ONLY as the contrast-mutation input for the detector -- never as a value
#: under test.
_HISTORICAL_INLINE_BUILD = {
    "name": "SLM | Build frontend for production (#10435)",
    "ansible.builtin.command": {
        "cmd": "npm run build:slm",
        "chdir": "{{ slm_frontend_dir }}",
    },
}


def _load(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _walk(node: Any) -> Iterator[dict]:
    """Yield every mapping anywhere in a parsed playbook, at any nesting."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def _includes(document: Any) -> Iterator[str]:
    """Yield the target of every include_tasks/import_tasks in *document*."""
    for mapping in _walk(document):
        for key in ("ansible.builtin.include_tasks", "include_tasks", "ansible.builtin.import_tasks", "import_tasks"):
            target = mapping.get(key)
            if isinstance(target, str):
                yield target
            elif isinstance(target, dict) and isinstance(target.get("file"), str):
                yield target["file"]


def _delegates_to(entry_point: Path, shared: Path) -> bool:
    """True when *entry_point* includes *shared*, resolved as Ansible resolves it.

    Ansible resolves a relative include against the directory of the file doing
    the including, so the check is a real path resolution -- a renamed shared
    file breaks it, which a substring match on the basename would not.
    """
    for target in _includes(_load(entry_point)):
        if (entry_point.parent / target).resolve() == shared.resolve():
            return True
    return False


def _command_strings(mapping: dict) -> Iterator[str]:
    """Yield the command text of *mapping*, when it is a command/shell task."""
    for key in ("ansible.builtin.command", "command", "ansible.builtin.shell", "shell"):
        args = mapping.get(key)
        if isinstance(args, str):
            yield args
        elif isinstance(args, dict):
            for arg_key in ("cmd", "_raw_params"):
                value = args.get(arg_key)
                if isinstance(value, str):
                    yield value


def _builds_slm_frontend_inline(document: Any) -> list[str]:
    """Command strings in *document* that build the SLM frontend themselves.

    ``build:slm`` is the SLM frontend's own build script (it exports
    VITE_API_URL=/slm, #10435), so naming it is naming this component. A plain
    ``vite build`` counts too when the task's chdir points at the SLM frontend
    -- that is the form playbooks/provision-fleet-roles.yml used, and reading it
    as "not an SLM build" is how it stayed unfixed.
    """
    found: list[str] = []
    for mapping in _walk(document):
        chdir = ""
        for key in ("ansible.builtin.command", "command", "ansible.builtin.shell", "shell"):
            args = mapping.get(key)
            if isinstance(args, dict) and isinstance(args.get("chdir"), str):
                chdir = args["chdir"]
        for cmd in _command_strings(mapping):
            names_slm_script = "build:slm" in cmd
            names_generic_build = "vite build" in cmd or "npm run build" in cmd
            chdir_is_slm = "slm-frontend" in chdir or "slm_frontend" in chdir
            if names_slm_script or (names_generic_build and chdir_is_slm):
                found.append(cmd.strip())
    return found


def _ansible_yaml_files() -> list[Path]:
    return sorted(path for path in _ANSIBLE_ROOT.rglob("*.y*ml") if path.is_file() and path.suffix in {".yml", ".yaml"})


_SWEPT = _ansible_yaml_files()


def test_the_sweep_is_not_vacuous() -> None:
    """Floors under every count this module draws a conclusion from."""
    assert len(_ENTRY_POINTS) == _EXPECTED_ENTRY_POINTS, (
        f"expected {_EXPECTED_ENTRY_POINTS} SLM-frontend entry points, the set names "
        f"{len(_ENTRY_POINTS)}. #15557 is a divergence defect: shrinking the set is how a "
        "caller stops being checked."
    )
    missing = [name for name, path in _ENTRY_POINTS.items() if not path.is_file()]
    assert not missing, f"entry points moved or were renamed: {missing}"
    assert _SHARED_BUILD.is_file(), f"{_SHARED_BUILD} is missing — nothing to delegate to"
    assert _SHARED_MARKER.is_file(), f"{_SHARED_MARKER} is missing — nothing to delegate to"
    assert len(_SWEPT) >= _MIN_ANSIBLE_FILES_SWEPT, (
        f"swept only {len(_SWEPT)} Ansible YAML files (floor {_MIN_ANSIBLE_FILES_SWEPT}) — the "
        "sweep collapsed rather than the tree being clean."
    )


@pytest.mark.parametrize("name", sorted(_ENTRY_POINTS))
def test_every_entry_point_delegates_to_the_shared_staged_publish(name: str) -> None:
    entry_point = _ENTRY_POINTS[name]
    assert _delegates_to(entry_point, _SHARED_BUILD), (
        f"{entry_point.relative_to(_REPO_ROOT)} does not include "
        f"{_SHARED_BUILD.relative_to(_REPO_ROOT)}. Building the SLM frontend any other way "
        "publishes a failed build into the directory nginx is serving (#15430, #15462, #15557)."
    )


@pytest.mark.parametrize("name", sorted(_ENTRY_POINTS))
def test_every_entry_point_records_the_deployed_commit(name: str) -> None:
    entry_point = _ENTRY_POINTS[name]
    assert _delegates_to(entry_point, _SHARED_MARKER), (
        f"{entry_point.relative_to(_REPO_ROOT)} does not include "
        f"{_SHARED_MARKER.relative_to(_REPO_ROOT)}. Without the .deployed_commit marker the "
        "deployment that produced a host's state cannot be identified afterwards — the absence "
        "that made the #15462 incident unattributable."
    )


def test_no_ansible_file_builds_the_slm_frontend_inline() -> None:
    """The catcher for a FIFTH entry point arriving with a fresh copy."""
    offenders: dict[str, list[str]] = {}
    for path in _SWEPT:
        if path.resolve() == _SHARED_BUILD.resolve():
            continue
        try:
            document = _load(path)
        except yaml.YAMLError:  # pragma: no cover - a malformed playbook is its own failure
            continue
        commands = _builds_slm_frontend_inline(document)
        if commands:
            offenders[str(path.relative_to(_REPO_ROOT))] = commands
    assert not offenders, (
        "these Ansible files build the SLM frontend themselves instead of delegating to "
        f"{_SHARED_BUILD.relative_to(_REPO_ROOT)}: {offenders}. Each inline copy is a build that "
        "can publish its own failure into the served dist/ (#15557)."
    )


def test_the_inline_build_detector_discriminates() -> None:
    """Contrast mutation: the pre-#15557 task shape must still be flagged.

    Without this, `test_no_ansible_file_builds_the_slm_frontend_inline` passing
    would be indistinguishable from a detector that matches nothing at all.
    """
    flagged = _builds_slm_frontend_inline([_HISTORICAL_INLINE_BUILD])
    assert flagged == ["npm run build:slm"], (
        "the detector no longer recognises the pre-#15557 inline build shape, so a green sweep "
        f"proves nothing (got {flagged!r})."
    )


def test_the_shared_publish_never_builds_into_the_served_directory() -> None:
    """The property the whole issue exists for, asserted on the shared file."""
    tasks = _load(_SHARED_BUILD)
    builds = [cmd for mapping in _walk(tasks) for cmd in _command_strings(mapping)]
    build_cmds = [cmd for cmd in builds if "build:slm" in cmd]
    assert len(build_cmds) == 1, f"expected exactly one build command, found {build_cmds!r}"
    assert "--outDir dist.staging" in build_cmds[0], (
        f"the shared build does not target dist.staging: {build_cmds[0]!r}. vite empties its "
        "outDir before writing, so building into the served dist/ is the defect itself."
    )

    text = _SHARED_BUILD.read_text(encoding="utf-8")
    assert "dist.staging/index.html" in text, (
        "the shared publish does not verify dist.staging/index.html — a build that reports "
        "success but produces no entry point makes every /slm/ path 403 (#15462)."
    )

    fails = [mapping for mapping in _walk(tasks) if "ansible.builtin.fail" in mapping]
    assert len(fails) >= 2, (
        f"the shared publish carries {len(fails)} fail gate(s); it needs both — one for a "
        "non-zero build rc and one for a bundle with no usable index.html (#15557)."
    )
    assert all("when" in mapping for mapping in fails), (
        "a fail gate with no `when:` aborts every run; each gate must state the condition it " "refuses on."
    )
