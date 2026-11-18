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

import ast
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
from pathlib import Path

from autobot_shared.paths import scrubbed_git_env
from autobot_shared.status_enums import Severity
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

#: The canonical floor's source file, located relative to this one rather than
#: through `repo_tests._paths.repo_root()`. Importing that helper would add the
#: cross-tree dependency this whole arrangement exists to avoid — the point is
#: to compare against `tools/lint/` without importing from it. #15925's
#: one-root-spelling guard scopes to `repo_tests/`, so this is outside it by
#: design rather than by omission.
_CANONICAL_FLOOR_SOURCE = Path(__file__).resolve().parents[2] / "tools" / "lint" / "_scan_helpers.py"

# The seventh copy of this number (#15928, #16076). The canonical one is
# `tools.lint._scan_helpers.TRACKED_PY_FLOOR`, which the six sites in
# `repo_tests/` and `tools/lint/` import directly. This file cannot: it lives in
# a tree that does not import from `tools/lint/`, and adding that dependency to
# a backend unit test to share an integer is the worse trade.
#
# So the value is duplicated and the DUPLICATION is pinned instead. Reading the
# canonical value out of its source with `ast` needs no import to resolve, and
# it turns "these two agree today" into "these two cannot disagree" -- which is
# the whole of #15928 applied to the one site that could not be consolidated.
# Without it this is #15928's own defect at one-seventh scale: a number that is
# right today, in a second place, pinned by nothing, waiting for the next
# re-measure to move six sites and silently strand this one.
_TRACKED_PY_FLOOR = 5_400


def _canonical_tracked_py_floor() -> int:
    """`TRACKED_PY_FLOOR` from `tools/lint/_scan_helpers.py`, read not imported."""
    source = _CANONICAL_FLOOR_SOURCE.read_text(encoding="utf-8")
    for node in ast.parse(source).body:
        targets = node.targets if isinstance(node, ast.Assign) else []
        if any(isinstance(t, ast.Name) and t.id == "TRACKED_PY_FLOOR" for t in targets):
            return int(ast.literal_eval(node.value))
    raise AssertionError(f"TRACKED_PY_FLOOR not found in {_CANONICAL_FLOOR_SOURCE} — the parse read nothing")


def test_the_local_floor_still_matches_the_canonical_one():
    """#16076: the copy this file has to keep cannot drift from the original.

    Six sites import the canonical constant and move with it. This one cannot,
    so it is compared to it instead — by reading the file, which adds no
    cross-tree import and so sidesteps the dependency that made consolidation
    the wrong trade in the first place.
    """
    canonical = _canonical_tracked_py_floor()
    assert _TRACKED_PY_FLOOR == canonical, (
        f"_TRACKED_PY_FLOOR here is {_TRACKED_PY_FLOOR}; the canonical "
        f"tools.lint._scan_helpers.TRACKED_PY_FLOOR is {canonical}.\n"
        f"Six sites import that constant and moved with it; this one is a copy "
        f"and did not. Set this to {canonical}."
    )


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
        env=scrubbed_git_env(),
    )
    return [line for line in out.stdout.splitlines() if line]


# This guard's own fixture data (VERIFICATION_METHOD_UNION, the wire-spelling
# test) legitimately spells out every member value, so it is excluded from
# its own scan the same way the enum definition itself is.
_SELF = "autobot-backend/services/knowledge_grounding_models_test.py"


def _bare_literal_files() -> set[str]:
    """Files (outside the enum definition) containing a bare vocabulary literal."""
    needles = tuple(f'"{value}"' for _, value in VERIFICATION_METHOD_UNION)
    offenders: set[str] = set()
    for rel in _tracked_python_files():
        if not (rel.startswith("autobot-backend/") or rel.startswith("autobot_shared/")):
            continue
        if rel in {"autobot-backend/services/knowledge_grounding_models.py", _SELF}:
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


class TestTheMergedClaimKeepsEveryProducersWireShape:
    """#18086: one Claim for the classifier, GroundedAgent and the conflict resolver."""

    _PRE_MERGE_PAYLOAD = {
        "claim_text": "port 8080 is open",
        "claim_type": "factual",
        "kb_status": "in_kb",
        "confidence": 0.9,
        "sources": [],
        "kb_fact": None,
        "timestamp": 1.0,
        "metadata": {"k": "v"},
    }

    def test_a_cached_pre_merge_payload_still_loads(self):
        from services.knowledge_grounding_models import Claim, ClaimType, KBStatus

        claim = Claim.from_dict(self._PRE_MERGE_PAYLOAD)
        assert (claim.claim_type, claim.kb_status) == (ClaimType.FACTUAL, KBStatus.IN_KB)
        assert claim.source == "" and claim.subject == ""

    def test_an_unclassified_claim_round_trips(self):
        from services.knowledge_grounding_models import Claim

        claim = Claim(claim_text="x", source="agent", subject="s", predicate="p", object="o")
        assert Claim.from_dict(claim.to_dict()) == claim

    def test_confidence_is_validated_and_timestamp_is_stamped(self):
        import pytest

        from services.knowledge_grounding_models import Claim

        assert Claim(claim_text="x").timestamp is not None
        with pytest.raises(ValueError):
            Claim(claim_text="x", confidence=1.5)


class TestTheMergedVerifiedClaimAndConflictKeepTheirWireShapes:
    """#18086: one VerifiedClaim and one Conflict for GroundedAgent and its siblings."""

    def test_a_cached_pre_merge_verifier_payload_still_loads(self):
        from services.knowledge_grounding_models import Claim, VerificationStatus, VerifiedClaim

        payload = {
            "original_claim": Claim(claim_text="x", confidence=0.4).to_dict(),
            "verified_as": "verified",
            "source": "kb_rag",
            "source_text": "t",
            "source_url": None,
            "confidence": 0.9,
            "timestamp": 2.0,
            "requires_human_review": True,
        }
        loaded = VerifiedClaim.from_dict(payload)
        assert loaded.verified_as is VerificationStatus.VERIFIED and loaded.kb_status is None
        assert loaded.claim.claim_text == "x" and loaded.requires_human_review is True

    def test_a_grounded_verified_claim_round_trips(self):
        from services.knowledge_grounding_models import Claim, ClaimStatus, VerifiedClaim

        vc = VerifiedClaim(claim=Claim(claim_text="x"), kb_status=ClaimStatus.IN_KB, kb_source="f1", evidence=["e"])
        assert VerifiedClaim.from_dict(vc.to_dict()) == vc

    def test_conflict_without_either_producers_identity_raises(self):
        import pytest

        from api.knowledge_grounding_models import Conflict

        with pytest.raises(ValueError):
            Conflict()

    def test_both_conflict_producers_build_the_same_class(self):
        from api.knowledge_grounding_models import Conflict, ConflictResolution

        by_id = Conflict(claim_1_id="c1", description="d", severity=Severity.HIGH.value)
        assert by_id.resolution is ConflictResolution.PENDING_REVIEW.__class__("pending_review")
        assert by_id.max_confidence() == 0.0 and by_id.kb_says is None
