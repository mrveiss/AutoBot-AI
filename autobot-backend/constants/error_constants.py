# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared error message string constants for HTTP responses and logging.

MIGRATION (Issue #GH7440):
    This module re-exports from autobot_shared.ssot_constants for backward compatibility.
    Import directly from autobot_shared.ssot_constants for new code.
"""

from autobot_shared.ssot_constants import (  # noqa: F401,F403
    ERR_ASSESSMENT_NOT_FOUND,
    ERR_CONNECTOR_NOT_FOUND,
    ERR_DIRECTORY_NOT_FOUND,
    ERR_EXPERIMENT_NOT_FOUND,
    ERR_FILE_NOT_FOUND,
    ERR_FILE_OR_DIR_NOT_FOUND,
    ERR_INVALID_CREDENTIALS,
    ERR_INVALID_TOKEN,
    ERR_JOB_NOT_FOUND,
    ERR_PATH_NOT_FOUND,
    ERR_SESSION_NOT_FOUND,
    ERR_TEMPLATE_NOT_FOUND,
    ERR_WORKFLOW_NOT_FOUND,
)
