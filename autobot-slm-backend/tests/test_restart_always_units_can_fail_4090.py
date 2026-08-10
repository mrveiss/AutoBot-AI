# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every restarting unit must be able to reach `failed` (#4090).

ChromaDB restarted 1681 times over ~4h45m and never appeared in
`systemctl --failed`. Nothing was broken about the detection — there was none to
break. `Restart=always` reschedules forever, so a unit whose ExecStart can never
succeed stays `activating` and the one thing an operator checks structurally
cannot show it. RAG, knowledge-base search, codebase-analytics embeddings and
conversation retrieval were all down for the duration; it surfaced through an
unrelated investigation.

systemd's own defaults do not save you, which is the part worth pinning:
``DefaultStartLimitIntervalSec=10s`` with ``DefaultStartLimitBurst=5`` needs five
restarts *inside ten seconds*, and ``RestartSec`` spaces them further apart than
that. At ``RestartSec=10`` five restarts take ~50s, so the rate never reaches the
limit and the unit loops until someone notices. The limit is only reachable when

    StartLimitIntervalSec > RestartSec * StartLimitBurst

which is the invariant asserted below — not merely "the directives are present".
A unit could set both and still be unable to fail, which would look like a fix
and be none.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ANSIBLE_ROOT = Path(__file__).resolve().parents[1] / "ansible"

# `on-failure` is in scope alongside `always`, and leaving it out was the first
# version's mistake: an ExecStart that can never succeed never exits cleanly, so
# `on-failure` reschedules just as indefinitely. The unit from the incident —
# the redis role's autobot-chromadb, which won the template race and is what
# actually runs — is `on-failure`, so the narrow check missed the very thing it
# was written for.
_RESTARTING = re.compile(r"^\s*Restart\s*=\s*(always|on-failure)\s*$", re.MULTILINE)
_DIRECTIVE = r"^\s*{}\s*=\s*(?P<v>\S+)\s*$"

# Jinja-templated values (RestartSec={{ x }}) resolve from role defaults; the
# largest default in the tree is 10s. Using that as the assumed worst case keeps
# the check honest without evaluating templates.
_ASSUMED_MAX_TEMPLATED_RESTART_SEC = 10

# systemd's defaults, for the "would the default have caught it?" assertion.
_SYSTEMD_DEFAULT_INTERVAL_SEC = 10
_SYSTEMD_DEFAULT_BURST = 5


def _unit_templates() -> list[Path]:
    return sorted(_ANSIBLE_ROOT.rglob("*.service.j2"))


def _restart_always_units() -> list[Path]:
    return [p for p in _unit_templates() if _RESTARTING.search(p.read_text(encoding="utf-8"))]


def _directive(text: str, name: str) -> str | None:
    m = re.search(_DIRECTIVE.format(name), text, re.MULTILINE)
    return m.group("v") if m else None


# systemd accepts time spans with unit suffixes ("5min", "1h", "100ms"), and a
# bare number means seconds. Parsing only the leading digits read "5min" as 5
# seconds and produced a false failure on autobot-agent — a detector that cried
# wolf, in a test written to stop exactly that.
_TIME_UNITS = {"us": 1e-6, "ms": 1e-3, "s": 1, "sec": 1, "m": 60, "min": 60, "h": 3600, "hr": 3600}


def _seconds(raw: str | None, default: float) -> float:
    """Seconds from a systemd time-span value, tolerating Jinja and unit suffixes."""
    if raw is None:
        return default
    if "{{" in raw:
        return _ASSUMED_MAX_TEMPLATED_RESTART_SEC
    total = 0.0
    matched = False
    for value, unit in re.findall(r"(\d+(?:\.\d+)?)\s*([a-z]*)", raw):
        if unit and unit not in _TIME_UNITS:
            continue
        total += float(value) * _TIME_UNITS.get(unit, 1)
        matched = True
    return total if matched else default


def test_there_are_restart_always_units_to_check():
    """Guard the guard: a glob that stops matching would pass everything."""
    units = _restart_always_units()
    assert len(units) >= 10, f"expected the fleet's long-running units, found {len(units)}"


@pytest.mark.parametrize("unit", _restart_always_units(), ids=lambda p: p.name)
def test_restart_always_unit_declares_a_start_limit(unit: Path):
    text = unit.read_text(encoding="utf-8")
    interval = _directive(text, "StartLimitIntervalSec") or _directive(text, "StartLimitInterval")
    burst = _directive(text, "StartLimitBurst")

    assert interval is not None and burst is not None, (
        f"{unit.name} sets Restart=always with no start limit — a unit that can never "
        "exec will restart forever and never appear in `systemctl --failed` (#4090)"
    )


@pytest.mark.parametrize("unit", _restart_always_units(), ids=lambda p: p.name)
def test_the_start_limit_is_actually_reachable(unit: Path):
    """Present-but-unreachable is the failure mode, not absent.

    This is the assertion that would have caught the original bug even if every
    unit had carried systemd's defaults explicitly.
    """
    text = unit.read_text(encoding="utf-8")
    restart_sec = _seconds(_directive(text, "RestartSec"), default=0)
    interval = _seconds(_directive(text, "StartLimitIntervalSec") or _directive(text, "StartLimitInterval"), 0)
    burst = int(_directive(text, "StartLimitBurst") or 0)

    needed = restart_sec * burst
    assert interval > needed, (
        f"{unit.name}: StartLimitIntervalSec={interval} but {burst} restarts "
        f"{restart_sec}s apart span {needed}s — the limit can never be reached, so the "
        "unit loops forever exactly as it did before (#4090)"
    )


@pytest.mark.parametrize("unit", _restart_always_units(), ids=lambda p: p.name)
def test_systemd_defaults_would_not_have_been_enough(unit: Path):
    """Pins WHY each unit needs an explicit limit.

    If this ever fails, systemd's defaults became sufficient for that unit and
    the explicit directives are merely redundant — worth knowing, not a bug.
    """
    text = unit.read_text(encoding="utf-8")
    restart_sec = _seconds(_directive(text, "RestartSec"), default=0)
    if restart_sec == 0:
        pytest.skip("no RestartSec: systemd's 100ms default trips its own start limit")

    assert restart_sec * _SYSTEMD_DEFAULT_BURST > _SYSTEMD_DEFAULT_INTERVAL_SEC, (
        f"{unit.name}: RestartSec={restart_sec}s would trip systemd's own "
        f"{_SYSTEMD_DEFAULT_BURST}-in-{_SYSTEMD_DEFAULT_INTERVAL_SEC}s default"
    )


def test_chromadb_the_unit_that_looped_1681_times_is_covered():
    """Named explicitly: it is the incident, and it ships from TWO roles."""
    units = [p for p in _restart_always_units() if p.name == "autobot-chromadb.service.j2"]
    assert len(units) == 2, (
        "autobot-chromadb.service.j2 is expected in both the ai-stack and redis roles "
        f"(see #4090 — they race and whichever runs last wins); found {len(units)}"
    )
    for unit in units:
        text = unit.read_text(encoding="utf-8")
        assert _directive(text, "StartLimitBurst") is not None, f"{unit} lost its start limit"
