# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reading the secrets store, with absence and corruption kept distinct (#14126).

Its own module for the same reason as ``secrets_store_errors``: ``api/secrets.py``
sits at its recorded size ceiling and a grandfathered file may not grow (#14236),
so the fix had to make room rather than take it. Extracting the read is the
honest way to do that — the caller keeps the caching policy, this owns the file.

The distinction is the whole point. A missing file is a fresh install and reads
as an empty store. A file that is present and unparseable is a fault, and must
not read as "no secrets are configured": every caller then sees a healthy, empty
store, and the next write persists that emptiness over the ciphertext still on
disk, turning a recoverable parse error into permanent data loss.
"""

from __future__ import annotations

import json
from typing import Dict, Optional

from security.secrets_store_errors import SecretsStoreUnavailable


def load_secrets_json(path: str) -> Optional[Dict[str, Dict]]:
    """Return the parsed store, or ``None`` when the file does not exist.

    Raises:
        SecretsStoreUnavailable: the file exists and is not valid JSON.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        # Raced a delete since the caller's exists() check; absent is a fresh install.
        return None
    except json.JSONDecodeError as exc:
        raise SecretsStoreUnavailable("secrets file is not valid JSON") from exc
