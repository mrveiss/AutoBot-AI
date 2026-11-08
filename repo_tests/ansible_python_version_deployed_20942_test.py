# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20942: .python-version must be deployed to the install root.

autobot_shared/python_floor.py reads ``<install root>/.python-version``; without a
task that copies it there every startup logs "unreadable" and uses the fallback.
Every play of the updater that deploys autobot_shared must stage it too.
"""

import copy as _copy
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_ANSIBLE = _ROOT / "autobot-slm-backend" / "ansible"
_ROLE = _ANSIBLE / "roles" / "_shared" / "tasks" / "stage_shared_manifests.yml"
_PLAYBOOK = _ANSIBLE / "playbooks" / "update-all-nodes.yml"
_DEST = "{{ autobot.base_dir }}/.python-version"


def _tasks(node) -> list[dict]:
    out: list[dict] = []
    if isinstance(node, list):
        for item in node:
            if isinstance(item, dict):
                out.append(item)
                for key in ("block", "rescue", "always", "tasks"):
                    out.extend(_tasks(item.get(key)))
    return out


def _load(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _is_staging(task: dict) -> bool:
    cp = task.get("ansible.builtin.copy") or task.get("copy")
    return (
        isinstance(cp, dict)
        and str(cp.get("src", "")).endswith("/.python-version")
        and str(cp.get("dest", "")) == _DEST
    )


def _deploys_shared(task: dict) -> bool:
    un = task.get("unarchive") or task.get("ansible.builtin.unarchive")
    return isinstance(un, dict) and str(un.get("src", "")).endswith("/shared.tar.gz")


def _tags(task: dict) -> set[str]:
    tags = task.get("tags") or []
    return {tags} if isinstance(tags, str) else set(tags)


def deploys_python_version(path: Path) -> bool:
    """True if a copy task in ``path`` lands ``.python-version`` at base_dir root."""
    return any(_is_staging(t) for t in _tasks(_load(path)))


def play_gaps(plays: list[dict]) -> list[str]:
    """Plays deploying autobot_shared without a staging task that always runs."""
    gaps: list[str] = []
    for play in plays:
        tasks = _tasks(play.get("tasks"))
        deploys = [t for t in tasks if _deploys_shared(t)]
        if not deploys:
            continue
        staging = [t for t in tasks if _is_staging(t)]
        name = str(play.get("name"))
        if not staging:
            gaps.append(f"{name}: no .python-version staging task")
            continue
        for dep in deploys:
            if not any("always" in _tags(s) or _tags(dep) <= _tags(s) for s in staging):
                gaps.append(f"{name}: staging tags do not cover {dep.get('name')}")
    return gaps


def test_source_file_exists():
    assert (_ROOT / ".python-version").is_file()


def test_role_stages_python_version():
    assert deploys_python_version(_ROLE), f"{_ROLE.name} does not deploy .python-version (#20942)"


def test_playbook_has_shared_deploying_plays():
    shared_plays = [p for p in _load(_PLAYBOOK) if any(_deploys_shared(t) for t in _tasks(p.get("tasks")))]
    assert len(shared_plays) >= 2, "expected the SLM and infrastructure plays to deploy autobot_shared"


def test_every_play_deploying_autobot_shared_stages_python_version():
    assert play_gaps(_load(_PLAYBOOK)) == []


def test_control_removing_staging_from_one_play_fails():
    plays = _load(_PLAYBOOK)
    target = next(p for p in plays if any(_deploys_shared(t) for t in _tasks(p.get("tasks"))))
    mutated = _copy.deepcopy(plays)
    victim = mutated[plays.index(target)]
    victim["tasks"] = [t for t in victim["tasks"] if not _is_staging(t)]
    assert play_gaps(mutated), "control: removing staging from a play must be detected"


def test_control_detector_rejects_a_file_without_the_task(tmp_path):
    other = tmp_path / "x.yml"
    other.write_text(
        "- ansible.builtin.copy:\n    src: a/constraints/shared.txt\n    dest: '{{ autobot.base_dir }}/c'\n",
        encoding="utf-8",
    )
    assert not deploys_python_version(other)
