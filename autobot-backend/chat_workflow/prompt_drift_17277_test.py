# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#17277: the stable prompt prefix is hashed per turn and a change is reported."""

import json
from types import SimpleNamespace

from chat_workflow import prompt_drift as pd

STABLE = "persona\n\nrules\n\ntools"


def test_hash_recorded_per_turn_and_stable_text_is_same():
    meta: dict = {}
    blocks: dict = {}
    first = pd.record_turn_prefix(meta, "en|-|0", STABLE, blocks)
    again = pd.record_turn_prefix(meta, "en|-|0", STABLE, blocks)
    assert first["kind"] == "first" and again["kind"] == "same"
    assert meta[pd.METADATA_KEY]["en|-|0"]["hash"] == pd.prefix_record(STABLE)["hash"]


def test_changed_persona_or_tool_descriptor_is_reported_as_drift():
    for edited in ("PERSONA\n\nrules\n\ntools", "persona\n\nrules\n\ntools v2"):
        meta: dict = {}
        blocks: dict = {}
        pd.record_turn_prefix(meta, "k", STABLE, blocks)
        report = pd.record_turn_prefix(meta, "k", edited, blocks)
        assert report["kind"] == "drift" and report["changed"]
        assert report["previous"] != report["current"]
        assert report["changed_blocks"] == ([0] if edited.startswith("PERSONA") else [2])


def test_release_change_is_intended_not_drift():
    old = pd.prefix_record(STABLE, release="1.0")
    new = pd.prefix_record(STABLE + " edit", release="1.1")
    assert pd.compare_records(old, new)["kind"] == "release_change"


def test_report_carries_no_prompt_text():
    secret = "/home/someone/secret-host"
    old = pd.prefix_record(STABLE)
    report = pd.compare_records(old, pd.prefix_record(STABLE + "\n\n" + secret))
    assert secret not in json.dumps(report) and secret not in json.dumps(old)


def test_persisted_metadata_keeps_only_hash_release_and_chars():
    meta: dict = {}
    blocks: dict = {}
    pd.record_turn_prefix(meta, "k", STABLE, blocks)
    assert set(meta[pd.METADATA_KEY]["k"]) == {"hash", "release", "chars"}
    assert "blocks" not in repr(meta) and blocks["k"]  # the per-block hashes stay on the in-memory side


def test_a_personality_switch_is_a_different_key_not_drift(monkeypatch):
    session = SimpleNamespace(metadata={})
    for pid, text in (("calm", STABLE), ("bold", "PERSONA BOLD\n\nrules\n\ntools")):
        monkeypatch.setattr(pd, "active_personality_id", lambda pid=pid: pid)
        pd.record_session_prefix(session, "en", None, False, text)
    assert len(session.metadata[pd.METADATA_KEY]) == 2  # two keys, so the second turn compared against nothing
    assert pd.prefix_key("en", None, False, "calm") != pd.prefix_key("en", None, False, "bold")


def test_key_separates_company_and_codeexec():
    assert (
        len({pd.prefix_key("en", None, False), pd.prefix_key("en", "c", False), pd.prefix_key("en", None, True)}) == 3
    )


def test_session_hook_is_non_fatal():
    pd.record_session_prefix(None, "en", None, False, STABLE)
    pd.record_session_prefix(object(), "en", None, False, STABLE)
