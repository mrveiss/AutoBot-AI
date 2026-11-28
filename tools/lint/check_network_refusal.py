#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Guard: every network_subnet/network_gateway definition refuses when unset (#17642).

``network_subnet`` is the source of firewall and pg_hba rules. Every definition
used to fall back to ``''`` or ``0.0.0.0/0``, so an unresolved value opened the
rule to any source with no error. Each now ends in ``undef(hint=...)``.

Text checks cannot prove the hint is reachable: with the key missing from the
secrets file, ``grep`` exits 1 and the ``pipe`` lookup raised before ``undef``
was ever evaluated. So this evaluates EVERY definition with the real
ansible-core -- run by ansible-role-facts-test, which installs the fleet's pin;
the python suite has no ansible binary. For each definition:

- unset (env empty, secrets file absent) -> the play fails and names the variable;
- whitespace-only env -> refused the same way, not taken as a value;
- a real value in the env -> resolves to it.

The definition list is also imported by
repo_tests/network_never_hardcoded_17642_test.py, so text and behaviour
checks read one population. Run from the ansible directory, like its siblings:

    python3 ../../tools/lint/check_network_refusal.py
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess  # nosec B404  # git/ansible plumbing, fixed argv, no shell
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from autobot_shared.paths import scrubbed_git_env  # noqa: E402

SECRETS = "/etc/autobot/slm-secrets.env"
BUILDER = ROOT / "autobot-slm-backend/services/inventory_builder.py"
DEF_RE = re.compile(r"""["']?network_(subnet|gateway)["']?\s*:\s*["'](\{\{.*?\}\})""", re.S)
PATHSPECS = (":(glob)autobot-slm-backend/ansible/**/*.yml", "install.sh")
VALUES = {"NETWORK_SUBNET": "198.51.100.0/24", "NETWORK_GATEWAY": "198.51.100.1"}


def definition_files() -> list[Path]:
    """Tracked files that may define the variables -- git, never a tree walk (#15955)."""
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--", *PATHSPECS],
        check=True,
        capture_output=True,
        text=True,
        env=scrubbed_git_env(),
    ).stdout
    return [ROOT / p for p in out.split("\0") if p]


def definitions() -> list[tuple[str, str]]:
    """(file name, Jinja expression) for every lookup-based definition."""
    found = []
    for path in definition_files():
        text = path.read_text(encoding="utf-8")
        found += [(path.name, m.group(2)) for m in DEF_RE.finditer(text) if "lookup(" in m.group(2)]
    return found


def builder_definitions() -> list[tuple[str, str]]:
    """inventory_builder.py's two values, rendered by its own helper (no SLM imports needed)."""
    tree = ast.parse(BUILDER.read_text(encoding="utf-8"))
    helper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_secrets_lookup")
    namespace: dict = {}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), str(BUILDER), "exec"), namespace)  # nosec B102
    lookup = namespace["_secrets_lookup"]
    return [(BUILDER.name, lookup("NETWORK_SUBNET")), (BUILDER.name, lookup("NETWORK_GATEWAY"))]


def _evaluate(var: str, definition: str, env: dict, tmp: Path) -> subprocess.CompletedProcess:
    inventory = {"all": {"hosts": {"localhost": {"ansible_connection": "local"}}, "vars": {var: definition}}}
    inv = tmp / "inv.json"
    inv.write_text(json.dumps(inventory), encoding="utf-8")
    cmd = ["ansible", "localhost", "-i", str(inv), "-m", "debug", "-a", f"msg={{{{ {var} }}}}"]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=env)


def check(name: str, definition: str, tmp: Path) -> list[str]:
    """Problems with one definition; empty when it refuses unset/blank and resolves a value."""
    key = re.search(r"NETWORK_(SUBNET|GATEWAY)", definition).group(0)
    var = key.lower()
    definition = definition.replace(SECRETS, str(tmp / "absent.env"))
    # ansible.cfg's log_path may not be writable where this runs; the log is not under test.
    base = {
        "PATH": os.environ["PATH"],
        "HOME": str(tmp),
        "ANSIBLE_LOCAL_TEMP": str(tmp),
        "ANSIBLE_LOG_PATH": str(tmp / "ansible.log"),
    }
    problems = []
    for label, env in (("unset", base), ("blank", {**base, key: "  "})):
        run = _evaluate(var, definition, env, tmp)
        out = run.stdout + run.stderr
        # The error echoes the whole template, hint included, so the hint's text alone
        # proves nothing: a refusal is Ansible's undefined-variable error, and a lookup
        # that raised first (grep without `|| true`) is an unhandled exception instead.
        refused = "undefined variable" in out and "unhandled exception" not in out and f"{var} is unset" in out
        if run.returncode == 0 or not refused:
            problems.append(f"{name} {var} {label}: not refused with its hint ({run.stdout.strip()[-200:]})")
    run = _evaluate(var, definition, {**base, key: VALUES[key]}, tmp)
    if run.returncode != 0 or VALUES[key] not in run.stdout:
        problems.append(f"{name} {var} given: did not resolve to {VALUES[key]} ({run.stdout.strip()[-200:]})")
    return problems


def main() -> int:
    targets = definitions() + builder_definitions()
    if len(targets) < 17:
        print(f"FAIL: read {len(targets)} definitions, expected at least 17 -- the scan is broken")
        return 1
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, definition in targets:
            problems += check(name, definition, Path(tmp))
    for problem in problems:
        print(f"FAIL: {problem}")
    print(f"{len(targets)} definitions evaluated, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
