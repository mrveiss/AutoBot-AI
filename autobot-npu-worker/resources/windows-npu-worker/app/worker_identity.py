# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Worker identity and pairing state, persisted to disk (#15642).

Issue #641 made the main host the authority on a worker's ID: this worker only
reads the ID it was assigned and records which host assigned it. Both facts
outlive the process, so both live in files under ``config/`` — and reading and
writing those two files is the whole of this module's job.

This module ships inside the standalone Windows package: PyInstaller's
``installer/npu_worker.spec`` analyses ``app/npu_worker.py`` with
``pathex=[app]``, and ``scripts/install.ps1`` copies only this tree. Nothing
here may import ``autobot_shared`` — it is not on the worker's disk.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Worker ID file for persistence across restarts (Issue #68 - duplicate registration fix)
WORKER_ID_FILE = Path(__file__).parent.parent / "config" / ".worker_id"

# Issue #641: Registration status
# Tracks whether this worker has been paired with main host
PAIRING_STATUS_FILE = Path(__file__).parent.parent / "config" / ".pairing_status"


def get_persistent_worker_id(prefix: str = "windows_npu_worker") -> str | None:
    """
    Get persistent worker ID assigned by main host.

    Issue #641: Worker ID is now assigned by main host, not self-generated.
    This function only READS an existing ID - it does not generate new ones.
    New workers start with no ID and wait for main host to assign one via /pair endpoint.

    Args:
        prefix: Worker ID prefix (unused, kept for backwards compatibility)

    Returns:
        Persistent worker ID string if assigned, None if not yet paired
    """
    try:
        if WORKER_ID_FILE.exists():
            with open(WORKER_ID_FILE, "r", encoding="utf-8") as f:
                worker_id = f.read().strip()
                if worker_id:
                    logger.info("Loaded persistent worker ID: %s", worker_id)
                    return worker_id
    except Exception as e:
        logger.warning("Failed to read worker ID file: %s", e)

    # Issue #641: Do NOT generate new ID - wait for main host to assign one
    logger.info("No worker ID assigned yet - waiting for main host to pair")
    return None


def save_worker_id(worker_id: str) -> bool:
    """
    Save worker ID assigned by main host.

    Issue #641: Called when main host pairs with this worker and assigns an ID.

    Args:
        worker_id: The ID assigned by main host

    Returns:
        True if saved successfully, False otherwise
    """
    try:
        WORKER_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(WORKER_ID_FILE, "w", encoding="utf-8") as f:
            f.write(worker_id)
        logger.info("Saved worker ID from main host: %s", worker_id)
        return True
    except Exception as e:
        logger.error("Failed to save worker ID: %s", e)
        return False


def get_pairing_status() -> Dict[str, Any]:
    """
    Get current pairing status with main host.

    Issue #641: Returns information about whether this worker is paired.

    Returns:
        Dict with pairing status information
    """
    try:
        if PAIRING_STATUS_FILE.exists():
            with open(PAIRING_STATUS_FILE, "r", encoding="utf-8") as f:
                import json

                return json.load(f)
    except Exception as e:
        logger.warning("Failed to read pairing status: %s", e)

    return {
        "paired": False,
        "main_host": None,
        "paired_at": None,
    }


def save_pairing_status(main_host: str, worker_id: str) -> bool:
    """
    Save pairing status after successful pairing with main host.

    Issue #641: Records when and with which main host this worker was paired.

    Args:
        main_host: IP/hostname of the main host
        worker_id: The assigned worker ID

    Returns:
        True if saved successfully, False otherwise
    """
    try:
        import json

        PAIRING_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        status = {
            "paired": True,
            "main_host": main_host,
            "worker_id": worker_id,
            "paired_at": datetime.now().isoformat(),
        }
        with open(PAIRING_STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(status, f, indent=2)
        logger.info("Saved pairing status: paired with %s", main_host)
        return True
    except Exception as e:
        logger.error("Failed to save pairing status: %s", e)
        return False
