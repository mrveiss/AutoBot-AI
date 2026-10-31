# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one reader of ``complete.yaml`` for the env-file generator and validator (#18964)."""

from pathlib import Path

import yaml

COMPLETE_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "complete.yaml"


def load_config():
    """Load the complete.yaml configuration"""
    with open(COMPLETE_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
