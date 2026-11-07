# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20941: the ai-stack's secrets-root-key read is the shared one, tag-safe, fail-closed and diff-free.

Four ways the first cut could drop the key without a word: a failed read replaced an existing key with
nothing, `--tags config` skipped the read's tasks (tags on an include gate only the include), the env
templates echoed secrets into `--diff` output, and the SLM file's path was a literal. Each check has a
control that proves the detector fires on the broken shape.
"""

from __future__ import annotations

from pathlib import Path

import jinja2
import yaml
from repo_tests._paths import repo_root

ANSIBLE = repo_root() / "autobot-slm-backend" / "ansible"
SHARED = ANSIBLE / "_shared" / "tasks" / "read_slm_secrets_root_key.yml"
AI_ENV = ANSIBLE / "roles" / "ai-stack" / "tasks" / "env_files.yml"
BACKEND_READ = ANSIBLE / "roles" / "backend" / "tasks" / "read_secrets_root_key.yml"
GROUP_ALL = ANSIBLE / "inventory" / "group_vars" / "all.yml"
_SHARED_NAME = "read_slm_secrets_root_key.yml"


def _tasks(path: Path) -> list[dict]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, list) and loaded, f"{path.name} parsed to no tasks: this guard would pass vacuously"
    return loaded


def _include_of(tasks: list[dict]) -> dict:
    hits = [t for t in tasks if _SHARED_NAME in str(t.get("ansible.builtin.include_tasks"))]
    assert len(hits) == 1, f"expected exactly one include of {_SHARED_NAME}, found {len(hits)}"
    return hits[0]


def _apply_tags(task: dict) -> set[str]:
    module = task["ansible.builtin.include_tasks"]
    return set((module.get("apply") or {}).get("tags") or []) if isinstance(module, dict) else set()


def _reaches_reader_under(task: dict, tag: str) -> bool:
    """True when `--tags <tag>` runs the include AND the tasks inside the included file."""
    return tag in set(task.get("tags") or []) and tag in _apply_tags(task)


# --- tags reach the reader -------------------------------------------------------------------


def test_a_tag_filtered_run_reads_the_key_in_the_ai_stack() -> None:
    include = _include_of(_tasks(AI_ENV))
    for tag in ("ai", "config"):
        assert _reaches_reader_under(include, tag), f"--tags {tag} must run the reader's tasks (apply: tags)"


def test_a_tag_filtered_run_reads_the_key_in_the_backend() -> None:
    include = _include_of(_tasks(BACKEND_READ))
    for tag in ("backend", "config", "env"):
        assert _reaches_reader_under(include, tag), f"--tags {tag} must run the reader's tasks (apply: tags)"


def test_control_an_include_with_tags_but_no_apply_is_caught() -> None:
    broken = {"ansible.builtin.include_tasks": _SHARED_NAME, "tags": ["ai", "config"]}
    assert not _reaches_reader_under(broken, "config")
    assert not _reaches_reader_under({"ansible.builtin.include_tasks": {"file": _SHARED_NAME}, "tags": ["ai"]}, "ai")


# --- one implementation ----------------------------------------------------------------------


def test_the_backend_and_the_ai_stack_share_one_reader() -> None:
    marker = "AUTOBOT_SECRETS_ROOT_KEY=\\K"
    homes = [p.name for p in (SHARED, AI_ENV, BACKEND_READ) if marker in p.read_text(encoding="utf-8")]
    assert homes == [SHARED.name], f"the read must exist only in {SHARED.name}; found {homes}"
    assert _include_of(_tasks(AI_ENV)) and _include_of(_tasks(BACKEND_READ))


def test_the_reader_takes_its_path_from_the_ssot_var_and_reads_privileged() -> None:
    tasks = _tasks(SHARED)
    probe = next(t for t in tasks if "ansible.builtin.command" in t)
    assert "slm_secrets_env_path" in str(probe["ansible.builtin.command"]["argv"]), "the path is the SSOT var"
    stat = next(t for t in tasks if "ansible.builtin.stat" in t)
    assert "slm_secrets_env_path" in stat["ansible.builtin.stat"]["path"]
    assert probe.get("become") is True and probe.get("delegate_to") == "localhost" and probe.get("no_log") is True
    assert "slm_secrets_env_path" in GROUP_ALL.read_text(encoding="utf-8"), "the SSOT var must be declared"


def test_an_unreadable_file_fails_the_read_instead_of_reading_as_empty() -> None:
    probe = next(t for t in _tasks(SHARED) if "ansible.builtin.command" in t)
    assert "|| true" not in str(probe), "`|| true` turned a failed read into an empty key"
    failed = jinja2.Environment().from_string("{{ " + str(probe["failed_when"]) + " }}")
    verdict = lambda rc: failed.render(_slm_root_key_probe={"rc": rc}) == "True"  # noqa: E731
    assert verdict(2) and not verdict(0) and not verdict(1), "rc 2 (unreadable) fails; rc 1 (no line) is only empty"


# --- an empty read never drops a key the env file holds --------------------------------------


def _refusal_fires(key: str, rcs: list[int], tasks: list[dict] | None = None) -> bool:
    tasks = tasks or _tasks(AI_ENV)
    fail = next(t for t in tasks if "Stop before dropping the secrets root key" in str(t.get("name")))
    conds = fail["when"]
    ctx = {
        "autobot_secrets_root_key": key,
        "_ai_env_root_key_present": {"results": [{"rc": rc} for rc in rcs]},
    }
    env = jinja2.Environment()
    return all(env.from_string("{{ " + str(c) + " }}").render(**ctx) == "True" for c in conds)


def test_an_empty_new_key_over_an_existing_one_fails_the_update() -> None:
    assert _refusal_fires("", [0, 1]), "env file holds a key (rc 0), this run has none: must refuse"
    assert _refusal_fires("", [2, 1]), "env file unreadable (rc 2) counts as 'may hold one': must refuse"


def test_controls_the_refusal_stays_quiet_when_nothing_is_lost() -> None:
    assert not _refusal_fires("new-key", [0, 0]), "a key to render: nothing is dropped"
    assert not _refusal_fires("", [1, 1]), "no env file yet: nothing to protect"
    assert not _refusal_fires("", []), "no probe result: nothing to protect"


def test_the_refusal_sits_between_the_read_and_the_first_render() -> None:
    names = [str(t.get("name")) for t in _tasks(AI_ENV)]
    read = next(i for i, n in enumerate(names) if "Read the SLM's secrets root key" in n)
    refuse = next(i for i, n in enumerate(names) if "Stop before dropping the secrets root key" in n)
    render = next(i for i, n in enumerate(names) if "Deploy /etc/autobot/autobot-ai-stack.env" in n)
    assert read < refuse < render


# --- secrets stay out of --diff --------------------------------------------------------------


def _undiffed_templates(tasks: list[dict]) -> list[str]:
    return [
        str(t["name"])
        for t in tasks
        if "ansible.builtin.template" in t and t["ansible.builtin.template"].get("src") == "ai-stack.env.j2"
        if t.get("diff") is not False
    ]


def test_both_ai_stack_env_renders_hide_their_diff() -> None:
    tasks = _tasks(AI_ENV)
    rendered = [t for t in tasks if "ansible.builtin.template" in t]
    assert len(rendered) == 2, "expected the two env-file renders; re-point this guard if that changed"
    assert _undiffed_templates(tasks) == []


def test_control_a_render_without_diff_false_is_caught() -> None:
    broken = [{"name": "x", "ansible.builtin.template": {"src": "ai-stack.env.j2"}}]
    assert _undiffed_templates(broken) == ["x"]
    assert _undiffed_templates([{**broken[0], "diff": True}]) == ["x"]
