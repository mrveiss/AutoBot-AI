# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one stdlib-only ``.env`` reader (#19232).

Moved out of ``env_drift_detector`` so ``redis_management.database_overrides`` can read the
Redis DB overrides from the project ``.env`` in processes whose venv ships neither
python-dotenv nor pydantic -- the SLM agent (#14278). Stdlib only, on purpose.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

__all__ = ["parse_env_file", "parse_env_text"]


def parse_env_text(text: str) -> Dict[str, str]:
    """Parse ``.env`` content into ``{KEY: value}`` -- the one parser; it never touches a file.

    Handles:
    - Blank lines and comment lines (# ...)
    - KEY=value and KEY="value" and KEY='value'
    - Inline comments stripped with care: after a closing quote (``"2" # note``), or after
      `` #`` in an unquoted value; a ``#`` inside quotes is data

    Callers that must keep their own file read next to a path guard (CodeQL
    py/path-injection wants the guard and the read in one scope, #16229) read the
    text themselves and hand it here.
    """
    result: Dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw_val = line.partition("=")
        key = key.strip()
        if key:
            result[key] = _value(raw_val.strip())
    return result


def _quoted_value(raw_val: str) -> str | None:
    """The text inside *raw_val*'s opening quote and its match, when only blank or a ``#`` comment follows."""
    if raw_val[:1] not in ('"', "'"):
        return None
    end = raw_val.find(raw_val[0], 1)
    if end == -1:
        return None
    rest = raw_val[end + 1 :].strip()
    return raw_val[1:end] if not rest or rest.startswith("#") else None


def _value(raw_val: str) -> str:
    """One stripped value: ``"2" # note`` -> ``2``, ``"a # b"`` -> ``a # b``, ``2 # note`` -> ``2``."""
    quoted = _quoted_value(raw_val)
    if quoted is not None:
        return quoted
    if len(raw_val) >= 2 and raw_val[0] in ('"', "'") and raw_val[-1] == raw_val[0]:
        return raw_val[1:-1]  # surrounding quotes with the same quote inside, as before
    comment_idx = raw_val.find(" #")  # inline comment, unquoted values only
    return raw_val[:comment_idx].strip() if comment_idx != -1 else raw_val


def parse_env_file(env_path: Path) -> Dict[str, str]:
    """Read *env_path* and parse it with :func:`parse_env_text`; an unreadable file is ``{}``, logged."""
    try:
        text = env_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("cannot read .env file %s: %s", env_path, exc)
        return {}
    return parse_env_text(text)
