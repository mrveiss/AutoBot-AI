# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Typed text and the input delay of the chat Desktop controls (#22145)."""

import importlib

import pytest

from api import vnc_host_actions as actions


class _Recorder:
    def __init__(self):
        self.keys = []

    async def key(self, keysym, down):
        self.keys.append((keysym, down))


@pytest.mark.asyncio
async def test_tab_and_newline_in_typed_text_send_the_named_keysyms():
    session = _Recorder()
    await actions._type(session, "a\tb\n")
    downs = [k for k, down in session.keys if down]
    assert downs == [ord("a"), 0xFF09, ord("b"), 0xFF0D]


@pytest.mark.parametrize("raw", ["inf", "nan", "-1", "0", "999", "junk"])
def test_input_delay_is_always_finite_and_bounded(monkeypatch, raw):
    monkeypatch.setenv("AUTOBOT_VNC_INPUT_STEP_DELAY_S", raw)
    try:
        reloaded = importlib.reload(actions)
        assert 0.0 <= reloaded.VNC_INPUT_STEP_DELAY_S <= 5.0
    finally:
        monkeypatch.delenv("AUTOBOT_VNC_INPUT_STEP_DELAY_S")
        importlib.reload(actions)
