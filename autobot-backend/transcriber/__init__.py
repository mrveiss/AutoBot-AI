# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Transcriber module — general-purpose audio transcription for AutoBot."""

# Export Database class with both names for compatibility
from transcriber.database import Database

# Alias for Dev_new_gui compatibility
TranscriberDatabase = Database

__all__ = ["Database", "TranscriberDatabase"]
