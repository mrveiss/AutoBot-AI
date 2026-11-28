# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Read the junit file one pre-board lane shard wrote (#21359).

Split from ``preboard_guard_lane_report.py`` so the verdict logic and the reading of pytest's writer
each stay small. Every shape below is what pytest's own ``_pytest/junitxml.py`` writes, read at the
version the suite runs (9.2.0, ``junit_family=xunit1`` as the lane passes it):

* call-time skip (``pytest.skip()``, a ``skip``/``skipif`` mark): ``<skipped type="pytest.skip"
  message="<reason>">path:line: <reason></skipped>``; pytest has already removed ``Skipped: ``.
* collection skip (``pytest.importorskip`` or ``pytest.skip(..., allow_module_level=True)`` at module
  top): ``<skipped message="collection skipped">('<abs path>', <line>, 'Skipped: <reason>')</skipped>``
  with NO ``type``. The reason is only in the element text, as the ``str()`` of that tuple. Its
  testcase has ``classname=""``, ``name="<dotted module>"`` and ``file="<module path>"``.
* expected failure: ``<skipped type="pytest.xfail" message="<reason>"/>``. It RAN, so it is not a skip.
* strict unexpected pass: a ``<failure message="[XPASS(strict)] <reason>">``.
* collection error: ``<error message="collection failure">`` on the same module-shaped testcase.

Under ``xunit2`` the testcase has no ``file``; :func:`node_id` then falls back to the dotted names.
"""

from __future__ import annotations

import ast
import re
import xml.etree.ElementTree as ET  # nosec B405  # parses the junit file pytest itself wrote
from pathlib import Path
from typing import Any

#: The ``type`` pytest gives the ``skipped`` element of an expected failure: it RAN.
XFAIL_TYPE = "pytest.xfail"

#: The ``message`` pytest gives a skipped COLLECTOR; the reason is in the element text.
COLLECTION_SKIPPED = "collection skipped"

_SKIPPED_PREFIX = "Skipped: "
_TRAILING_TUPLE_END = re.compile(r"""['"]\)\s*$""")


def first_line(text: str | None) -> str:
    """The first non-blank-led line of *text*, stripped; ``""`` when there is none."""
    stripped = (text or "").strip()
    return stripped.splitlines()[0].strip() if stripped else ""


def file_of(nodeid: str) -> str:
    """The file part of a node id."""
    return nodeid.split("::", 1)[0]


def node_id(case: ET.Element) -> str:
    """The pytest node id of a junit ``testcase``.

    A COLLECTOR record (``classname=""``, ``name`` the dotted module) is the module path alone.
    """
    name, classname, path = case.get("name", ""), case.get("classname", ""), case.get("file", "")
    if not path:
        return f"{classname}::{name}" if classname else name
    module = path[:-3].replace("/", ".") if path.endswith(".py") else path
    if not classname and name == module:
        return path
    parts = classname[len(module) + 1 :].split(".") if classname.startswith(module + ".") else []
    return "::".join([path, *parts, name])


def _collection_reason(text: str | None) -> str:
    """The reason inside a collection skip's text: ``str((path, lineno, 'Skipped: <reason>'))``."""
    body = (text or "").strip()
    try:
        value = ast.literal_eval(body)
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        value = None
    if isinstance(value, (tuple, list)) and len(value) == 3 and isinstance(value[2], str):
        return first_line(value[2].removeprefix(_SKIPPED_PREFIX))
    found = body.find(_SKIPPED_PREFIX)
    return _TRAILING_TUPLE_END.sub("", first_line(body[found + len(_SKIPPED_PREFIX) :])) if found >= 0 else ""


def skip_reason(skipped: ET.Element) -> str:
    """Why a test was skipped, from the ``message`` attribute and, for a collector, the element text."""
    message = first_line(skipped.get("message"))
    if skipped.get("type") is None and message == COLLECTION_SKIPPED:
        return _collection_reason(skipped.text) or message
    return message


def outcome_of(case: ET.Element) -> str:
    """``failed`` | ``skipped`` | ``passed``. An expected failure ran, so it is not a skip."""
    if case.find("failure") is not None or case.find("error") is not None:
        return "failed"
    skipped = case.find("skipped")
    if skipped is not None and skipped.get("type") != XFAIL_TYPE:
        return "skipped"
    return "passed"


def failures_of(case: ET.Element, nodeid: str) -> list[dict[str, str]]:
    """Each ``failure`` / ``error`` child of *case* as ``{nodeid, kind, message}`` (first line)."""
    found = []
    for kind in ("failure", "error"):
        element = case.find(kind)
        if element is not None:
            message = first_line(element.get("message") or element.text)
            found.append({"nodeid": nodeid, "kind": kind, "message": message})
    return found


def parse_junit(path: Path) -> dict[str, Any]:
    """Executed count, failures, raw skips ``{nodeid, reason}`` and the files that ran, of one junit file."""
    out: dict[str, Any] = {"executed": 0, "failed": [], "skipped": [], "ran": set()}
    for case in ET.parse(path).getroot().iter("testcase"):  # nosec B314  # our own pytest output
        nodeid, outcome = node_id(case), outcome_of(case)
        if outcome == "skipped":
            out["skipped"].append({"nodeid": nodeid, "reason": skip_reason(case.find("skipped"))})
            continue
        out["executed"] += 1
        out["ran"].add(file_of(nodeid))
        out["failed"] += failures_of(case, nodeid)
    return out
