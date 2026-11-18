# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Shared by the machine-queue tests (#20518, #21098): the hook's queue functions, and a fake load source.

No test may read the real load average: it would wait whenever the host is busy. Every script that runs
``machine_slot_wait`` points ``AUTOBOT_MACHINE_SLOT_LOADAVG`` at a file written here.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root

HOOK = (repo_root() / "tools/git-hooks/pre-push").read_text(encoding="utf-8")
LOW_LOAD = "0.10"


def hook_functions(*names: str) -> str:
    """The hook's own text of the named shell functions, or of the whole queue (every ``machine_slot_*``)."""
    wanted = names or tuple(re.findall(r"^(machine_slot_\w+)\(\) \{$", HOOK, re.MULTILINE))
    return "\n".join(re.search(rf"^{n}\(\) \{{\n(?:.*\n)*?\}}$", HOOK, re.MULTILINE).group(0) for n in wanted)


def fake_load(path: Path, value: str = LOW_LOAD) -> Path:
    path.write_text(f"{value} 1.00 1.00 1/100 1234\n", encoding="utf-8")
    return path
