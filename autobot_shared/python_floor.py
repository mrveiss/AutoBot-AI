# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Interpreter floor enforcement (#20903).

The floor is declared once, in ``<repo>/.python-version``. This module reads it
and refuses to let ``autobot_shared`` import on anything older, with an error
that says what to run instead. Without it, an older interpreter dies on the
first 3.11+ construct deep in the tree (for example the possessive quantifier
in ``prompt_rules``: ``re.error: multiple repeat``), which names the symptom
and not the cause.

Dependency-free on purpose (``sys`` and ``pathlib`` only) and written to parse
and run on 3.8+, because it must produce its message on exactly the
interpreters it rejects: no ``match``, no runtime ``X | Y``, no possessive
regex.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: Last-resort floor if ``.python-version`` cannot be read on a deployed host.
#: Swept by ``repo_tests/python_version_declaration_drift_test.py`` so it cannot
#: drift from the SSOT file.
_FALLBACK_PYTHON_FLOOR = (3, 14)

_REPO_ROOT = Path(__file__).resolve().parent.parent


class UnsupportedPythonError(RuntimeError):
    """The running interpreter is older than the declared floor."""


def declared_python_version():
    """``(major, minor)`` read from ``.python-version``, or ``None`` if unreadable."""
    try:
        text = (_REPO_ROOT / ".python-version").read_text(encoding="utf-8").strip()
        major, minor = text.split(".")[:2]
        return int(major), int(minor)
    except (OSError, ValueError):
        return None


def minimum_python_version():
    """The declared floor; the swept fallback if ``.python-version`` is unreadable."""
    declared = declared_python_version()
    return _FALLBACK_PYTHON_FLOOR if declared is None else declared


def require_supported_python(version=None, executable=None):
    """Raise :class:`UnsupportedPythonError` unless ``version`` meets the floor."""
    version = tuple(sys.version_info) if version is None else tuple(version)
    executable = sys.executable if executable is None else executable
    floor = minimum_python_version()
    if tuple(version[:2]) >= floor:
        return
    wanted = "%d.%d" % floor
    found = ".".join(str(part) for part in version[:3])
    raise UnsupportedPythonError(
        "AutoBot requires Python %s or newer (floor declared in .python-version); "
        "this is Python %s at %s. Run it with the project interpreter instead: "
        "%s/venv/bin/python or ~/.venv-python-suite/bin/python (built by "
        "scripts/setup-ci-parity-env.sh). On a deployed host, install.sh / the SLM "
        "self-update provision python%s. See issue #20903." % (wanted, found, executable, _REPO_ROOT, wanted)
    )
