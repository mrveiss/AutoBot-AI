# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Structural assertions about WHERE redaction happens (#17667, #17673).

Split out of ``kb_content_redaction_chokepoint_guard_test.py`` when that file
reached the 600-line ceiling. Not a test module -- the leading underscore keeps it
out of collection, the way ``_paths.py`` and ``_analytics_metadata_detect.py`` are
helpers rather than suites.

Every function here answers a question a substring cannot: *before*, *in place*,
*through the caller's dict*. Those words are about structure; ``in source`` is about
presence, which is why both assertions that used to live here as text matches could
pass on the regression they named and fail on a refactor that strengthened it.
"""

from __future__ import annotations

import ast


def _callee_name(node: ast.AST) -> str | None:
    """The called name, whether the call is bare or attribute-style."""
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return None


#: The declared entry points that redact. `sanitize_fact_content` runs the injection
#: pass and then `redact_content` (see `sanitize_fact_content` in
#: `knowledge/ingest_sanitize.py`), so either
#: satisfies the property below. This stays a list because "does this call redact?"
#: cannot be answered without following the callee across files -- but it is a list of
#: *primitives*, not of call sites, so it grows only when a third way to redact is
#: introduced, and the assertion below is about position rather than spelling.
#:
#: This list is safe ONLY while the assertion around it stays positional. Strip the
#: before-the-loop check and keep the list, and the guard silently becomes a
#: membership test -- "is one of these two names mentioned" -- which is the shape it
#: was rewritten to escape (#15826). The list answers a narrow sub-question; it is
#: not the claim.
REDACTING_CALLS = frozenset({"redact_content", "sanitize_fact_content"})


def redacts_input_data_before_the_extract_loop(source: str) -> tuple[bool, str]:
    """Whether `_run_extract_stage` reassigns `input_data` from a redacting call,
    positioned before the loop over extract tasks.

    Returns (ok, why-not).
    """
    fn = next(
        (
            n
            for n in ast.walk(ast.parse(source))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_run_extract_stage"
        ),
        None,
    )
    if fn is None:
        return False, "_run_extract_stage no longer exists in runner.py -- re-derive this guard"

    loops = [n.lineno for n in ast.walk(fn) if isinstance(n, (ast.For, ast.AsyncFor))]
    if not loops:
        return False, "_run_extract_stage has no task loop -- the shape this guard assumes is gone"
    first_loop = min(loops)

    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        callee = _callee_name(node.value.func)
        if callee not in REDACTING_CALLS:
            continue
        targets = [t for tgt in node.targets for t in (tgt.elts if isinstance(tgt, ast.Tuple) else [tgt])]
        if not any(isinstance(t, ast.Name) and t.id == "input_data" for t in targets):
            continue
        if node.lineno < first_loop:
            return True, ""
        return False, (
            f"the redacting call is at line {node.lineno}, AFTER the extract task loop at "
            f"line {first_loop} -- chunks built in that loop would carry unredacted text"
        )
    return False, (f"no call to any of {sorted(REDACTING_CALLS)} reassigns input_data in _run_extract_stage")


#: #17673: this property used to be asserted by substring --
#: `'target_version["content"] = redact_content(target_version["content"])' in source`.
#: Same defect as the runner-path assertion replaced in #17667: a claim about
#: structure enforced by presence. It held whether the mutation ran first, last or
#: not at all, and would have failed on an equivalent rewrite that kept the property.
#:
#: The property here is NOT the runner's. That one is positional within one function
#: (redact before the extract loop). This one is **aliasing**: `_apply_version_to_fact`
#: receives `target_version` from its caller and must write the redacted value back
#: through a subscript on that dict, because `revert_to_version` reads the same dict
#: again afterwards to record the revert. A local-only redaction satisfies every
#: reasonable reading of "it redacts" and leaves the second write raw -- the exact
#: regression #13708's review found.
#:
#: Hence two assertions rather than a mirror of the runner's one: the write goes
#: through the caller's dict, AND the apply call precedes the record call.


def redacts_target_version_in_place(source: str) -> tuple[bool, str]:
    """Whether `_apply_version_to_fact` assigns a redacting call's result back into
    `target_version["content"]` rather than into a local. Returns (ok, why-not).
    """
    fn = next(
        (
            n
            for n in ast.walk(ast.parse(source))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "_apply_version_to_fact"
        ),
        None,
    )
    if fn is None:
        return False, "_apply_version_to_fact no longer exists in versioning.py -- re-derive this guard"

    local_only: list[str] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        if _callee_name(node.value.func) not in REDACTING_CALLS:
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id == "target_version"
                and isinstance(target.slice, ast.Constant)
                and target.slice.value == "content"
            ):
                return True, ""
            if isinstance(target, ast.Name):
                local_only.append(target.id)

    if local_only:
        return False, (
            f"the redacted value is assigned to the local name(s) {sorted(set(local_only))} instead of "
            'back into target_version["content"], so the caller\'s dict still holds the raw value'
        )
    return False, f'no call to any of {sorted(REDACTING_CALLS)} writes target_version["content"]'


def applies_the_version_before_recording_it(source: str) -> tuple[bool, str]:
    """Whether `revert_to_version` calls `_apply_version_to_fact` before `create_version`.

    The in-place write only helps if it happens before the read. Swapping the two
    calls leaves the property textually present and defeated.
    """
    fn = next(
        (
            n
            for n in ast.walk(ast.parse(source))
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "revert_to_version"
        ),
        None,
    )
    if fn is None:
        return False, "revert_to_version no longer exists in versioning.py -- re-derive this guard"

    calls = [(c.lineno, _callee_name(c.func)) for c in ast.walk(fn) if isinstance(c, ast.Call)]
    applies = [ln for ln, name in calls if name == "_apply_version_to_fact"]
    records = [ln for ln, name in calls if name == "create_version"]
    if not applies:
        return False, "revert_to_version no longer calls _apply_version_to_fact at all"
    if not records:
        return False, "revert_to_version no longer calls create_version -- re-derive this guard"
    if min(applies) < min(records):
        return True, ""
    return False, (
        f"_apply_version_to_fact is called at line {min(applies)}, AFTER create_version at "
        f"line {min(records)} -- the version is recorded before it is redacted"
    )
