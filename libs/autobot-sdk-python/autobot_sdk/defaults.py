# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pagination and search defaults for the SDK's resource methods.

These mirror ``autobot_shared.ssot_constants.QueryDefaults`` value for value.
They are *duplicated* rather than imported because this package ships to PyPI
with two dependencies -- ``httpx`` and ``pydantic`` -- and importing the
platform's shared module would drag the whole backend into a client install.

Duplication is only safe if something stops it drifting: the client and the
server would otherwise disagree about a page size while both looked correct in
isolation. ``repo_tests/sdk_defaults_match_ssot_test.py`` pins every constant
here against ``QueryDefaults`` and fails if either side moves alone.
"""

from __future__ import annotations

#: Results returned by ``knowledge.search()`` when the caller does not say.
DEFAULT_SEARCH_LIMIT: int = 10

#: Rows per page for list endpoints when the caller does not say.
DEFAULT_PAGE_SIZE: int = 50

#: Where a list starts when the caller does not say.
DEFAULT_OFFSET: int = 0
