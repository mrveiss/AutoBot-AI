# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
ACP stdio framing (#14825).

One complete JSON message per line, on stdout, and nothing else. Two properties
carry the whole transport:

* a malformed line must be skipped rather than killing the session — each line
  is an independent message, and the peer may still send valid traffic;
* concurrent writes must not interleave, because notifications are emitted from
  streaming tasks while a response may be written at the same time. A torn line
  corrupts the stream for good.
"""

import asyncio
import io
import json

import pytest

from acp.transport import StdioTransport


@pytest.mark.asyncio
async def test_send_writes_one_json_line(monkeypatch):
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    transport = StdioTransport()

    await transport.send({"jsonrpc": "2.0", "id": 1, "result": {}})

    written = out.getvalue()
    assert written.endswith("\n")
    assert written.count("\n") == 1
    assert json.loads(written)["id"] == 1


@pytest.mark.asyncio
async def test_send_does_not_embed_raw_newlines(monkeypatch):
    """A newline inside a value would otherwise split one message into two."""
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    transport = StdioTransport()

    await transport.send({"text": "line one\nline two"})

    assert out.getvalue().count("\n") == 1
    assert json.loads(out.getvalue())["text"] == "line one\nline two"


@pytest.mark.asyncio
async def test_send_preserves_non_ascii(monkeypatch):
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    transport = StdioTransport()

    await transport.send({"text": "café — 日本語"})

    assert json.loads(out.getvalue())["text"] == "café — 日本語"


@pytest.mark.asyncio
async def test_concurrent_sends_do_not_interleave(monkeypatch):
    """Every line must parse; a torn write corrupts the stream permanently."""
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    transport = StdioTransport()

    await asyncio.gather(*(transport.send({"n": i, "pad": "x" * 200}) for i in range(30)))

    lines = [ln for ln in out.getvalue().split("\n") if ln]
    assert len(lines) == 30
    assert sorted(json.loads(ln)["n"] for ln in lines) == list(range(30))


@pytest.mark.asyncio
async def test_send_serialises_unknown_types_rather_than_raising(monkeypatch):
    """`default=str` keeps one odd value from killing the whole session."""
    out = io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    transport = StdioTransport()

    class Odd:
        def __str__(self) -> str:
            return "odd-value"

    await transport.send({"v": Odd()})

    assert json.loads(out.getvalue())["v"] == "odd-value"
