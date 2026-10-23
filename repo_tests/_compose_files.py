# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every tracked docker-compose file, wherever it lives -- one enumeration for every compose guard (#17500).

The ChromaDB guard (#15317) and the exposure/credentials guard (#17500) each enumerated
``docker-compose*.yml`` at the root and ``docker/*.yml``, so the stacks under
``autobot-infrastructure/`` (loki, playwright, playwright-vnc, secure-sandbox) sat outside both:
a Grafana password, a VNC password default and four all-interface ports lived there unseen.
The patterns are git pathspecs, matched by git: in git's default matching ``*`` also crosses
``/``, so ``*docker-compose*.yml`` reaches any depth. Files without a ``services:`` mapping are
dropped, so a stray YAML file cannot inflate the count.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

COMPOSE_FILE_PATTERNS = ("*docker-compose*.yml", "docker/*.yml")


def load_yaml_mapping(path: Path) -> dict:
    """Parse *path* as YAML, tolerating an empty or non-mapping document."""
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


def discover_compose_files(root: Path) -> list[str]:
    """Every tracked compose file under *root* that declares ``services:``, repo-relative."""
    found: set[str] = set()
    for pattern in COMPOSE_FILE_PATTERNS:
        try:
            found.update(tracked_paths(root, pattern))
        except EmptyEnumeration:
            continue
    return sorted(rel for rel in found if "services" in load_yaml_mapping(root / rel))


#: 8 compose files on 2026-10-23: docker-compose.yml, docker-compose.hardened.yml,
#: docker-compose.override.example.yml and docker/mcp-bridges.yml, plus the loki stack and the
#: playwright, playwright-vnc and secure-sandbox stacks under autobot-infrastructure/.
COMPOSE_FILES = declare(
    "compose-files",
    discover=discover_compose_files,
    floor=7,
    growth=3,
    what="tracked docker-compose files at any depth (#15317, #17500)",
)
