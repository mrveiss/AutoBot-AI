# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
r"""Shared loading and `when:`-evaluation helpers for ansible task-list guards.

Extracted when `pgdg_preserved_repo_is_verified_17897_test.py` was split at the
600-line ceiling (#17897): the behavioural half, which runs the role's embedded shell,
and the meta-check half, which reads its `when:` expressions and messages, both need
these. The module exists to keep the split from duplicating them -- it is not a
speculative framework, and `eval_when` in particular is only faithful for conditions
built from the filters modelled below.

A WARNING that belongs with any Jinja-based ansible harness: a plain Jinja environment
does NOT reproduce Ansible's string-literal semantics. Measured on ansible-core 2.17.14,
Ansible hands a filter the literal `'\1'` as backslash-one, while Jinja applies
`unicode_escape` and hands it `\x01`. So a harness built on this module will accept a
regex group spec that Ansible rejects, and vice versa (#17912 was that raise). Assert
such text, do not render it -- `ansible_regex_backslash_scalar_17897_test.py` is the single
home for that assertion and enforces it repo-wide.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import jinja2
import jinja2.meta
import pytest
import yaml
from repo_tests._paths import repo_root


def load_tasks(path: Path) -> list[dict]:
    """The task list at `path`, or a failure naming what moved."""
    if not path.exists():
        pytest.fail(f"{path.relative_to(repo_root())} does not exist -- the fix's home moved")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, list):
        pytest.fail(f"{path.relative_to(repo_root())} did not parse as a task list")
    return [t for t in loaded if isinstance(t, dict)]


def named(tasks: list[dict], fragment: str) -> dict:
    """The first task whose name contains `fragment`."""
    hits = [t for t in tasks if fragment in str(t.get("name", ""))]
    assert hits, f"no task whose name contains {fragment!r} -- the mechanism was removed"
    return hits[0]


def when_of(task: dict) -> str:
    """A task's `when:` as one expression, list form ANDed together."""
    when = task.get("when")
    return " and ".join(f"({c})" for c in when) if isinstance(when, list) else str(when)


def resolved_vars(path: Path) -> dict:
    """A vars/defaults file with its values' references to the file's own names rendered.

    `ollama_models` lists `"{{ ollama_embedding_model }}"`, so a test reading the raw list sees the
    reference, not the model ansible pulls. A value naming anything the file does not define (an
    inventory or fact name) is left as written.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    env = jinja2.Environment(autoescape=False, undefined=jinja2.StrictUndefined)  # noqa: S701 - vars, not markup

    def render(value: object) -> object:
        if isinstance(value, list):
            return [render(v) for v in value]
        if isinstance(value, str) and "{{" in value:
            if not jinja2.meta.find_undeclared_variables(env.parse(value)) <= raw.keys():
                return value
            return env.from_string(value).render(**raw)
        return value

    return {k: render(v) for k, v in raw.items()}


def play_vars(play: Any, playbook: Path) -> dict:
    """The resolved names a play loads through `vars_files` (paths relative to the playbook)."""
    loaded: dict = {}
    for rel in play.get("vars_files", []) if isinstance(play, dict) else []:
        loaded.update(resolved_vars((playbook.parent / rel).resolve()))
    return loaded


def loop_items(loop: object, names: dict) -> list[list]:
    """A task's `loop:` as `[items]`: a literal list, or a single `{{ name }}` read through `names`.

    Empty when the loop is neither, so a reference to a name the play does not load is not counted.
    """
    if isinstance(loop, list):
        return [loop]
    ref = re.fullmatch(r"\{\{\s*(\w+)\s*\}\}", loop) if isinstance(loop, str) else None
    return [names[ref.group(1)]] if ref and ref.group(1) in names else []


def eval_when(expr: str, **state: object) -> bool:
    """Evaluate an ansible `when` as Jinja, modelling the filters it uses."""
    env = jinja2.Environment(autoescape=False)  # noqa: S701 - a condition, not markup
    env.filters["bool"] = lambda v: (str(v).strip().lower() in {"true", "yes", "1", "on"} or v is True)
    env.tests["match"] = lambda v, pattern: re.match(pattern, str(v)) is not None
    return bool(env.compile_expression(expr, undefined_to_none=True)(**state))
