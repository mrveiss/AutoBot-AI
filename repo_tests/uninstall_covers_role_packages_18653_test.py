# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every package a role installs is removed by the uninstaller or kept with a reason (#18653 AC2).

Removed: the install record's packages, SHARED_PACKAGES (--purge-shared), POSTGRES_PACKAGES
(when PostgreSQL holds only AutoBot). Kept: KEPT_PACKAGES in scripts/uninstall.sh, grouped by
reason. A package a role starts installing that is in none of them fails here, so the
uninstaller's coverage cannot silently fall behind the roles.
"""

from __future__ import annotations

import fnmatch
import re

from repo_tests.uninstall_covers_role_components_18653_test import _INSTALL, _ROOT, _array, _docs, _resolve

_APT_MODULES = ("apt", "ansible.builtin.apt", "package", "ansible.builtin.package")
#: Package expressions no role chooses: apply-system-updates.yml installs what the operator passes.
#: Matched EXACTLY -- a substring test would also exempt `{{ other_specific_packages }}`.
_OPERATOR_SUPPLIED = frozenset(
    {"{{ specific_packages.split(',') if specific_packages is string else specific_packages }}"}
)


def _var_maps(docs) -> list[dict]:
    """Every vars mapping: role defaults and vars/, group_vars, and play-level vars."""
    maps = []
    for path, doc in docs:
        if path.match("*/defaults/main.yml") or path.match("*/vars/*.yml") or "group_vars" in path.parts:
            maps += [doc] if isinstance(doc, dict) else []
        elif isinstance(doc, list):
            maps += [p["vars"] for p in doc if isinstance(p, dict) and isinstance(p.get("vars"), dict)]
    return maps


def _strings_at(node, key: str) -> list[str]:
    """Every string, or string in a list, found under `key` anywhere inside `node`."""
    found: list[str] = []
    if isinstance(node, dict):
        for k, v in node.items():
            if k == key:
                found += (
                    [v] if isinstance(v, str) else [x for x in v if isinstance(x, str)] if isinstance(v, list) else []
                )
            found += _strings_at(v, key)
    elif isinstance(node, list):
        for item in node:
            found += _strings_at(item, key)
    return found


def _expand(value, loop, maps: list[dict], python: str) -> list[str]:
    if isinstance(value, list):
        return [n for v in value for n in _expand(v, loop, maps, python)]
    if not isinstance(value, str):
        return []
    value = value.replace("{{ python_interpreter_version }}", python)
    expr = re.fullmatch(r"\{\{\s*(.*?)\s*\}\}", value.strip(), re.S)
    if not expr:  # a name with a template inside it, e.g. postgresql-{{ postgresql_version }}
        strings = {k: v for m in maps for k, v in m.items() if isinstance(v, str) and "{{" not in v}
        return [_resolve(value, strings)]
    inner = expr.group(1)
    if inner == "item":
        return _expand(loop, None, maps, python) if loop is not None else [value]
    if inner.startswith("["):  # Jinja list literals -- the quoted names inside the brackets only
        return [n for lst in re.findall(r"\[([^\[\]]*)\]", inner) for n in re.findall(r"'([a-z0-9][a-z0-9.+-]*)'", lst)]
    path = re.fullmatch(r"(\w+)(?:\[\w+\])?(?:\.(\w+))?", inner)
    if path:
        top = [m[path[1]] for m in maps if path[1] in m]
        names = _strings_at(top, path[2]) if path[2] else [n for v in top for n in _expand(v, None, maps, python)]
        if names:
            return names
    return [value]


def _role_packages(docs=None) -> dict[str, str]:
    """{package or unresolved expression: a file installing it}; `docs` defaults to the real tree."""
    real = docs is None
    docs = _docs() if real else docs
    maps = _var_maps(docs)
    python = (_ROOT / ".python-version").read_text(encoding="utf-8").strip()
    found: dict[str, str] = {}

    def walk(node, path) -> None:
        if isinstance(node, dict):
            for mod in _APT_MODULES:
                call = node.get(mod)
                if isinstance(call, dict) and str(call.get("state", "present")) in ("present", "latest"):
                    loop = node.get("loop") or node.get("with_items")
                    for name in _expand(call.get("name") or call.get("pkg"), loop, maps, python):
                        found.setdefault(name, str(path.relative_to(_ROOT)))
            for value in node.values():
                walk(value, path)
        elif isinstance(node, list):
            for item in node:
                walk(item, path)

    for path, doc in docs:
        walk(doc, path)
    assert not real or len(found) > 100, f"read {len(found)} role packages -- the scan is broken"
    return found


def _recorded_packages() -> list[str]:
    """Packages install.sh writes to the install record (`record_install package ...`)."""
    text = _INSTALL.read_text(encoding="utf-8")
    names = re.findall(r'record_install package "?([a-z0-9][a-z0-9.+-]*)"?', text)
    for loop in re.findall(r"for \w+ in ([^;]+); do record_install package", text):
        names += loop.split()
    return names


def _removed_or_kept() -> list[str]:
    return _recorded_packages() + _array("SHARED_PACKAGES") + _array("POSTGRES_PACKAGES") + _array("KEPT_PACKAGES")


def uncovered_packages(installed, patterns: list[str]) -> list[str]:
    return sorted(n for n in installed if "{{" not in n and not any(fnmatch.fnmatch(n, p) for p in patterns))


def test_every_package_a_role_installs_is_removed_or_kept() -> None:
    missing = uncovered_packages(_role_packages(), _removed_or_kept())
    assert not missing, f"role packages the uninstaller neither removes nor keeps with a reason: {missing}"


def test_every_package_expression_resolves() -> None:
    """An unresolved name is a package nothing checks; only operator input is allowed to stay one."""
    unresolved = {n: f for n, f in _role_packages().items() if "{{" in n}
    unexpected = {n: f for n, f in unresolved.items() if n not in _OPERATOR_SUPPLIED}
    assert not unexpected, f"package names the guard cannot resolve: {unexpected}"


def test_every_kept_package_is_one_a_role_installs() -> None:
    """A kept entry no role installs is a stale reason; globs are exempt (they name families)."""
    installed = set(_role_packages())
    stale = [p for p in _array("KEPT_PACKAGES") if not any(c in p for c in "*?[") and p not in installed]
    assert not stale, f"KEPT_PACKAGES entries no role installs: {stale}"


def test_a_new_role_package_in_no_list_is_caught() -> None:
    assert uncovered_packages({"autobot-new-daemon": "x", "nginx": "y"}, _removed_or_kept()) == ["autobot-new-daemon"]


def test_role_package_discovery_contrast(tmp_path) -> None:
    """_role_packages() finds a present/latest apt install, looped or not, and ignores an absent one."""
    task_file = _ROOT / "autobot-slm-backend/ansible/roles/contrast/tasks/main.yml"
    tasks = [
        {"apt": {"name": "contrast-present"}},
        {"ansible.builtin.apt": {"name": "{{ item }}", "state": "latest"}, "loop": ["contrast-looped"]},
        {"apt": {"name": "contrast-absent", "state": "absent"}},
        {"debug": {"msg": "contrast-not-a-package"}},
    ]
    found = _role_packages([(task_file, tasks)])
    assert set(found) == {"contrast-present", "contrast-looped"}


def test_an_unresolved_expression_that_merely_contains_the_operator_name_is_not_exempt() -> None:
    assert "{{ other_specific_packages }}" not in _OPERATOR_SUPPLIED
    assert all("{{" in op for op in _OPERATOR_SUPPLIED)


def test_the_install_record_packages_are_read() -> None:
    assert {"python3.14", "python3.14-venv", "python3.14-dev"} <= set(_recorded_packages())
