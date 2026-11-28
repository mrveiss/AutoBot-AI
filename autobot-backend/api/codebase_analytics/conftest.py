# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""codebase_analytics test setup: no test opens the real code collection through the run record (#21003).

The results routes label their answer with the source's run record
(``run_status.run_response_fields``), which reads the ChromaDB collection.  A test
that calls one of those handlers directly, with its own store patched, must not
fall through to the deployment's store.  With no collection the record reads as
absent (``run: None``); a test that exercises the record patches the accessor itself.
"""

from unittest.mock import AsyncMock, patch

import pytest

from api.codebase_analytics import run_status


@pytest.fixture(autouse=True)
def _no_real_run_record_store():
    with patch.object(run_status, "get_code_collection_async", AsyncMock(return_value=None)):
        yield
