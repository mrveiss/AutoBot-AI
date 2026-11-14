# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one ``ReportError`` for the CI report readers (#18954).

``pipeline-scripts/marker_suite_report.py`` and ``security_scan_gate.py`` each
defined this identical class. A report that cannot be read or understood is a
failure, never a zero count: both readers raise it instead of returning an
empty result that would read as "nothing found".
"""

from __future__ import annotations


class ReportError(RuntimeError):
    """A report could not be read or understood. Never downgraded to zero."""
