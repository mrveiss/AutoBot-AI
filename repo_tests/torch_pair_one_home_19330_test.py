# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""torch / torchvision have ONE home: a coupled pair in ``constraints/shared.txt`` (#19330).

Maintainer decision 2026-10-26: 2.14.1 / 0.29.1. The pair used to be pinned in seven places at
three patch levels -- 2.12.1 in the backend image (#19072), 2.14.0 on GPU hosts, 2.14.1 elsewhere.

Requirements files are guarded by ``scripts/check_constraint_drift.py`` (a constrained package
listed with a version fails). This guard covers what that script does not read: a ``torch==`` /
``torchvision>=`` literal in a Dockerfile, a workflow, an Ansible file, a shell script or a
template. Those install the pair with ``-c constraints/shared.txt`` or read the pin from it.
It also holds the pair coupled: torchvision ``0.N`` is built for torch ``2.(N-15)``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

_ROOT = repo_root()
_HOME = "constraints/shared.txt"
_ROOTS = (".github", "docker", "autobot-infrastructure", "autobot-slm-backend/ansible", "scripts", "install.sh")
_SUFFIXES = (".yml", ".yaml", ".sh", ".j2", ".py")
_LITERAL = re.compile(
    r"\btorch(?:vision)?\s*(?:===|==|~=|!=|<=|>=|<|>)\s*v?\d|\btorch(?:vision)?-\d+\.\d+[^\s]*\.whl",
    re.IGNORECASE,
)
_COMMENT = re.compile(r"^\s*#")


def _countable(p: Path) -> bool:
    return p.is_file() and (p.suffix in _SUFFIXES or p.name.startswith("Dockerfile") or p.suffix == ".Dockerfile")


def _sources(root: Path) -> list[Path]:
    found = []
    for top in _ROOTS:
        base = root / top
        if base.is_file():
            found.append(base)
        elif base.is_dir():
            found += [p for p in sorted(base.rglob("*")) if _countable(p) and not p.name.endswith("_test.py")]
    return found


REACH = declare(
    "torch-pair-literals",
    discover=_sources,
    floor=1033,  # mid-window: population 1087, window (979, 1087)
    growth=108,  # ~10%: ordinary growth between repins must not turn an unrelated PR red
    what="workflow, docker, infrastructure, Ansible and script files",
    roots=_ROOTS,
)


def literals(text: str, rel: str) -> list[str]:
    """Each torch/torchvision version literal on a non-comment line of *text*."""
    return [
        f"{rel}:{n}: {m.group(0)}"
        for n, line in enumerate(text.splitlines(), 1)
        if not _COMMENT.match(line)
        for m in _LITERAL.finditer(line.split(" #", 1)[0])
    ]


def pair() -> dict[str, tuple[int, int, int]]:
    text = (_ROOT / _HOME).read_text(encoding="utf-8")
    return {
        name: tuple(int(x) for x in ver.split("."))
        for name, ver in re.findall(r"^(torch|torchvision)==(\d+\.\d+\.\d+)\s*$", text, re.MULTILINE)
    }


def test_the_home_holds_the_decided_coupled_pair() -> None:
    assert pair() == {"torch": (2, 14, 1), "torchvision": (0, 29, 1)}, "maintainer decision 2026-10-26 (#19330)"


def test_torchvision_is_built_for_the_pinned_torch() -> None:
    p = pair()
    assert p["torchvision"][1] - 15 == p["torch"][1], f"torchvision {p['torchvision']} is not torch {p['torch']}'s"


def test_no_torch_literal_outside_the_constraints_file() -> None:
    files = REACH.examined(_ROOT)
    found = [h for p in files for h in literals(p.read_text(encoding="utf-8"), p.relative_to(_ROOT).as_posix())]
    REACH.completed(files)
    assert not found, f"install the pair with -c {_HOME} or read the pin from it (#19330): {found}"


@pytest.mark.parametrize(
    "text",
    [
        "               torch==2.12.1 torchvision==0.27.1 \\\n",
        "    pip install torch>=2.6.0\n",
        "RUN pip install Torch==2.12.1\n",
        '      name: "torchvision==0.29.1"\n',
        "    pip install 'torch>2' 'torchvision<1'\n",
        "    pip install torch!=2.13.0\n",
        "    pip install https://example.invalid/torch-2.14.1-cp314-cp314-linux_x86_64.whl\n",
    ],
)
def test_each_literal_shape_is_flagged(text: str) -> None:
    assert literals(text, "x")


def test_reading_the_pin_and_comments_are_not_flagged() -> None:
    clean = (
        "               torch torchvision -c /app/constraints/shared.txt \\\n"
        "  # torch>=2.11.0 plus transitive vllm, which requires torch==2.10.0\n"
        "pin=\"$(grep -m1 -E '^torch==[0-9][^ #]*' constraints/shared.txt)\"\n"
    )
    assert not literals(clean, "x")
