# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Install-root-relative directory names that are safe to hand to a deletion (#22030).

Role removal passes a directory to a playbook that deletes ``<install root>/<dir>``. A value of ``.``, ``..``, an
absolute path or anything containing a ``..`` segment would delete the root or reach outside it, so every producer
and the python consumer go through :func:`safe_relative_dir` and the playbook repeats the same checks.
"""

from __future__ import annotations

import posixpath
import re

from autobot_shared.fleet_constants import FLEET_INSTALL_ROOT

#: The characters the playbook accepts too (``remove-role.yml``): no whitespace, quotes or shell metacharacters.
_PLAIN = re.compile(r"[A-Za-z0-9._+@/-]+")


def safe_relative_dir(value: object) -> str | None:
    """``value`` normalised ("a/b"), or None unless it is a non-empty relative path of plain segments."""
    if not isinstance(value, str) or not value or value.startswith("/") or not _PLAIN.fullmatch(value):
        return None
    segments = value.rstrip("/").split("/")
    if not segments or any(seg in ("", ".", "..") for seg in segments):
        return None
    return "/".join(segments)


def relative_to_root(path: object, root: str = FLEET_INSTALL_ROOT) -> str | None:
    """``path`` relative to ``root`` when it is strictly inside it (and safe), else None."""
    if not isinstance(path, str) or not path:
        return None
    normalised = path.rstrip("/")
    if posixpath.normpath(normalised) != normalised:  # a "." / ".." / "//" segment: refuse rather than resolve
        return None
    prefix = root.rstrip("/") + "/"
    return safe_relative_dir(normalised[len(prefix) :]) if normalised.startswith(prefix) else None


def overlaps(first: str, second: str) -> bool:
    """Whether two relative directories are the same or one contains the other."""
    return first == second or first.startswith(second + "/") or second.startswith(first + "/")
