# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One loader for the enterprise-security YAML configs (#14892).

Five managers each open a policy file under ``PATH.get_config_path("security", ...)``.
Four of them shared a copy of the same ``_load_config`` body, whose miss branch
wrote its built-in defaults back to the path it had just failed to read. Under
#14892's broken ``CONFIG_DIR`` that path did not exist, so the write created a
decoy ``infrastructure/shared/config/security/`` tree — and from then on the
*next* boot read those defaults back and reported success. A one-time miss
became a permanent, self-confirming wrong answer, and the security policy
actually in force was one nobody had written or reviewed.

So the miss branch here does two things differently: it never writes, and it
says so at WARNING naming the exact path it looked for. `source` makes the same
fact available programmatically, which is what `utils/error_catalog.py` — the
one consumer of `CONFIG_DIR` that was already distinguishable — does with its
own `source`/`searched_paths` attributes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict

import yaml

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: ``source`` values. A caller comparing against these does not have to
#: re-derive whether the file was there.
SOURCE_FILE = "file"
SOURCE_BUILTIN_DEFAULTS = "builtin-defaults"


@dataclass(frozen=True)
class LoadedConfig:
    """A config plus where it actually came from."""

    values: Dict[str, Any]
    source: str
    searched_path: Path

    @property
    def loaded_from_file(self) -> bool:
        """True only when the configured file was read."""
        return self.source == SOURCE_FILE


def load_security_config(
    config_path: str | Path,
    defaults_factory: Callable[[], Dict[str, Any]],
    description: str,
) -> LoadedConfig:
    """Read *config_path*, falling back to built-in defaults loudly and without writing.

    Args:
        config_path: the YAML file to read.
        defaults_factory: builds the built-in defaults, called only on a miss.
        description: what the config governs, for the log line.
    """
    path = Path(config_path)
    try:
        if path.is_file():
            with open(path, "r", encoding="utf-8") as handle:
                values = yaml.safe_load(handle)
            # An empty or all-comments YAML file parses to None. Treating that
            # as a loaded config hands every consumer an empty policy.
            if isinstance(values, dict):
                return LoadedConfig(values=values, source=SOURCE_FILE, searched_path=path)
            logger.warning(
                "%s config at %s parsed to %s, not a mapping; using built-in defaults instead.",
                description,
                path,
                type(values).__name__,
            )
        else:
            logger.warning(
                "%s config not found at %s; using built-in defaults. The policy in force is "
                "the code default, not a reviewed file — create that file to change it. "
                "Nothing is written to that path (#14892).",
                description,
                path,
            )
    except (OSError, yaml.YAMLError) as exc:
        logger.error("Failed to read %s config at %s: %s; using built-in defaults.", description, path, exc)
    return LoadedConfig(values=defaults_factory(), source=SOURCE_BUILTIN_DEFAULTS, searched_path=path)
