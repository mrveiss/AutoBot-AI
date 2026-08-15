# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every component installs into the interpreter its unit runs (#14278).

The agent installed into system Python with `--break-system-packages`, so a
transitive dependency the distro owns could not be replaced:

    ERROR: Cannot uninstall typing_extensions 4.10.0, RECORD file not found.
           Hint: The package was installed by debian.

Provisioning an external node stopped there.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ROLES = _REPO_ROOT / "autobot-slm-backend" / "ansible" / "roles"


def _pip_tasks() -> list[tuple[str, dict]]:
    """(role file, pip task args) for every ansible pip task in the roles tree."""
    found = []
    for path in sorted(_ROLES.rglob("*.yml")):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:  # pragma: no cover
            continue

        def walk(node):
            if isinstance(node, list):
                for item in node:
                    walk(item)
            elif isinstance(node, dict):
                pip = node.get("ansible.builtin.pip") or node.get("pip")
                if isinstance(pip, dict):
                    found.append((str(path.relative_to(_ROLES)), pip))
                for value in node.values():
                    walk(value)

        walk(document)
    return found


def test_the_scan_found_pip_tasks():
    """An empty scan makes every rule below vacuous."""
    assert len(_pip_tasks()) >= 4


def test_no_role_installs_into_system_python_with_break_system_packages():
    """`--break-system-packages` lets pip WRITE to the system environment. It does
    not let pip remove what dpkg owns, so any distro-managed transitive
    dependency aborts the install."""
    offenders = [
        f"{role_file}: {pip.get('name')}"
        for role_file, pip in _pip_tasks()
        if "break-system-packages" in str(pip.get("extra_args") or "")
    ]

    assert offenders == [], "\n".join(offenders)


def test_the_agent_installs_into_a_virtualenv():
    tasks = [pip for role_file, pip in _pip_tasks() if role_file.startswith("slm_agent/")]

    assert tasks, "no pip task found in the slm_agent role"
    assert all(task.get("virtualenv") for task in tasks), "the agent still installs outside a venv"


def test_the_agent_unit_runs_the_venv_interpreter():
    """The install target and the running interpreter must be the same one.

    A venv that the unit does not use is worse than no venv: the dependencies are
    installed somewhere nothing imports from, and the failure appears at runtime
    rather than at install time.
    """
    unit = (_ROLES / "slm_agent" / "templates" / "slm-agent.service.j2").read_text(encoding="utf-8")
    exec_start = next(line for line in unit.splitlines() if line.startswith("ExecStart="))

    defaults = yaml.safe_load(
        (_ROLES / "slm_agent" / "defaults" / "main.yml").read_text(encoding="utf-8")
    )
    venv_var = "slm_agent_venv"

    assert "/usr/bin/python3" not in exec_start
    # The unit references the venv by VARIABLE, so assert on that rather than on
    # a literal path — the template never contains the resolved directory.
    assert venv_var in exec_start, f"ExecStart does not use {{{{ {venv_var} }}}}: {exec_start}"
    assert defaults[venv_var].endswith("/venv")


def test_the_unit_still_sets_pythonpath_for_autobot_shared():
    """#11508: the agent imports autobot_shared from the install base rather than
    borrowing another component's venv. Moving to its own venv must not lose
    that — PYTHONPATH is honoured by any interpreter, so it should be untouched.
    """
    unit = (_ROLES / "slm_agent" / "templates" / "slm-agent.service.j2").read_text(encoding="utf-8")

    assert re.search(r"^Environment=PYTHONPATH=.*slm_agent_dir", unit, re.MULTILINE)


def test_the_venv_path_is_derived_from_the_install_dir():
    """A hardcoded second path would drift from slm_agent_dir."""
    defaults = yaml.safe_load(
        (_ROLES / "slm_agent" / "defaults" / "main.yml").read_text(encoding="utf-8")
    )

    assert "slm_agent_dir" in str(defaults.get("slm_agent_venv", ""))


# ---------------------------------------------------------------------------
# The venv must contain everything the agent's import chain touches
# ---------------------------------------------------------------------------


def _agent_import_closure() -> set[str]:
    """Third-party module names reachable from the agent's package import.

    A clean venv inherits nothing, so anything on this chain that is not in
    `slm_agent_python_packages` is a crash at process start. `pyyaml` was
    exactly that: satisfied under system Python by whatever apt had installed,
    absent the moment the agent got its own venv.
    """
    import ast as _ast

    agent_pkg = _ROLES / "slm_agent" / "files" / "slm" / "agent"
    shared = _REPO_ROOT / "autobot_shared"
    seen: set[str] = set()
    # Tests never run on the node; their imports are not runtime dependencies.
    queue = [
        p
        for p in agent_pkg.rglob("*.py")
        if not (p.name.startswith("test_") or p.name.endswith("_test.py"))
    ]
    visited_files: set[Path] = set()

    while queue:
        path = queue.pop()
        if path in visited_files or not path.is_file():
            continue
        visited_files.add(path)
        try:
            tree = _ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover
            continue
        for node in _ast.walk(tree):
            names = []
            if isinstance(node, _ast.ImportFrom) and node.module:
                # Relative imports are internal by definition.
                if node.level:
                    continue
                names = [node.module]
            elif isinstance(node, _ast.Import):
                names = [a.name for a in node.names]
            for name in names:
                top = name.split(".")[0]
                if top == "autobot_shared":
                    target = shared / Path(*name.split(".")[1:])
                    for candidate in (target.with_suffix(".py"), target / "__init__.py"):
                        if candidate.is_file():
                            queue.append(candidate)
                elif top in {"slm", "__future__"}:
                    continue
                else:
                    # Resolvable next to the agent package or inside
                    # autobot_shared -> internal, not a venv dependency.
                    # Internal if it resolves anywhere in the repo's own import
                    # roots. `utils`, `config` and `constants` are backend
                    # modules, not PyPI distributions.
                    local = [
                        root / suffix
                        for root in (agent_pkg, agent_pkg.parent, shared, _REPO_ROOT / "autobot-backend")
                        for suffix in (f"{top}.py", f"{top}/__init__.py")
                    ]
                    if not any(candidate.is_file() for candidate in local):
                        seen.add(top)
    return seen


# Modules the standard library provides; a venv always has them.
_STDLIB = {
    "asyncio", "json", "logging", "os", "platform", "socket", "subprocess", "sys",
    "time", "typing", "pathlib", "datetime", "dataclasses", "enum", "functools",
    "hashlib", "re", "shutil", "uuid", "contextlib", "collections", "itertools",
    "threading", "traceback", "warnings", "base64", "secrets", "signal", "copy",
    "inspect", "importlib", "math", "random", "string", "textwrap", "urllib", "io",
    "abc", "glob", "tempfile", "types", "weakref", "struct", "binascii", "errno",
    "ipaddress", "getpass", "argparse", "configparser", "csv", "gzip", "pickle",
    "queue", "select", "shlex", "stat", "statistics", "unicodedata", "zlib",
    "concurrent", "sqlite3", "unittest", "ssl", "http", "email", "html", "xml",
}

# Pulled in by a package that IS listed, so a venv gets them transitively.
_TRANSITIVE = {"pydantic"}

# PyPI distribution names differ from import names for a few packages.
_IMPORT_TO_DISTRIBUTION = {"yaml": "pyyaml", "pydantic_settings": "pydantic-settings"}


def test_the_import_closure_was_actually_walked():
    """An empty closure would make the rule below vacuous."""
    closure = _agent_import_closure()

    assert "yaml" in closure, f"the walk did not reach yaml: {sorted(closure)}"


def test_every_third_party_import_the_agent_reaches_is_installed_in_its_venv():
    """The blind spot the first version of this PR had.

    The other tests here assert on Ansible YAML structure; none of them looks at
    what the agent actually imports, so a missing runtime dependency was
    invisible to the whole suite.
    """
    defaults = yaml.safe_load(
        (_ROLES / "slm_agent" / "defaults" / "main.yml").read_text(encoding="utf-8")
    )
    installed = {str(pkg).lower() for pkg in defaults["slm_agent_python_packages"]}

    missing = sorted(
        _IMPORT_TO_DISTRIBUTION.get(name, name)
        for name in _agent_import_closure()
        if name not in _STDLIB
        and name not in _TRANSITIVE
        and _IMPORT_TO_DISTRIBUTION.get(name, name).lower() not in installed
    )

    assert missing == [], f"the agent imports these but the venv would not have them: {missing}"


def test_the_code_sync_command_installs_the_same_set_into_the_same_venv():
    """A code-sync that updates a different interpreter than the unit runs, with
    a different package list than provisioning, cannot keep the agent working."""
    registry = (
        _REPO_ROOT / "autobot-slm-backend" / "services" / "role_registry.py"
    ).read_text(encoding="utf-8")
    match = re.search(r'"post_sync_cmd":\s*\((.*?)\),\n', registry[registry.index("_SLM_AGENT_DIR,"):], re.DOTALL)
    assert match, "no post_sync_cmd found for the slm-agent role"
    command = match.group(1)

    assert "venv/bin/pip" in command, f"code-sync targets the wrong interpreter: {command}"

    defaults = yaml.safe_load(
        (_ROLES / "slm_agent" / "defaults" / "main.yml").read_text(encoding="utf-8")
    )
    for package in defaults["slm_agent_python_packages"]:
        assert str(package) in command, f"{package} is provisioned but not installed on code-sync"
