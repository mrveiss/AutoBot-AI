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
import shutil
import subprocess
from pathlib import Path

import pytest
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
    assert not real or len(found) >= _PACKAGE_FLOOR, f"read {len(found)} role packages -- the scan is broken"
    return found


#: Measured 148 resolved role packages on 2026-10-19 (#18727); a floor near the count catches a scan
#: that silently lost a share of the roles, with headroom for a few packages to go.
_PACKAGE_FLOOR = 140


def _recorded_packages() -> list[str]:
    """Packages install.sh writes to the install record (`record_install package ...`)."""
    text = _INSTALL.read_text(encoding="utf-8")
    names = re.findall(r'record_install package "?([a-z0-9][a-z0-9.+-]*)"?', text)
    for loop in re.findall(r"for \w+ in ([^;]+); do record_install package", text):
        names += loop.split()
    for call in re.findall(r'^\s*apt_install_recorded "[^"]*" ([^;\n]+)', text, re.M):  # #18727
        names += call.split()
    return names


def _removed_or_kept() -> list[str]:
    return _recorded_packages() + _array("SHARED_PACKAGES") + _array("POSTGRES_PACKAGES") + _array("KEPT_PACKAGES")


def uncovered_packages(installed, patterns: list[str]) -> list[str]:
    """Names no pattern covers; an apt ``name=version`` pin is matched by its name (#19329)."""

    def covered(name: str) -> bool:
        bare = name.split("=", 1)[0]
        return any(fnmatch.fnmatch(bare, p) for p in patterns)

    return sorted(n for n in installed if "{{" not in n and not covered(n))


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


def recorded_but_kept(recorded: list[str], kept: list[str]) -> list[str]:
    """Install-record packages a KEPT_PACKAGES entry also covers. plan_packages() purges every recorded
    package, so such a package would be removed although KEPT_PACKAGES promises no uninstall does."""
    return sorted(n for n in recorded if any(fnmatch.fnmatch(n, k) for k in kept))


def test_no_recorded_package_is_also_kept() -> None:
    """#18727: the install record and KEPT_PACKAGES must be disjoint."""
    overlap = recorded_but_kept(_recorded_packages(), _array("KEPT_PACKAGES"))
    assert not overlap, f"recorded (purged) yet listed as kept: {overlap}"


def test_the_overlap_check_sees_exact_and_glob_matches() -> None:
    assert recorded_but_kept(["python3.14", "redis-tools", "libfoo-dev"], ["redis-tools", "lib*-dev", "nginx"]) == [
        "libfoo-dev",
        "redis-tools",
    ]
    assert recorded_but_kept(["python3.14"], ["nginx", "lib*-dev"]) == []


# --- the record holds only what install.sh itself installed (#18727) --------------------------


def _helpers() -> str:
    """install.sh's record helpers, as written there."""
    text = _INSTALL.read_text(encoding="utf-8")
    parts = [
        re.search(rf"^{name}\(\) \{{.*?^\}}$|^{name}\(\) \{{.*\}}$", text, re.M | re.S)
        for name in ("record_install", "pkg_installed", "apt_install_recorded")
    ]
    assert all(parts), "install.sh no longer defines the record helpers"
    return "\n".join(m.group(0) for m in parts)


def _install_with(tmp_path: Path, preinstalled: list[str], packages: list[str]) -> list[str]:
    """Run apt_install_recorded with dpkg-query/apt stubbed: *preinstalled* report `ok installed`."""
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash unavailable")
    record = tmp_path / "install-record"
    script = "\n".join(
        [
            "set -euo pipefail",
            f'INSTALL_RECORD="{record}"',
            f'PRE=" {" ".join(preinstalled)} "',
            'dpkg-query() { case "$PRE" in *" ${@: -1} "*) printf "install ok installed";; *) return 1;; esac; }',
            'run_ok() { shift; "$@"; }',
            "env() { :; }  # apt-get install, stubbed",
            _helpers(),
            f'apt_install_recorded "Installing" {" ".join(packages)}',
        ]
    )
    out = subprocess.run([bash, "-c", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return record.read_text(encoding="utf-8").split() if record.exists() else []


def test_a_package_installed_before_is_never_recorded(tmp_path: Path) -> None:
    """27's review: nodejs installed without `node` on PATH was recorded, so --uninstall purged it."""
    assert _install_with(tmp_path, ["nodejs"], ["nodejs"]) == []


def test_only_the_packages_install_sh_added_are_recorded(tmp_path: Path) -> None:
    assert _install_with(tmp_path, ["python3.14"], ["python3.14", "python3.14-venv"]) == ["package=python3.14-venv"]
    assert _install_with(tmp_path / "fresh", [], ["ansible"]) == ["package=ansible"]


def test_a_version_pinned_package_is_covered_by_its_name() -> None:
    """#19329: ``grafana=11.1.0`` is the package ``grafana``; a wrong name still fails."""
    assert uncovered_packages(["grafana=11.1.0"], ["grafana"]) == []
    assert uncovered_packages(["grafanax=11.1.0"], ["grafana"]) == ["grafanax=11.1.0"]
