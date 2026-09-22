# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ai-stack role must copy and filter the SAME manifest (#17242).

The role names that manifest twice, and two existing guards force it to:

* #14272's `test_the_copy_scan_sees_the_ai_stack_role` reads the COPY task's src
  **basename**, so that src has to end in a literal `requirements-ai.txt`.
* #14809's `test_requirements_are_not_delivered_twice` allows the task file
  exactly one `ai-stack/requirements-ai.txt`, so the filter step has to reach the
  manifest through a variable instead.

Neither side can adopt the other's form, so two independent expressions of one
path are unavoidable. The residual risk, raised in review on #17241: override the
tail variable and the role copies one manifest while filtering another --
silently, because each half stays individually valid and both guards stay green.

Static: this is a disagreement between two lines of YAML, which is what static
reading proves. CI does not execute Ansible.

Mutation check: change `ai_stack_requirements_rel` to name a different file and
this goes red quoting both sides.
"""

from __future__ import annotations

import re

import yaml
from repo_tests._paths import repo_root

_ROLE = repo_root() / "autobot-slm-backend" / "ansible" / "roles" / "ai-stack"
_TASKS = _ROLE / "tasks" / "main.yml"
_DEFAULTS = _ROLE / "defaults" / "main.yml"

_COPY_TASK = "Deploy requirements-ai.txt"
_FILTER_TASK = "Create filtered AI-stack requirements"

#: Whitespace-split, but a ``{{ ... }}`` expression counts as ONE token. Without
#: this, `{{ code_source_dir }}/{{ ai_stack_requirements_rel }}` splits into five
#: pieces and the path is lost -- the same tokenizer the manifest resolver needs
#: for the same reason.
_TOKEN = re.compile(r"(?:\{\{[^{}]*\}\}|[^\s{}])+")

#: The canonical filter script; its first argument is the manifest being read.
_FILTER_SCRIPT = "build-filtered-requirements.sh"


def _expand(text: str, defaults: dict) -> str:
    """Substitute role defaults, twice, so a var defined via another resolves."""
    for _ in range(2):
        for key, value in defaults.items():
            if isinstance(value, str):
                text = text.replace("{{ %s }}" % key, value)
    return text


def _normalise(path: str) -> str:
    """Collapse whitespace inside Jinja so two spellings of one path compare equal.

    Compares the WHOLE path, not a suffix. An earlier version compared only the
    tail after the last `}}`, so a copy rooted at `{{ alternate_code_source_dir }}`
    and a filter rooted at `{{ code_source_dir }}` matched — two different files,
    one passing assertion.
    """
    return " ".join(path.split())


def _sources() -> tuple[str, str, dict]:
    tasks = yaml.safe_load(_TASKS.read_text(encoding="utf-8"))
    defaults = yaml.safe_load(_DEFAULTS.read_text(encoding="utf-8")) or {}
    copy_src = filter_src = ""
    for task in tasks:
        if not isinstance(task, dict):
            continue
        name = str(task.get("name", ""))
        if _COPY_TASK in name:
            module = task.get("ansible.builtin.copy") or task.get("copy") or {}
            copy_src = str(module.get("src", ""))
        elif _FILTER_TASK in name:
            module = task.get("ansible.builtin.shell") or task.get("shell") or {}
            cmd = module if isinstance(module, str) else str(module.get("cmd", ""))
            # The SOURCE is the script's first argument, not any token that
            # happens to name the manifest. Scanning for a match picked the
            # redirect TARGET -- /tmp/filtered-requirements-ai... -- whose tail
            # is ".txt", which every path ends with, so the comparison below
            # passed against anything. Caught by mutation, not by reading.
            tokens = _TOKEN.findall(cmd)
            for i, token in enumerate(tokens):
                if token.endswith(_FILTER_SCRIPT) and i + 1 < len(tokens):
                    filter_src = tokens[i + 1]
                    break
    return copy_src, filter_src, defaults


def test_the_scan_finds_both_tasks():
    """Either task going missing would make the comparison below vacuous."""
    copy_src, filter_src, _ = _sources()

    assert copy_src, f"no task named {_COPY_TASK!r} with a copy src"
    assert filter_src, f"no task named {_FILTER_TASK!r} naming a manifest"


def test_copy_and_filter_resolve_to_the_same_manifest():
    """Copying one manifest and filtering another is invisible at runtime."""
    copy_src, filter_src, defaults = _sources()
    resolved_copy = _expand(copy_src, defaults)
    resolved_filter = _expand(filter_src, defaults)

    assert _normalise(resolved_copy) == _normalise(resolved_filter), (
        f"the ai-stack role copies {resolved_copy!r} but filters {resolved_filter!r} — "
        "an override makes these diverge, and the role then installs a filtered copy of a "
        "manifest it never delivered"
    )


# ---------------------------------------------------------------------------
# Contrast fixtures. Reading the live role proves today's state and nothing
# about the detector. These two inputs have a known answer by construction, so
# a detector that stopped discriminating fails here rather than going quietly
# green — which is what the first version of this guard did: it compared only
# the tail after the last `}}`, so ".txt" matched everything.
# ---------------------------------------------------------------------------

_AGREEING = """
- name: "AI Stack | Deploy requirements-ai.txt before installing from it"
  ansible.builtin.copy:
    src: "{{ code_source_dir }}/some/dir/requirements-ai.txt"
    dest: "{{ ai_install_dir }}/requirements-ai.txt"

- name: Create filtered AI-stack requirements
  ansible.builtin.shell:
    cmd: >-
      bash {{ code_source_dir }}/scripts/build-filtered-requirements.sh
      {{ code_source_dir }}/{{ ai_stack_requirements_rel }}
      {{ code_source_dir }}
      > /tmp/out.txt
"""

_DIVERGING = _AGREEING.replace(
    "{{ code_source_dir }}/some/dir/requirements-ai.txt",
    "{{ code_source_dir }}/a/different/dir/requirements-ai.txt",
)

_FIXTURE_DEFAULTS = {"ai_stack_requirements_rel": "some/dir/requirements-ai.txt"}


def _compare(tasks_yaml: str) -> bool:
    """True when the fixture's copy and filter name the same manifest."""
    tasks = yaml.safe_load(tasks_yaml)
    copy_src = filter_src = ""
    for task in tasks:
        name = str(task.get("name", ""))
        if _COPY_TASK in name:
            copy_src = str((task.get("ansible.builtin.copy") or task.get("copy") or {}).get("src", ""))
        elif _FILTER_TASK in name:
            module = task.get("ansible.builtin.shell") or task.get("shell") or {}
            cmd = module if isinstance(module, str) else str(module.get("cmd", ""))
            tokens = _TOKEN.findall(cmd)
            for i, token in enumerate(tokens):
                if token.endswith(_FILTER_SCRIPT) and i + 1 < len(tokens):
                    filter_src = tokens[i + 1]
                    break
    left = _normalise(_expand(copy_src, _FIXTURE_DEFAULTS))
    right = _normalise(_expand(filter_src, _FIXTURE_DEFAULTS))
    return left == right


def test_the_detector_accepts_matching_references():
    """The negative half: agreement must not be reported as drift."""
    assert _compare(_AGREEING), "the detector flags a role whose copy and filter agree"


def test_the_detector_rejects_diverging_references():
    """The positive half: this is the defect the guard exists for."""
    assert not _compare(_DIVERGING), (
        "the detector passed a role that copies one manifest and filters another — "
        "the comparison has stopped discriminating"
    )
