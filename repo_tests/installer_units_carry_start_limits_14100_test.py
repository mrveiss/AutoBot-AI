# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shell-written systemd units obey the same rules as the ansible ones (#14100).

#4090 was a unit whose ExecStart could never succeed. With ``Restart=on-failure``
and no start limit it restarted forever, never reached ``failed``, and so never
appeared in ``systemctl --failed``: chroma looped 1681 times over ~4h45m while
systemctl reported it running. The fix added start limits to the ansible unit
templates, and two guards protect them --
``autobot-slm-backend/tests/test_restart_always_units_can_fail_4090.py`` and
``autobot-slm-backend/tests/services/test_chromadb_unit_single_owner_13870_test.py``.

Both walk ``ansible/**`` and recognise a unit writer only as an
``ansible.builtin.template`` task or a ``*.j2`` file. ``install-bare-metal.sh``
writes systemd units with shell heredocs, so it is invisible to both by
construction -- it wrote a fourth ``autobot-chromadb.service`` carrying none of
the #4090 values, and its generic service factory emitted every other unit the
same way. This is the first reader of that script.

Two invariants, both structural, so they hold for units added later:

1. a unit that restarts declares a *reachable* start limit in ``[Unit]``
2. an ``EnvironmentFile`` the installer itself writes is mandatory, not ``-``
   optional -- #12513, because the optional form is what let a missing
   credential file produce a running-but-unauthenticated service.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPO_ROOT / "autobot-infrastructure/shared/scripts/install-bare-metal.sh"

# `cat > <dest> <<EOF` ... `EOF`, the shape the installer uses for every unit.
_HEREDOC = re.compile(
    r"^\s*cat\s*>\s*\"?(?P<dest>[^\"\s]+\.service)\"?\s*<<\s*[\"']?(?P<tag>\w+)[\"']?\s*$",
    re.MULTILINE,
)
_RESTARTING = re.compile(r"^\s*Restart\s*=\s*(always|on-failure)\s*$", re.MULTILINE)
_RESTART_SEC = re.compile(r"^\s*RestartSec\s*=\s*(\d+)\s*$", re.MULTILINE)
_INTERVAL = re.compile(r"^\s*StartLimitIntervalSec?\s*=\s*(\d+)\s*$", re.MULTILINE)
_BURST = re.compile(r"^\s*StartLimitBurst\s*=\s*(\d+)\s*$", re.MULTILINE)


def _units() -> List[Tuple[str, str]]:
    """Every systemd unit body the installer heredocs, as (dest, body)."""
    text = INSTALLER.read_text(encoding="utf-8")
    lines = text.splitlines()
    found: List[Tuple[str, str]] = []
    for match in _HEREDOC.finditer(text):
        start = text[: match.start()].count("\n") + 1
        tag = match.group("tag")
        body: List[str] = []
        for line in lines[start:]:
            if line.strip() == tag:
                break
            body.append(line)
        else:  # pragma: no cover - an unterminated heredoc would not parse as shell
            pytest.fail(f"heredoc for {match.group('dest')} is never closed")
        found.append((match.group("dest"), "\n".join(body)))
    return found


def _section_of(body: str, directive: str) -> str:
    """Which [Section] a directive appears under, or '' if it is absent."""
    section = ""
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped
        elif stripped.startswith(directive + "="):
            return section
    return ""


_UNITS = _units()
_RESTARTING_UNITS = [(dest, body) for dest, body in _UNITS if _RESTARTING.search(body)]


def test_the_installer_still_writes_units_this_guard_can_see() -> None:
    """Guard the guard.

    If the heredoc shape changes -- a different redirect, a templating step, a
    helper function -- this parser silently finds nothing and every assertion
    below passes vacuously. That is the failure mode that let the installer
    drift away from the ansible templates unnoticed in the first place.
    """
    assert INSTALLER.exists(), f"{INSTALLER} moved; this guard needs its new path"
    assert len(_UNITS) >= 2, (
        "no systemd heredocs found in the installer. Either it stopped writing "
        f"units, or it writes them in a shape this parser does not recognise. "
        f"Found: {[dest for dest, _ in _UNITS]}"
    )
    assert _RESTARTING_UNITS, "no restarting unit found; the #4090 class cannot be checked"


@pytest.mark.parametrize("dest,body", _RESTARTING_UNITS, ids=lambda v: str(v)[:60])
def test_a_restarting_unit_declares_a_start_limit(dest: str, body: str) -> None:
    assert _INTERVAL.search(body), (
        f"{dest} sets Restart= but no StartLimitIntervalSec. A unit whose "
        "ExecStart can never succeed will restart forever, never reach failed, "
        "and never show up in `systemctl --failed` (#4090)."
    )
    assert _BURST.search(body), f"{dest} sets StartLimitIntervalSec but no StartLimitBurst"


@pytest.mark.parametrize("dest,body", _RESTARTING_UNITS, ids=lambda v: str(v)[:60])
def test_the_start_limit_is_reachable(dest: str, body: str) -> None:
    """A start limit narrower than the restart spacing can never trigger."""
    interval = int(_INTERVAL.search(body).group(1))
    burst = int(_BURST.search(body).group(1))
    restart_sec_match = _RESTART_SEC.search(body)
    restart_sec = int(restart_sec_match.group(1)) if restart_sec_match else 100
    assert interval > restart_sec * burst, (
        f"{dest}: StartLimitIntervalSec={interval} but {burst} restarts spaced "
        f"RestartSec={restart_sec}s apart span {restart_sec * burst}s. The unit "
        "restarts out of the window every time, so the limit never fires -- "
        "which is indistinguishable from having no limit at all."
    )


@pytest.mark.parametrize("dest,body", _RESTARTING_UNITS, ids=lambda v: str(v)[:60])
def test_start_limit_directives_live_in_the_unit_section(dest: str, body: str) -> None:
    """systemd rejects these in [Service] with 'Unknown key name'."""
    for directive in ("StartLimitIntervalSec", "StartLimitBurst"):
        assert _section_of(body, directive) == "[Unit]", (
            f"{dest}: {directive} is under {_section_of(body, directive) or 'no section'}, "
            "not [Unit]. systemd logs 'Unknown key name' and ignores it, so the "
            "unit looks protected in the file and is not protected at runtime."
        )


@pytest.mark.parametrize("dest,body", _UNITS, ids=lambda v: str(v)[:60])
def test_an_environment_file_the_installer_writes_is_mandatory(dest: str, body: str) -> None:
    """#12513: the optional form hides a missing credential file.

    ``EnvironmentFile=-`` tells systemd to start anyway when the file is absent.
    For a file the installer creates itself, absence means the install did not
    complete -- starting regardless is how chroma came up unauthenticated.
    """
    optional: Dict[str, str] = {}
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("EnvironmentFile=-"):
            optional[dest] = stripped
    assert not optional, (
        f"{dest} declares {optional.get(dest)}. The installer writes that file "
        "itself, so the optional form converts an incomplete install into a "
        "service running without its configuration rather than a unit that "
        "refuses to start (#12513, #14100)."
    )
