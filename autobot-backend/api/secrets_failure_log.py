# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A secrets-handler failure description that names the cause, never a value (#19476).

#18648 pinned handler error logs to the exception class name because an
arbitrary exception text can echo a secret (``RuntimeError("echo <value>")``).
A class name alone left #19476's ``TypeError`` undiagnosable. This keeps the
rule and adds only what cannot carry a value:

* the innermost frame's ``file:line in function`` (source coordinates), and
* the exception message, only for classes whose text describes *types and
  attribute names*, never operand values (``Object of type datetime is not
  JSON serializable``).
"""

from __future__ import annotations

import os
import traceback

#: Messages of these classes name types/attributes, not values.
_MESSAGE_SAFE = (TypeError, AttributeError)


def describe_failure(exc: BaseException) -> str:
    """Return ``Class[: message] at file:line in func`` for a log line."""
    text = type(exc).__name__
    if type(exc) in _MESSAGE_SAFE:
        text += f": {exc}"
    frames = traceback.extract_tb(exc.__traceback__)
    if frames:
        last = frames[-1]
        text += f" at {os.path.basename(last.filename)}:{last.lineno} in {last.name}"
    return text
