# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-credential capability scoping for paired devices (#14964).

Reaching AutoBot's remote-control surface has been equivalent to full control:
a paired-device record carried no capabilities, no approval state and no
revocation, so no enforcement point could ask *"is this credential allowed this
capability"*. This module is the answer to that question, expressed as a pure
predicate so the decision is the same wherever it is asked.

Two properties this module exists to guarantee
----------------------------------------------

**Positive assertion only.** :func:`capability_granted` returns ``True`` on one
path and one path only -- the requested capability is a known one, the
credential is approved, it is not revoked, and the capability name is present
in the stored grant set. Every other input, including every malformed or
unreadable one, falls out of the function as ``False``. There is no
default-allow branch to reach.

**Deny by construction for unknown capabilities.** The enum is a permanent
compatibility surface. A capability added to :class:`DeviceCapability` in a
later release is denied for every credential issued before it existed, because
that credential's stored grant set cannot contain a name nobody could write
into it yet. A capability name that is *not* in the enum is denied outright --
an unrecognised name is a denial, never a pass-through.

Deliberately **not** in scope here: whether a capability is enabled
platform-wide. That is the feature-flag axis (#14962) and is a different
question with a different subject. The two axes are combined by the caller, and
when both apply the stricter answer wins -- the same precedent
``services/feature_flags.combine_enforcement_modes`` sets for global mode
versus per-endpoint override.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Iterable


class DeviceCapability(str, Enum):
    """What a paired-device credential may be permitted on the control surface.

    Values are stored verbatim in ``desktop_mobile_devices.permissions`` and are
    therefore a persisted wire format: rename a value and every credential
    holding the old name silently loses the grant. Add new members; never
    repurpose an existing value.
    """

    #: Observe the canonical desktop framebuffer.
    DESKTOP_VIEW = "desktop:view"
    #: Inject keyboard/pointer events into the canonical desktop.
    DESKTOP_INPUT = "desktop:input"
    #: Open an interactive terminal session.
    TERMINAL = "terminal"
    #: Move files on or off the host across the control surface.
    FILE_TRANSFER = "file_transfer"


#: The grant set every credential starts from, and the value existing rows are
#: backfilled with by migration ``20260824_084``. Serialised form of "no
#: capability at all". Named here so the migration, the model default and the
#: tests all read the same literal rather than three copies of ``"[]"``.
NO_CAPABILITIES_JSON = "[]"

#: Every capability name the platform recognises. Membership of this set is the
#: first gate in :func:`capability_granted`; a name outside it is denied before
#: any stored grant is even consulted.
KNOWN_CAPABILITIES: frozenset[str] = frozenset(member.value for member in DeviceCapability)


def parse_device_permissions(raw: object) -> frozenset[str]:
    """Read a stored grant set, degrading to *no grants* on anything unreadable.

    ``raw`` is whatever the database column yielded: the JSON text this codebase
    writes, an already-decoded list (some drivers decode JSON columns), or --
    for a row written before the column existed, by a different writer, or by a
    corrupted update -- something else entirely. Only a JSON array of strings,
    or a list/tuple of strings, produces grants. Everything else, ``None``
    included, yields the empty set, because the safe reading of "I cannot tell
    what this credential was granted" is "nothing".

    Names not in :data:`KNOWN_CAPABILITIES` are dropped here as well, so a
    grant set cannot smuggle in a capability the platform does not define.
    """
    if isinstance(raw, (list, tuple)):
        return _known_names(raw)
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError:
            return frozenset()
    if not isinstance(raw, str):
        return frozenset()
    try:
        decoded = json.loads(raw)
    except (ValueError, TypeError):
        return frozenset()
    if not isinstance(decoded, (list, tuple)):
        return frozenset()
    return _known_names(decoded)


def _known_names(values: Iterable[object]) -> frozenset[str]:
    """Keep only entries that are strings naming a capability we define."""
    return frozenset(value for value in values if isinstance(value, str) and value in KNOWN_CAPABILITIES)


def serialise_device_permissions(capabilities: Iterable[DeviceCapability | str]) -> str:
    """Render a grant set for storage, dropping anything not a known capability.

    The inverse of :func:`parse_device_permissions` for the values it accepts.
    Sorted so the stored text is stable and two equal grant sets compare equal
    as strings in tests and in audit diffs.
    """
    names = _known_names(value.value if isinstance(value, DeviceCapability) else value for value in capabilities)
    return json.dumps(sorted(names))


def capability_granted(
    *,
    capability: DeviceCapability | str,
    permissions_raw: object,
    is_approved: object,
    revoked_at: object,
) -> bool:
    """Positive assertion: is *this* credential permitted *this* capability?

    ``True`` requires all four of: a capability this platform defines, an
    approved credential, an un-revoked credential, and the capability's name
    present in the credential's stored grant set. The arguments are taken as
    ``object`` on purpose -- they arrive straight off a database row, and a
    column that is ``None`` or an unexpected type must deny rather than raise
    (an exception on the authorisation path is a refusal the caller has to
    remember to catch; a ``False`` is one it cannot forget).
    """
    name = capability.value if isinstance(capability, DeviceCapability) else capability
    if not isinstance(name, str) or name not in KNOWN_CAPABILITIES:
        return False
    if is_approved is not True:
        return False
    if revoked_at is not None:
        return False
    return name in parse_device_permissions(permissions_raw)


def missing_capabilities(
    *,
    required: Iterable[DeviceCapability | str],
    permissions_raw: object,
    is_approved: object,
    revoked_at: object,
) -> tuple[str, ...]:
    """The subset of ``required`` this credential does **not** hold, sorted.

    An empty tuple means every requirement is positively satisfied. Callers
    needing "all of these" -- the raw VNC proxy socket, which carries both
    framebuffer and input on one stream -- use this so the refusal can name
    what was missing instead of only that something was.
    """
    denied = [
        (capability.value if isinstance(capability, DeviceCapability) else str(capability))
        for capability in required
        if not capability_granted(
            capability=capability,
            permissions_raw=permissions_raw,
            is_approved=is_approved,
            revoked_at=revoked_at,
        )
    ]
    return tuple(sorted(denied))
