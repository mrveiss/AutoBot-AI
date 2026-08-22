# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Replay transcript resolution must cover every subprocess adapter (#14760).

#13614 fixed transcript resolution by reading the adapter's state file instead
of recomputing a path from the wrong run id. It fixed it for one adapter family:
`_resolve_adapter_output_file` imported `claude_code_adapter`'s helpers directly,
so the copilot adapters — whose files are `llc_copilot_*`, not `llc_agent_*` —
missed on both the state-file lookup and the fallback, every time. The run
completed, a transcript was written, and `output_text` stayed empty: the exact
symptom #13614 was filed for, still live for two of the four subprocess types.

The function was generic in name only. These drive the real scheduler entry
point for **every registered subprocess adapter**, so a family that resolves to
nothing is a failure here rather than a silently empty replay record.
"""

from __future__ import annotations

import json
import os

import pytest

from llc.adapters import subprocess_base
from llc.adapters.base import registered_adapter_types
from llc.adapters.subprocess_base import (
    adapter_transcript_helpers,
    is_subprocess_adapter,
    placeholder_run_id,
)
from llc.scheduler.heartbeat_scheduler import _resolve_adapter_output_file

SUBPROCESS_TYPES = [
    "claude_code",
    "claude_code_subscription",
    "copilot_local",
    "copilot_subscription",
]


def _subprocess_types_in_registry() -> list[str]:
    """Every registered type whose adapter runs an external CLI subprocess.

    Derived from the registry rather than listed here, so a newly registered
    adapter is covered the moment it is added.
    """
    from llc.adapters.base import get_adapter

    return [t for t in registered_adapter_types() if is_subprocess_adapter(get_adapter(t))]


class TestEverySubprocessAdapterResolvesItsTranscript:
    @pytest.mark.parametrize("adapter_type", SUBPROCESS_TYPES)
    def test_the_state_file_is_the_authority(self, adapter_type, tmp_path):
        """The recorded path wins, whatever scheme the adapter names files with."""
        _, state_path = adapter_transcript_helpers(adapter_type)
        external_run_id = "4242/sess-abc"
        recorded = str(tmp_path / "the-real-transcript.jsonl")

        with open(state_path(str(tmp_path), external_run_id), "w", encoding="utf-8") as fh:
            json.dump({"output_file": recorded}, fh)

        resolved = _resolve_adapter_output_file(adapter_type, str(tmp_path), "agent-1", external_run_id)

        assert resolved == recorded

    @pytest.mark.parametrize("adapter_type", SUBPROCESS_TYPES)
    def test_the_fallback_names_the_file_the_adapter_actually_wrote(self, adapter_type, tmp_path):
        """No state file: rebuild from the PLACEHOLDER id, in this family's scheme.

        Two things have to be right at once, and #14760 had the second wrong for
        the copilot pair: the run id must be the placeholder the adapter named
        the file with (`0/<session>`, not the returned `<pid>/<session>`), and
        the filename scheme must be this adapter's own.
        """
        output_path, _ = adapter_transcript_helpers(adapter_type)
        external_run_id = "4242/sess-abc"

        resolved = _resolve_adapter_output_file(adapter_type, str(tmp_path), "agent-1", external_run_id)

        expected = output_path(str(tmp_path), "agent-1", placeholder_run_id("sess-abc"))
        assert resolved == expected
        # The placeholder pid, not the returned one — rebuilding from 4242 names
        # a file no run has ever written.
        assert "4242" not in os.path.basename(resolved)

    def test_the_two_families_do_not_share_a_scheme(self, tmp_path):
        """Guards the shape of the bug itself.

        If copilot resolution ever collapses back onto the claude_code helpers,
        both would resolve to the same name and every assertion above would
        still pass — each family would simply be checked against whatever it
        resolved to.
        """
        claude = _resolve_adapter_output_file("claude_code", str(tmp_path), "agent-1", "1/s")
        copilot = _resolve_adapter_output_file("copilot_local", str(tmp_path), "agent-1", "1/s")

        assert claude != copilot
        assert "llc_agent_" in os.path.basename(claude)
        assert "llc_copilot_" in os.path.basename(copilot)


class TestTheCoverageIsDerivedNotListed:
    def test_every_registered_subprocess_adapter_has_path_helpers(self):
        """A new subprocess adapter cannot land without transcript resolution.

        This is the assertion that makes the fix durable. A lookup table keyed by
        adapter_type would be a second list to maintain by hand, and its failure
        mode is silent — the missing entry yields no transcript, which reads
        exactly like a run that produced none.
        """
        missing = [t for t in _subprocess_types_in_registry() if adapter_transcript_helpers(t) is None]

        assert not missing, (
            f"registered subprocess adapters with no transcript path helpers: {missing}. "
            "Declare _output_path and _state_path as staticmethods on the adapter class, "
            "or replay records for these types will be silently empty (#14760)."
        )

    def test_the_parametrized_list_still_matches_the_registry(self):
        """Keeps the list above honest.

        The tests in this file parametrize over a literal list for readable ids.
        If the registry grows a subprocess adapter, that list is now wrong — say
        so here rather than let the new type go unexercised.
        """
        assert sorted(_subprocess_types_in_registry()) == sorted(SUBPROCESS_TYPES)


class TestNonSubprocessAdaptersResolveToNothing:
    @pytest.mark.parametrize("adapter_type", ["autobot_agent", "codex_subscription", "no_such_adapter"])
    def test_no_path_is_invented_for_them(self, adapter_type, tmp_path):
        """In-process and unimplemented adapters write no transcript.

        Returning None is right; returning some other family's path would make
        the caller stat a file that never exists and record the run as though
        the transcript were merely missing.
        """
        assert _resolve_adapter_output_file(adapter_type, str(tmp_path), "agent-1", "1/s") is None


class TestAMisdeclaredAdapterIsNotSilentlyResolved:
    def test_an_adapter_missing_output_path_yields_no_helpers(self, monkeypatch):
        """The base class annotates the helpers; it does not default them.

        So an adapter that never assigns one must resolve to None rather than
        inherit some other family's scheme.
        """

        class HalfDeclared(subprocess_base.SubprocessLifecycleAdapter):
            _state_path = staticmethod(lambda output_dir, run_id: "/tmp/x")  # nosec B108  # test double

        from llc.adapters import base as adapters_base

        monkeypatch.setitem(adapters_base._registry, "_test_half_declared", HalfDeclared())

        assert adapter_transcript_helpers("_test_half_declared") is None
