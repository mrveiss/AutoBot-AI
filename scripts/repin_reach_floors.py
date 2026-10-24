#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Re-pin every stale reach floor mid-window in one command (#19282).

A reach floor goes stale when the tree outgrows it (repo_tests/_reach.py ``Reach.staleness``).
Merge trains enforce staleness (``AUTOBOT_REACH_AUDIT=1``, set in ci.yml for train-* heads); this
script is how a train fixes it. It imports every guard, measures each floor-based declaration
against the live tree, and rewrites each stale literal ``floor=`` inside its ``declare(...)`` call
to the window's mid value, then re-measures to confirm the new floor is not stale.

Exit codes:
  0  nothing stale and every guard imported (or, writing, everything stale was re-pinned)
  1  stale floors remain (``--check``), or one could not be re-pinned automatically
  2  some guard failed to import, so its floor was NOT measured -- never reported as clean

Only literal integer floors are rewritten. A floor written as an expression is reported, not
touched, so a human decides what it should derive from. An existing comment on the floor line is
kept, except a ``# mid-window: ...`` comment, which is refreshed with the new measurement.

Usage:
    python scripts/repin_reach_floors.py           # re-pin every stale floor
    python scripts/repin_reach_floors.py --check   # report only
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import inspect
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))


def _declarations() -> tuple[list, dict[str, str]]:
    """(floor-based declarations, {module: import error}) after importing every guard."""
    from repo_tests import reach_declarations_test as meta  # noqa: PLC0415 - imports every guard

    failures = dict(getattr(meta, "IMPORT_FAILURES", {}))
    return [r for r in meta._declarations() if r.min_fraction is None], failures


def _floor_node(source: str, name: str) -> ast.AST | None | bool:
    """The ``floor=`` value node of the ``declare("<name>", ...)`` call; None if no such call;
    False if the call has no ``floor=`` keyword."""
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", None)) == "declare"):
            continue
        if not (node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == name):
            continue
        floor = next((k.value for k in node.keywords if k.arg == "floor"), None)
        return floor if floor is not None else False
    return None


def repin_source(source: str, name: str, mid: int, count: int, low: int, high: int) -> tuple[str, str]:
    """*source* with *name*'s literal floor set to *mid*; returns (new source, status)."""
    node = _floor_node(source, name)
    if node is None:
        return source, "declare() call not found"
    if node is False:
        return source, "declare() call has no floor= keyword"
    if not (isinstance(node, ast.Constant) and type(node.value) is int):
        return source, "floor is not a literal integer -- re-pin by hand"
    # ast columns are UTF-8 BYTE offsets, and only bytes.splitlines breaks lines where ast does (\n, \r, \r\n).
    lines = source.encode("utf-8").splitlines(keepends=True)
    row = node.lineno - 1
    head = lines[row][: node.col_offset].decode("utf-8")
    new_line = head + str(mid) + lines[row][node.end_col_offset :].decode("utf-8")
    stamp = f"# mid-window: population {count}, window ({low}, {high})"
    new_line = re.sub(r"#\s*mid-window:[^\n]*", stamp, new_line)
    if "#" not in new_line[len(head) :]:
        new_line = new_line.rstrip("\n") + f"  {stamp}\n"
    lines[row] = new_line.encode("utf-8")
    return b"".join(lines).decode("utf-8"), "re-pinned"


def _source_file(reach) -> Path | None:
    """The file whose source holds this declaration's ``declare(`` call."""
    module = sys.modules.get(getattr(reach.discover, "__module__", ""))
    candidates = [Path(inspect.getsourcefile(module))] if module else []
    candidates += sorted(_ROOT.glob("repo_tests/*.py"))
    for path in candidates:
        if _floor_node(path.read_text(encoding="utf-8"), reach.name) is not None:
            return path
    return None


def _repin(reach) -> str:
    """Re-pin one stale declaration in its source; returns a one-line result."""
    low, high, mid = reach.window(_ROOT)
    count = len(reach.population(_ROOT))
    path = _source_file(reach)
    if path is None:
        return f"SKIP  {reach.name}: declare() call not found"
    new, status = repin_source(path.read_text(encoding="utf-8"), reach.name, mid, count, low, high)
    if status != "re-pinned":
        return f"SKIP  {reach.name}: {status} ({path.relative_to(_ROOT)})"
    if dataclasses.replace(reach, floor=mid).staleness(_ROOT) is not None:
        return f"SKIP  {reach.name}: the mid-window value {mid} is still stale -- check skips=/growth="
    path.write_text(new, encoding="utf-8")
    return f"PIN   {reach.name}: floor -> {mid} (population {count}) in {path.relative_to(_ROOT)}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="report stale floors; change nothing")
    args = parser.parse_args(argv)
    declarations, failures = _declarations()
    if failures:
        print(
            f"ERROR: {len(failures)} guard module(s) failed to import, so their floors were NOT "
            f"measured: {', '.join(sorted(failures))}",
            file=sys.stderr,
        )
    stale = [(r, why) for r in declarations if (why := r.staleness(_ROOT))]
    if args.check:
        for reach, why in stale:
            print(f"STALE {reach.name}: {why.splitlines()[0]}")
    else:
        results = [_repin(r) for r, _ in stale]
        print("\n".join(results))
        stale = [s for s, line in zip(stale, results) if not line.startswith("PIN")]
    if failures:
        return 2
    if stale:
        print(f"{len(stale)} stale floor(s) remain. Fix with: python scripts/repin_reach_floors.py")
        return 1
    print("No stale reach floors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
