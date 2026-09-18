# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15603: every user-frontend entry point publishes through the SAME staged swap.

The sibling to ``slm_frontend_staged_publish_15557_test.py`` (read that
module's docstring for the full incident history — #15430/#15462, vite
emptying its outDir before writing, nginx's ``try_files``/``autoindex off``
turning a failed build into a 403 for the whole tree). #15557 fixed this for
the SLM frontend across four entry points by having all of them delegate to
one shared task file, ``roles/_shared/tasks/build_publish_slm_frontend.yml``.
The user frontend (``autobot-frontend``) carried the identical unstaged shape
in five more places, tracked separately because it is a different component
behind a different nginx site.

#15603 extends the SAME shared file (two new optional variables,
``slm_frontend_publish_build_script`` and ``slm_frontend_publish_build_env``)
rather than forking it, so this guard cannot just check "does the file
include the shared task file" the way the SLM guard does — several of these
entry points (``update-node.yml``, ``update-all-nodes.yml``) ALSO delegate to
the shared file for the SLM frontend, in the same file, so that check alone
would pass on the pre-#15603 code purely from the pre-existing SLM call.

The real signal is the include's own ``vars:``: every user-frontend call site
passes ``slm_frontend_publish_build_script: "build"`` (the user frontend has
no dedicated production script, unlike SLM's ``build:slm``); no SLM call site
does. That is what this guard actually checks per entry point, alongside the
inline-build sweep that catches a sixth site arriving with a fresh copy.

Lives in ``repo_tests/`` for the same reason its sibling does: CI's shard
command passes an explicit path list that does not reach
``autobot-slm-backend/ansible``, and ``install-slm.sh`` lives outside it too.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import pytest
import yaml
from repo_tests._paths import repo_root

_REPO_ROOT = repo_root()
_ANSIBLE_ROOT = _REPO_ROOT / "autobot-slm-backend" / "ansible"

_SHARED_BUILD = _ANSIBLE_ROOT / "roles" / "_shared" / "tasks" / "build_publish_slm_frontend.yml"

#: Every Ansible entry point that builds the user frontend, per #15603's own
#: sweep. deploy-native-services.yml targets a differently-named legacy tree
#: (`autobot-vue`, not `autobot-frontend`) but is the same defect shape.
_ENTRY_POINTS: dict[str, Path] = {
    "frontend-role": _ANSIBLE_ROOT / "roles" / "frontend" / "tasks" / "main.yml",
    "slm_manager-role-colocated": _ANSIBLE_ROOT / "roles" / "slm_manager" / "tasks" / "main.yml",
    "update-node": _ANSIBLE_ROOT / "playbooks" / "update-node.yml",
    "update-all-nodes": _ANSIBLE_ROOT / "playbooks" / "update-all-nodes.yml",
    "enable-tls": _ANSIBLE_ROOT / "enable-tls.yml",
    "deploy-native-services": _ANSIBLE_ROOT / "playbooks" / "deploy-native-services.yml",
}

#: The vacuity floor. Six entry points are known; a shrunk set means a caller
#: was dropped or renamed without this guard being told, not that the defect
#: is gone.
_EXPECTED_ENTRY_POINTS = 6

#: Shared with the SLM guard's own floor — same tree, same reasoning.
_MIN_ANSIBLE_FILES_SWEPT = 60

#: The pre-#15603 shape of roles/frontend/tasks/main.yml's build task, kept
#: ONLY as the contrast-mutation input for the detector — never as a value
#: under test.
_HISTORICAL_INLINE_BUILD = {
    "name": "Frontend | Build production frontend",
    "command": "npx vite build",
    "args": {"chdir": "{{ frontend_install_dir }}/autobot-frontend"},
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


def _include_tasks_calls(document: Any) -> Iterator[tuple[str, dict]]:
    """Yield (target, vars) for every include_tasks/import_tasks in *document*."""
    for mapping in _walk(document):
        for key in ("ansible.builtin.include_tasks", "include_tasks", "ansible.builtin.import_tasks", "import_tasks"):
            target = mapping.get(key)
            call_vars = mapping.get("vars") if isinstance(mapping.get("vars"), dict) else {}
            if isinstance(target, str):
                yield target, call_vars
            elif isinstance(target, dict) and isinstance(target.get("file"), str):
                yield target["file"], call_vars


def _delegates_to_shared_build_for_user_frontend(entry_point: Path) -> bool:
    """True when *entry_point* stages the USER frontend through the shared file.

    Resolves the include path the way Ansible does (relative to the including
    file's own directory), and requires the specific
    ``slm_frontend_publish_build_script: "build"`` marker on that call — the
    one thing distinguishing a user-frontend call site from a pre-existing SLM
    one delegating to the very same shared file in the very same document.
    """
    for target, call_vars in _include_tasks_calls(_load(entry_point)):
        if (entry_point.parent / target).resolve() != _SHARED_BUILD.resolve():
            continue
        if call_vars.get("slm_frontend_publish_build_script") == "build":
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


def _builds_user_frontend_inline(document: Any) -> list[str]:
    """Command strings in *document* that build the user frontend themselves.

    A plain ``vite build``/``npm run build`` counts when the task's chdir (or,
    for a shell block, the command text itself) names the user frontend's own
    tree — ``autobot-frontend`` or the legacy ``autobot-vue``. Excludes
    ``build:slm``, which names the SLM frontend, never this one.
    """
    found: list[str] = []
    for mapping in _walk(document):
        chdir = ""
        for key in ("ansible.builtin.command", "command", "ansible.builtin.shell", "shell"):
            args = mapping.get(key)
            if isinstance(args, dict) and isinstance(args.get("chdir"), str):
                chdir = args["chdir"]
        # Free-form module syntax (`command: npx vite build` as a bare string,
        # not `ansible.builtin.command: {cmd: ..., chdir: ...}`) carries its
        # module arguments in a SIBLING `args:` key on the same task, not
        # nested inside the module key — the pre-#15603 shape of
        # roles/frontend/tasks/main.yml's own build task used exactly this
        # form, which is why the contrast mutation below pins it explicitly.
        top_level_args = mapping.get("args")
        if isinstance(top_level_args, dict) and isinstance(top_level_args.get("chdir"), str):
            chdir = top_level_args["chdir"]
        for cmd in _command_strings(mapping):
            if "build:slm" in cmd:
                continue
            names_generic_build = "vite build" in cmd or "npm run build" in cmd
            names_frontend_tree = "autobot-frontend" in chdir or "autobot-frontend" in cmd or "autobot-vue" in chdir or "autobot-vue" in cmd
            if names_generic_build and names_frontend_tree:
                found.append(cmd.strip())
    return found


def _ansible_yaml_files() -> list[Path]:
    return sorted(path for path in _ANSIBLE_ROOT.rglob("*.y*ml") if path.is_file() and path.suffix in {".yml", ".yaml"})


_SWEPT = _ansible_yaml_files()


def test_the_sweep_is_not_vacuous() -> None:
    """Floors under every count this module draws a conclusion from."""
    assert len(_ENTRY_POINTS) == _EXPECTED_ENTRY_POINTS, (
        f"expected {_EXPECTED_ENTRY_POINTS} user-frontend entry points, the set names "
        f"{len(_ENTRY_POINTS)}. #15603 is a divergence defect: shrinking the set is how a "
        "caller stops being checked."
    )
    missing = [name for name, path in _ENTRY_POINTS.items() if not path.is_file()]
    assert not missing, f"entry points moved or were renamed: {missing}"
    assert _SHARED_BUILD.is_file(), f"{_SHARED_BUILD} is missing — nothing to delegate to"
    assert len(_SWEPT) >= _MIN_ANSIBLE_FILES_SWEPT, (
        f"swept only {len(_SWEPT)} Ansible YAML files (floor {_MIN_ANSIBLE_FILES_SWEPT}) — the "
        "sweep collapsed rather than the tree being clean."
    )


@pytest.mark.parametrize("name", sorted(_ENTRY_POINTS))
def test_every_entry_point_delegates_to_the_shared_staged_publish(name: str) -> None:
    entry_point = _ENTRY_POINTS[name]
    assert _delegates_to_shared_build_for_user_frontend(entry_point), (
        f"{entry_point.relative_to(_REPO_ROOT)} does not stage the user frontend through "
        f"{_SHARED_BUILD.relative_to(_REPO_ROOT)} (an include_tasks call with "
        "slm_frontend_publish_build_script: \"build\"). Building it any other way publishes a "
        "failed build into the directory nginx is serving (#15430, #15462, #15603)."
    )


def test_no_ansible_file_builds_the_user_frontend_inline() -> None:
    """The catcher for a SIXTH entry point arriving with a fresh copy."""
    offenders: dict[str, list[str]] = {}
    for path in _SWEPT:
        if path.resolve() == _SHARED_BUILD.resolve():
            continue
        try:
            document = _load(path)
        except yaml.YAMLError:  # pragma: no cover - a malformed playbook is its own failure
            continue
        commands = _builds_user_frontend_inline(document)
        if commands:
            offenders[str(path.relative_to(_REPO_ROOT))] = commands
    assert not offenders, (
        "these Ansible files build the user frontend themselves instead of delegating to "
        f"{_SHARED_BUILD.relative_to(_REPO_ROOT)}: {offenders}. Each inline copy is a build that "
        "can publish its own failure into the served directory (#15603)."
    )


def test_the_inline_build_detector_discriminates() -> None:
    """Contrast mutation: the pre-#15603 task shape must still be flagged.

    Without this, a clean `test_no_ansible_file_builds_the_user_frontend_inline`
    would be indistinguishable from a detector that matches nothing at all.
    """
    flagged = _builds_user_frontend_inline([_HISTORICAL_INLINE_BUILD])
    assert flagged == ["npx vite build"], (
        "the detector no longer recognises the pre-#15603 inline build shape, so a green sweep "
        f"proves nothing (got {flagged!r})."
    )


def test_install_slm_sh_no_longer_discards_a_build_failure() -> None:
    """AC2: a failed SLM Admin UI build must fail the install, not `|| true` past it."""
    script = _REPO_ROOT / "autobot-infrastructure" / "shared" / "scripts" / "install-slm.sh"
    assert script.is_file(), f"{script} is missing"
    text = script.read_text(encoding="utf-8")
    assert "set -e" in text, "the script no longer traps a failing command — the fix relies on this"
    assert "npm run build --silent 2>/dev/null || true" not in text, (
        "install-slm.sh still swallows a build failure with `|| true` — the installer would "
        "report success over an empty dist/ (#15603)."
    )


def test_manifest_no_longer_declares_the_dead_exec_start_build_step() -> None:
    """AC3: manifest.yml's build oneshot named a field nothing reads."""
    manifest = _REPO_ROOT / "autobot-infrastructure" / "autobot-slm-frontend" / "manifest.yml"
    assert manifest.is_file(), f"{manifest} is missing"
    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    services = data.get("services") or []
    assert not any("exec_start" in svc for svc in services), (
        "manifest.yml still declares a services[].exec_start build step — confirmed to have zero "
        "consumers anywhere in the codebase (#15603); either wire a real reader or keep it out."
    )
