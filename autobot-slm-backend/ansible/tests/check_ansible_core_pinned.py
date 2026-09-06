#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The ansible-playbook CI invokes must be the fleet's ansible-core (#15824).

`ansible-role-facts-test` installed ansible-core with apt and then ran whatever
`ansible-playbook` PATH resolved to. Those were different programs: the job logs
carry no DEFAULT_GATHER_SUBSET deprecation even though ansible.cfg sets
`gather_subset = !hardware`, and that option is only silent from ansible-core
2.18 onward -- while the install step had just fetched 2.16.3. A guard that runs
an interpreter nobody deployed proves nothing about the hosts, and #15822 is what
that costs: the newer interpreter does not apply the `set_fact` bool coercion the
fleet's 2.17.14 does, so the guard read a decidable token where every host read a
bool, and wrong-node cleanup stayed dead for eleven days behind a green check.

Installing the pin is not enough on its own -- a shadowing binary earlier on PATH
puts the job straight back where it was. So this asserts the *resolved*
interpreter, not the one the install step asked for.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PIN_FILE = _REPO_ROOT / "constraints" / "ansible-core.txt"

_PIN_RE = re.compile(r"^ansible-core==([0-9][0-9A-Za-z.\-]*)\s*$")
_VERSION_RE = re.compile(r"\[core ([0-9][0-9A-Za-z.\-]*)\]")


def read_pin() -> str:
    """Return the pinned ansible-core version from the single source."""
    if not _PIN_FILE.is_file():
        raise SystemExit(f"MISSING PIN FILE: {_PIN_FILE}")

    for line in _PIN_FILE.read_text(encoding="utf-8").splitlines():
        match = _PIN_RE.match(line.strip())
        if match:
            return match.group(1)

    raise SystemExit(f"NO PIN IN {_PIN_FILE}\n  Expected a line of the form 'ansible-core==<version>'.")


def resolve_interpreter() -> Path:
    """Return the ansible-playbook PATH actually resolves to."""
    found = shutil.which("ansible-playbook")
    if not found:
        raise SystemExit(
            "NO ansible-playbook ON PATH\n  The workflow installs the pin into a venv and prepends its bin/ to PATH."
        )
    return Path(found).resolve()


def installed_version(interpreter: Path) -> str:
    """Return the core version the resolved interpreter reports."""
    # ansible.cfg points log_path at a fleet path this process may not own, and
    # an unwritable log is a hard error on `--version` alone. The version is a
    # property of the binary, not of the run, so logging is disabled for it.
    env = {**os.environ, "ANSIBLE_LOG_PATH": os.devnull}
    completed = subprocess.run(
        [str(interpreter), "--version"],
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
        env=env,
    )
    match = _VERSION_RE.search(completed.stdout)
    if not match:
        raise SystemExit(
            f"COULD NOT READ A VERSION FROM {interpreter}\n"
            f"  stdout: {completed.stdout.strip()[:400]}\n"
            f"  stderr: {completed.stderr.strip()[:400]}"
        )
    return match.group(1)


def main() -> int:
    pinned = read_pin()
    interpreter = resolve_interpreter()
    running = installed_version(interpreter)

    print(f"pin ({_PIN_FILE.name}): ansible-core=={pinned}")
    print(f"resolved interpreter:   {interpreter}")
    print(f"reported version:       core {running}")

    if running != pinned:
        print(
            "\nANSIBLE-CORE MISMATCH: the guard is not testing the fleet's interpreter.\n"
            f"  pinned:   {pinned}\n"
            f"  running:  {running}\n"
            f"  resolved: {interpreter}\n"
            "  Either something earlier on PATH shadows the pinned venv, or the fleet\n"
            "  moved and constraints/ansible-core.txt was not moved with it (#15824)."
        )
        return 1

    print("\nOK: CI runs the fleet's ansible-core.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
