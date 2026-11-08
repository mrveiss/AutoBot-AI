# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one atomic file replacement and dry-run report for generator scripts (#18964).

``write_atomically`` and ``report_output`` were declared verbatim in
``enhance_workflow_ui.py`` and ``npu_worker_design.py``; ``write_atomically`` was
declared a third time in ``optimize_agents.py``.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_NEW_FILE_MODE = 0o644


def write_atomically(file_path: Path, content: str) -> None:
    """Replace ``file_path``'s contents with ``content`` via temp-then-rename.

    A write that fails or is interrupted partway through would otherwise
    leave a truncated file on disk (#14546, #14563). Writing to a sibling temp
    file first and renaming it into place means ``file_path`` is only ever
    replaced once the new content is fully written -- the rename is atomic on
    the same filesystem, and a crash before it leaves any pre-existing file
    untouched. An existing file keeps its mode; a new one gets 0o644.
    """
    original_mode = file_path.stat().st_mode if file_path.exists() else _NEW_FILE_MODE
    fd, tmp_name = tempfile.mkstemp(dir=file_path.parent, prefix=f".{file_path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(content)
        os.chmod(tmp_name, original_mode)
        os.replace(tmp_name, file_path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def report_output(target: Path, content: str, apply_changes: bool) -> None:
    """Print what generating ``target`` would change (or just changed).

    Plain stdout is the contract of the generator CLIs that call this, so the
    ``print`` lines carry the documented exemption rather than going to a logger.
    """
    verb = "Wrote" if apply_changes else "Would write"
    if not target.exists():
        print(f"  {verb} {target} ({len(content)} bytes, new file)")  # noqa: print
        return

    existing = target.read_text(encoding="utf-8")
    if existing == content:
        print(f"  (unchanged) {target}: content already up to date")  # noqa: print
        return

    print(
        f"  {verb} {target} ({len(existing)} -> {len(content)} bytes, existing file would be replaced)"
    )  # noqa: print
