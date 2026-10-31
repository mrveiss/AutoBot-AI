# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The install root is written once, as `autobot.base_dir` (#15632; #18587 part 1, #18880).

`/opt/autobot` stays the folder AutoBot deploys to; the point is one definition. The literal
elsewhere in Ansible code is frozen per file in opt_autobot_literal_ratchet_18880_baseline.py
and only goes down. install.sh's AUTOBOT_BASE must equal it: `-e` cannot set one key of the
`autobot:` mapping without replacing the mapping, and that mapping must stay template-free
for controller plays (#15731), so equality is pinned here instead of passed at run time.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.opt_autobot_literal_ratchet_18880_baseline import BASELINE

from tools.lint._comment_syntax import code_lines
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOT = repo_root()
_ANSIBLE = "autobot-slm-backend/ansible"
_DEFINITION_FILE = f"{_ANSIBLE}/inventory/group_vars/all.yml"
_DEFINITION = 'base_dir: "/opt/autobot"'
# Prose and frozen copies are not configuration (owner, 2026-10-22, #18882): Markdown, Python
# docstrings (as comments already are), and tests/fixtures/ -- byte-for-byte copies of past files
# that reproduce an old defect, which a rewrite would turn into a different fixture.
_PROSE_SUFFIXES = (".md",)
_FROZEN_PREFIX = f"{_ANSIBLE}/tests/fixtures/"


def _docstring_lines(text: str) -> set[int]:
    """1-based line numbers of every module, class and function docstring."""
    lines: set[int] = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                lines.update(range(first.lineno, first.end_lineno + 1))
    return lines


def _in_scope(path: str) -> bool:
    """Configuration, not prose or a frozen copy -- the one boundary discovery and counting share."""
    return not (path.endswith(_PROSE_SUFFIXES) or path.startswith(_FROZEN_PREFIX))


def _ansible_files(root: Path) -> list[str]:
    try:
        return [p for p in tracked_paths(root, _ANSIBLE) if _in_scope(p)]
    except EmptyEnumeration:
        return []


REACH = declare(
    "opt-autobot-literal-ratchet-18880",
    discover=_ansible_files,
    # mid-window on the SCANNED population (prose and fixtures excluded at discovery, CodeRabbit
    # on #19388): 479 tracked - 17 out of scope = 462; floor 462 - 20 = 442, window (422, 462)
    floor=442,
    growth=40,
    what="tracked ansible files",
    roots=(_ANSIBLE,),
)


def literal_counts(files: dict[str, str]) -> dict[str, int]:
    """{path: code occurrences of /opt/autobot}, the one definition excluded, zeros dropped."""
    counts = {}
    for path, text in files.items():
        if not _in_scope(path):
            continue
        prose = _docstring_lines(text) if path.endswith(".py") else set()
        lines = code_lines(text, name=path, strip_trailing=True)
        n = sum(
            line.text.count("/opt/autobot")
            for line in lines
            if line.lineno not in prose and not (path == _DEFINITION_FILE and line.text.strip() == _DEFINITION)
        )
        if n:
            counts[path] = n
    return counts


def _live() -> dict[str, int]:
    files = {}
    for rel in REACH.examined(_ROOT):
        try:
            files[rel] = (_ROOT / rel).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue  # binary assets carry no path literal
    return literal_counts(files)


def test_the_literal_count_only_goes_down() -> None:
    live = _live()
    grown = {p: (BASELINE.get(p, 0), n) for p, n in live.items() if n > BASELINE.get(p, 0)}
    assert not grown, f"new /opt/autobot literals -- use {{{{ autobot.base_dir }}}}: {grown}"
    shrunk = {p: (b, live.get(p, 0)) for p, b in BASELINE.items() if live.get(p, 0) < b}
    assert not shrunk, f"literals removed -- lower BASELINE to match, so the slack is not re-spent: {shrunk}"


def _group_vars_all() -> dict:
    import yaml

    return yaml.safe_load((_ROOT / _DEFINITION_FILE).read_text(encoding="utf-8"))


def test_the_install_root_is_defined_once() -> None:
    """autobot.base_dir is the one root; a second name for it (the retired top-level
    autobot_base_dir) must not come back."""
    assert _group_vars_all()["autobot"]["base_dir"] == "/opt/autobot"
    seconds = [
        rel
        for rel in REACH.examined(_ROOT)
        if rel.endswith((".yml", ".yaml"))
        and re.search(r"^\s*autobot_base_dir\s*:", (_ROOT / rel).read_text(encoding="utf-8"), re.M)
    ]
    assert not seconds, f"a second install-root variable: {seconds}"


def test_install_sh_and_ansible_agree_on_the_root() -> None:
    install = (_ROOT / "install.sh").read_text(encoding="utf-8")
    m = re.search(r'^readonly AUTOBOT_BASE="([^"]+)"', install, re.M)
    assert m, "install.sh no longer declares AUTOBOT_BASE"
    root = _group_vars_all()["autobot"]["base_dir"]
    assert m.group(1) == root, (
        f"install.sh AUTOBOT_BASE={m.group(1)!r} != autobot.base_dir={root!r} in {_DEFINITION_FILE}; "
        "change both together"
    )


def test_no_role_default_or_group_var_restates_the_root() -> None:
    """#18880 AC: every role default / vars / group_vars path under the root derives from it."""
    leftover = [p for p in BASELINE if re.search(r"/(defaults|vars|group_vars)/", p)]
    assert not leftover, leftover


def test_the_counter_sees_code_and_ignores_comments_and_the_definition() -> None:
    files = {
        _DEFINITION_FILE: 'autobot:\n  base_dir: "/opt/autobot"\n# lives in /opt/autobot\nx: /opt/autobot/y\n',
        "a.yml": "dest: /opt/autobot/a  # under /opt/autobot\n",
        "b.j2": "ExecStart={{ autobot.base_dir }}/run\n",
    }
    assert literal_counts(files) == {_DEFINITION_FILE: 1, "a.yml": 1}


def test_prose_and_frozen_fixtures_are_outside_the_boundary_and_code_still_counts() -> None:
    """The 2026-10-22 boundary: Markdown, docstrings and tests/fixtures/ are not counted;
    the same literal in YAML, a template, a shell script or Python code still is."""
    files = {
        "README.md": "Installs to /opt/autobot.\n",
        f"{_FROZEN_PREFIX}old/task.yml": "path: /opt/autobot/x\n",
        "check.py": '"""Seen on a live /opt/autobot run."""\nROOT = "/opt/autobot"\n',
        "task.yml": "dest: /opt/autobot/a\n",
        "unit.j2": "ExecStart=/opt/autobot/run\n",
        "run.sh": 'D="/opt/autobot/b"\n',
    }
    assert literal_counts(files) == {"check.py": 1, "task.yml": 1, "unit.j2": 1, "run.sh": 1}


_SYNONYMS = ("project_root", "slm_base_dir", "autobot_repo_dir", "frontend_install_dir")


# `[ \t]*` (never `\s*`, which crosses the newline) and `.*?` so an EMPTY value is captured.
_SYNONYM_DEF = re.compile(rf"^[ \t]*({'|'.join(_SYNONYMS)}):[ \t]*(.*?)[ \t]*(?:#.*)?$", re.M)


def synonym_definitions(files: dict[str, str]) -> dict[str, list[tuple[str, str]]]:
    """{synonym: [(path, value), ...]} over YAML files, an empty value kept as ``""``."""
    defs: dict[str, list[tuple[str, str]]] = {}
    for rel, text in files.items():
        if rel.endswith((".yml", ".yaml")) and not rel.startswith(_FROZEN_PREFIX):
            for m in _SYNONYM_DEF.finditer(text):
                defs.setdefault(m.group(1), []).append((rel, m.group(2)))
    return defs


def stray_synonyms(defs: dict[str, list[tuple[str, str]]]) -> list[tuple[str, str, str]]:
    return [(name, rel, v) for name, sites in defs.items() for rel, v in sites if v != '"{{ autobot.base_dir }}"']


def test_the_root_synonyms_are_the_root_not_a_second_name_for_it() -> None:
    """#18882 AC2/AC3: the four older names for the install root are each defined only as
    `{{ autobot.base_dir }}`, so none can name the root separately again."""
    yaml_files = [rel for rel in REACH.examined(_ROOT) if rel.endswith((".yml", ".yaml"))]
    defs = synonym_definitions({rel: (_ROOT / rel).read_text(encoding="utf-8") for rel in yaml_files})
    assert set(defs) == set(
        _SYNONYMS
    ), f"a synonym's definition is no longer found: {sorted(set(_SYNONYMS) - set(defs))}"
    stray = stray_synonyms(defs)
    assert not stray, f"a root synonym that is not autobot.base_dir: {stray}"


def test_contrast_an_empty_synonym_definition_is_stray() -> None:
    files = {
        "good.yml": 'project_root: "{{ autobot.base_dir }}"  # the root\n',
        "empty.yml": "project_root:\n  nested: x\n",
        "blank.yml": "slm_base_dir: # nothing\n",
    }
    defs = synonym_definitions(files)
    assert defs["project_root"] == [("good.yml", '"{{ autobot.base_dir }}"'), ("empty.yml", "")]
    assert stray_synonyms(defs) == [("project_root", "empty.yml", ""), ("slm_base_dir", "blank.yml", "")]
    assert stray_synonyms(synonym_definitions({"good.yml": files["good.yml"]})) == []
