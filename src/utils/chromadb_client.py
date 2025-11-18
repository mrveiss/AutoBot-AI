# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Reusable ChromaDB Client Initialization

Provides a centralized function for creating ChromaDB clients with
consistent configuration across the entire codebase.
"""

import logging
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

logger = logging.getLogger(__name__)


def get_chromadb_client(
    db_path: str,
    allow_reset: bool = False,
    anonymized_telemetry: bool = False
) -> chromadb.PersistentClient:
    """
    Create a ChromaDB persistent client with consistent configuration.

    Args:
        db_path: Path to the ChromaDB database directory
        allow_reset: Whether to allow database resets (default: False)
        anonymized_telemetry: Whether to enable telemetry (default: False)

    Returns:
        Configured ChromaDB PersistentClient

    Raises:
        Exception: If client initialization fails
    """
    try:
        # Ensure directory exists
        chroma_path = Path(db_path)
        chroma_path.mkdir(parents=True, exist_ok=True)

        # Create persistent client with standardized settings
        client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=ChromaSettings(
                allow_reset=allow_reset,
                anonymized_telemetry=anonymized_telemetry
            )
        )

        logger.info(f"ChromaDB client initialized at: {chroma_path}")
        return client

    except Exception as e:
        logger.error(f"Failed to initialize ChromaDB client: {e}")
        raise
