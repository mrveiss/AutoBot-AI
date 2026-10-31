# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""What a failed git step tells an operator, and whether one retry can cure it (#20089)."""

from __future__ import annotations

import re

from autobot_shared.secret_redaction import redact_content, redact_text

GIT_FAILURE_DETAIL_CHARS = 400
# Failures one retry can cure. An auth failure or a timeout is not one of them.
_TRANSIENT = re.compile(
    r"\.lock|another git process|could not resolve host|temporary failure|connection (reset|refused|timed out)"
    r"|couldn't connect to server|remote end hung up|early eof|returned error: 5\d\d",
    re.IGNORECASE,
)
_GIT_MESSAGE = re.compile(r"^(fatal|error):", re.IGNORECASE)


def redacted(text: str) -> str:
    return redact_content(redact_text(text))


def _bounded(text: str) -> str:
    """Cut to the limit, keeping a transient marker past it: the retry decision reads this text."""
    marker = _TRANSIENT.search(text)
    if marker is None or marker.end() <= GIT_FAILURE_DETAIL_CHARS:
        return text[:GIT_FAILURE_DETAIL_CHARS]
    found = marker.group(0)
    return f"{text[: GIT_FAILURE_DETAIL_CHARS - len(found) - 5]} ... {found}"


def failure_detail(stderr: bytes | None) -> str:
    """One redacted line: git's own fatal/error messages, or all of stderr when it printed none.

    One line because summarize_playbook_failure reads a later ``fatal:`` line as an Ansible host
    failure. Progress output is dropped first, so the bound cannot cut away the message itself.
    """
    lines = [line.strip() for line in (stderr or b"").decode("utf-8", errors="replace").splitlines() if line.strip()]
    messages = [line for line in lines if _GIT_MESSAGE.match(line)] or lines
    return _bounded(redacted("; ".join(messages)))


def is_transient(failure: str) -> bool:
    return bool(_TRANSIENT.search(failure))
