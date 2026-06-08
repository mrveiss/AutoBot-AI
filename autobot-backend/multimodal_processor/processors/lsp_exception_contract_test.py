# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""#6755 LSP exception contract regression tests.

The cross-file analyzer (#6747) flagged ``VisionProcessor.process`` and
``VoiceProcessor.process`` as ``lsp_exception_contract_changed``: their
parent ``BaseModalProcessor.process`` only declares ``NotImplementedError``,
but the subclasses raised ``ValueError`` for unsupported modalities.
Liskov substitution requires subclasses NOT to raise exceptions outside
the parent's declared contract — callers handling only the parent's
exception types would silently miss the ``ValueError`` and crash.

These tests pin the fix shape (return a failure ``ProcessingResult``,
don't raise) so a future refactor can't silently re-introduce a bare
``raise ValueError`` inside ``process``.
"""

from __future__ import annotations

import inspect

# ---------------------------------------------------------------------------
# Source-level guards: pin the no-raise contract on `.process()`
# ---------------------------------------------------------------------------


def _process_source(cls) -> str:
    return inspect.getsource(cls.process)


def test_vision_processor_process_does_not_raise_value_error() -> None:
    """Pin the LSP fix: the source of ``VisionProcessor.process`` must not
    contain a bare ``raise ValueError`` for unsupported-modality handling.
    The fix shape is to return a failure ``ProcessingResult`` instead."""
    from multimodal_processor.processors.vision import VisionProcessor

    src = _process_source(VisionProcessor)
    # The early-return shape replaces the original `raise ValueError(...)`.
    assert "raise ValueError" not in src, (
        "#6755 regression: VisionProcessor.process re-introduced a bare "
        "`raise ValueError` — parent BaseModalProcessor.process only declares "
        "NotImplementedError; LSP requires subclasses NOT to raise outside "
        "the parent contract. Return a failure ProcessingResult instead."
    )
    # Pin the replacement shape so the contract is observable in the source.
    assert "success=False" in src
    assert "Unsupported modality" in src


def test_voice_processor_process_does_not_raise_value_error() -> None:
    """Same contract as VisionProcessor — pin both."""
    from multimodal_processor.processors.voice import VoiceProcessor

    src = _process_source(VoiceProcessor)
    assert "raise ValueError" not in src, (
        "#6755 regression: VoiceProcessor.process re-introduced a bare "
        "`raise ValueError` — return a failure ProcessingResult instead."
    )
    assert "success=False" in src
    assert "Unsupported modality" in src


def test_base_processor_process_only_declares_notimplementederror() -> None:
    """Pin the parent contract — if it ever changes (e.g. starts declaring
    ValueError), the subclass tests above need to be re-evaluated."""
    from multimodal_processor.base import BaseModalProcessor

    src = _process_source(BaseModalProcessor)
    # Parent declares NotImplementedError only. Any other `raise X` in the
    # parent body would change the LSP contract for ALL subclasses.
    assert "NotImplementedError" in src
    raise_lines = [line for line in src.splitlines() if line.strip().startswith("raise ")]
    # Exactly one `raise` (NotImplementedError); no others.
    assert len(raise_lines) == 1, f"Parent contract drift: expected 1 `raise`, found {len(raise_lines)}"
    assert "NotImplementedError" in raise_lines[0]
