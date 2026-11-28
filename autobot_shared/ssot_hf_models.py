# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""HuggingFace models the backend loads at runtime and install must therefore pre-fetch (#19869, #19738).

The one place their ids are written. Each is read by the code that loads it and by
``autobot_shared.model_prefetch``, which install runs. Every id here MUST have an entry in
``pinned_model_registry`` (its revision and weight digests); a test pins that.
"""

from __future__ import annotations

#: Speech-to-text, loaded by ``autobot-backend/media/audio/pipeline.py``.
SPEECH_TO_TEXT_MODEL = "openai/whisper-base"
#: Code embeddings, loaded by ``autobot-backend/code_embedding_generator.py``.
CODE_EMBEDDING_MODEL = "microsoft/codebert-base"

#: What install fetches into the service user's cache, and checks is there afterwards.
PREFETCHED_HF_MODELS: tuple[str, ...] = (SPEECH_TO_TEXT_MODEL, CODE_EMBEDDING_MODEL)
