#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Fail when a shell `${AUTOBOT_*_PORT:-N}` fallback disagrees with the SSOT (#14198).

Every one of these scripts sources `lib/ssot-config.sh`, which assigns the SSOT
value with `:=` before the fallback is ever evaluated. So the literal is dead —
right up until the library fails to load. Every source line is
``source ... 2>/dev/null || true`` (deliberately, so a missing library cannot
abort a status script), which is exactly what makes the fallback reachable.

`AUTOBOT_BROWSER_SERVICE_PORT:-3000` sat in 19 sites that way. 3000 is
**Grafana's** port; the browser service is 9001 (`ssot_config.py`: "Issue #4052:
9001; 3000 is Grafana"). A library that failed to load would have pointed every
one of those health checks at the wrong service.

Scope, deliberately narrow: this does **not** ban fallbacks. 164 of them exist
and 145 agree with the SSOT, where the literal is harmless redundancy. Banning
the shape would mean churning every one of those sites to fix one real defect.
What is banned is a fallback that **disagrees** — the invariant, not the shape.

A variable with no SSOT entry is reported once as unverifiable rather than
failed: those families are tracked in #14173, and failing on them here would
block on someone else's decision.
"""

from __future__ import annotations

import argparse
import re
import subprocess  # nosec B404  # git plumbing, fixed argv, no shell
import sys
from pathlib import Path

_FALLBACK = re.compile(r"\$\{(AUTOBOT_[A-Z0-9_]*PORT):-([0-9]+)\}")
_SSOT_FIELD = re.compile(r'Field\(\s*default=(\d+)[^)]*alias="(AUTOBOT_[A-Z0-9_]*PORT)"')

_SSOT_PATH = Path("autobot_shared/ssot_config.py")

# Files whose *point* is to exercise a diverging literal. The shell library's
# own self-test asserts that sourcing it overrides `${AUTOBOT_BROWSER_SERVICE_PORT:-3000}`
# with 9001, and that a MISSING library leaves 3000 standing — the second
# assertion is the reason #14198 exists, so removing the literal would delete
# the evidence. Same mechanism the sibling checkers use for their own sources.
_ALLOWLIST = frozenset(
    {
        "autobot-infrastructure/shared/tests/test_ssot_config_lib.sh",
        "tools/lint/check_port_fallbacks_match_ssot_test.py",
    }
)


def _repo_root() -> Path:
    """Absolute repo root, or die — every path below is resolved against it."""
    result = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0 or not result.stdout.strip():
        sys.exit(f"FATAL: cannot locate the repo root: {result.stderr.strip()}")
    return Path(result.stdout.strip())


def _ssot_ports(root: Path) -> dict[str, str]:
    """Map every AUTOBOT_*_PORT alias to its SSOT default, or die."""
    path = root / _SSOT_PATH
    if not path.is_file():
        sys.exit(f"FATAL: {_SSOT_PATH} not found — refusing to report clean without the SSOT")
    parsed = {m.group(2): m.group(1) for m in _SSOT_FIELD.finditer(path.read_text(encoding="utf-8"))}
    if not parsed:
        sys.exit(f"FATAL: no AUTOBOT_*_PORT fields parsed from {_SSOT_PATH} — the pattern has drifted")
    # `default=0` is a "not configured" sentinel, not a port. `AUTOBOT_POSTGRES_PORT`
    # and `AUTOBOT_SMTP_PORT` both use it. Comparing a shell fallback against 0
    # would fail a perfectly correct `${AUTOBOT_POSTGRES_PORT:-5432}` — a guard
    # that blocks correct code is worse than the gap it closes, so a sentinel
    # default makes the variable unverifiable rather than wrong.
    comparable = {var: value for var, value in parsed.items() if value != "0"}
    # Review finding on this PR: the fatal check above runs on `parsed`, BEFORE
    # this filter. A mass edit that turned every real port field into
    # `default=0` — a bad find/replace, a merge conflict, over-applying the
    # sentinel convention — would leave `parsed` non-empty (so the check passes)
    # and `comparable` empty. Every fallback then reads as "no SSOT entry", and
    # the guard prints a clean verdict over a tree it never compared. Reproduced:
    # a `:-3000` browser fallback was reported clean with exit 0. The invariant
    # has to be asserted on the map that is actually used.
    if not comparable:
        sys.exit(
            f"FATAL: every AUTOBOT_*_PORT field in {_SSOT_PATH} has the sentinel default=0 "
            f"({len(parsed)} parsed) — nothing left to compare against, refusing to report clean"
        )
    return comparable


def _shell_files(root: Path) -> list[str]:
    """Tracked shell scripts, or die rather than scan nothing."""
    result = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "ls-files", "*.sh"], cwd=str(root), capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        sys.exit(f"FATAL: git ls-files failed: {result.stderr.strip()}")
    files = result.stdout.split()
    if not files:
        sys.exit("FATAL: git ls-files listed no shell scripts — refusing to report clean on an empty scope")
    return files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("filenames", nargs="*", help="ignored; the whole tracked tree is always checked")
    parser.parse_args(argv)

    root = _repo_root()
    ssot = _ssot_ports(root)

    violations: list[str] = []
    unverifiable: set[str] = set()
    for name in _shell_files(root):
        if name in _ALLOWLIST:
            continue
        path = root / name
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in _FALLBACK.finditer(line):
                var, literal = match.group(1), match.group(2)
                expected = ssot.get(var)
                if expected is None:
                    unverifiable.add(var)
                elif literal != expected:
                    violations.append(f"{name}:{lineno}: {var} falls back to {literal}, SSOT says {expected}")

    if unverifiable:
        print(  # noqa: print
            "check-port-fallbacks: no SSOT entry for "
            + ", ".join(sorted(unverifiable))
            + " — unverifiable, tracked in #14173"
        )

    if not violations:
        print("check-port-fallbacks: every AUTOBOT_*_PORT fallback agrees with the SSOT")  # noqa: print
        return 0

    print(f"check-port-fallbacks: {len(violations)} fallback(s) disagree with the SSOT\n")  # noqa: print
    for violation in violations:
        print(f"  FAIL  {violation}")  # noqa: print
    print(  # noqa: print
        "\nThese literals are dead while lib/ssot-config.sh loads, because it assigns\n"
        "the SSOT value with `:=` first. Every source line is `2>/dev/null || true`,\n"
        "so a library that fails to load makes them live — pointing at the wrong\n"
        "service rather than failing visibly.\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
