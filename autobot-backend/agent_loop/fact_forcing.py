# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Fact-forcing gate for the agent loop (GH#11149).

The detection logic now lives in the dependency-free
``autobot_shared.fact_forcing_guard`` (GH#11178) so the production tool-dispatch
seam can reuse it without importing the heavy ``agent_loop`` package. This module
re-exports the loop-facing surface.
"""

from autobot_shared.fact_forcing_guard import (
    fact_forcing_env_enabled,
    first_uninvestigated_edit,
    record_investigation,
    record_investigations,
    uninvestigated_edit_path,
)

__all__ = [
    "fact_forcing_env_enabled",
    "first_uninvestigated_edit",
    "record_investigation",
    "record_investigations",
    "uninvestigated_edit_path",
]
