# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Where the system-knowledge templates and their runtime copies live (#18556, #18577).

The ONE tracked tree of templates is read-only to the import. The runtime copies and backups the
managers write live under ``<project root>/data`` (gitignored). Both come from the same
``project_root()`` so they cannot disagree about which checkout they belong to.
"""

from dataclasses import dataclass
from pathlib import Path

from autobot_shared.paths import project_root

SYSTEM_KNOWLEDGE_TEMPLATES_REL = Path("autobot-backend") / "resources" / "knowledge"
SYSTEM_KNOWLEDGE_RUNTIME_REL = Path("data") / "system_knowledge"
SYSTEM_KNOWLEDGE_BACKUP_REL = Path("data") / "system_knowledge_backups"


@dataclass(frozen=True)
class SystemKnowledgeDirs:
    """The three directories of the system-knowledge import, all under one root."""

    templates: Path  # tracked, read-only to the import
    runtime: Path  # gitignored, editable copies
    backup: Path  # gitignored, pre-reinstall snapshots


def system_knowledge_dirs(root: Path | None = None) -> SystemKnowledgeDirs:
    """Template, runtime and backup directories resolved from ONE root (default: ``project_root()``)."""
    root = root if root is not None else project_root()
    return SystemKnowledgeDirs(
        templates=root / SYSTEM_KNOWLEDGE_TEMPLATES_REL,
        runtime=root / SYSTEM_KNOWLEDGE_RUNTIME_REL,
        backup=root / SYSTEM_KNOWLEDGE_BACKUP_REL,
    )


def system_knowledge_templates_dir() -> Path:
    """The system-knowledge template directory under the resolved project root."""
    return system_knowledge_dirs().templates
