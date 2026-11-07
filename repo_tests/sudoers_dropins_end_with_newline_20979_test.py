# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20979: a sudoers drop-in without a trailing newline is rejected by a newer visudo.

Every ansible task that writes under /etc/sudoers.d (copy, template, lineinfile,
blockinfile) must end its content with a newline and be visudo-validated, either by
its own `validate: visudo -cf %s` or by a sibling task that runs `visudo -cf` on it.
"""

import re
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root

_SUDOERS_DIR = "/etc/sudoers.d"
_MODULES = ("copy", "template", "lineinfile", "blockinfile")
_VALIDATE = re.compile(r"visudo\s+-cf\s+%s")
_VISUDO_CMD = re.compile(r"visudo\s+-cf\s+(\S+)")
_VAR = re.compile(r"\{\{\s*(\w+)\s*\}\}")
_SKIP_PARTS = {"node_modules", ".git"}


def _module_of(task: dict) -> tuple[str, dict] | None:
    for key, value in task.items():
        name = str(key).rsplit(".", 1)[-1]
        if name in _MODULES and key in (name, f"ansible.builtin.{name}"):
            return name, value if isinstance(value, dict) else {}
    return None


def _render(text: object, play_vars: dict) -> str:
    return _VAR.sub(lambda m: str(play_vars.get(m.group(1), m.group(0))), str(text))


def _walk(node: object, play_vars: dict, siblings: list):
    if isinstance(node, list):
        sibs = [n for n in node if isinstance(n, dict)]
        for item in node:
            yield from _walk(item, play_vars, sibs)
    elif isinstance(node, dict):
        scoped = {**play_vars, **(node.get("vars") if isinstance(node.get("vars"), dict) else {})}
        if _module_of(node):
            yield node, scoped, siblings
        for value in node.values():
            if isinstance(value, (list, dict)):
                yield from _walk(value, scoped, siblings)


def _sudoers_tasks(docs: list[tuple[str, object]]):
    for origin, doc in docs:
        for task, scoped, sibs in _walk(doc, {}, []):
            module, args = _module_of(task)
            target = _render(args.get("dest") or args.get("path") or "", scoped)
            if target.startswith(_SUDOERS_DIR):
                yield origin, task, module, args, target, scoped, sibs


def _template_text(origin: str, src: str) -> str | None:
    base = Path(origin).parent
    for cand in (base / src, base / "templates" / src, base.parent / "templates" / src):
        if cand.is_file():
            return cand.read_text(encoding="utf-8")
    return None


def _content_problem(origin: str, module: str, args: dict) -> str | None:
    if module in ("lineinfile", "blockinfile"):
        return None  # the module terminates the line/block itself
    if module == "template":
        text = _template_text(origin, str(args.get("src", "")))
        return None if text and text.endswith("\n") else "template missing or no trailing newline"
    content = args.get("content")
    if not isinstance(content, str):
        return "no literal content: to check"
    return None if content.endswith("\n") else "content has no trailing newline"


def _validated(args: dict, target: str, scoped: dict, sibs: list) -> bool:
    if _VALIDATE.search(str(args.get("validate", ""))):
        return True
    for sib in sibs:
        cmd = sib.get("command") or sib.get("ansible.builtin.command") or sib.get("shell")
        found = _VISUDO_CMD.search(_render(cmd, scoped)) if cmd else None
        if found and found.group(1) == target:
            return True
    return False


def _problems(docs: list[tuple[str, object]]) -> list[str]:
    out = []
    for origin, task, module, args, target, scoped, sibs in _sudoers_tasks(docs):
        label = f"{origin}: {task.get('name', target)}"
        problem = _content_problem(origin, module, args)
        if problem:
            out.append(f"{label}: {problem}")
        if not _validated(args, target, scoped, sibs):
            out.append(f"{label}: no `visudo -cf %s` validation")
    return out


def _load_all(path: Path) -> list[tuple[str, object]]:
    try:
        loaded = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    except yaml.YAMLError:
        return []  # a Jinja-templated file is not YAML until rendered
    return [(str(path), doc) for doc in loaded]


def _repo_docs() -> list[tuple[str, object]]:
    docs = []
    for ansible_dir in repo_root().rglob("ansible"):
        if not ansible_dir.is_dir() or _SKIP_PARTS & set(ansible_dir.parts):
            continue
        for path in sorted(ansible_dir.rglob("*.y*ml")):
            if path.is_file() and path.suffix in (".yml", ".yaml"):
                docs.extend(_load_all(path))
    return docs


def test_repo_sudoers_dropins_end_with_newline_and_are_validated():
    docs = _repo_docs()
    seen = list(_sudoers_tasks(docs))
    assert len(seen) >= 8, f"found only {len(seen)} sudoers tasks -- the walker lost them"
    assert _problems(docs) == []


def _fixture(content: str, validate: str | None = "visudo -cf %s") -> list[tuple[str, object]]:
    args = {"dest": "/etc/sudoers.d/x", "content": content}
    if validate:
        args["validate"] = validate
    return [("fixture.yml", yaml.safe_load(yaml.safe_dump([{"name": "t", "copy": args}])))]


def test_guard_fails_without_trailing_newline():
    assert any("no trailing newline" in p for p in _problems(_fixture("u ALL=(ALL) NOPASSWD: ALL")))


def test_guard_fails_without_validate():
    assert any("validation" in p for p in _problems(_fixture("u ALL=(ALL) NOPASSWD: ALL\n", None)))


def test_guard_passes_on_a_good_fixture():
    assert _problems(_fixture("u ALL=(ALL) NOPASSWD: ALL\n")) == []


def test_block_scalar_keep_chomp_is_accepted_and_strip_is_not():
    good = yaml.safe_load("- copy:\n    dest: /etc/sudoers.d/x\n    validate: visudo -cf %s\n    content: |\n      a\n")
    bad = yaml.safe_load("- copy:\n    dest: /etc/sudoers.d/x\n    validate: visudo -cf %s\n    content: |-\n      a\n")
    assert _problems([("g.yml", good)]) == []
    assert _problems([("b.yml", bad)])


@pytest.mark.parametrize("validate", ["visudo -c %s", "true"])
def test_guard_rejects_a_validate_that_is_not_visudo_cf(validate):
    assert _problems(_fixture("a\n", validate))
