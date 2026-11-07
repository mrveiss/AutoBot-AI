# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""What a failed git step tells an operator, and whether one retry can cure it (#20089)."""

from __future__ import annotations

import re

from autobot_shared.secret_redaction import redact_content, redact_text

GIT_FAILURE_DETAIL_CHARS = 400
# Failures one retry can cure, as git reports them. An auth failure is not one, nor is the step's own
# timeout in _run_git, which never reaches this text as git output. "connection timed out" is the network.
_TRANSIENT = re.compile(
    r"\.lock|another git process|could not resolve host|temporary failure|connection (reset|refused|timed out)"
    r"|couldn't connect to server|remote end hung up|early eof|returned error: 5\d\d",
    re.IGNORECASE,
)
_GIT_MESSAGE = re.compile(r"^(fatal|error):", re.IGNORECASE)


def redacted(text: str) -> str:
    return redact_content(redact_text(text))


def _bounded(messages: list[str]) -> str:
    """Join within the limit: each message keeps a share, and a transient marker past it is carried.

    The retry decision reads this text, so it is classified on the full text before anything is cut.
    """
    text = "; ".join(messages)
    if len(text) <= GIT_FAILURE_DETAIL_CHARS:
        return text
    marker = _TRANSIENT.search(text)
    found = f" ... {marker.group(0)}" if marker else ""
    room = GIT_FAILURE_DETAIL_CHARS - len(found)
    share = max((room - 2 * (len(messages) - 1)) // len(messages), 1)  # 2: the "; " between them
    return "; ".join(message[:share] for message in messages)[:room] + found


def failure_detail(stderr: bytes | None) -> str:
    """One redacted line: git's own fatal/error messages, or all of stderr when it printed none.

    One line because summarize_playbook_failure reads a later ``fatal:`` line as an Ansible host
    failure. Progress output is dropped first, so the bound cannot cut away the message itself.
    """
    lines = [line.strip() for line in (stderr or b"").decode("utf-8", errors="replace").splitlines() if line.strip()]
    messages = [line for line in lines if _GIT_MESSAGE.match(line)] or lines
    return _bounded([redacted(message) for message in messages])


def is_transient(failure: str) -> bool:
    return bool(_TRANSIENT.search(failure))
