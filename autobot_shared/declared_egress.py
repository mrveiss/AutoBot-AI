# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Egress that happens inside a library call the AST detector cannot see (#17576, AC4).

``repo_tests/egress_default_guard_17576_test.py`` finds outbound HTTP by looking for HTTP-client
calls. Some network traffic is made *by a library on our behalf*: ``recognize_google`` posts audio
to a fixed Google endpoint from inside the ``speech_recognition`` package, and no HTTP call appears
in our source. Such a site is declared here instead of being silently absent from the census, so
the guard's population is "everything the detector sees plus everything declared" rather than
"everything the detector happens to see".

An entry is a claim about the code, and ``declared_egress_test.py`` holds it to that: the path must
exist and the symbol must still appear in it, so a removed or renamed call turns the entry red
rather than leaving a stale exemption.

Tracking: #18229 (route both speech paths through the guarded path, or keep them declared with the
destination fixed). Parent: #17576.
"""

from __future__ import annotations

from typing import NamedTuple


class DeclaredEgress(NamedTuple):
    """One library-mediated outbound call."""

    path: str
    symbol: str
    destination: str
    reason: str
    issue: int


DECLARED_EGRESS: tuple[DeclaredEgress, ...] = (
    DeclaredEgress(
        path="autobot-backend/voice_processing/speech_recognition.py",
        symbol="recognize_google",
        destination="Google Web Speech API (fixed endpoint inside the speech_recognition package)",
        reason="the Generic provider sends user audio to an external recogniser; no HTTP call is visible in our source",
        issue=18229,
    ),
    DeclaredEgress(
        path="autobot-backend/voice_interface.py",
        symbol="recognize_google",
        destination="Google Web Speech API (fixed endpoint inside the speech_recognition package)",
        reason=(
            "user audio sent to an external recogniser. deferred: file owned by "
            "issue-17855-shared-authority-callers, so the conversion lands after that branch merges"
        ),
        issue=18229,
    ),
)
