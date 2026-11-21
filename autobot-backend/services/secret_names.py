# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reserved secret names (#17850): the ``connector:`` prefix belongs to the connector credential writer.

The connector mirror adopts, rotates and (on reconcile) deletes the envelope row named
``connector:<id>:auth``. A user-created secret under that prefix could be adopted, overwritten and later
deleted by it, so user-facing create and rename are refused. Only ``services.credential_write`` (which calls
the raw ``EnvelopeSecretsService``, not the coordinator) may create or rotate such names. Existing rows are
left untouched: the check runs on a NEW name only, never on read, list or delete.
"""

from __future__ import annotations

import unicodedata

from services.credential_write import CONNECTOR_NAME_PREFIX


class ReservedSecretNameError(Exception):
    """A user-facing create or rename asked for a reserved name; answered as the fixed 409 (no name echoed)."""


def is_reserved_secret_name(name: str | None) -> bool:
    """True when *name* starts with the reserved prefix after whitespace, case and Unicode-width folding."""
    folded = unicodedata.normalize("NFKC", name or "").strip().casefold()
    return folded.startswith(CONNECTOR_NAME_PREFIX)


def refuse_reserved_secret_name(name: str | None) -> None:
    """Raise :class:`ReservedSecretNameError` when a user-supplied *name* is reserved."""
    if is_reserved_secret_name(name):
        raise ReservedSecretNameError("secret name prefix is reserved")
