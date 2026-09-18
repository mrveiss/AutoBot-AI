# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard: every ChatKnowledgeService method that hands a caller prompt-bound
RAG context passes it through the content firewall first (#16771 AC5).

#16771 found conversation_aware_retrieve was the chat's actual RAG path but
never firewalled its output; #16930 fixed that. A follow-up review of #16930
found two MORE public methods on the same class with the identical gap --
smart_retrieve_knowledge and retrieve_combined_knowledge both build their
returned context from raw retrieve_relevant_knowledge() content with no
inspect_rag_context call, and neither is called by anything today. Per the
no-debris rule that does not make the gap acceptable: a future caller of
either method inherits an already-broken security guarantee silently, which
is exactly how conversation_aware_retrieve's own gap went unnoticed.

Scope: the three methods checked here are the TERMINAL ones -- each is a
public method whose own docstring declares its return as context "for LLM
prompt", and none of the three is itself consumed by another public method on
this class before reaching an external caller. retrieve_relevant_knowledge
and retrieve_documentation are deliberately NOT in this list: both are
internal composition helpers that conversation_aware_retrieve /
smart_retrieve_knowledge / retrieve_combined_knowledge call and then firewall
the ASSEMBLED result of -- firewalling them a second time at their own level
would nest delimiter markers around content already delimited by the caller,
which is not what "one inspection point" (#16771's own AC5) means.

Hand-enumerated rather than tree-scanned for the same reason as
repo_tests/ingestion_redaction_guard_test.py: "returns prompt context" is not
a discoverable syntactic pattern, so repo_tests._reach's tree-scanning-guard
floor mechanism doesn't apply here either.

#16930 review split: the three entry points' repeated inspect-then-quarantine
sequence moved into rag_firewall.inspect_and_quarantine (services/knowledge/
rag_firewall.py), to bring service.py back under its file-size ceiling. A
literal ``inspect_rag_context(`` no longer appears in any entry point's own
source -- only in the helper's. Per CLAUDE_RULES rule 7 ("grep the behavior,
not the symbol, on extraction PRs"), _calls_inspect_rag_context now also
accepts a call to inspect_and_quarantine as evidence, but ONLY because
test_inspect_and_quarantine_itself_calls_the_firewall below pins the other
end of that indirection: if the helper ever stopped calling
inspect_rag_context, that test would fail even though every entry point
still shows a green ``inspect_and_quarantine(`` match.
"""

from __future__ import annotations

import inspect

import pytest

_ENTRY_POINTS = [
    "conversation_aware_retrieve",
    "smart_retrieve_knowledge",
    "retrieve_combined_knowledge",
]

# A call to either marker satisfies the guard -- see the module docstring for
# why inspect_and_quarantine is trustworthy evidence here, and not just a
# same-shaped name.
_FIREWALL_CALL_MARKERS = ("inspect_rag_context(", "inspect_and_quarantine(")


def _calls_inspect_rag_context(source: str) -> bool:
    """True if *source* calls the firewall, directly or via the extracted
    inspect_and_quarantine helper (see _FIREWALL_CALL_MARKERS).

    Checked against the method's own source, not the module's imports, so a
    method that imports the firewall but never calls it still fails.
    """
    return any(marker in source for marker in _FIREWALL_CALL_MARKERS)


@pytest.mark.parametrize("method_name", _ENTRY_POINTS)
def test_rag_entry_point_passes_through_the_content_firewall(method_name: str) -> None:
    from services.knowledge.service import ChatKnowledgeService

    method = getattr(ChatKnowledgeService, method_name)
    source = inspect.getsource(method)
    assert _calls_inspect_rag_context(source), (
        f"ChatKnowledgeService.{method_name} returns RAG context to a caller but its "
        "source has no inspect_rag_context(...) call -- unfirewalled content would "
        "reach the chat prompt unfiltered (#16771 AC5)."
    )


def test_inspect_and_quarantine_itself_calls_the_firewall() -> None:
    """Pins the other end of the indirection the three tests above rely on.

    If rag_firewall.inspect_and_quarantine stopped calling inspect_rag_context,
    every entry point above would still show a green ``inspect_and_quarantine(``
    match while firewalling nothing -- the exact "did not look" failure mode
    MEASUREMENT_DISCIPLINE.md warns about, just moved one hop away.
    """
    from services.knowledge.rag_firewall import inspect_and_quarantine

    source = inspect.getsource(inspect_and_quarantine)
    assert "inspect_rag_context(" in source, (
        "rag_firewall.inspect_and_quarantine no longer calls inspect_rag_context -- "
        "every RAG entry point that relies on it (#16771 AC5) would silently stop "
        "being firewalled."
    )


def test_negative_control_a_method_that_skips_the_firewall_is_caught() -> None:
    """Proves the assertion above can fail, not just always pass.

    Without this, a broken detection helper (matching the import instead of a
    call, or the wrong string) would report green against every real entry
    point without ever having demonstrated it can see a violation -- the
    "did not look" failure MEASUREMENT_DISCIPLINE.md warns about.
    """

    def _fake_entry_point_that_skips_the_firewall(context_string: str) -> str:
        return context_string.strip()

    source = inspect.getsource(_fake_entry_point_that_skips_the_firewall)
    assert not _calls_inspect_rag_context(source), "negative control itself contains an inspect_rag_context(...) call"
