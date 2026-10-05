#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Read ONE numeric figure out of the phase-validation report, or fail loudly (#17674).

WHY THIS IS A FILE AND NOT TWO INLINE ONE-LINERS. There are two gates in
``.github/workflows/phase_validation.yml`` reading a top-level figure out of
``phase_validation_results.json``, at two thresholds. Both were written as
``python3 -c '... r.get(KEY, 0) ...' 2>/dev/null || echo "0"``, and both turn
three distinct facts -- *the key is absent*, *the file is unreadable*, *the
reader crashed* -- into the single number ``0``. ``0`` is also a legitimate
measurement, so the gate then reports a broken transport as a low score. One
reader, one call site shape, so the next fix lands once.

THE RULE IT ENFORCES (``docs/developer/MEASUREMENT_DISCIPLINE.md``). An absent
measurement is not a zero. A real ``0.0`` prints and the caller gates on it; an
absent, null or non-numeric value exits non-zero with a message that names the
key asked for and the keys actually present, so the next occurrence is
diagnosable from the log alone rather than from 34 hours of bisection.

Stdlib only, on purpose: it runs in the CI gate step before any dependency is
guaranteed, and a reader that cannot import is a reader that returns nothing.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from typing import Any, Dict

#: Exit status for "there was no measurement to read". Distinct from 1 so a
#: caller can tell a broken instrument from a figure below its threshold.
NO_MEASUREMENT = 3


class NoMeasurement(LookupError):
    """Raised when the report holds no numeric value for the requested key."""


def _load(path: str) -> Dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as handle:
            report = json.load(handle)
    except OSError as exc:
        raise NoMeasurement(
            f"phase-validation: report {path!r} is unreadable ({type(exc).__name__}: {exc}) -- nothing was measured"
        ) from exc
    except json.JSONDecodeError as exc:
        raise NoMeasurement(
            f"phase-validation: report {path!r} is not valid JSON ({exc}) -- nothing was measured"
        ) from exc
    if not isinstance(report, dict):
        raise NoMeasurement(
            f"phase-validation: report {path!r} is a {type(report).__name__}, not an object -- nothing was measured"
        )
    return report


def read_figure(path: str, key: str) -> float:
    """Return the numeric ``key`` from the report at ``path``.

    :raises NoMeasurement: when the file cannot be read, or the key is absent,
        null or non-numeric. The message names the key and lists the top-level
        keys that ARE present, because a producer/consumer key mismatch is the
        failure this exists for and the key list is what identifies it.
    """
    report = _load(path)
    value = report.get(key)
    # ``bool`` is an ``int``; ``True`` is not a measurement. ``NaN`` and
    # ``Infinity`` are floats that `json` happily round-trips and that `bc`
    # reads as 0 -- a number-shaped non-measurement, which is this issue.
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise NoMeasurement(
            f"phase-validation: no numeric {key!r} in {path!r}. "
            f"It is {value!r}. Top-level keys present: {sorted(report)}. "
            f"measures={report.get('measures')!r}. "
            "An ABSENT measurement is NOT 0: this is a producer/consumer key mismatch, "
            "or a run that measured nothing -- NOT a low score (#17674)."
        )
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", help="path to phase_validation_results.json")
    parser.add_argument("key", help="top-level key to read, e.g. structural_presence")
    args = parser.parse_args(argv)

    try:
        print(read_figure(args.report, args.key))
    except NoMeasurement as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return NO_MEASUREMENT
    return 0


if __name__ == "__main__":
    sys.exit(main())
