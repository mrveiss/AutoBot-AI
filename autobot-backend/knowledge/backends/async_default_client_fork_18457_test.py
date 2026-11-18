# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#18457: ``get_async_default_client`` has ONE definition, in knowledge.backends.

``utils.chromadb_client`` carried a byte-for-byte equivalent wrapper that no
caller imported; the canonical one forwards the same three keyword arguments.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import utils.chromadb_client as chromadb_client
from knowledge import backends


def test_utils_module_no_longer_defines_the_second_copy():
    assert not hasattr(chromadb_client, "get_async_default_client")
    assert "get_async_default_client" not in chromadb_client.__all__


@pytest.mark.asyncio
async def test_canonical_client_serves_the_former_signature():
    raw = MagicMock()
    fake = AsyncMock(return_value=raw)
    with patch("utils.async_chromadb_client.get_async_chromadb_client", fake):
        client = await backends.get_async_default_client(db_path="p", allow_reset=True, anonymized_telemetry=False)
    fake.assert_awaited_once_with(db_path="p", allow_reset=True, anonymized_telemetry=False)
    assert isinstance(client, backends.AsyncChromaDBClient)
