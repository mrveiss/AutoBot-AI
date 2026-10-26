# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The severity vocabulary of a codebase-analytics *problem*, most severe first (#19336).

Not ``autobot_shared.status_enums.Severity``: a problem can be graded ``hint`` (an
editor-style suggestion), which that enum deliberately does not carry. The report and the
charts both list problems in this order; this is the one place it is written down.
"""

PROBLEM_SEVERITY_ORDER: tuple[str, ...] = ("high", "medium", "low", "info", "hint")
