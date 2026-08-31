# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC company-scoped contact SQLAlchemy model (#13969).

A contact is a human who appears in a process — the supplier you email, the
customer you call — who has no account and must never be able to log in.
This is a deliberately separate table from ``users``: ``users`` is the
authentication boundary (password hash, session lookups, JWT subject), and
putting a non-authenticating identity inside it would mean every auth column
gains a row it must specially exclude — one missed exclusion is a login
path. ``LLCContact`` carries no password, no session relationship, and no
column any login/session lookup ever queries, so the absence of a login path
is structural, not merely unused code. See ``llc/tests/test_contact_no_login.py``.

Scoping (not tenant isolation — companies inside AutoBot are organisational
units of one installation, not customer isolation boundaries, per the
umbrella #13935 owner correction): every contact belongs to exactly one
``company_id``, mirroring ``LLCCompanyMembership`` and ``LLCSecret``. A
contact who legitimately serves two companies (e.g. a supplier shared by an
IT company and a marketing company inside the same installation) is
duplicated as two rows today rather than linked — this is the simplest
option and matches every other company-scoped LLC model's shape. Making one
contact referenceable from multiple companies would need a many-to-many
``llc_contact_company_links`` join table and a decision on what "delete"
means when other companies still hold a link; that is a product decision,
not an implementation detail, and is tracked as a follow-up decision issue
rather than guessed at here — tracked as #13998.

Company soft-delete purges contacts too (#13969 review M2): ``CompanyService.delete()``
is a soft delete (``Organization.deleted_at``), and every company listing filters
``deleted_at.is_(None)`` — so without this, a soft-deleted company's contacts would
vanish from every UI path while their PII stayed at rest forever. ``CompanyService.delete()``
therefore also issues a hard DELETE against ``llc_contacts`` for that company_id in the
same transaction. See ``llc/services/company.py::delete`` docstring for the reasoning.

Never in the embedding/knowledge plane: no code path in ``llc/services/contact.py``
imports ``knowledge``, ``llc.kb``, or ``utils.async_chromadb_client`` — a
contact's PII can never be pushed into a vector store, which cannot honour a
deletion request once written. See ``llc/tests/test_contacts_no_embedding.py``.

Not an org-chart hierarchy member (per the owner decision on #13969): no
``reports_to``, no budget, no heartbeat. ``get_org_chart`` must never query
this table.
"""

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base


class LLCContact(Base):
    """A human in a process with no account — never a ``users`` row.

    ``full_name`` is the only required field; ``email``/``phone`` are the
    process contact channels and ``role_title`` is free text describing the
    contact's function (e.g. "Accounts Payable at Acme Supplies") — deliberately
    NOT ``MembershipRole``, which is a ``users``-only company-role vocabulary
    and does not apply to a person with no account.
    """

    __tablename__ = "llc_contacts"

    # id is a client-side default (not server_default=gen_random_uuid()) so the
    # ORM always supplies it explicitly — matches LLCSecret, and keeps this
    # model creatable against a plain SQLite test engine with no Postgres
    # function support.
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(sa.String(320), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(sa.String(64), nullable=True)
    role_title: Mapped[Optional[str]] = mapped_column(sa.String(255), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )


__all__ = ["LLCContact"]
