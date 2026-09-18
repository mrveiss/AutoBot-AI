# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Replay-log redaction catches a credential in free text, not just a named key (#13708).

Its own module rather than a method on ``test_replay.TestLogToDict``: that file is
grandfathered at its size ceiling, and a grandfathered file may not grow (#14236) --
the ratchet's rule is to split, not to raise the ceiling.

Uses the real ``llm_shared.credential_redaction``, not the fake-module stub that
``test_replay``'s ``test_redact_pii_strips_sensitive_key`` installs. That stub is
scoped to its own test (saved and restored in a ``finally``), so it cannot leak
here -- and proving the real path is exactly what this test is for.
"""

from llc.services.replay_service import _log_to_dict
from llc.tests.test_replay import _make_log


def test_redact_pii_catches_a_credential_in_free_text_not_just_a_named_key():
    """#13708: closes the gap the module docstring used to document as absent."""
    # Fabricated and never issued. It must look like a real password or the
    # redactor has nothing to catch, so detect-secrets' KeywordDetector is right
    # about its shape and wrong about it being a secret (#13708).
    password_shaped = "Xy9#mK2!Zq"  # pragma: allowlist secret
    body = f"Onboarding email: your temporary password is {password_shaped}. Please change it."
    log = _make_log(inputs_snapshot={"title": "task"}, output_text=body)

    d = _log_to_dict(log, redact_pii=True)

    assert password_shaped not in d["output_text"]
    assert "Please change it." in d["output_text"]
