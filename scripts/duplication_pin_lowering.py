#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Lower the duplication-guard pins that a merge to main has left slack under (#16324).

`duplication_gate.py` fails a scope OVER its pin and only advises UNDER it, so a PR that
removes duplication without editing the pin leaves slack a later PR can spend. Editing the
pin in every dedup PR makes them all conflict on one line, so a PR under its pin stays
advisory and THIS runs after the merge: it reads the logs the guard job wrote on the push to
main and lowers each pin that is above its scope's measured count to that count.

It only ever lowers. A count over its pin, an UNMEASURED or non-numeric pin, and a log that
cannot be read are all left alone: raising a ratchet is a reviewed, declared scope change
(#18461), never an automatic one.

Usage:

    python3 scripts/duplication_pin_lowering.py PINS LOGDIR
    python3 scripts/duplication_pin_lowering.py --export PINS

PINS is ``.github/duplication-pins.json``, the one home of every pin: the workflow reads it
(``--export`` prints ``VAR=value`` lines for ``$GITHUB_ENV``) and this rewrites it. Only that
data file changes, so the bot's push never touches a workflow file (which GITHUB_TOKEN cannot
push).

The first form prints one ``VAR OLD -> NEW`` line per pin it lowered, rewrites PINS in place,
and exits 0 whether or not anything changed. Exit 2: a log or the pins file is missing or
unreadable, so no pin is touched.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import NamedTuple

_spec = importlib.util.spec_from_file_location("duplication_gate", Path(__file__).parent / "duplication_gate.py")
duplication_gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(duplication_gate)  # type: ignore[union-attr]


class Scope(NamedTuple):
    """One jscpd scope: the env var holding its pin and the log its gate step tees."""

    pin_var: str
    log_name: str


#: Every scope duplication-guard.yml gates. repo_tests/duplication_guard_scopes_18559_test.py
#: holds this table to the workflow, so dropping a scope from either side fails.
SCOPES: tuple[Scope, ...] = (
    Scope("MAX_DUP_LINES", "main-dup.log"),
    Scope("SLM_MAX_DUP_LINES", "slm-gate.log"),
    Scope("TOOLING_MAX_DUP_LINES", "tooling-gate.log"),
    Scope("CROSS_GUI_MAX_DUP_LINES", "cross-gui-gate.log"),
    Scope("CROSS_BACKEND_MAX_DUP_LINES", "cross-backend-gate.log"),
)


def measure(logdir: Path) -> dict[str, int]:
    """Duplicated lines per pin variable; raises OSError/ValueError on an unreadable log."""
    counts: dict[str, int] = {}
    for scope in SCOPES:
        text = (logdir / scope.log_name).read_text(encoding="utf-8", errors="replace")
        counts[scope.pin_var] = duplication_gate.parse_totals(text).duplicated_lines
    return counts


def lower_pins(pins: dict[str, int], counts: dict[str, int]) -> tuple[dict[str, int], list[tuple[str, int, int]]]:
    """Return *pins* with every pin above its count lowered, and the changes made.

    A pin that is not a plain count (UNMEASURED, a string, a bool) is left alone, and a count
    at or over its pin never raises it.
    """
    lowered = dict(pins)
    changes: list[tuple[str, int, int]] = []
    for var, measured in counts.items():
        old = pins.get(var)
        if not isinstance(old, int) or isinstance(old, bool) or measured >= old:
            continue
        lowered[var] = measured
        changes.append((var, old, measured))
    return lowered, changes


def load_pins(path: Path) -> dict[str, int]:
    """Read the pins file; raises OSError/ValueError when it is not a JSON object."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def main(argv: list[str]) -> int:
    try:
        if len(argv) == 2 and argv[0] == "--export":
            for var, pin in load_pins(Path(argv[1])).items():
                print(f"{var}={pin}")
            return 0
        if len(argv) != 2:
            print(__doc__, file=sys.stderr)
            return 2
        pins_path, logdir = Path(argv[0]), Path(argv[1])
        pins = load_pins(pins_path)
        counts = measure(logdir)
    except (OSError, ValueError) as exc:
        print(f"could not read the pins or a scope's jscpd totals: {exc}. No pin was touched.", file=sys.stderr)
        return 2
    lowered, changes = lower_pins(pins, counts)
    if changes:
        pins_path.write_text(json.dumps(lowered, indent=2) + "\n", encoding="utf-8")
    for var, old, new in changes:
        print(f"{var} {old} -> {new}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
