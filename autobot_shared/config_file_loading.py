# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One loader for "read a YAML config, else fall back to built-in defaults" (#14892).

#14892 AC3 asks, of every consumer that reaches a file through
``PATH.CONFIG_DIR``, whether an absent config is distinguishable from a loaded
one. It usually was not: the miss branch returned the same shape as the hit
branch, so a config nobody had written read exactly like a config someone had
reviewed.

This module is the answer for every such consumer. :class:`LoadedConfig` carries
``source`` beside ``values``, so the fact is available programmatically rather
than only in a log line, and the miss branch **never writes**.

That last rule is not decorative. The five ``security/enterprise`` managers each
carried a copy of this body whose miss branch wrote its built-in defaults back to
the path it had just failed to read. Under #14892's broken ``CONFIG_DIR`` that
path did not exist, so the write created a decoy ``infrastructure/shared/config/
security/`` tree — and the *next* boot read those defaults back and reported
success. A one-time miss became a permanent, self-confirming wrong answer, and
the security policy in force was one nobody had written or reviewed.

It lives in ``autobot_shared`` rather than under ``security/enterprise`` because
``security.enterprise.__init__`` eagerly imports all five managers, one of which
needs an optional dependency; a core module such as ``event_manager`` cannot take
that import just to load a YAML file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, Callable, Dict

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


def parse_key_value(handle: IO[str]) -> Dict[str, str]:
    """Parse ``key=value`` lines (``#`` comments and lines without ``=`` skipped), for ``parser=``.

    The one definition of this format; :func:`format_key_value` is its writer.
    """
    parsed: Dict[str, str] = {}
    for line in handle:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def format_key_value(values: Dict[str, Any]) -> str:
    """Render *values* as ``key=value`` lines, the inverse of :func:`parse_key_value`."""
    return "".join(f"{key}={value}\n" for key, value in values.items())


def load_config_file(
    config_path: str | Path,
    defaults_factory: Callable[[], Dict[str, Any]],
    description: str,
    parser: Callable[[IO[str]], Any] = yaml.safe_load,
) -> LoadedConfig:
    """Read *config_path*, falling back to built-in defaults loudly and without writing.

    Args:
        config_path: the YAML file to read.
        defaults_factory: builds the built-in defaults, called only on a miss.
        description: what the config governs, for the log line.
        parser: reads an open text handle into the parsed document. Defaults to
            YAML; pass ``json.load`` for a strict-JSON file so it is not read with
            YAML's laxer grammar (#17855).

    Returns:
        The values plus the ``source`` they came from and the path searched.
    """
    path = Path(config_path)
    try:
        if path.is_file():
            with open(path, "r", encoding="utf-8") as handle:
                values = parser(handle)
            # An empty or all-comments YAML file parses to None. Treating that
            # as a loaded config hands every consumer an empty policy — and
            # every consumer that then calls ``.get()`` on it raises instead.
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
                "%s config not found at %s; using built-in defaults. The settings in force are "
                "the code defaults, not a reviewed file — create that file to change them. "
                "Nothing is written to that path (#14892).",
                description,
                path,
            )
    except (OSError, ValueError, yaml.YAMLError) as exc:  # ValueError covers json.JSONDecodeError
        logger.error("Failed to read %s config at %s: %s; using built-in defaults.", description, path, exc)
    return LoadedConfig(values=defaults_factory(), source=SOURCE_BUILTIN_DEFAULTS, searched_path=path)
