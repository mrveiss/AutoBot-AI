# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical vault & principal namespace for AutoBot's unified secrets infrastructure.

Task 9.1 of umbrella #10088. The single source of truth for the ``vault_id``
strings that ``secrets_envelope.derive_vault_key()`` consumes and that a wrapped
DEK stores as its ``grantee`` — so the crypto layer, the RBAC checks, and the
audit access-graph all agree on one namespace instead of passing ad-hoc strings.

A :class:`VaultRef` is a key/access boundary; a :class:`PrincipalKind` is the
kind of actor that resolves to a set of vaults (the resolution itself —
credential → principal → vaults via role/team/company membership — is DB-backed
and lands with Task 2/9.2).

Canonical string form: ``system`` for the singleton system vault, else
``<kind>:<id>`` (e.g. ``user:alice``, ``company:acme-42``, ``role:admin``). The
``id`` may not contain the ``:`` separator or whitespace, which keeps the
encoding unambiguous and round-trippable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

_SEP = ":"
# Matches the String(255) limit on company_id / agent_id in the LLC models.
_MAX_ID_LEN = 255


class VaultKind(str, Enum):
    """A key/access boundary within the one secrets store."""

    SYSTEM = "system"  # admin-only system secrets (provider keys, internal tokens)
    USER = "user"  # a person's personal vault
    AGENT = "agent"  # an agent's own vault
    SERVICE = "service"  # a service principal's vault
    TEAM = "team"  # a team / department group vault
    ROLE = "role"  # a role group vault
    COMPANY = "company"  # an LLC company vault
    NODE = "node"  # a fleet node's credential vault


class PrincipalKind(str, Enum):
    """The kind of actor that authenticates and resolves to a set of vaults."""

    USER = "user"
    AGENT = "agent"
    SERVICE = "service"
    WORKFLOW = "workflow"


# Vault kinds that are singletons (no id): exactly the system vault.
_SINGLETON_KINDS = frozenset({VaultKind.SYSTEM})


@dataclass(frozen=True)
class VaultRef:
    """A reference to one vault: a kind plus an id (id omitted for ``system``).

    Frozen + hashable so it can be a dict key or set member (e.g. the set of
    vaults a principal may use, or a grant's grantee).
    """

    kind: VaultKind
    id: str | None = None

    def __post_init__(self) -> None:
        if self.kind in _SINGLETON_KINDS:
            if self.id is not None:
                raise ValueError(f"{self.kind.value} vault takes no id")
            return
        if not self.id:
            raise ValueError(f"{self.kind.value} vault requires an id")
        if _SEP in self.id:
            raise ValueError(f"vault id may not contain the {_SEP!r} separator: {self.id!r}")
        if any(c.isspace() for c in self.id):
            raise ValueError(f"vault id may not contain whitespace: {self.id!r}")
        if len(self.id) > _MAX_ID_LEN:
            raise ValueError(f"vault id exceeds {_MAX_ID_LEN} chars")

    def to_str(self) -> str:
        """Canonical ``vault_id`` string for crypto/storage."""
        if self.id is None:
            return self.kind.value
        return f"{self.kind.value}{_SEP}{self.id}"

    def __str__(self) -> str:
        return self.to_str()

    @classmethod
    def parse(cls, value: str) -> VaultRef:
        """Parse a canonical ``vault_id`` string back into a :class:`VaultRef`."""
        kind_str, sep, id_str = value.partition(_SEP)
        kind = VaultKind(kind_str)  # raises ValueError on an unknown kind
        return cls(kind, id_str if sep else None)
