# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A comment must not cite a `path:LINE`; cite the symbol (#15877).

Measured across 464 guard files -- `repo_tests/`, `.github/workflows/`,
`scripts/check_*.py`, `scripts/lib/*.sh`, and every ansible task file -- 118
comments assert a mechanism that lives somewhere else. Their accuracy depends
almost entirely on **what kind of referent they use**:

===============  =======  =======  =====================================
referent kind    checked  wrong    note
===============  =======  =======  =====================================
path             74       2        one retired file, one prose heading
symbol           30       1        and that one resolved -- see below
line number      ~14      5-6      an order of magnitude worse
===============  =======  =======  =====================================

A line number is the weakest possible referent, for a reason that is structural
rather than a matter of care: **it is invalidated by edits to code it does not
describe.** Insert a line anywhere above and every citation below it is wrong,
having documented nothing incorrectly. Worse, it does not fail loudly -- it
fails *into* whatever now occupies the line, so the reader lands on a blank
line, an `env:` block, or a docstring quote, and reads a plausible near-miss
rather than an error. Two of the audited citations pointed at the comment
introducing the construct: still followable, and one edit from not being.

A symbol survives edits and breaks a grep loudly when renamed. A path survives
edits and fails obviously when followed. So the rule is: name the thing.

## Why this guard forbids the form instead of checking the target

Checking that citations resolve was measured too, and it is weak: of the 8
surviving citations, exactly **2** are mechanically detectable (one unresolvable
file, one line past end of file). The other 6 point at a real line in a real
file that says something else -- which needs the claim's meaning, not its
syntax. A lint catching 2 of 8 would license the other 6.

Forbidding the form catches all of it, and costs nothing, because the form is
already rare: 8 instances in 464 files.

## What this guard cannot do

It checks referent *shape*, never referent *truth*. The single most consequential
finding of the audit was a comment whose symbol referent resolved perfectly --
`scripts/lib/git-root.sh` citing `autobot_shared.paths.AMBIENT_GIT_VARS` -- while
the invariant it asserted ("keep the two lists in sync") was false, the lists
having diverged by two variables. No shape check reaches that. It needed the
claim turned into a test, which is what `ambient_git_vars_mirror_test.py` is.
Verifying that pointers resolve and verifying that claims hold are different
tools, and only the first is cheap.
"""

from __future__ import annotations

import os
import re
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

#: `(citing file, cited target)` for every citation that predates this rule.
#: Keyed on the CITED TARGET, not on the citing line number -- keying a baseline
#: about stale line numbers to a line number would rot the same way.
#: This list may shrink. It must never grow.
_BASELINE = frozenset(
    {
        # Quotes the stale citation it is correcting, deliberately (#15894).
        (".github/workflows/phase_validation.yml", "network_constants.py:34"),
        # ansible-core's own source, not vendored here — no symbol to name.
        ("autobot-slm-backend/ansible/roles/_shared/tasks/clean_wrong_node_dir.yml", "lib/ansible/plugins/action/set_fact.py:54"),
        ("autobot-slm-backend/ansible/roles/slm_manager/tasks/service_units.yml", "main.yml:673"),
        ("autobot-slm-backend/ansible/roles/slm_manager/tasks/service_units.yml", "bind_self_update_socket.yml:32"),
        ("repo_tests/bare_default_route_dependency_guard_test.py", "repo_tests/with_error_handling_single_definition_test.py:134"),
        ("repo_tests/bare_default_route_dependency_guard_test.py", "api/knowledge.py:2035"),
        ("repo_tests/sdk_response_model_contract_test.py", "api/agent_config.py:1024"),
        ("repo_tests/unprefixed_placeholder_string_test.py", "autobot-backend/api/codebase_analytics/config_duplication_detector.py:510"),
    }
)

#: The sweep must reach the tree it claims to sweep. Below this it is measuring
#: its own glob, not the repo.
_MIN_FILES = 300


def _scan():
    """Yield `(relative path, line number, citation)` for comment-borne citations."""
    files = 0
    for pattern in _SCOPES:
        for path in sorted(_ROOT.glob(pattern)):
            if not path.is_file():
                continue
            files += 1
            rel = path.relative_to(_ROOT).as_posix()
            is_py = path.suffix == ".py"
            for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                stripped = line.strip()
                if not (stripped.startswith("#") or (is_py and '"""' in line)):
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


def test_the_baseline_still_describes_real_citations() -> None:
    """A baseline entry whose citation is gone must be deleted, not carried.

    Otherwise the list grows stale in the same way the citations do, and a
    future author reads it as a record of what exists.
    """
    live = {(rel, cite) for rel, _, cite in _scan()}
    vanished = sorted(_BASELINE - live)
    assert not vanished, (
        "these baseline entries no longer exist — remove them so the list keeps "
        f"meaning what it says:\n" + "\n".join(f"  {f} -> {c}" for f, c in vanished)
    )


def test_no_new_comment_cites_a_line_number() -> None:
    """The rule. Name the symbol; a line number is invalidated by unrelated edits."""
    new = sorted({(rel, number, cite) for rel, number, cite in _scan() if (rel, cite) not in _BASELINE})
    assert not new, "\n".join(
        [
            "a comment cites a line number, which is the referent kind that goes wrong "
            "an order of magnitude more often than a symbol (#15877):",
            *(f"  {rel}:{number} cites {cite}" for rel, number, cite in new),
            "",
            "Cite the symbol, the function, or the step NAME instead. A line number is "
            "invalidated by edits to code it does not describe, and it fails silently "
            "INTO whatever now occupies the line rather than failing loudly.",
        ]
    )
