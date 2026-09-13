# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15075 — every key of ``_COMPONENT_PYTHON_TARGET`` must actually be consulted.

The map used to carry an ``autobot-npu-worker`` entry that nothing could read.
Its two readers (``_ensure_target_python_installed``, ``_ensure_venv_python``)
are called only from ``_run_post_sync_steps``'s ``if component in
_COMPONENT_PIP_PATHS:`` branch, and that map has never held the worker — the
exclusion is deliberate (MVA-79: the backend branch recreates the venv, which
would wipe the venv the chroma binary lives in). So the entry read as the
single authoritative interpreter for a component it could not reach: editing
it looked like a version bump and changed nothing on the host, which is the
silently-unapplied-config failure #13747 is about.

What the guard asserts, in the two directions that can go wrong:

* **reachability** — every key is in ``_COMPONENT_PIP_PATHS`` (the gate the
  readers sit behind), and passing that key through a reader produces a step
  naming the interpreter it maps to. A fourth entry dropped into the same dead
  slot fails here rather than sitting inert;
* **vacuity** — the map, and the set of keys the loop iterates, are asserted
  non-empty first. A test that enumerates and asserts per item passes when the
  enumeration is empty, which is how #15087's router guard came to assert
  nothing; emptying this map must fail this file, not silence it.

``test_worker_dispatch_never_reaches_the_python_target_readers`` pins the
premise itself: it is the dispatch gate, not a convention, that makes a
non-``_COMPONENT_PIP_PATHS`` key unreadable.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

# ---------------------------------------------------------------------------
# #12572: import api.code_sync with real Pydantic schema stand-ins installed
# then removed — see _code_sync_import.py for why this dance is necessary.
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _code_sync_import import import_code_sync  # noqa: E402

import_code_sync()

import asyncio  # noqa: E402

from api import code_sync  # noqa: E402
from api.code_sync import (  # noqa: E402
    _COMPONENT_PIP_PATHS,
    _COMPONENT_PYTHON_TARGET,
    _WORKER_COMPONENTS,
    _ensure_target_python_installed,
    _run_post_sync_steps,
)

#: Path of the ansible tasks file the map's comment now points readers at for
#: the NPU worker's interpreter. Asserted to exist and to still pin 3.14, so
#: the pointer cannot rot into a second dead reference (#15075 AC2).
_NPU_ROLE_TASKS = Path(__file__).resolve().parents[2] / "ansible" / "roles" / "npu-worker" / "tasks" / "main.yml"


def _run(coro):
    return asyncio.run(coro)


def test_the_python_target_map_is_not_empty() -> None:
    """An empty map would make every per-key assertion below vacuous (#15087)."""
    assert _COMPONENT_PYTHON_TARGET, "_COMPONENT_PYTHON_TARGET is empty — the guard would assert nothing"


def test_every_python_target_key_sits_behind_the_branch_that_reads_it() -> None:
    """Keys outside _COMPONENT_PIP_PATHS are unreachable: the readers are gated on it."""
    unreachable = sorted(set(_COMPONENT_PYTHON_TARGET) - set(_COMPONENT_PIP_PATHS))
    assert not unreachable, (
        f"{unreachable} cannot be read: _ensure_target_python_installed and _ensure_venv_python "
        "are called only from _run_post_sync_steps's `if component in _COMPONENT_PIP_PATHS:` "
        "branch. Add the component there (only if the backend-shaped steps genuinely apply — "
        "MVA-79), or decide its interpreter where its ansible role does (#15075)."
    )


def test_every_python_target_value_reaches_an_observable_step() -> None:
    """Each mapped interpreter must show up in the steps log for its own component."""
    components = sorted(_COMPONENT_PYTHON_TARGET)
    assert components, "no components to check — see test_the_python_target_map_is_not_empty (#15087)"
    for component in components:
        target = _COMPONENT_PYTHON_TARGET[component]
        steps: list[str] = []
        with patch.object(code_sync.shutil, "which", return_value=f"/usr/bin/{target}"):
            _run(_ensure_target_python_installed(component, steps))
        assert any(target in step for step in steps), (
            f"{component}: nothing in the steps log names {target}, so the mapped value was " "never read (#15075)"
        )


def test_worker_dispatch_never_reaches_the_python_target_readers(tmp_path) -> None:
    """The premise: a worker component is routed past both readers entirely.

    This is what makes an entry outside _COMPONENT_PIP_PATHS dead rather than
    merely unconventional — and it is preserved deliberately (MVA-79), so it is
    asserted rather than assumed.
    """
    assert "autobot-npu-worker" in _WORKER_COMPONENTS
    with (
        patch.object(code_sync, "_compute_deps_changed", AsyncMock(return_value=False)),
        patch.object(code_sync, "_snapshot_component", AsyncMock(return_value=None)),
        patch.object(code_sync, "_run_post_sync_worker_branch", AsyncMock(return_value=True)) as worker,
        patch.object(code_sync, "_ensure_target_python_installed", AsyncMock()) as ensure_target,
        patch.object(code_sync, "_ensure_venv_python", AsyncMock(return_value=False)) as ensure_venv,
    ):
        _run(_run_post_sync_steps("autobot-npu-worker", str(tmp_path), str(tmp_path), restart=False))
    assert worker.await_count == 1, "the worker branch is what handles autobot-npu-worker"
    assert ensure_target.await_count == 0
    assert ensure_venv.await_count == 0


def test_the_npu_worker_interpreter_is_decided_where_the_comment_says() -> None:
    """The map's comment redirects a version bump to the ansible role; keep it true."""
    assert _NPU_ROLE_TASKS.is_file(), f"{_NPU_ROLE_TASKS.name} moved — update the comment in code_sync.py (#15075)"
    body = _NPU_ROLE_TASKS.read_text(encoding="utf-8")
    assert "python3.14" in body, (
        "roles/npu-worker/tasks/main.yml no longer pins python3.14. That file, not "
        "_COMPONENT_PYTHON_TARGET, is where the NPU worker's interpreter is decided (#13747, #15075)."
    )
