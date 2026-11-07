# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fixtures shared by the issue-claims API, credential and CLI tests (#18811)."""

from tests.coordination._issue_claims_cli_harness import cli, no_file_writes  # noqa: F401
from tests.coordination._issue_claims_harness import claims_redis, harness, secrets_db  # noqa: F401
