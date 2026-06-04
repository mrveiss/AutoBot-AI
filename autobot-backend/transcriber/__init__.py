# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Transcriber module — general-purpose audio transcription for AutoBot."""

# Export Database class with both names for compatibility
from transcriber.database import Database, get_transcriber_db
# Alias for Dev_new_gui compatibility
TranscriberDatabase = Database

__all__ = ["Database", "TranscriberDatabase", "get_transcriber_db"]
