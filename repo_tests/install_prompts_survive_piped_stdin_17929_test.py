# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""`curl | sudo bash` must not kill the installer at a prompt (#17929).

The documented install is ``curl -fsSL <raw install.sh> | sudo bash``. Under that
invocation **stdin is the pipe carrying the script**, not the terminal, so a bare
``read`` gets EOF and returns 1 -- and ``install.sh``'s ``set -euo pipefail``
turns that into an immediate, silent abort. The observed failure was the prompt
line printing and the shell returning, with no error and nothing installed.

The repaired contract has two halves and this file asserts both, because fixing
only the first produces something worse than the crash:

1. a prompt reads from ``/dev/tty``, so it reaches the real terminal whatever
   stdin is;
2. when there is **no** terminal at all, the caller is told -- it does not
   silently continue with an empty password. ``|| true`` on the original read
   would have satisfied (1)'s symptom and installed a blank admin credential.

**Why these are text assertions and not a rendered run.** Executing ``install.sh``
provisions a host; it is not runnable from a test. What is checkable without
running it is that no prompt reads from stdin, that the tty path is used, and
that the generator is single-sourced -- the properties whose absence caused the
defect. The behavioural half is covered by ``test_the_helper_survives_a_closed_tty``
below, which executes only the extracted helper.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from repo_tests._paths import repo_root

_INSTALL = Path("install.sh")


def _source() -> str:
    return (repo_root() / _INSTALL).read_text(encoding="utf-8")


#: A `read` that takes its input from stdin: no `<&fd` and no `< /dev/tty`.
#: This is the construct that aborts under `set -e` when stdin is the script pipe.
#: `-p` may be bundled into a combined short flag -- the live defect was `read -rsp`,
#: which a pattern requiring a standalone `-p ` does not match at all. The contrast
#: case below is what caught that; without it this guard passed over the very line
#: it exists to find.
_BARE_READ = re.compile(r"^\s*(?:IFS=\s*)?read\s+(?![^\n]*(?:<&|</dev/tty))[^\n]*(?:-[a-zA-Z]*p\b|--prompt)", re.M)


def _code_lines(source: str) -> str:
    """Source with comment-only lines dropped.

    A text guard that scans the whole file matches the comment explaining the
    rule as readily as a violation of it -- this one did, on the very comment
    saying why `[[ -r /dev/tty ]]` is insufficient.
    """
    return "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))


def test_no_prompt_reads_from_stdin() -> None:
    """The defect itself: an interactive prompt on stdin under `curl | bash`."""
    offenders = _BARE_READ.findall(_source())
    assert not offenders, (
        f"{len(offenders)} prompt(s) in install.sh read from stdin: {offenders}. Under the "
        "documented `curl -fsSL ... | sudo bash` stdin is the pipe carrying the script, so "
        "`read` gets EOF, returns 1, and `set -euo pipefail` aborts the installer with no "
        "message. Prompt via /dev/tty instead."
    )


def test_the_detector_sees_a_bare_prompt() -> None:
    """Without this the clean result above licenses nothing."""
    assert _BARE_READ.findall('    read -rsp "  pw > " input\n'), "combined short flags must match"
    assert _BARE_READ.findall('    read -r -p "x > " v\n'), "separated flags must match too"


def test_a_tty_backed_prompt_is_not_reported() -> None:
    """The contrast: the repaired form must not be flagged."""
    assert not _BARE_READ.findall('    IFS= read -rs -p "${__prompt}" __value <&"${__fd}" || return 1\n')


def test_the_tty_is_tested_by_opening_it_not_by_a_mode_check() -> None:
    """`[[ -r /dev/tty ]]` passes where opening fails, and leaks a raw bash error.

    Under `setsid`, in a container, or in any process with no controlling
    terminal, the device node exists and is readable by mode while `open()`
    returns ENXIO. Only an open test matches what the read will do.
    """
    source = _code_lines(_source())
    assert "exec {__fd}</dev/tty" in source, "the tty must be probed by opening it"
    assert "[[ -r /dev/tty ]]" not in source, (
        "a mode check on /dev/tty passes in a session with no controlling terminal and then "
        "the redirect fails, printing bash's own 'No such device or address' to the operator"
    )


def test_the_no_terminal_path_is_loud_rather_than_silent() -> None:
    """A missing terminal must warn, not quietly install a blank credential."""
    source = _source()
    assert "No terminal available to read a password" in source, (
        "the no-tty branch must say so: `|| true` on the read would continue with an empty "
        "ADMIN_PASSWORD, which is worse than the abort it replaces"
    )


def test_one_password_generator_not_four() -> None:
    """The interactive-blank and no-terminal paths must not drift in length or alphabet."""
    source = _source()
    inline = source.count("openssl rand -base64 24 | tr -dc")
    assert inline == 1, (
        f"{inline} inline password generators in install.sh; expected exactly 1 (the body of "
        "generate_admin_password). Separate copies drift in length or alphabet, and the "
        "interactive and no-terminal paths must produce the same shape of credential."
    )
    assert source.count("ADMIN_PASSWORD=$(generate_admin_password)") >= 3


def test_the_helper_survives_a_closed_tty() -> None:
    """Behavioural half, run on the extracted helper rather than on the installer.

    Executes the real `prompt_from_tty` under `set -euo pipefail` with no
    controlling terminal — the `curl | sudo bash` case — and asserts the script
    reaches its end instead of aborting at the prompt.
    """
    source = _source()
    start = source.index("prompt_from_tty() {")
    helper = source[start : source.index("\n}\n", start) + 3]

    script = (
        "set -euo pipefail\n" + helper + 'if prompt_from_tty answer "pw > " --silent; then echo "GOT:${answer}"; '
        'else echo "NO_TTY"; fi\n'
        'echo "REACHED_END"\n'
    )
    done = subprocess.run(
        ["setsid", "bash", "-c", script],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert done.returncode == 0, f"installer aborted at the prompt: rc={done.returncode} {done.stderr}"
    assert "NO_TTY" in done.stdout, f"expected the no-terminal branch, got {done.stdout!r}"
    assert "REACHED_END" in done.stdout, "the script did not get past the prompt"
    assert "No such device" not in done.stderr, f"bash's own tty error leaked to the operator: {done.stderr!r}"


def test_the_uninstall_confirmation_fails_CLOSED_not_open() -> None:
    """The two no-terminal branches go opposite ways, deliberately.

    A missing terminal at the password prompt costs a generated credential, so
    it continues. A missing terminal at the uninstall confirmation would cost an
    unconfirmed destructive wipe, so it refuses. Pinned because the obvious
    tidying -- making both branches behave "consistently" -- turns the second
    into a silent `rm` of every service, database and directory the banner lists.
    """
    source = _source()
    start = source.index("Type 'UNINSTALL' to confirm")
    block = source[start : start + 900]

    assert "prompt_from_tty confirmation" in block, "the confirmation must read the tty, not stdin"
    assert "exit 1" in block, (
        "a missing terminal here must ABORT. Falling through would run an uninstall nobody "
        "confirmed; today's `set -e` abort is accidentally fail-safe and this keeps that "
        "outcome deliberately."
    )
    assert "--yes" in block, "refusing without naming the non-interactive flag strands the operator"
