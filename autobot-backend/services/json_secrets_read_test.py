# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The envelope-read-unusable log names a hash of secret_id, never the raw id (#16444).

CodeQL flagged this line (py/clear-text-logging-sensitive-data): secret_id is
a DB row id, not a credential, but the taint tracker flags it on the
parameter name alone. Pins the property (raw id absent from the log), not
the mechanism.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_raw_secret_id_never_logged_on_decryption_failure(caplog):
    from autobot_shared.secrets_envelope import DecryptionError
    from services.json_secrets_read import read_imported_json_secret_in_session

    fake_row = AsyncMock()
    fake_row.id = "row-id-1"

    with (
        patch("services.json_secrets_read._find_by_marker", new=AsyncMock(return_value=fake_row)),
        patch("services.envelope_secrets_service.EnvelopeSecretsService") as mock_service_cls,
        caplog.at_level("WARNING"),
    ):
        mock_service_cls.return_value.read = AsyncMock(side_effect=DecryptionError("bad key"))
        result = await read_imported_json_secret_in_session(
            session=AsyncMock(), secret_id="my-secret-id", root_key=b"k" * 32
        )

    assert result is None
    assert "my-secret-id" not in caplog.text
    assert "Envelope read unusable" in caplog.text
