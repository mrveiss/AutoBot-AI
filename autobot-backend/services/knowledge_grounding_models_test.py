# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15005 — VerificationMethod pins the claim-verification vocabulary.

Ground-truthed against the tree, not the issue body: #15005 named
``kb_lookup``/``external_research``/``causal_inference`` as the three
in-use values and missed that ``services/grounded_agent.py`` actually
produces ``claim_verifier_rag``, never ``external_research`` or
``causal_inference``. See ``VerificationMethod``'s docstring for the full
per-member evidence and the fact-provenance boundary this deliberately does
not cross.
"""

from __future__ import annotations

import subprocess  # nosec B404  # fixed argv, no shell, no caller input
from pathlib import Path

from services.knowledge_grounding_models import VerificationMethod

REPO_ROOT = Path(__file__).resolve().parents[2]

VERIFICATION_METHOD_UNION = {
    ("KB_LOOKUP", "kb_lookup"),
    ("CLAIM_VERIFIER_RAG", "claim_verifier_rag"),
    ("EXTERNAL_RESEARCH", "external_research"),
    ("CAUSAL_INFERENCE", "causal_inference"),
}

# The one docstring prose block exempt from the no-bare-literal scan below —
# a ```json response-body example in an endpoint docstring, read rather than
# executed. Rewriting it to an enum read would produce invalid JSON (the
# exact #14956 regression the severity ratchet now guards against).
_DELIBERATE_PROSE_FILE = "autobot-backend/api/knowledge_grounding.py"

_TRACKED_PY_FLOOR = 3000


def test_verification_method_is_exactly_the_produced_and_reserved_union():
    members = {(m.name, m.value) for m in VerificationMethod}
    assert members == VERIFICATION_METHOD_UNION


def test_the_two_produced_members_resolve_from_their_wire_spellings():
    """kb_lookup and claim_verifier_rag are already on the wire (VerifiedClaim.to_dict)."""
    assert VerificationMethod("kb_lookup") is VerificationMethod.KB_LOOKUP
    assert VerificationMethod("claim_verifier_rag") is VerificationMethod.CLAIM_VERIFIER_RAG


def _tracked_python_files() -> list[str]:
    out = subprocess.run(  # nosec B603  # fixed argv, no shell
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in out.stdout.splitlines() if line]


def _bare_literal_files() -> set[str]:
    """Files (outside the enum definition) containing a bare vocabulary literal."""
    needles = tuple(f'"{value}"' for _, value in VERIFICATION_METHOD_UNION)
    offenders: set[str] = set()
    for rel in _tracked_python_files():
        if not (rel.startswith("autobot-backend/") or rel.startswith("autobot_shared/")):
            continue
        if rel == "autobot-backend/services/knowledge_grounding_models.py":
            continue
        try:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        except OSError:
            continue
        if any(needle in text for needle in needles):
            offenders.add(rel)
    return offenders


def test_the_enumeration_reaches_the_repo():
    assert len(_tracked_python_files()) >= _TRACKED_PY_FLOOR


def test_no_bare_verification_method_literal_outside_the_enum_or_prose():
    """#15005 AC: a grep confirms no bare literal remains outside the enum."""
    offenders = _bare_literal_files() - {_DELIBERATE_PROSE_FILE}
    assert not offenders, (
        f"#15005: bare VerificationMethod literals found outside the enum: "
        f"{sorted(offenders)}. Use services.knowledge_grounding_models.VerificationMethod."
    )


def test_the_deliberate_prose_file_still_carries_the_literal():
    """A stale exemption would exempt nothing while looking authoritative."""
    assert _DELIBERATE_PROSE_FILE in _bare_literal_files()
