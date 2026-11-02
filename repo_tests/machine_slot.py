# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""One machine-wide queue for heavy local work, at lower priority (#20518, owner decision).

The slots are flock(2) locks on files the pre-push hook's ``machine_slot_wait`` takes too, so hooks,
``repin_reach_floors.py`` and big pytest runs share one limit. A dead holder's lock goes with it, and
waiting is never bounded: a queued run does not time out. CI has its own runners and never queues.
The limit is a setting until it is measured.
"""

from __future__ import annotations

import fcntl
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from autobot_shared.env_utils import env_float, env_int

HELD_ENV = "AUTOBOT_MACHINE_SLOT_HELD"
#: Fewer tests than this in a run without xdist stay out of the queue: running the test you changed is cheap.
BIG_RUN_TESTS = env_int("AUTOBOT_MACHINE_SLOT_BIG_RUN", 100)
_NICENESS = 10
_held: Optional[int] = None


def _slot_paths() -> list[Path]:
    runtime = os.getenv("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    root = Path(os.getenv("AUTOBOT_MACHINE_SLOT_DIR") or Path(runtime) / "autobot-machine-slots")
    root.mkdir(parents=True, exist_ok=True)
    return [root / f"slot-{i}" for i in range(1, env_int("AUTOBOT_MACHINE_SLOTS", 4) + 1)]


def _try_take(path: Path) -> Optional[int]:
    fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return fd


def _lower_priority() -> None:
    os.nice(_NICENESS)
    if shutil.which("ionice"):
        subprocess.run(["ionice", "-c", "3", "-p", str(os.getpid())], check=False, capture_output=True)


def acquire() -> None:
    """Wait for a slot and keep it until this process ends; nothing when CI or a parent already holds one."""
    global _held
    if os.getenv("CI") or os.getenv(HELD_ENV) or _held is not None:
        return
    told = False
    while _held is None:
        _held = next((fd for fd in map(_try_take, _slot_paths()) if fd is not None), None)
        if _held is None:
            if not told:
                sys.stderr.write("Waiting for a machine slot (#20518)...\n")
                told = True
            time.sleep(env_float("AUTOBOT_MACHINE_SLOT_POLL", 5.0))
    os.environ[HELD_ENV] = "1"
    _lower_priority()


def pytest_configure(config: Any) -> None:
    """A parallel run is big by definition; its workers inherit the held slot."""
    if config.getoption("numprocesses", None):
        acquire()


def pytest_collection_finish(session: Any) -> None:
    if len(session.items) >= BIG_RUN_TESTS:
        acquire()
