# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Copies of the system-knowledge templates in the editable runtime directory (#18556).

The runtime dir (``system_knowledge_dirs().runtime``) is the operator-editable copy, so the import must never
replace an operator's edit. A manifest beside the copies records the hash of what the import last
wrote; a runtime file is overwritten only while it still hashes to that record.
"""

import hashlib
import json
import shutil
from pathlib import Path
from typing import Callable

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

MANIFEST_NAME = ".template_hashes.json"

COPIED = "copied"
UNCHANGED = "unchanged"
KEPT_EDITED = "kept_edited"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_manifest(runtime_dir: Path) -> dict:
    try:
        return json.loads((runtime_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def sync_runtime_copy(template: Path, runtime_dir: Path, relative: str) -> str:
    """Bring ``runtime_dir/relative`` up to ``template`` unless the operator changed it.

    Returns ``COPIED``, ``UNCHANGED`` (already identical) or ``KEPT_EDITED`` (the runtime file
    matches neither the new template nor the last copy the import made -- skipped with a warning,
    never overwritten). Blocking: call through ``asyncio.to_thread``.
    """
    return _sync(runtime_dir, relative, _digest(template), lambda target: shutil.copy2(template, target))


def sync_runtime_text(text: str, runtime_dir: Path, relative: str) -> str:
    """Same keep-if-edited rule for generated content (the fallback default templates)."""
    data = text.encode("utf-8")
    return _sync(runtime_dir, relative, hashlib.sha256(data).hexdigest(), lambda target: target.write_bytes(data))


def _sync(runtime_dir: Path, relative: str, new: str, write: Callable[[Path], object]) -> str:
    target = runtime_dir / relative
    manifest = _load_manifest(runtime_dir)
    if target.exists():
        current = _digest(target)
        if current == new:
            if manifest.get(relative) != new:
                _save_manifest(runtime_dir, {**manifest, relative: new})
            return UNCHANGED
        if current != manifest.get(relative):
            logger.warning(
                "Runtime copy %s differs from the template and from the last import; keeping it. "
                "Delete it to take the template.",
                target,
            )
            return KEPT_EDITED
    target.parent.mkdir(parents=True, exist_ok=True)
    write(target)
    _save_manifest(runtime_dir, {**manifest, relative: new})
    return COPIED


def _save_manifest(runtime_dir: Path, manifest: dict) -> None:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
