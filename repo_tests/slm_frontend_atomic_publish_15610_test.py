# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15610: publishing the SLM frontend is ONE step, never a sequence.

The promotion used to be two sequential renames:

    mv dist          -> dist.previous
    mv dist.staging  -> dist

Between them the served directory did not exist, so a request landing in that
window got neither the previous bundle nor the new one — nginx serves the SLM
UI with ``try_files`` and ``autoindex off``, so an absent target answers 403 for
every path under /slm/. Two *Ansible tasks* means the window is a module round
trip wide, not a syscall wide, and #15557 had just widened its reach from one
entry point to four by making them all share the file.

A directory rename pair cannot be made atomic. A symlink flip can, because
``rename(2)`` over a symlink has no observable intermediate state. So the
served path is now ``current``, a symlink, and publishing is::

    ln -s dist-<id> .current.next && mv -T .current.next current

``ln -sfn dist-<id> current`` is NOT the same thing: GNU ln unlinks the old
name and then creates the new one, which is the window with extra steps. The
Python half (``services/slm_frontend_build.py``) uses ``os.replace`` on the
same staging symlink for the same reason.

What this module asserts, and why each part is here:

1. the shared task file writes the served pointer exactly once, with the
   atomic idiom, and nothing in the Ansible tree renames the served path as a
   directory — ``test_the_two_rename_detector_discriminates`` re-runs the
   detector over the pre-#15610 task pair so that a clean sweep means
   something rather than meaning the detector matches nothing;
2. every nginx config in the tree serves ``current`` — a flip the web server
   never follows is not a fix, and the served-path change has to land with the
   publish change rather than after it;
3. both publishers bound their retention — one build directory per deploy,
   forever, is how this fix would become a disk-full incident.

Floors bind to the sweep's REACH, not to what it found: a sweep that collapses
to zero files passes vacuously, and a vacuous guard over a defect whose nature
is "correct here, absent there" is worse than none.

Lives in ``repo_tests/`` because CI's shard command passes an explicit path
list and ``autobot-slm-backend/ansible`` is not on it — a test placed beside
the playbooks is collected by a bare local pytest and by nothing that gates a
merge.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterator

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ANSIBLE_ROOT = _REPO_ROOT / "autobot-slm-backend" / "ansible"
_SHARED_BUILD = _ANSIBLE_ROOT / "roles" / "_shared" / "tasks" / "build_publish_slm_frontend.yml"
_PYTHON_PUBLISHER = _REPO_ROOT / "autobot-slm-backend" / "services" / "slm_frontend_build.py"

#: The served pointer, and the names the pre-#15610 layout renamed instead.
_SERVED_LINK = "current"
_ROLLBACK_LINK = "previous"
_RETIRED_NAMES = ("dist.staging", "dist.previous")

#: Both halves of the publish. The Ansible task file cannot be included by the
#: Python module (it runs in the SLM backend's venv, against SLM_DEPLOYED_ROOT)
#: so the layout is a contract between two files, and a guard that checked only
#: one would let them drift — which is the #15557 defect one level up.
_PUBLISHERS = {"ansible-shared-task-file": _SHARED_BUILD, "python-self-sync": _PYTHON_PUBLISHER}

#: The Ansible tree is ~150 YAML files. Well below this and the sweep collapsed
#: (a moved directory, a broken glob) rather than the tree being clean.
_MIN_ANSIBLE_FILES_SWEPT = 60

#: nginx configs and templates across the whole repo. Well below this and the
#: nginx sweep collapsed rather than the configs being clean.
_MIN_NGINX_FILES_SWEPT = 20

#: The SLM UI is served by two configs: the Ansible-managed site template and
#: the static one bootstrap writes before Ansible ever runs. Fewer than two
#: means the sweep stopped finding one of them, not that one stopped existing.
_MIN_SERVED_PATH_DIRECTIVES = 2

#: Templates rendered onto an SLM host — nginx sites, systemd units, helper
#: scripts. The served path is named outside nginx too: `slm-admin-ui.service`
#: probes the bundle's index.html, and a probe left on the pre-#15610 directory
#: fails permanently on a host provisioned after this change, because that
#: directory is never created there.
_TEMPLATE_ROOTS = (
    _ANSIBLE_ROOT / "roles" / "slm_manager" / "templates",
    _REPO_ROOT / "autobot-infrastructure" / "autobot-slm-frontend" / "templates",
)

#: Well below this and the template sweep collapsed rather than being clean.
_MIN_TEMPLATE_FILES_SWEPT = 8

#: How the retired directory is spelled where the path is built from the SSOT
#: variable, and where it is a literal. Both forms are the same mistake.
_RETIRED_PATH_FORMS = ("slm_frontend_dir }}/dist", "autobot-slm-frontend/dist")

#: The pre-#15610 publish, kept ONLY as the contrast-mutation input for the
#: detector — never as a value under test.
_HISTORICAL_TWO_RENAME_PUBLISH: list[dict[str, Any]] = [
    {
        "name": "SLM | Frontend: keep the current bundle as a fallback (#15557)",
        "ansible.builtin.command": {
            "cmd": "mv {{ slm_frontend_publish_dir }}/dist {{ slm_frontend_publish_dir }}/dist.previous",
            "removes": "{{ slm_frontend_publish_dir }}/dist",
        },
    },
    {
        "name": "SLM | Frontend: publish the staged build (#15557)",
        "ansible.builtin.command": {
            "cmd": "mv {{ slm_frontend_publish_dir }}/dist.staging {{ slm_frontend_publish_dir }}/dist",
            "creates": "{{ slm_frontend_publish_dir }}/dist",
        },
    },
]

#: An nginx `root`/`alias` and the whole path it names. The path may be a
#: Jinja expression with spaces inside it (`{{ slm_frontend_dir }}/current`),
#: so it runs to the semicolon rather than to the first whitespace.
_SERVED_PATH_DIRECTIVE = re.compile(r"^[ \t]*(root|alias)[ \t]+([^;\n]+);", re.MULTILINE)


def _walk(node: Any) -> Iterator[dict]:
    """Yield every mapping anywhere in a parsed playbook, at any nesting."""
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


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


def _renames_the_served_path(document: Any) -> list[str]:
    """Commands that move the SLM frontend's served path as a directory.

    A `mv` naming `dist`, `dist.staging` or `dist.previous` is the pre-#15610
    shape whatever else the task says; a `mv` onto `current` is only safe when
    its source is the staging symlink and `-T` makes it a rename of the link
    rather than a move *into* the directory it points at.
    """
    offenders: list[str] = []
    for mapping in _walk(document):
        for cmd in _command_strings(mapping):
            for line in cmd.splitlines():
                tokens = line.split()
                if "mv" not in tokens:
                    continue
                bare = [token.rsplit("/", 1)[-1].rstrip(";") for token in tokens]
                if any(name in bare for name in ("dist", *_RETIRED_NAMES)):
                    offenders.append(line.strip())
                elif _SERVED_LINK in bare and not ("-T" in tokens and f".{_SERVED_LINK}.next" in bare):
                    offenders.append(line.strip())
    return offenders


def _ansible_yaml_files() -> list[Path]:
    return sorted(path for path in _ANSIBLE_ROOT.rglob("*.y*ml") if path.is_file() and path.suffix in {".yml", ".yaml"})


def _nginx_files() -> list[Path]:
    found: list[Path] = []
    for pattern in ("*.conf", "*.conf.j2"):
        found += [
            path
            for path in _REPO_ROOT.rglob(pattern)
            if path.is_file() and "node_modules" not in path.parts and ".git" not in path.parts
        ]
    return sorted(set(found))


def _served_path_directives() -> dict[str, list[str]]:
    """Every nginx root/alias in the tree that names the SLM frontend tree."""
    directives: dict[str, list[str]] = {}
    for path in _NGINX_FILES:
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = [
            value.strip()
            for _, value in _SERVED_PATH_DIRECTIVE.findall(text)
            if "slm-frontend" in value or "slm_frontend" in value
        ]
        if hits:
            directives[str(path.relative_to(_REPO_ROOT))] = hits
    return directives


_SWEPT = _ansible_yaml_files()
_NGINX_FILES = _nginx_files()


def test_the_sweep_is_not_vacuous() -> None:
    """Floors under every count this module draws a conclusion from."""
    for name, path in _PUBLISHERS.items():
        assert path.is_file(), f"the {name} publisher is missing or moved: {path}"
    assert len(_SWEPT) >= _MIN_ANSIBLE_FILES_SWEPT, (
        f"swept only {len(_SWEPT)} Ansible YAML files (floor {_MIN_ANSIBLE_FILES_SWEPT}) — the "
        "sweep collapsed rather than the tree being clean."
    )
    assert len(_NGINX_FILES) >= _MIN_NGINX_FILES_SWEPT, (
        f"swept only {len(_NGINX_FILES)} nginx config/template files (floor "
        f"{_MIN_NGINX_FILES_SWEPT}) — the sweep collapsed rather than the configs being clean."
    )
    directives = _served_path_directives()
    assert len(directives) >= _MIN_SERVED_PATH_DIRECTIVES, (
        f"found the SLM served path in only {len(directives)} nginx file(s) "
        f"(floor {_MIN_SERVED_PATH_DIRECTIVES}): {sorted(directives)}. A served-path guard that "
        "cannot find the served path proves nothing."
    )


def test_the_shared_publish_writes_the_served_pointer_exactly_once() -> None:
    """One atomic step, not a sequence that passes through nothing.

    Two tasks each doing half of the swap is the defect: between them the
    served path does not exist. One task, one `rename(2)`, and the name goes
    straight from the old bundle to the new one.
    """
    document = yaml.safe_load(_SHARED_BUILD.read_text(encoding="utf-8"))
    publishing = [
        cmd
        for mapping in _walk(document)
        for cmd in _command_strings(mapping)
        if re.search(rf"\bmv\b.*\b{_SERVED_LINK}\b", cmd)
    ]
    assert len(publishing) == 1, (
        f"the shared publish writes the served pointer in {len(publishing)} command(s): "
        f"{publishing!r}. Splitting the swap across two steps is #15610 itself."
    )
    idiom = publishing[0]
    assert "ln -sfn " in idiom and f".{_SERVED_LINK}.next" in idiom, (
        f"the publish does not stage the new symlink under a temporary name: {idiom!r}"
    )
    assert re.search(rf"mv -T \.{_SERVED_LINK}\.next {_SERVED_LINK}", idiom), (
        f"the publish does not replace the served pointer with a single rename(2): {idiom!r}. "
        "`ln -sfn <target> current` unlinks the name before recreating it — that is the window."
    )


def test_no_ansible_file_renames_the_served_path() -> None:
    """The catcher for the two-rename shape coming back anywhere in the tree."""
    offenders: dict[str, list[str]] = {}
    for path in _SWEPT:
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:  # pragma: no cover - a malformed playbook is its own failure
            continue
        found = _renames_the_served_path(document)
        if found:
            offenders[str(path.relative_to(_REPO_ROOT))] = found
    assert not offenders, (
        f"these Ansible files move the SLM frontend's served path as a directory: {offenders}. "
        "A directory rename pair cannot be atomic; between the two the path does not exist "
        "(#15610)."
    )


def test_the_two_rename_detector_discriminates() -> None:
    """Contrast mutation: the pre-#15610 publish must still be flagged.

    Without this, `test_no_ansible_file_renames_the_served_path` passing would
    be indistinguishable from a detector that matches nothing at all.
    """
    flagged = _renames_the_served_path(_HISTORICAL_TWO_RENAME_PUBLISH)
    assert len(flagged) == 2, (
        f"the detector no longer recognises the pre-#15610 two-rename publish, so a green sweep "
        f"proves nothing (got {flagged!r})."
    )


def test_the_shared_publish_never_stages_into_a_retired_name() -> None:
    """`dist.staging` and `dist.previous` were the two-rename layout's names.

    They are gone, and their absence is asserted rather than assumed: a task
    file that still writes them is one that still renames directories.
    """
    text = _SHARED_BUILD.read_text(encoding="utf-8")
    commands = " ".join(
        cmd for mapping in _walk(yaml.safe_load(text)) for cmd in _command_strings(mapping)
    )
    still_used = [name for name in _RETIRED_NAMES if name in commands]
    assert not still_used, (
        f"the shared publish still writes the pre-#15610 names {still_used}. The rollback slot is "
        f"the `{_ROLLBACK_LINK}` symlink now, and the staging slot is the build's own directory."
    )


def test_every_nginx_config_serves_the_flipped_pointer() -> None:
    """A symlink flip the web server never follows is not a fix.

    nginx resolves root/alias per request, so a flip is served immediately —
    but only to a config that names the pointer. The served-path change has to
    land with the publish change, not after it.
    """
    wrong = {
        path: [value for value in values if not value.rstrip("/").endswith(f"/{_SERVED_LINK}")]
        for path, values in _served_path_directives().items()
    }
    wrong = {path: values for path, values in wrong.items() if values}
    assert not wrong, (
        f"these nginx configs still serve a directory the publish renames: {wrong}. The publish "
        f"points `{_SERVED_LINK}` at each build; a config naming anything else serves a stale "
        "bundle after a green deploy, or 403s once that directory is pruned (#15610)."
    )


def _template_files() -> list[Path]:
    return sorted(
        path for root in _TEMPLATE_ROOTS if root.is_dir() for path in root.rglob("*") if path.is_file()
    )


def test_no_slm_host_template_still_names_the_retired_directory() -> None:
    """The served path is named outside nginx too.

    `slm-admin-ui.service` tests `<bundle>/index.html` before curling the UI. A
    host provisioned after #15610 never has the pre-#15610 directory, so a probe
    left pointing at it fails forever while nginx serves the bundle correctly —
    a monitor that reports an outage that is not happening, which is how the
    real one stops being believed.
    """
    swept = _template_files()
    assert len(swept) >= _MIN_TEMPLATE_FILES_SWEPT, (
        f"swept only {len(swept)} SLM host template files (floor {_MIN_TEMPLATE_FILES_SWEPT}) — "
        "the sweep collapsed rather than the templates being clean."
    )
    offenders = {}
    for path in swept:
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = [form for form in _RETIRED_PATH_FORMS if f"{form}/" in text]
        if hits:
            offenders[str(path.relative_to(_REPO_ROOT))] = hits
    assert not offenders, (
        f"these templates still name the pre-#15610 build directory: {offenders}. It is the "
        f"directory a publish replaced; `{_SERVED_LINK}` is the one that exists on every node."
    )


@pytest.mark.parametrize("publisher", sorted(_PUBLISHERS))
def test_both_publishers_bound_their_retention(publisher: str) -> None:
    """One build directory per deploy, forever, is a disk-full incident.

    Each half carries the bound in its own runtime's SSOT — Ansible inventory
    for the task file, an env-backed module constant for the Python module —
    because neither can read the other's. Both must carry one.
    """
    text = _PUBLISHERS[publisher].read_text(encoding="utf-8")
    assert "slm_frontend_release_keep" in text or "_RELEASE_KEEP" in text, (
        f"the {publisher} publisher names no retention bound, so build directories accumulate "
        "one per deploy with nothing removing them (#15610)."
    )
    assert re.search(rf"\b{_ROLLBACK_LINK}\b", text), (
        f"the {publisher} publisher never writes `{_ROLLBACK_LINK}`, so the bundle it replaced is "
        "unreachable — `dist.previous` was the rollback target and something has to replace it."
    )
