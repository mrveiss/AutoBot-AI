# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A comment must not cite a `path:LINE`; cite the symbol (#15877).

Across 465 guard files -- `repo_tests/`, `.github/workflows/`,
`scripts/check_*.py`, `scripts/lib/*.sh`, and every ansible task file -- 118
comments assert a mechanism that lives elsewhere. Their accuracy depends almost
entirely on **what kind of referent they use**:

===============  =======  =======  =====================================
referent kind    checked  wrong    note
===============  =======  =======  =====================================
path             74       2        one retired file, one prose heading
symbol           30       1        and that one resolved -- see below
line number      ~14      5-6      an order of magnitude worse
===============  =======  =======  =====================================

A line number is the weakest possible referent for a structural reason rather
than a matter of care: **it is invalidated by edits to code it does not
describe.** Insert a line anywhere above and every citation below it is wrong,
having documented nothing incorrectly. And it does not fail loudly -- it fails
*into* whatever now occupies the line, so the reader lands on a blank line, an
`env:` block, or a docstring quote and reads a plausible near-miss. Two audited
citations pointed at the comment introducing the construct: still followable,
and one edit away from not being.

A symbol survives edits and breaks a grep loudly when renamed. A path survives
edits and fails obviously when followed. So: name the thing.

## Why this forbids the form instead of checking the target

Checking that citations resolve was measured and rejected. Of the citations
present, only a handful are mechanically detectable at all -- an unresolvable
file, a line past end of file. The rest point at a real line in a real file
that now says something else, which needs the claim's meaning, not its syntax.
A lint that caught those few would **license** the rest, because the tree would
report clean.

## What the first version of this file got wrong

The scan matched Python comment lines with `stripped.startswith("#") or
\'\"\"\"\' in line`. That second clause matches only the lines *opening or
closing* a docstring -- never a line inside one. It found 8 citations. The
correct scan, which tokenizes comments and takes docstring spans from the AST,
finds 26.

Review (#15896) caught it, and the failure is this file's own subject aimed at
this file: **the population was counted through the instrument's blind spot,
and the cost argument for the rule -- "the form is already rare" -- rested on a
number that measured the filter rather than the tree.** Had it shipped, the
baseline would have frozen at 8 and the ~18 unseen citations would have become
permanently exempt without ever appearing in the list whose job is to record
exemptions.

Note also what `test_the_sweep_reached_the_tree` could NOT do about it: it
counts *files reached*, which was 465 either way. A non-vacuity check built for
the glob says nothing about the filter.

## What this guard cannot do

It checks referent *shape*, never referent *truth*. The audit's most
consequential finding was a comment whose symbol referent resolved perfectly --
`scripts/lib/git-root.sh` citing `autobot_shared.paths.AMBIENT_GIT_VARS` --
while the invariant it asserted was false, the lists having diverged by two
variables. No shape check reaches that; it needed the claim turned into a test,
which is `ambient_git_vars_mirror_test.py`.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]

_SCOPES = (
    "repo_tests/**/*.py",
    ".github/workflows/*.yml",
    "scripts/check_*.py",
    "scripts/lib/*.sh",
    "autobot-slm-backend/ansible/roles/**/tasks/*.yml",
)

_CITE = re.compile(r"([A-Za-z0-9_./-]+\.(?:py|yml|yaml|sh|j2|ts|vue|md)):(\d+)")

#: This file's own baseline literal is data, not commentary -- excluded by path
#: so the guard does not count its own exemption list as 26 fresh violations.
_SELF = "repo_tests/comment_line_number_citations_test.py"

#: `(citing file, cited target)` for every citation predating this rule. Keyed on
#: the CITED TARGET, never on the citing line number -- keying a baseline about
#: stale line numbers to a line number would rot exactly the same way.
#: This list may shrink. It must never grow.
_BASELINE = frozenset(
    {
        (".github/workflows/phase_validation.yml", "network_constants.py:34"),
        ("autobot-slm-backend/ansible/roles/_shared/tasks/clean_wrong_node_dir.yml", "lib/ansible/plugins/action/set_fact.py:54"),
        ("autobot-slm-backend/ansible/roles/slm_manager/tasks/service_units.yml", "bind_self_update_socket.yml:32"),
        ("autobot-slm-backend/ansible/roles/slm_manager/tasks/service_units.yml", "main.yml:673"),
        ("repo_tests/bare_default_route_dependency_guard_test.py", "api/knowledge.py:2035"),
        ("repo_tests/bare_default_route_dependency_guard_test.py", "repo_tests/with_error_handling_single_definition_test.py:134"),
        ("repo_tests/credential_vault_resolution_guard_test.py", "initialization/lifespan.py:1353"),
        ("repo_tests/deployment_script_imports_resolve_test.py", "test_startup_coordinator.sh:15"),
        ("repo_tests/first_party_symbols_bound_test.py", "api/heartbeat.py:38"),
        ("repo_tests/first_party_symbols_bound_test.py", "autobot-backend/models/settings.py:24"),
        ("repo_tests/fixture_fixed_path_teardown_guard_test.py", "api/codebase_analytics/endpoints/report_scoping_test.py:384"),
        ("repo_tests/fixture_fixed_path_teardown_guard_test.py", "services/knowledge/code_graph_provenance_test.py:95"),
        ("repo_tests/frontend_duplicate_typecheck_compile_guard_test.py", "frontend-test.yml:132"),
        ("repo_tests/sdk_response_model_contract_test.py", "api/agent_config.py:1024"),
        ("repo_tests/severity_literal_shape_guard_test.py", "autobot-backend/security/command_patterns.py:78"),
        ("repo_tests/severity_literal_shape_guard_test.py", "autobot_shared/delta_engine.py:120"),
        ("repo_tests/severity_literal_shape_guard_test.py", "autobot_shared/env_drift_detector.py:55"),
        ("repo_tests/slm_self_update_socket_activation_order_test.py", "main.yml:673"),
        ("repo_tests/test_ci_import_smoke_paths_14252.py", "verify-generated-types.yml:216"),
        ("repo_tests/test_module_path_anchors_15181_test.py", "autobot-backend/tests/unit/test_agents_status_pg_optional.py:54"),
        ("repo_tests/test_module_path_anchors_15181_test.py", "scripts/test_first_remediation.py:32"),
        ("repo_tests/test_module_path_anchors_15181_test.py", "test_agents_status_pg_optional.py:54"),
        ("repo_tests/transformers_resume_download_guard_test.py", "llm_shared/optimization/hf_quantizer.py:97"),
        ("repo_tests/unprefixed_placeholder_string_test.py", "autobot-backend/api/codebase_analytics/config_duplication_detector.py:510"),
        ("repo_tests/with_error_handling_single_definition_test.py", "repo_tests/lint/canonical/test_context.py:76"),
        ("repo_tests/with_error_handling_single_definition_test.py", "scripts/check_ansible_file_references_test.py:40"),
    }
)

#: The "must never grow" above is a comment, and this file's whole thesis is
#: that a comment cannot fail. So it is also an assertion. Raising this number
#: is the deliberate act; doing it silently is what the rule prevents.
_MAX_BASELINE = 26

#: Pinned to the current count. This population only grows with normal work, so
#: the floor is tripped by deletion or by a narrowed glob -- both of which should
#: cost a deliberate line. A loose floor would let a third of the tree fall out
#: of scope while the rule below reported it clean.
_MIN_FILES = 465


def _eligible_lines(path: Path) -> set[int]:
    """Line numbers carrying prose: `#` comments, and every line inside a docstring.

    Docstring spans come from the AST rather than from matching quote characters.
    A line *inside* a triple-quoted string contains no quotes at all, which is
    how the first version of this guard missed 18 of its own population.
    """
    if path.suffix != ".py":
        return {
            number
            for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1)
            if line.strip().startswith("#")
        }

    lines: set[int] = set()
    try:
        with io.open(path, "rb") as handle:
            for token in tokenize.tokenize(handle.readline):
                if token.type == tokenize.COMMENT:
                    lines.add(token.start[0])
    except (tokenize.TokenError, SyntaxError, UnicodeDecodeError):
        pass  # a file this cannot tokenize is another guard's problem

    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return lines

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body or not isinstance(body[0], ast.Expr):
            continue
        doc = body[0].value
        if isinstance(doc, ast.Constant) and isinstance(doc.value, str):
            lines.update(range(doc.lineno, (doc.end_lineno or doc.lineno) + 1))
    return lines


def _scan():
    """Yield `(relative path, line number, citation)` for prose-borne citations."""
    files = 0
    for pattern in _SCOPES:
        for path in sorted(_ROOT.glob(pattern)):
            if not path.is_file():
                continue
            files += 1
            rel = path.relative_to(_ROOT).as_posix()
            if rel == _SELF:
                continue
            eligible = _eligible_lines(path)
            for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if number not in eligible:
                    continue
                for match in _CITE.finditer(line):
                    yield rel, number, match.group(0)
    _scan.files = files


def test_the_sweep_reached_the_tree() -> None:
    """Positive assertion first — an empty glob reports a clean repo."""
    list(_scan())
    assert _scan.files >= _MIN_FILES, (
        f"swept only {_scan.files} files (floor {_MIN_FILES}) — the globs matched almost nothing, "
        "so the rule below would pass by reading an empty tree"
    )


def test_the_scan_can_see_inside_docstrings() -> None:
    """The check the first version needed and did not have.

    `test_the_sweep_reached_the_tree` counts *files*, and the broken filter
    reached every file — it simply could not read most of their prose. So reach
    has to be asserted over what is actually consumed.

    The first attempt at this test asserted that lines inside THIS module's
    docstring were eligible — and passed against the broken filter, because this
    docstring quotes the triple-quote character while describing the bug. The
    test for a blind spot was satisfiable by the text explaining the blind spot.

    So it now asserts the capability over real data: at least one citation must
    be found on a line that is neither a `#` comment nor a line bearing a
    triple-quote. Only a scan that understands docstring *spans* can produce one.
    """
    deep = [
        (rel, number, cite)
        for rel, number, cite in _scan()
        if rel.endswith(".py")
        and not (line := (_ROOT / rel).read_text(encoding="utf-8", errors="replace").splitlines()[number - 1]).strip().startswith("#")
        and '"""' not in line
    ]
    assert deep, (
        "every citation found sits on a `#` line or a line carrying a triple-quote, "
        "which is exactly what a quote-matching filter can see. The scan is not "
        "reading docstring bodies, and will miss the majority of the population "
        "(8 of 26 were visible to the broken filter)."
    )


def test_the_baseline_has_not_grown() -> None:
    """The 'must never grow' comment, given a way to fail."""
    assert len(_BASELINE) <= _MAX_BASELINE, (
        f"the baseline holds {len(_BASELINE)} entries against a cap of {_MAX_BASELINE}. "
        "It may shrink; growing it means new line-number citations were exempted "
        "rather than fixed."
    )


def test_the_baseline_still_describes_real_citations() -> None:
    """A baseline entry whose citation is gone must be deleted, not carried."""
    live = {(rel, cite) for rel, _, cite in _scan()}
    vanished = sorted(_BASELINE - live)
    assert not vanished, "these baseline entries no longer exist — remove them:\n" + "\n".join(
        f"  {f} -> {c}" for f, c in vanished
    )


def test_no_new_comment_cites_a_line_number() -> None:
    """The rule. Name the symbol; a line number is invalidated by unrelated edits."""
    new = sorted({(rel, number, cite) for rel, number, cite in _scan() if (rel, cite) not in _BASELINE})
    assert not new, "\n".join(
        [
            "a comment cites a line number, the referent kind that goes wrong an order "
            "of magnitude more often than a symbol (#15877):",
            *(f"  {rel}:{number} cites {cite}" for rel, number, cite in new),
            "",
            "Cite the symbol, the function, or the step NAME instead. A line number is "
            "invalidated by edits to code it does not describe, and fails silently INTO "
            "whatever now occupies the line rather than failing loudly.",
        ]
    )
