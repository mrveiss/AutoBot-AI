# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A generated systemd unit may not contain an unexpanded ``${...}`` (#14036).

``cat > x.service << 'EOF'`` — quoted delimiter — disables shell parameter
expansion for the whole block. A ``${AUTOBOT_VNC_USER:-autobot}`` written
inside one lands in the unit file verbatim, and systemd has no bash-style
``:-`` default syntax, so ``User=${AUTOBOT_VNC_USER:-autobot}`` is not a valid
directive value. Every run of the script produced a broken unit.

The failure is quiet in the worst way: the script exits 0 having written a file
that looks plausible, and the breakage only appears when someone starts the
unit.

Two rules, because fixing this has two ways to go wrong:

1. A quoted unit heredoc must contain no ``${...}`` at all.
2. An *unquoted* one — the fix — may only reference variables the script has
   already assigned. Unquoting is what makes expansion work, and it also
   exposes every other token in the block: ``${USER}`` expands to ``root``
   under ``sudo``, which is how these scripts came to reference ``/home/root``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]

_SKIP_DIRS = ("venv/", "node_modules/", ".git/", ".worktrees/")

# A heredoc whose target is a unit file, or anywhere under a systemd directory.
_UNIT_SUFFIXES = (".service", ".timer", ".socket", ".mount", ".path")

_HEREDOC = re.compile(r"""cat\s*>>?\s*(?P<target>\S+)\s*<<-?\s*(?P<q>['"]?)(?P<delim>\w+)(?P=q)\s*$""")

# ${NAME}, ${NAME:-default}, $NAME
_VAR_REF = re.compile(r"\$\{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)[^}]*\}|\$(?P<bare>[A-Za-z_][A-Za-z0-9_]*)")

# `local`/`declare`/`readonly`/`typeset` bind a name just as plainly as a bare
# assignment does. Reading only the bare form reported 10 false positives in
# install-bare-metal.sh, where every unit variable is a function `local`.
_ASSIGNMENT = re.compile(
    r"^\s*(?:export\s+|local\s+|declare\s+(?:-\w+\s+)?|readonly\s+|typeset\s+)?"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)="
)

# Names systemd itself resolves at runtime, which must reach the unit file
# unexpanded. A script wanting one writes it escaped; this list keeps the rule
# from demanding a shell assignment for something the shell must not touch.
_SYSTEMD_RUNTIME_VARS = frozenset({"MAINPID", "TERM", "PATH", "HOME", "USER", "LOGNAME", "SHELL"})


def _shell_scripts() -> list[Path]:
    return sorted(
        p
        for p in _REPO_ROOT.rglob("*.sh")
        if not any(skip in str(p.relative_to(_REPO_ROOT)) for skip in _SKIP_DIRS)
    )


def _unit_heredocs(path: Path):
    """Yield (target, quoted, start_line, body_lines, assigned_before)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    assigned: set[str] = set()
    i = 0
    while i < len(lines):
        assignment = _ASSIGNMENT.match(lines[i])
        if assignment:
            assigned.add(assignment.group("name"))
        match = _HEREDOC.search(lines[i])
        if match:
            target, delim = match.group("target"), match.group("delim")
            body, j = [], i + 1
            while j < len(lines) and lines[j].strip() != delim:
                body.append((j + 1, lines[j]))
                j += 1
            is_unit = target.endswith(_UNIT_SUFFIXES) or "/systemd/" in target
            if is_unit:
                yield target, bool(match.group("q")), i + 1, body, set(assigned)
            i = j
        i += 1


def _scripts_writing_units() -> list[Path]:
    return [p for p in _shell_scripts() if any(_unit_heredocs(p))]


def test_the_scan_finds_the_scripts_it_is_meant_to_guard():
    """An empty scan reads exactly like a clean one.

    If the heredoc pattern ever stops matching — a reformat, a different
    redirect form — every rule below passes over zero blocks and reports
    success.
    """
    found = _scripts_writing_units()
    assert found, "no script writing a systemd unit was found — the scan is broken, not the repo"


@pytest.mark.parametrize("script", _scripts_writing_units(), ids=lambda p: p.name)
def test_a_quoted_unit_heredoc_contains_no_variable_reference(script):
    offenders = [
        f"{script.relative_to(_REPO_ROOT)}:{ln}  {text.strip()}"
        for _target, quoted, _start, body, _assigned in _unit_heredocs(script)
        if quoted
        for ln, text in body
        if "${" in text
    ]
    assert not offenders, "a quoted heredoc does not expand — these land in the unit verbatim:\n" + "\n".join(offenders)


@pytest.mark.parametrize("script", _scripts_writing_units(), ids=lambda p: p.name)
def test_an_unquoted_unit_heredoc_only_uses_variables_the_script_defines(script):
    """Unquoting is the fix; it is also what makes ``$USER`` a live hazard.

    These scripts run under ``sudo``, where ``$USER`` is ``root`` — which is
    how a path meant for the VNC user resolved to ``/home/root``.
    """
    offenders = []
    for _target, quoted, _start, body, assigned in _unit_heredocs(script):
        if quoted:
            continue
        for ln, text in body:
            # an escaped \$ is deliberate and reaches the unit as-is
            for match in _VAR_REF.finditer(re.sub(r"\\\$", "", text)):
                name = match.group("braced") or match.group("bare")
                if name not in assigned and name not in _SYSTEMD_RUNTIME_VARS:
                    offenders.append(f"{script.relative_to(_REPO_ROOT)}:{ln}  ${name} is never assigned in this script")
    assert not offenders, "\n".join(offenders)


@pytest.mark.parametrize("script", _scripts_writing_units(), ids=lambda p: p.name)
def test_a_line_continuation_survives_into_the_unit(script):
    """An unquoted heredoc eats a trailing backslash as a continuation.

    The joined line is still valid to systemd, so nothing breaks loudly — but
    the written file stops matching the script that wrote it, and the next
    person diffing them finds a discrepancy with no cause. It must be ``\\\\``.
    """
    offenders = [
        f"{script.relative_to(_REPO_ROOT)}:{ln}"
        for _target, quoted, _start, body, _assigned in _unit_heredocs(script)
        if not quoted
        for ln, text in body
        if re.search(r"(?<!\\)\\$", text)
    ]
    assert not offenders, "unescaped line continuation inside an unquoted heredoc:\n" + "\n".join(offenders)


def test_the_vnc_units_resolve_to_a_real_user():
    """The reported case, checked by expanding the script the way bash would.

    Static substitution rather than execution: the assignments are read out of
    the script and applied to the heredoc body, so this says what the file
    would contain without running anything from the checkout.
    """
    scripts = [
        _REPO_ROOT / "autobot-infrastructure/shared/scripts/utilities/fix-vnc-desktop.sh",
        _REPO_ROOT / "autobot-infrastructure/shared/scripts/utilities/fix-vnc-wsl.sh",
    ]
    checked = 0
    for script in scripts:
        assert script.is_file(), f"{script} is gone — this test names a file that no longer exists"
        text = script.read_text(encoding="utf-8")
        values = dict(re.findall(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)="?([^"\n]*)"?', text, re.M))

        def substitute(match: re.Match) -> str:
            """``${NAME}`` from the script, else ``${NAME:-default}``'s default.

            The default branch matters: the resolved value is *built* from one
            (``VNC_USER="${AUTOBOT_VNC_USER:-autobot}"``), so ignoring it leaves
            the expansion stuck one level short and the assertion below reports
            an unresolved token that resolves fine at runtime.
            """
            name, default = match.group(1), match.group(2)
            if name in values:
                return values[name]
            return default if default is not None else match.group(0)

        def expand(raw: str) -> str:
            out = raw
            for _ in range(5):  # VNC_HOME references VNC_USER references the default
                new = re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}", substitute, out)
                if new == out:
                    break
                out = new
            return out

        for _target, _quoted, _start, body, _assigned in _unit_heredocs(script):
            for _ln, line in body:
                if line.startswith(("User=", "Group=", "WorkingDirectory=", "Environment=HOME=")):
                    resolved = expand(line)
                    assert "${" not in resolved and "$" not in resolved, f"{script.name}: {line} -> {resolved}"
                    assert resolved.split("=", 1)[1].strip(), f"{script.name}: {line} resolved to an empty value"
                    checked += 1
    assert checked >= 8, f"expected the four directives across both scripts' units, checked {checked}"
