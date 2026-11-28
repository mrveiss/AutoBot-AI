# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#19812: a URL's credentials are percent-encoded; PGPASSWORD and -U must not be."""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))

from _code_sync_import import import_code_sync  # noqa: E402

import_code_sync()

from api.code_sync import _build_pg_dump_command  # noqa: E402


def test_pg_dump_gets_the_real_credentials_from_an_encoded_url() -> None:
    parsed = urlparse("postgresql://u%40x:a%40%3A%2F%25b@db.local:5432/name")  # pragma: allowlist secret
    cmd, env = _build_pg_dump_command(parsed, Path("/tmp/d.dump"), {})
    assert env["PGPASSWORD"] == "a@:/%b"  # pragma: allowlist secret
    assert cmd[cmd.index("-U") + 1] == "u@x"
