# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM's token-revocation state, in its own PostgreSQL (#18663).

The SLM is the configuration and monitoring layer: it is what deploys the
fleet, Redis included, so it must work with nothing but its own database. Its
revocation checks fail CLOSED (#16387); kept in a Redis the SLM host never has,
every authenticated request was refused and nobody could log in.

- ``slm_revoked_tokens``: one row per logged-out HS256 token (``jti``) until the
  token would have expired anyway.
- ``slm_password_epochs``: per subject, the time of the last password change; a
  token issued before it is revoked (#12924).

Beside ``models/database.py`` rather than in it: that file is at its size ceiling.
Registered on the same ``Base`` so ``create_all`` creates them; the migration
covers databases created earlier.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, String

from models.database import Base


class RevokedToken(Base):
    """A logged-out token, refused until ``expires_at`` (its own expiry)."""

    __tablename__ = "slm_revoked_tokens"

    jti = Column(String(64), primary_key=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)


class PasswordEpoch(Base):
    """The last password change of ``subject``, in epoch seconds."""

    __tablename__ = "slm_password_epochs"

    subject = Column(String(255), primary_key=True)
    epoch = Column(BigInteger, nullable=False)
