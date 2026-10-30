# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the shared transcript normalizer (#11137). Every fixture is synthetic."""

import gzip
import json

import pytest

from services.execution import claude_code_backend as backend
from services.execution import transcript_normalizer as tn

CLAUDE_LINES = [
    {"type": "assistant", "message": {"content": [{"type": "text", "text": "hello"}]}},
    {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Read", "input": {"p": "x"}}]},
    },
    {"type": "assistant", "message": {"content": [{"type": "thinking", "thinking": "..."}]}},
    {"type": "tool_result", "tool_use_id": "t1", "output": "ok", "is_error": False},
    {"type": "result", "subtype": "success", "is_error": False, "result": "done", "usage": {"n": 1}},
    {"type": "error", "error": "boom"},
    {"type": "unknown_ev"},
]


def _saved_claude():
    return [
        {"type": "user", "timestamp": "2026-01-01T00:00:00Z", "message": {"content": "question"}},
        {
            "type": "assistant",
            "timestamp": "2026-01-01T00:00:01Z",
            "message": {
                "content": [
                    {"type": "thinking", "thinking": "hmm"},
                    {"type": "text", "text": "answer"},
                    {"type": "tool_use", "id": "c1", "name": "Bash", "input": {"cmd": "ls"}},
                ]
            },
        },
        {
            "type": "user",
            "timestamp": "2026-01-01T00:00:02Z",
            "message": {"content": [{"type": "tool_result", "tool_use_id": "c1", "content": "out", "is_error": True}]},
        },
        {"type": "ai-title", "title": "ignored"},
    ]


def _codex():
    return [
        {"type": "session_meta", "payload": {"id": "s"}},
        {
            "type": "response_item",
            "timestamp": "T1",
            "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "q"}]},
        },
        {
            "type": "response_item",
            "timestamp": "T2",
            "payload": {"type": "function_call", "name": "shell", "call_id": "k1", "arguments": '{"c": 1}'},
        },
        {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "k1", "output": "res"}},
        {"type": "response_item", "payload": {"type": "reasoning", "summary": []}},
        {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "a"}]},
    ]


class TestSpawnedRunOutputUnchanged:
    """The backend's parser IS the normalizer's, and decodes exactly as it did before extraction."""

    def test_backend_uses_normalizer(self):
        assert backend._parse_cli_line is tn.parse_cli_line
        assert backend._StepEvent is tn.StepEvent

    def test_golden_outputs(self):
        got = [backend._parse_cli_line(json.dumps(o)) for o in CLAUDE_LINES]
        assert got[0] == backend._StepEvent(kind="message", content={"text": "hello"})
        assert got[1] == backend._StepEvent(
            kind="tool_use", content={"input": {"p": "x"}}, tool_name="Read", tool_id="t1"
        )
        assert got[2] is None
        assert got[3] == backend._StepEvent(
            kind="tool_result", content={"output": "ok", "is_error": False}, tool_id="t1"
        )
        assert got[4] == backend._StepEvent(
            kind="complete",
            content={"subtype": "success", "is_error": False, "result": "done", "usage": {"n": 1}},
        )
        assert got[5] == backend._StepEvent(kind="error", content={"error": "boom"})
        assert got[6] is None
        assert all(g is None or (g.role == "" and g.timestamp == "") for g in got)

    @pytest.mark.parametrize("raw", ["", "  ", "not json", "[1, 2]", "null"])
    def test_garbage_is_skipped(self, raw):
        assert backend._parse_cli_line(raw) is None

    def test_defaults_when_keys_missing(self):
        step = backend._parse_cli_line('{"type": "result"}')
        assert step.content == {"subtype": "", "is_error": False, "result": "", "usage": {}}


class TestClaudeSavedTranscript:
    def test_all_blocks_decoded_thinking_dropped(self):
        events = [e for rec in _saved_claude() for e in tn.normalize_record(rec)]
        assert [(e.kind, e.role) for e in events] == [
            ("message", "user"),
            ("message", "assistant"),
            ("tool_use", "assistant"),
            ("tool_result", "user"),
        ]
        assert events[0].content == {"text": "question"}
        assert events[2].tool_name == "Bash" and events[2].tool_id == "c1"
        assert events[3].content == {"output": "out", "is_error": True}
        assert events[1].timestamp == "2026-01-01T00:00:01Z"


class TestCodex:
    def test_response_items(self):
        events = [e for rec in _codex() for e in tn.normalize_record(rec)]
        assert [e.kind for e in events] == ["message", "tool_use", "tool_result", "message"]
        assert events[0].role == "user" and events[0].content == {"text": "q"}
        assert events[1].tool_name == "shell" and events[1].content == {"input": {"c": 1}}
        assert events[2].tool_id == "k1" and events[2].content["output"] == "res"
        assert events[3].role == "assistant"

    def test_non_json_arguments_kept_raw(self):
        rec = {"type": "response_item", "payload": {"type": "function_call", "name": "n", "arguments": "a b"}}
        assert tn.normalize_record(rec)[0].content == {"input": "a b"}

    def test_unknown_records_yield_nothing(self):
        assert tn.normalize_record({"type": "turn_context"}) == []
        assert tn.normalize_record({"type": "response_item", "payload": "x"}) == []


class TestHistory:
    def test_prompt_project_timestamp(self):
        line = json.dumps({"display": "do x", "project": "/p/a", "timestamp": 1_700_000_000_000, "sessionId": "s1"})
        entry = tn.parse_history_line(line)
        assert entry == tn.EvidenceEntry("do x", "/p/a", "2023-11-14T22:13:20+00:00", "s1")

    def test_missing_fields_and_invalid_lines(self):
        assert tn.parse_history_line('{"display": "p"}') == tn.EvidenceEntry("p", "", "", "")
        for raw in ("nope", "[]", '{"display": "  "}', '{"project": "x"}'):
            assert tn.parse_history_line(raw) is None


class TestFiles:
    def _write(self, path, records, gz=False):
        text = "".join(json.dumps(r) + "\n" for r in records) + "{broken\n"
        opener = gzip.open if gz else open
        with opener(path, "wt", encoding="utf-8") as fh:
            fh.write(text)

    def test_plain_and_gzip_identical(self, tmp_path):
        self._write(tmp_path / "a.jsonl", _saved_claude())
        self._write(tmp_path / "b.jsonl.gz", _saved_claude(), gz=True)
        plain, gz = tn.read_transcript(tmp_path / "a.jsonl"), tn.read_transcript(tmp_path / "b.jsonl.gz")
        assert plain.items == gz.items and len(plain.items) == 4
        assert plain.skipped == 1 and not plain.truncated

    def test_batch_expands_directories(self, tmp_path):
        self._write(tmp_path / "a.jsonl", _saved_claude())
        self._write(tmp_path / "b.jsonl.gz", _codex(), gz=True)
        (tmp_path / "skip.txt").write_text("x", encoding="utf-8")
        batch = tn.read_transcripts([tmp_path])
        assert sorted(p.rsplit("/", 1)[1] for p in batch.results) == ["a.jsonl", "b.jsonl.gz"]
        assert batch.failed == {}

    def test_history_file_gzip(self, tmp_path):
        path = tmp_path / "history.jsonl.gz"
        self._write(path, [{"display": "p1", "project": "/x", "timestamp": 0}, {"display": ""}], gz=True)
        assert [e.prompt for e in tn.read_history(path).items] == ["p1"]


class TestBadInputDoesNotLoseTheBatch:
    @pytest.mark.parametrize("stamp", [1e300, float("nan"), float("inf"), -1e300, 10**30])
    def test_out_of_range_timestamp_is_a_malformed_line(self, stamp):
        assert tn.parse_history_line(json.dumps({"display": "p", "timestamp": stamp})) is None

    def test_one_bad_history_line_does_not_abort_the_read(self, tmp_path):
        path = tmp_path / "history.jsonl"
        lines = ['{"display": "ok1", "timestamp": 0}', '{"display": "bad", "timestamp": 1e300}', '{"display": "ok2"}']
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = tn.read_history(path)
        assert [e.prompt for e in result.items] == ["ok1", "ok2"] and result.skipped == 1

    def test_invalid_utf8_line_is_counted_not_fatal(self, tmp_path):
        path = tmp_path / "a.jsonl"
        path.write_bytes(b'\xff\xfe{"type":"user"}\n' + json.dumps(_saved_claude()[0]).encode() + b"\n")
        result = tn.read_transcript(path)
        assert len(result.items) == 1 and result.skipped == 1

    def test_corrupt_gzip_fails_alone(self, tmp_path):
        good = tmp_path / "a.jsonl"
        good.write_text(json.dumps(_saved_claude()[0]) + "\n", encoding="utf-8")
        whole = gzip.compress(b"x" * 5000)
        (tmp_path / "b.jsonl.gz").write_bytes(whole[: len(whole) // 2])  # truncated
        (tmp_path / "c.jsonl.gz").write_bytes(b"not gzip at all")
        batch = tn.read_transcripts([tmp_path])
        assert list(batch.results) == [str(good)]
        assert {k.rsplit("/", 1)[1] for k in batch.failed} == {"b.jsonl.gz", "c.jsonl.gz"}
        assert all(v.isidentifier() for v in batch.failed.values())  # class names only

    @pytest.mark.parametrize("content", [5, None, {"a": 1}, 1.5, True])
    def test_codex_text_tolerates_non_iterable_content(self, content):
        rec = {"type": "response_item", "payload": {"type": "message", "role": "user", "content": content}}
        assert tn.normalize_record(rec)[0].content == {"text": ""}
        assert tn._codex_text([{"type": "input_text", "text": 3}]) == ""


class TestBounds:
    def test_no_newline_file_is_cut_at_line_bound(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tn, "MAX_LINE_BYTES", 200)
        path = tmp_path / "a.jsonl"
        path.write_bytes(json.dumps(_saved_claude()[0]).encode() + b"\n" + b"y" * 10_000)
        result = tn.read_transcript(path)
        assert len(result.items) == 1
        assert (result.truncated, result.truncated_reason) == (True, "line_length")

    def test_decompressed_bytes_bound_stops_a_gzip_bomb(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tn, "MAX_DECOMPRESSED_BYTES", 2000)
        line = json.dumps(_saved_claude()[0]) + "\n"
        with gzip.open(tmp_path / "bomb.jsonl.gz", "wt", encoding="utf-8") as fh:
            fh.write(line * 1000)
        result = tn.read_transcript(tmp_path / "bomb.jsonl.gz")
        assert (result.truncated, result.truncated_reason) == (True, "decompressed_bytes")
        assert 0 < len(result.items) < 1000

    def test_event_bound_truncates_and_exact_fit_does_not(self, tmp_path, monkeypatch):
        path = tmp_path / "a.jsonl"
        path.write_text("".join(json.dumps(r) + "\n" for r in _saved_claude()), encoding="utf-8")  # 4 events
        monkeypatch.setattr(tn, "MAX_EVENTS", 4)
        assert tn.read_transcript(path).truncated is False
        monkeypatch.setattr(tn, "MAX_EVENTS", 3)
        cut = tn.read_transcript(path)
        assert (len(cut.items), cut.truncated, cut.truncated_reason) == (3, True, "events")

    def test_history_event_bound(self, tmp_path, monkeypatch):
        monkeypatch.setattr(tn, "MAX_EVENTS", 2)
        path = tmp_path / "history.jsonl"
        path.write_text("".join(json.dumps({"display": f"p{i}"}) + "\n" for i in range(5)), encoding="utf-8")
        result = tn.read_history(path)
        assert len(result.items) == 2 and result.truncated
