# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Field-level validation on ContactCreate/ContactUpdate (#13969 review M3).

A contact's stated purpose is "the supplier you email" — an unvalidated
``email`` field lets a CRLF become SMTP header injection the moment a sender
consumes it, and unvalidated ``full_name``/``notes`` become stored XSS at any
``v-html`` sink (#13938 renders these people in the Org Chart). The global
injection middleware scans SQL/command/path only, not XSS or CRLF, so this
has to be enforced at the schema.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from llc.api.contacts import ContactCreate, ContactUpdate


class TestEmailValidation:
    def test_valid_email_accepted(self) -> None:
        ContactCreate(full_name="Ada Lovelace", email="ada@supplier.example.com")

    def test_malformed_email_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ContactCreate(full_name="Ada Lovelace", email="not-an-email")

    def test_crlf_in_email_rejected(self) -> None:
        """The concrete SMTP header injection vector this validation closes."""
        with pytest.raises(ValidationError):
            ContactCreate(
                full_name="Ada Lovelace",
                email="ada@supplier.example.com\r\nBcc: attacker@evil.example.com",
            )


class TestPhoneValidation:
    def test_valid_phone_accepted(self) -> None:
        ContactCreate(full_name="Ada Lovelace", phone="+1 (555) 010-0100")

    def test_free_text_phone_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ContactCreate(full_name="Ada Lovelace", phone="call me maybe")

    def test_script_tag_in_phone_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ContactCreate(full_name="Ada Lovelace", phone="<script>alert(1)</script>")


class TestNotesBounded:
    def test_notes_within_limit_accepted(self) -> None:
        ContactCreate(full_name="Ada Lovelace", notes="x" * 2000)

    def test_notes_exceeding_limit_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ContactCreate(full_name="Ada Lovelace", notes="x" * 2001)


class TestFullNameStripped:
    def test_whitespace_only_full_name_rejected(self) -> None:
        """Before this validator, " " passed min_length=1 as a valid name."""
        with pytest.raises(ValidationError):
            ContactCreate(full_name="   ")

    def test_surrounding_whitespace_is_stripped(self) -> None:
        contact = ContactCreate(full_name="  Ada Lovelace  ")
        assert contact.full_name == "Ada Lovelace"

    def test_update_whitespace_only_full_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ContactUpdate(full_name="   ")

    def test_update_full_name_omitted_stays_none(self) -> None:
        update = ContactUpdate(phone="+1-555-0100")
        assert update.full_name is None
