# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the canonical vault/principal namespace (Task 9.1, #10094 / umbrella #10088)."""

from __future__ import annotations

import base64

import pytest

from autobot_shared import secrets_vault as sv
from autobot_shared.secrets_vault import PrincipalKind, VaultKind, VaultRef


class TestVaultKind:
    def test_expected_kinds(self) -> None:
        assert {k.value for k in VaultKind} == {
            "system",
            "user",
            "agent",
            "service",
            "team",
            "role",
            "company",
            "node",
        }


class TestPrincipalKind:
    def test_expected_kinds(self) -> None:
        assert {k.value for k in PrincipalKind} == {"user", "agent", "service", "workflow"}


class TestVaultRefFormat:
    @pytest.mark.parametrize(
        "ref,expected",
        [
            (VaultRef(VaultKind.SYSTEM), "system"),
            (VaultRef(VaultKind.USER, "alice"), "user:alice"),
            (VaultRef(VaultKind.COMPANY, "acme-42"), "company:acme-42"),
            (VaultRef(VaultKind.AGENT, "agent_007"), "agent:agent_007"),
            (VaultRef(VaultKind.NODE, "node.1"), "node:node.1"),
            (VaultRef(VaultKind.ROLE, "admin"), "role:admin"),
        ],
    )
    def test_to_str(self, ref: VaultRef, expected: str) -> None:
        assert ref.to_str() == expected
        assert str(ref) == expected

    @pytest.mark.parametrize(
        "ref",
        [
            VaultRef(VaultKind.SYSTEM),
            VaultRef(VaultKind.USER, "550e8400-e29b-41d4-a716-446655440000"),
            VaultRef(VaultKind.COMPANY, "acme-42"),
            VaultRef(VaultKind.TEAM, "platform"),
            VaultRef(VaultKind.NODE, "node_00.SLM"),
        ],
    )
    def test_parse_roundtrip(self, ref: VaultRef) -> None:
        assert VaultRef.parse(ref.to_str()) == ref


class TestVaultRefValidation:
    def test_system_takes_no_id(self) -> None:
        with pytest.raises(ValueError, match="no id"):
            VaultRef(VaultKind.SYSTEM, "x")

    def test_non_system_requires_id(self) -> None:
        with pytest.raises(ValueError, match="requires an id"):
            VaultRef(VaultKind.USER)
        with pytest.raises(ValueError, match="requires an id"):
            VaultRef(VaultKind.COMPANY, "")

    def test_id_rejects_separator(self) -> None:
        # An id containing ':' would make the canonical string ambiguous.
        with pytest.raises(ValueError, match="separator"):
            VaultRef(VaultKind.USER, "a:b")

    def test_id_rejects_whitespace(self) -> None:
        with pytest.raises(ValueError, match="whitespace"):
            VaultRef(VaultKind.USER, "a b")
        with pytest.raises(ValueError):
            VaultRef(VaultKind.USER, "a\tb")

    def test_id_rejects_overlong(self) -> None:
        with pytest.raises(ValueError, match="255"):
            VaultRef(VaultKind.USER, "x" * 256)

    def test_id_allows_255(self) -> None:
        assert VaultRef(VaultKind.USER, "x" * 255).id == "x" * 255


class TestVaultRefParse:
    def test_unknown_kind_rejected(self) -> None:
        with pytest.raises(ValueError):
            VaultRef.parse("bogus:1")

    def test_unknown_singleton_rejected(self) -> None:
        with pytest.raises(ValueError):
            VaultRef.parse("bogus")

    def test_empty_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="requires an id"):
            VaultRef.parse("user:")

    def test_system_with_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="no id"):
            VaultRef.parse("system:x")


class TestHashableUsableAsGrantee:
    def test_frozen_hashable(self) -> None:
        s = {VaultRef(VaultKind.COMPANY, "A"), VaultRef(VaultKind.COMPANY, "A"), VaultRef(VaultKind.USER, "alice")}
        assert len(s) == 2

    def test_distinct_refs_differ(self) -> None:
        assert VaultRef(VaultKind.COMPANY, "A") != VaultRef(VaultKind.COMPANY, "B")
        assert VaultRef(VaultKind.COMPANY, "A") != VaultRef(VaultKind.TEAM, "A")


class TestInteropWithEnvelopeCrypto:
    """The whole point of the namespace: to_str() is what derive_vault_key consumes."""

    def test_to_str_drives_distinct_keys(self, monkeypatch) -> None:
        from autobot_shared import secrets_envelope as env

        monkeypatch.setenv(env.ROOT_KEY_ENV, base64.urlsafe_b64encode(bytes(range(32))).decode())
        root = env.load_root_key()
        k_a = env.derive_vault_key(root, VaultRef(VaultKind.COMPANY, "A").to_str())
        k_b = env.derive_vault_key(root, VaultRef(VaultKind.COMPANY, "B").to_str())
        k_sys = env.derive_vault_key(root, VaultRef(VaultKind.SYSTEM).to_str())
        assert len({k_a, k_b, k_sys}) == 3
        assert len(k_a) == 32


class TestModuleConstants:
    def test_max_id_len_matches_db_string_limit(self) -> None:
        # company_id / agent_id are String(255) in the LLC models.
        assert sv._MAX_ID_LEN == 255
