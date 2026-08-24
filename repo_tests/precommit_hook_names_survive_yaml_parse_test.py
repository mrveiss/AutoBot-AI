# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A hook's name must parse to the string that was written (#14923).

``name: Function Length Check (Issue #620)`` is valid YAML for the string
``Function Length Check (Issue`` — an unquoted scalar ends where a space-``#``
opens a comment, so the issue reference the name exists to carry is discarded
before pre-commit ever sees it. 23 of this repository's 52 hook names were
losing text this way, and nothing warned: the file is well-formed, pre-commit
is behaving correctly, and the log simply prints a shorter name.

It is not cosmetic. The printed name is an identifier:
``pipeline-scripts/check_gating_precommit_hooks.py`` (#14878) resolves
``id -> name`` through ``yaml.safe_load`` precisely so it reproduces whatever
pre-commit will print, and #14181 / #14202 both match on the transcript. A
truncated name is a name a gate can fail to match, and an unmatched gate reads
exactly like a clean one.

The check has three independent halves, because each can pass while the others
are broken:

* **the property** — every ``name`` scalar parses to the text written after
  ``name:`` on its line. Compared against the *source line*, not against the
  parsed node: PyYAML's own end-mark for a plain scalar already stops at the
  comment, so a guard that compares a node with itself agrees with its own
  blind spot and always passes.
* **the floor** — the population is derived from the file (every repo block,
  local and remote), and asserted at the number actually there. A sweep that
  silently stops matching finds no offenders and reads exactly like a clean
  tree, so "0 problems out of 0 names" must fail by name.
* **the self-test** — the detector is fed a config it *must* reject. A checker
  that has stopped detecting reports a false PASS forever otherwise.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_REPO_ROOT = Path(__file__).resolve().parents[1]
_CONFIG = _REPO_ROOT / ".pre-commit-config.yaml"

# Measured on the branch that fixed #14923. Floors, not equalities: hooks get
# added. They exist so a matcher that has quietly stopped matching fails here
# instead of reporting a clean tree.
_MIN_HOOKS_WITH_A_NAME = 52
_MIN_NAMES_CARRYING_AN_ISSUE_REF = 30
# Names written with a *space* before the ``#`` — the exact spelling YAML
# destroys. If this ever reaches zero the property above is vacuous and the
# guard is guarding nothing, so it is asserted rather than assumed.
_MIN_NAMES_WITH_A_SPACE_HASH = 20

_NAME_LINE = re.compile(r"^\s*(?:-\s+)?name:[ \t]+(?P<scalar>\S.*?)[ \t]*$")


def _as_written(line: str) -> str | None:
    """The scalar text on a ``name:`` line, with any YAML quoting removed.

    This is "what the author typed", which is the thing the parsed value has to
    agree with. Returns None for a line that does not declare a name.
    """
    match = _NAME_LINE.match(line.rstrip("\r\n"))
    if match is None:
        return None
    scalar = match.group("scalar")
    if len(scalar) >= 2 and scalar[0] == scalar[-1] and scalar[0] in "'\"":
        body = scalar[1:-1]
        return body.replace("''", "'") if scalar[0] == "'" else body
    return scalar


def truncated_names(config_text: str) -> list[tuple[int, str, str]]:
    """Every ``name`` whose parsed value is not the text that was written.

    Extracted as a plain function over text so it can be mutated and driven
    with a synthetic config — a detector that is only ever pointed at a clean
    file cannot be distinguished from one that has stopped detecting.

    Returns ``(line number, as written, as parsed)`` triples.
    """
    problems: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(config_text.splitlines(), 1):
        written = _as_written(line)
        if written is None:
            continue
        scalar = line.split("name:", 1)[1].strip()
        parsed = yaml.safe_load(f"name: {scalar}")["name"]
        if str(parsed) != written:
            problems.append((lineno, written, str(parsed)))
    return problems


def _configured_names(config_text: str) -> list[str]:
    """Every hook name in the file, across every repo block, local or remote."""
    document = yaml.safe_load(config_text) or {}
    return [
        str(hook["name"])
        for repo in document.get("repos", [])
        for hook in repo.get("hooks", [])
        if hook.get("name") is not None
    ]


def test_the_config_exists_and_declares_the_hooks_this_guards() -> None:
    """Presence floor: an unreadable or shrunken config makes the rest vacuous."""
    assert _CONFIG.is_file(), ".pre-commit-config.yaml is gone — no subject"
    text = _CONFIG.read_text(encoding="utf-8")
    names = _configured_names(text)
    assert len(names) >= _MIN_HOOKS_WITH_A_NAME, (
        f"only {len(names)} hooks declare a name (expected at least "
        f"{_MIN_HOOKS_WITH_A_NAME}) — the population shrank or the sweep stopped matching"
    )
    with_ref = [name for name in names if "#" in name]
    assert len(with_ref) >= _MIN_NAMES_CARRYING_AN_ISSUE_REF, (
        f"only {len(with_ref)} hook names carry a '#' issue reference"
    )
    space_hash = [name for name in names if re.search(r"\s#", name)]
    assert len(space_hash) >= _MIN_NAMES_WITH_A_SPACE_HASH, (
        f"only {len(space_hash)} hook names contain a space-'#' — the exact spelling "
        "YAML truncates. Below this the property tested here has no live subject."
    )


def test_every_hook_name_parses_to_the_string_that_was_written() -> None:
    """#14923's acceptance criterion, checked by parsing rather than reading."""
    problems = truncated_names(_CONFIG.read_text(encoding="utf-8"))
    detail = "\n".join(
        f"  line {lineno}: written {written!r} -> parsed {parsed!r}"
        for lineno, written, parsed in problems
    )
    assert not problems, (
        f"{len(problems)} hook name(s) lose text to a YAML comment:\n{detail}\n"
        "An unquoted scalar ends at a space-'#'. Quote the value (single quotes "
        "keep '#' literal), or move the comment onto its own line."
    )


def test_the_detector_rejects_a_config_that_loses_a_name_to_a_comment() -> None:
    """Self-test. Without it, a detector that matches nothing passes forever.

    The offending spelling is assembled from fragments rather than written out,
    so this file does not trip the very pattern it exists to ban.
    """
    hash_ref = "#" + "14923"
    good = f"Guarded Thing ({hash_ref})"
    bad = f"Guarded Thing {hash_ref}"
    synthetic = "\n".join(
        (
            "repos:",
            "  - repo: local",
            "    hooks:",
            "      - id: guarded",
            f"        name: {bad}",
            "        entry: true",
            "        language: system",
        )
    )
    problems = truncated_names(synthetic)
    assert len(problems) == 1, f"the detector missed the planted truncation: {problems}"
    assert problems[0][1] == bad and problems[0][2] == "Guarded Thing", problems
    # `(#` is not a comment start, so the safe spelling must NOT be flagged —
    # a detector that flags everything is as useless as one that flags nothing.
    assert not truncated_names(synthetic.replace(bad, good)), (
        f"{good!r} is valid YAML for itself and must not be reported"
    )
    assert not truncated_names(synthetic.replace(bad, f"'{bad}'")), (
        "a quoted name keeps its text and must not be reported"
    )


def test_no_two_hooks_print_the_same_name() -> None:
    """Two names differing only after a '#' used to collapse to one string.

    That is what made truncation dangerous rather than untidy: a consumer
    matching the transcript cannot tell the two hooks apart, and #14878's gate
    would attribute one hook's verdict to the other.
    """
    names = _configured_names(_CONFIG.read_text(encoding="utf-8"))
    duplicates = sorted({name for name in names if names.count(name) > 1})
    assert not duplicates, f"hook names are not unique: {duplicates}"
