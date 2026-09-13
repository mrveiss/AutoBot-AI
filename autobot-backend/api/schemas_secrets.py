# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The boundary type for a secret's own kind (#14974).

Lives beside ``schemas_system`` rather than inside it: that module is a
grandfathered file under a size ceiling that may not rise, and this is a
self-contained pair -- one narrowing annotation and the validator it carries --
with no other tie to the several hundred models around it.

``SecretModel`` and ``SecretCreateRequest`` in ``api/schemas_system.py`` import
``StorableSecretType`` from here, so ``api.schemas_system.StorableSecretType``
resolves exactly as it did before the move.
"""

from typing import Annotated

from pydantic import AfterValidator, WithJsonSchema

from autobot_shared.status_enums import SecretType


def _reject_the_wildcard(value: SecretType) -> SecretType:
    """``ANY`` is a requirement quantifier, never a stored classification.

    #13846: the canonical ``SecretType`` carries the wildcard so an agent
    mapping can say "any available secret". Persisting it would put the
    string "any" in the ``secrets.type`` column, where it matches no kind
    and every by-type query would step over it.
    """
    if value is SecretType.ANY:
        raise ValueError(
            f"secret type '{SecretType.ANY.value}' is a requirement wildcard, "
            "not a storable kind; pick a concrete type"
        )
    return value


# The half of the canonical taxonomy a secret may actually be (#14974).
#
# ``SecretType`` is one enum on purpose (#13846), and ``ANY`` is a genuine
# member of it — but it is a wildcard *quantifier* over the taxonomy, legal
# only in the requirement layer, where ``SecretType.expand`` resolves it into
# the concrete kinds before any lookup happens. At this boundary there is
# nothing to quantify: a secret has exactly one kind. So the asymmetry is
# stated here rather than left implicit — the enum keeps the wildcard, and
# every request/response field that classifies a single secret uses this.
#
# It carries both halves of the narrowing, so the declared type and the
# accepted type cannot drift apart again:
#
# * ``AfterValidator`` rejects the wildcard at runtime (422 on the request,
#   a loud parse failure on a stored row that somehow carries "any").
# * ``WithJsonSchema`` narrows the *advertised* schema to the same set, so a
#   caller reading the generated client types is never offered a value the
#   endpoint will always refuse.
#
# The member list is derived from ``SecretType.concrete()``, never written
# out, so a kind added to the enum appears here with no second edit — that
# hand-listing is exactly the drift #13846 was filed about.
StorableSecretType = Annotated[
    SecretType,
    AfterValidator(_reject_the_wildcard),
    WithJsonSchema(
        {
            "type": "string",
            "enum": [member.value for member in SecretType.concrete()],
            "title": "StorableSecretType",
            "description": (
                "A single credential kind. The canonical SecretType taxonomy "
                "without its 'any' wildcard, which quantifies over the "
                "taxonomy in agent requirements and is never a secret's own "
                "kind."
            ),
        }
    ),
]
