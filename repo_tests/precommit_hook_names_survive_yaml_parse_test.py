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

import ast
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


def test_every_gated_hook_id_resolves_to_an_untruncated_name() -> None:
    """The pairing with #14921's gate, verified rather than assumed.

    ``pipeline-scripts/check_gating_precommit_hooks.py`` resolves each id in
    ``GATING_HOOK_IDS`` to a name and then looks for that exact name in
    pre-commit's transcript. If the name loses text to a YAML comment the gate
    searches for a string the log never contains, finds no result line, and — in
    the shape this whole cluster is about — a gate that matched nothing is a
    gate that reported nothing.

    Today's single gated hook, ``ssot-config-lib-guard``, was never affected:
    its ``#`` is preceded directly by ``(``, which is not a comment start. That
    is luck, not design, and it is exactly the sort of thing that stops being
    true when the second id is appended. Asserted here so the next append
    cannot silently pick a truncated name.

    ``GATING_HOOK_IDS`` is read out of the source with the AST rather than
    imported: importing the module for one tuple would install it in
    ``sys.modules`` for the rest of the session, which this repository has been
    bitten by before.
    """
    consumer = _REPO_ROOT / "pipeline-scripts" / "check_gating_precommit_hooks.py"
    assert consumer.is_file(), f"{consumer.name} is gone — #14921's gate has no subject"
    tree = ast.parse(consumer.read_text(encoding="utf-8"))
    gated: tuple[str, ...] = ()
    for node in ast.walk(tree):
        targets = [node.target] if isinstance(node, ast.AnnAssign) else getattr(node, "targets", [])
        if any(isinstance(name, ast.Name) and name.id == "GATING_HOOK_IDS" for name in targets):
            gated = tuple(ast.literal_eval(node.value))
    assert gated, (
        "GATING_HOOK_IDS could not be read from "
        f"{consumer.name} — the constant was renamed or restructured, and this "
        "check would otherwise verify an empty set and pass"
    )

    text = _CONFIG.read_text(encoding="utf-8")
    document = yaml.safe_load(text) or {}
    resolved = {
        hook["id"]: str(hook.get("name") or hook["id"])
        for repo in document.get("repos", [])
        for hook in repo.get("hooks", [])
        if "id" in hook
    }
    missing = [hook_id for hook_id in gated if hook_id not in resolved]
    assert not missing, (
        f"these gated hook ids are not in .pre-commit-config.yaml: {missing}. "
        "#14921's gate fails closed on this, but it should never get the chance"
    )
    # `resolved` holds the PARSED name — the string pre-commit will print and
    # the gate will look for. A truncation finding reports (line, written,
    # parsed), so the comparison has to be against its parsed element. Matching
    # the written one instead is a check that can never fire, and a first
    # attempt at this test did exactly that: it passed while a deliberately
    # truncated hook sat in GATING_HOOK_IDS.
    losses = {parsed: written for _, written, parsed in truncated_names(text)}
    truncated = {
        hook_id: (losses[resolved[hook_id]], resolved[hook_id])
        for hook_id in gated
        if resolved[hook_id] in losses
    }
    assert not truncated, (
        "a gated hook's printed name is not the name that was written "
        f"(written, printed): {truncated}. #14921's gate matches on the printed "
        "form, so it would search the transcript for a string that is never "
        "there — and a gate that matches nothing reports nothing (#14923)"
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
