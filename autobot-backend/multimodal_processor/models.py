# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Multimodal Processor Data Models

Dataclasses for input/output structures in multimodal processing.

Part of Issue #381 - God Class Refactoring
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict

from .types import ModalityType, ProcessingIntent


@dataclass
class MultiModalInput:
    """Unified input data structure for all modalities"""

    input_id: str
    modality_type: ModalityType
    intent: ProcessingIntent
    data: Any  # Flexible data field for any input type
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    # #13688: owner of this input, carried as a first-class field rather than a
    # metadata key so the memory write below it can be tenant-scoped. Set from
    # the authenticated principal at the API boundary.
    user_id: str | None = None


@dataclass
class ProcessingResult:
    """Unified result structure for all processing types"""

    result_id: str
    input_id: str
    modality_type: ModalityType
    intent: ProcessingIntent
    success: bool
    confidence: float
    result_data: Any
    processing_time: float
    error_message: str | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    # #13688: stamped from the originating input in MultiModalProcessor.process
    # so every result knows whose it is without each of the 25 construction
    # sites having to remember.
    user_id: str | None = None
