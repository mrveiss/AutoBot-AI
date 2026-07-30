# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Legacy per-store key-derivation adapters, read-only for migration (#10088 / Task 1.3).

The umbrella's Task 1.3 calls for "legacy-key adapters (Fernet
``AUTOBOT_SECRETS_KEY``, LLC HKDF, SLM AES-GCM, field-encryption) read-only for
migration" — a shared, database-free home for the exact key-derivation math a
legacy store used, so a migration importer can decrypt its rows without
importing the live service module (and, transitively, its whole package).

``derive_llc_company_fernet`` is the LLC HKDF adapter: it reproduces
``llc.services.secret``'s per-company Fernet derivation byte-for-byte
(HKDF-SHA256 keyed on ``company_id``, URL-safe-base64-encoded to a 44-char
Fernet key). ``llc.services.secret`` itself delegates to this function (kept
as the single source of truth) rather than duplicating the math, so the two
can never drift.

Deliberately depends on nothing but ``cryptography`` — no SQLAlchemy, no
``llc.*``, no FastAPI — so migration modules can import it without pulling in
``llc/services/__init__.py``'s eager import of every concrete LLC service
(itself a real, separately-tracked coupling risk; see the umbrella's Task 4
discovery).
"""

from __future__ import annotations

import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def derive_llc_company_fernet(master_key: bytes, company_id: str) -> Fernet:
    """Derive a Fernet instance whose key is specific to *company_id*.

    Uses HKDF-SHA256 to stretch *master_key* into 32 bytes, keyed to
    *company_id* so each LLC company has a distinct encryption key. The 32
    output bytes are URL-safe-base64-encoded to satisfy Fernet's requirement
    of a 44-character key string.
    """
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=company_id.encode("utf-8"),
    )
    derived = hkdf.derive(master_key)
    fernet_key = base64.urlsafe_b64encode(derived)
    return Fernet(fernet_key)
