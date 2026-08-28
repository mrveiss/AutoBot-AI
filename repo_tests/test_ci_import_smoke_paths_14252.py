# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every module a CI step imports by name must exist in the tree (#14252).

`deployment-check` asked whether the application's core imports resolve, using a
module path that had never existed. It raised ModuleNotFoundError on every run
for months. Nothing could tell: the only thing asserting that string was the job
it broke, and the job is not a required context, so its redness was permanent
background rather than a signal.

A check that cannot pass is indistinguishable from a check that is not there.
"""

from __future__ import annotations

import ast
import re
import sys
import textwrap
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOWS = _REPO_ROOT / ".github" / "workflows"

# `python3 -c '...'` / `python -c "..."` inline programs in workflow steps.
#
# `(?:\\.|(?!\1).)*` rather than `.+?`: a lazy match closes on the first quote
# of the same kind, including a backslash-escaped one, so
# `python -c "import json; print(f\"{x}\")"` was captured truncated. The
# fragment then failed to parse and its imports were checked against nothing.
#
# That alternation IS present and the capture IS complete -- stated flatly
# because the previous wording read as a live defect and produced two
# independent mis-diagnoses (#15152). If a program below looks truncated, check
# `_unescape_shell` and the `code[:60]` slice in the failure message before
# suspecting this pattern. `test_no_python_dash_c_invocation_escapes_the_extractor`
# keeps the alternation honest as more workflows are written.
_INLINE_PYTHON = re.compile(
    r"""python3?\s+-c\s+(?P<quote>['"])(?P<code>(?:\\.|(?!(?P=quote)).)*)(?P=quote)""",
    re.DOTALL,
)

# Every place a workflow starts an inline program, quoting ignored. Used to prove
# `_INLINE_PYTHON` captured one program per invocation: a form it cannot close on
# (an unbalanced quote, a `'"'"'` splice) yields no match at all, and a program
# the scan never sees is a program whose imports are checked against nothing --
# silently, which is the one outcome this file exists to make impossible.
_INLINE_PYTHON_INVOCATION = re.compile(r"python3?\s+-c\s")

# What may legally follow a complete shell argument. A capture that stopped early
# on an embedded quote ends mid-argument, so the next character is none of these.
_ARGUMENT_END = re.compile(r"[\s;|&>)]|\Z")

# Heredoc form: `python - <<'PY' ... PY`. A separate shape entirely, and one the
# quote-matching pattern above cannot see at all.
_HEREDOC_PYTHON = re.compile(
    r"""python3?\s+-\s*<<-?\s*['"]?(?P<tag>[A-Za-z_][A-Za-z0-9_]*)['"]?\n(?P<code>.*?)\n\s*(?P=tag)\b""",
    re.DOTALL,
)

# Roots the workflows put on PYTHONPATH for those inline programs.
#
# Applied uniformly, not per-step: a step whose own PYTHONPATH omits
# `autobot-backend` is still checked against it. That is deliberate (tracking the
# real PYTHONPATH per step would mean interpreting shell), but it has one known
# failure direction. `autobot-backend/mcp/` is a first-party package AND `mcp` is
# a pip distribution; a future step importing `mcp.<submodule>` that exists in
# the installed package but not in the repo's own would be reported missing here.
# Nothing does that today. If this test ever fails on a name that is genuinely a
# third-party package, that is the case — add it to the list below rather than
# widening the roots.
_IMPORT_ROOTS = ("autobot-backend", "autobot_shared", ".")

# Third-party and stdlib names are resolved by the installed environment, not the
# tree, so only first-party roots are checked. A name is first-party if its top
# level exists as a module or package under one of the roots above.
_STDLIB_OR_THIRD_PARTY_PREFIXES = ("os", "sys", "json", "pathlib", "subprocess")


def _normalise(code: str) -> str:
    """Strip the YAML block indentation a multi-line `-c` argument carries.

    A program written across several lines inside a workflow step arrives with
    the step's indentation on every line, so `ast.parse` raises IndentationError
    — a SyntaxError subclass, indistinguishable from "not python" to a bare
    except. `verify-generated-types.yml:216` is exactly this.
    """
    return textwrap.dedent(code.strip("\n") + "\n")


def _unescape_shell(code: str, quote: str) -> str:
    """Undo the backslash escaping a DOUBLE-quoted shell argument requires.

    `\\"` reaches python as `"`. Left in place, every such program is a syntax
    error and its imports go unchecked.

    Single-quoted arguments get none of this. `sh` performs no expansion or
    escape processing at all inside `'...'`, so a backslash there reaches python
    as a backslash. Unescaping one anyway rewrites the program into something the
    step never runs -- and rewrites it in the dangerous direction: on Python 3.12
    `f"{d.get(\\"k\\")}"` becomes the legal `f"{d.get("k")}"`, so the guard reports a
    clean parse for a step that dies with SyntaxError on every run. Fidelity to
    what the shell actually hands the interpreter is the whole basis of the check.
    """
    if quote != '"':
        return code
    return code.replace('\\"', '"').replace("\\$", "$").replace("\\`", "`")


def _inline_programs() -> list[tuple[str, str]]:
    found = []
    for workflow in sorted(_WORKFLOWS.glob("*.yml")):
        text = workflow.read_text(encoding="utf-8")
        for match in _INLINE_PYTHON.finditer(text):
            code = _unescape_shell(match.group("code"), match.group("quote"))
            found.append((workflow.name, _normalise(code)))
        for match in _HEREDOC_PYTHON.finditer(text):
            found.append((workflow.name, _normalise(match.group("code"))))
    return found


def _uncaptured_invocations() -> list[tuple[str, int, str]]:
    """Every `python -c` the extractor could not capture as one whole argument.

    Two ways a program goes missing without anyone noticing: `_INLINE_PYTHON`
    fails to match the invocation at all, or it matches but closes early, leaving
    the capture ending mid-argument. Both hand back less than the step runs.
    """
    escaped = []
    for workflow in sorted(_WORKFLOWS.glob("*.yml")):
        text = workflow.read_text(encoding="utf-8")
        for site in _INLINE_PYTHON_INVOCATION.finditer(text):
            line = text.count("\n", 0, site.start()) + 1
            match = _INLINE_PYTHON.match(text, site.start())
            if match is None:
                escaped.append((workflow.name, line, "no closing quote the extractor could find"))
            elif not _ARGUMENT_END.match(text, match.end()):
                escaped.append((workflow.name, line, f"capture ends mid-argument at {text[match.end()]!r}"))
    return escaped


def _parses(code: str) -> bool:
    try:
        ast.parse(code)
    except SyntaxError:
        return False
    return True


def _imported_names(code: str) -> list[str]:
    """Imports in `code`. Raises SyntaxError rather than reporting none.

    Returning [] on unparseable input is how a guard reports clean on something
    it could not read -- the same failure this whole file exists to catch, one
    layer earlier, at extraction instead of classification. A caller that gets []
    cannot tell "this program imports nothing" from "I could not read this
    program", and the import assertion below passes vacuously either way. Letting
    the SyntaxError out makes the second case fail, loudly, at the call site.
    """
    tree = ast.parse(code)
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
        elif isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
    return names


def _resolves_in_tree(dotted: str) -> bool:
    relative = Path(*dotted.split("."))
    for root in _IMPORT_ROOTS:
        base = _REPO_ROOT / root
        if (base / relative).with_suffix(".py").is_file():
            return True
        if (base / relative / "__init__.py").is_file():
            return True
    return False


def _is_first_party(dotted: str) -> bool:
    """True when the TOP level of the name exists in the tree.

    Keyed on the top level, not the full path: `security.secure_command_executor`
    must count as first-party (so its absence is a failure) precisely because
    `security/` is a real package here. Keying on the full path would classify
    every wrong path as third-party and pass.
    """
    top = dotted.split(".")[0]
    if top in _STDLIB_OR_THIRD_PARTY_PREFIXES:
        return False
    return _resolves_in_tree(top)


def test_the_scan_actually_found_inline_programs():
    """An empty scan would make the assertion below vacuous."""
    programs = _inline_programs()

    assert len(programs) >= 2, f"only {len(programs)} inline python programs found"


@pytest.mark.parametrize("workflow,code", _inline_programs())
def test_every_first_party_import_in_a_workflow_step_resolves(workflow, code):
    missing = [
        name
        for name in _imported_names(code)
        if _is_first_party(name) and not _resolves_in_tree(name)
    ]

    assert missing == [], (
        f"{workflow}: imports a module path that does not exist in the tree: {missing}. "
        "The step will raise ModuleNotFoundError on every run."
    )


def test_the_path_that_was_wrong_would_now_be_caught():
    """The reproduction, as a direct assertion on the classifier.

    `security` is a real package, so the top-level check calls this first-party;
    the full path does not resolve, so it is reported.
    """
    assert _is_first_party("security.secure_command_executor")
    assert not _resolves_in_tree("security.secure_command_executor")


def test_the_corrected_path_resolves():
    assert _resolves_in_tree("secure_command_executor")
    assert _resolves_in_tree("security_layer")
    assert _resolves_in_tree("app_factory")


def test_every_extracted_program_parses():
    """A program the extractor mangles is checked against nothing.

    Failing loudly here is the point: the guard must be able to say "I could not
    read this", which is different from "this is fine".

    Read the version in the message before concluding anything about the base.
    Whether a program parses is NOT environment-independent: PEP 701 made an
    f-string reusing its own quote type inside the expression legal from 3.12,
    so the same extracted text is a SyntaxError on 3.10/3.11 and fine on
    3.12/3.14. A failure here that reproduces on one checkout and not another is
    an interpreter difference until proven otherwise (#15152; #15091 records the
    same trap in the opposite direction).
    """
    unparseable = [
        (workflow, code[:60]) for workflow, code in _inline_programs() if not _parses(code)
    ]

    assert unparseable == [], (
        f"inline python that the extractor could not parse under python "
        f"{sys.version_info.major}.{sys.version_info.minor} — its imports are "
        f"checked against nothing: {unparseable}. Whether a program parses is "
        "version-dependent (PEP 701); confirm on the version CI runs before "
        "calling this a base failure."
    )


def test_no_python_dash_c_invocation_escapes_the_extractor():
    """Every inline program must be captured, whole, or the scan is short a program.

    The parse assertion below only speaks for programs the extractor handed back.
    A program it never captured, or captured a prefix of, is not in that list at
    all -- so the parse check reports clean and the import check has nothing to
    look at. Silence is the failure mode; this is the assertion that ends it.
    """
    escaped = _uncaptured_invocations()

    assert escaped == [], (
        "`python -c` invocations the extractor did not capture as one whole "
        f"argument -- their imports are checked against nothing: {escaped}"
    )


def test_phase_validation_inline_programs_are_actually_checked():
    """#15122: the step whose program the guard reported clean while reading none.

    Named rather than generic: the fix must leave this program parseable AND
    yielding imports, so it cannot be "made green" by rendering it invisible to
    the extractor.
    """
    programs = [code for name, code in _inline_programs() if name == "phase_validation.yml"]

    assert programs, "phase_validation.yml inline programs vanished from the scan"
    for code in programs:
        assert _imported_names(code), f"no imports extracted from: {code!r}"


def test_a_single_quoted_program_keeps_its_backslashes():
    """`sh` does no escape processing inside `'...'`, so neither may the extractor.

    Unescaping one anyway is the false-green direction: on Python 3.12 the
    rewritten form parses while the program the step actually runs does not.
    """
    literal = r'print(f"{d.get(\"k\")}")'

    assert _unescape_shell(literal, "'") == literal
    assert _unescape_shell(literal, '"') == 'print(f"{d.get("k")}")'


def test_an_unreadable_program_raises_rather_than_reporting_no_imports():
    """`_imported_names` must not answer "nothing imported" for "could not read"."""
    with pytest.raises(SyntaxError):
        _imported_names("import json; print(f\"{d.get(\\\"k\\\")}\")\n")
