# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The compose-fleet-nodes default has ONE home: the SLM config (#19323).

``SLM_COMPOSE_NODES`` defaulted to ``true`` in ``docker-compose.yml`` and ``false`` in
``compose_fleet.py``. Now ``Settings.compose_nodes_enabled`` (``autobot-slm-backend/config.py``)
owns it -- unset follows the deployment mode, on for docker_local, off on a bare host -- and
compose passes the variable through by name only. This guard fails on any reader or file that
restates a value: a compose ``SLM_COMPOSE_NODES=...`` / ``${SLM_COMPOSE_NODES:-...}`` or a Python
``getenv`` / ``environ`` read with its own fallback.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

_ROOT = repo_root()
_ROOTS = ("autobot-slm-backend", "autobot-infrastructure", "docker", "docker-compose.yml")
_SUFFIXES = (".py", ".yml", ".yaml", ".sh", ".env", ".j2")
_TEST = re.compile(r"(^|/)(tests?/|test_[^/]*\.py$|[^/]*_test\.py$|conftest\.py$)")
#: A value next to the name (``=``, ``: ``, ``:-``, ``-``, ``:=``, empty included), or a Python read
#: of the name by any reader (``getenv``, ``environ.get/setdefault/pop/[...]``, the registry ``env()``),
#: possibly split across lines.
_RESTATED = re.compile(
    r"\bSLM_COMPOSE_NODES['\"]?[ \t]*(?::-|:=|:(?=[ \t]|$)|=|-(?=[^-\s]))"
    r"|(?:\bgetenv\s*\(|\benviron\.(?:get|setdefault|pop)\s*\(|\benviron\s*\[|(?<![\w.])env\s*\()"
    r"\s*['\"]SLM_COMPOSE_NODES['\"]",
    re.S | re.M,
)


def _sources(root: Path) -> list[Path]:
    found = []
    for top in _ROOTS:
        base = root / top
        if base.is_file():
            found.append(base)
        elif base.is_dir():
            found += [
                p
                for p in sorted(base.rglob("*"))
                if p.suffix in _SUFFIXES and not _TEST.search(p.relative_to(root).as_posix())
            ]
    return found


REACH = declare(
    "compose-nodes-restated-default",
    discover=_sources,
    floor=1056,  # mid-window: population 1112, window (1000, 1112)
    growth=112,  # ~10%: ordinary growth between repins must not turn an unrelated PR red
    what="non-test SLM, infrastructure and docker files",
    roots=_ROOTS,
)


_COMMENT_LINE = re.compile(r"^[ \t]*#.*$", re.M)


def restated(text: str, rel: str) -> list[str]:
    """Each restated default in *text*; a comment line documents the override and is not read."""
    code = _COMMENT_LINE.sub("", text)  # blanked, not removed: line numbers hold
    return [f"{rel}:{code.count(chr(10), 0, m.start()) + 1}: {m.group(0)}" for m in _RESTATED.finditer(code)]


def test_no_file_restates_the_compose_nodes_default() -> None:
    files = REACH.examined(_ROOT)
    found = [h for p in files for h in restated(p.read_text(encoding="utf-8"), p.relative_to(_ROOT).as_posix())]
    REACH.completed(files)
    assert not found, f"the default lives in Settings.compose_nodes_enabled (#19323): {found}"


@pytest.mark.parametrize(
    "text",
    [
        "      - SLM_COMPOSE_NODES=${SLM_COMPOSE_NODES:-true}\n",
        "      - SLM_COMPOSE_NODES=true\n",
        'flag = os.getenv("SLM_COMPOSE_NODES", "false")\n',
        "flag = os.environ.get('SLM_COMPOSE_NODES')\n",
        'flag = os.environ["SLM_COMPOSE_NODES"]\n',
        '      SLM_COMPOSE_NODES: "true"\n',
        "      SLM_COMPOSE_NODES:\n",
        "      - SLM_COMPOSE_NODES=\n",
        "      - SLM_COMPOSE_NODES=${SLM_COMPOSE_NODES-true}\n",
        'os.environ.setdefault("SLM_COMPOSE_NODES", "1")\n',
        'os.environ.pop("SLM_COMPOSE_NODES", None)\n',
        'flag = os.environ.get(\n    "SLM_COMPOSE_NODES"\n)\n',
        'flag = env("SLM_COMPOSE_NODES")\n',
    ],
)
def test_each_restated_shape_is_flagged(text: str) -> None:
    assert restated(text, "x")


def test_a_pass_through_by_name_is_not_flagged() -> None:
    assert not restated("      - SLM_COMPOSE_NODES\n      # SLM_COMPOSE_NODES=true|false overrides\n", "x")
