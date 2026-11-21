# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Known sites where a Company OS (LLC) response is built from exception text (#21579).

Down-only: ratcheted against the base commit in `company_os_exception_text_21579_test.py`. A key is
`<path>::<enclosing function qualname>#<occurrence index>` as measured by
`repo_tests/_company_os_exception_text_scan.py`; the value is always 1. Empty once every site answers through
`http_refusal` or an exception's `public_detail`.
"""

from __future__ import annotations

COMPANY_OS_EXCEPTION_TEXT_SITES: dict[str, int] = {}
