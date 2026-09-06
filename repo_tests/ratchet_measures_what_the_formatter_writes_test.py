# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The size ratchet must rule on the size the formatter leaves (#15868).

Two mechanisms write to the same number and one of them writes last:

* the **size ratchet** (#14236) freezes a grandfathered file at the size it was
  granted, and fails in *both* directions -- over its ceiling, and under it;
* the **auto-format job** rewrites `.py` files after the author and pushes the
  result to the branch.

So a grandfathered file sitting exactly at its ceiling is one reformat away from
a red nobody introduced. Observed twice in one day in opposite directions. The
sharpest case: a file compacted 1083 -> 1075 to fit, its ceiling ratcheted down
to 1075 to match, and the bot then reflowed it back to 1081 -- over a ceiling
that had just been lowered *for that file*, with no human change in between.

The fix rules on the post-format size, which keeps the ratchet **monotonic**.
The tempting alternative -- let a ceiling rise when formatting caused the growth
-- reopens exactly the licence #14236 exists to remove, since any growth can be
attributed to the formatter.

## The scopes differ, and that is load-bearing

The ratchet walks every tracked `.py`. The formatter rewrites three directories.
Measured across all 497 grandfathered files: the **493** whose raw and formatted
sizes agree are all inside the formatter's scope; all **4** that differ are
outside it. Measuring post-format size for a file the formatter never touches
would invent a reflow that will never happen -- and would have demanded four
ceilings be lowered to sizes nothing produces.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_HOOK = _ROOT / "scripts" / "check_python_file_size.py"
_WORKFLOW = _ROOT / ".github" / "workflows" / "auto-fix-formatting.yml"


def _hook():
    """Load the hook by path — `scripts/` is not a package."""
    spec = importlib.util.spec_from_file_location("_size_hook", _HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_formatter_scope_matches_the_workflow() -> None:
    """`FORMATTER_SCOPE` is a hand-copied list; a comment saying so cannot fail.

    This is the #15877 shape — a claim that a mechanism elsewhere agrees with
    this one. It gets an assertion instead of a promise, because the whole fix
    depends on the two sets being the same, and the workflow can be edited by
    someone who never opens the hook.
    """
    text = _WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r"-m black[^\n]*?--line-length=\d+\s+([^\n]+)", text)
    assert match, f"{_WORKFLOW.name}: no `-m black ... <dirs>` invocation found — the parse read nothing"
    workflow_dirs = {part if part.endswith("/") else part + "/" for part in match.group(1).split() if not part.startswith("-")}
    assert workflow_dirs, "parsed an empty directory list from the black invocation"
    assert set(_hook().FORMATTER_SCOPE) == workflow_dirs, (
        "the ratchet's FORMATTER_SCOPE and the auto-format job's black invocation have "
        f"diverged:\n  hook:     {sorted(_hook().FORMATTER_SCOPE)}\n  workflow: {sorted(workflow_dirs)}\n"
        "A directory formatted by the bot but absent here is ruled on its raw size, which "
        "is the #15868 defect. One present here but not formatted invents a reflow."
    )


def test_a_file_outside_the_formatter_scope_is_ruled_on_its_raw_size(tmp_path) -> None:
    """The 4-file case. Nothing reflows these, so the raw count is the truth."""
    hook = _hook()
    ruled, note = hook._size_to_rule_on(tmp_path, "repo_tests/whatever_test.py", 1317)
    assert ruled == 1317, "a file outside the formatter's scope must be ruled on its raw size"
    assert note == "", "no post-format note belongs on a file the formatter never touches"


def test_an_in_scope_file_is_ruled_on_its_post_format_size(tmp_path) -> None:
    """The fix. A reflow with no semantic change must not move the verdict."""
    pytest.importorskip("black")
    # Must be a GRANDFATHERED path: post-format measurement is scoped to
    # KNOWN_LARGE, because only those files are judged by equality with a
    # recorded ceiling. Formatting every in-scope file instead was measured at
    # 262s over 5231 files -- correct and unusable.
    hook = _hook()
    rel = next(k for k in hook.KNOWN_LARGE if k.startswith(hook.FORMATTER_SCOPE))
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    # Semantically one statement, written across four lines. black joins it:
    # the raw count and the formatted count differ with no change of meaning.
    #
    # NO trailing comma after the last element. black's magic trailing comma
    # treats one as an instruction to keep the collection exploded, so the
    # first version of this fixture was reformatted to itself and the test
    # failed reporting 4 == 4. The fixture, not the code, was wrong.
    target.write_text("x = [\n    1,\n    2\n]\n", encoding="utf-8")
    raw = len(target.read_text(encoding="utf-8").splitlines())
    ruled, note = hook._size_to_rule_on(tmp_path, rel, raw)
    assert ruled < raw, (
        f"in-scope file ruled on {ruled} with a raw size of {raw}; the formatter would "
        "join these lines, so the ratchet is still judging a state the bot will overwrite"
    )
    assert "post-format" in note, "the message must say the verdict used the formatted size (AC4)"
    assert str(raw) in note and str(ruled) in note, "the note must give both numbers, or it cannot be checked"


def test_the_ratchet_still_only_turns_down() -> None:
    """AC3 — this must not become a way to raise a ceiling.

    Ruling on the post-format size changes *which* number is compared, never the
    comparison. A file whose formatted size exceeds its ceiling is still a
    violation; if this ever passes, the fix has become the licence #14236 removed.
    """
    hook = _hook()
    over = hook._grandfathered_verdict("some/file.py", 1200, 1100)
    assert over is not None and "may not grow" in over, "a file over its ceiling must still fail"
    under = hook._grandfathered_verdict("some/file.py", 1000, 1100)
    assert under is not None and "only turns down" in under, "an unlowered ceiling must still fail"


def test_a_missing_formatter_does_not_silently_pass(tmp_path) -> None:
    """`None` from the measurement means 'not measured', never 'fine'.

    If black is absent the audit falls back to the raw count and keeps ruling.
    The dangerous failure would be treating an unmeasurable file as compliant --
    the negative-assertion trap, one level down in the plumbing.
    """
    hook = _hook()
    rel = next(k for k in hook.KNOWN_LARGE if k.startswith(hook.FORMATTER_SCOPE))
    missing = tmp_path / rel
    assert hook.formatted_line_count(missing) is None, "an unreadable file must measure as None"
    ruled, note = hook._size_to_rule_on(tmp_path, rel, 900)
    assert ruled == 900, "an unmeasurable in-scope file falls back to its raw size, still ruled on"
    assert note == ""
