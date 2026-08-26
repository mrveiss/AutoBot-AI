# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The capability predicate denies everything it was not positively told to allow (#14964).

Every assertion here is about a *refusal* except one, and that asymmetry is the
point: ``capability_granted`` has exactly one path to ``True`` and this module
enumerates the ways a caller might hope to reach it without taking that path.
"""

import pytest

from autobot_shared.auth.device_capabilities import (
    KNOWN_CAPABILITIES,
    NO_CAPABILITIES_JSON,
    DeviceCapability,
    capability_granted,
    missing_capabilities,
    parse_device_permissions,
    serialise_device_permissions,
)

#: The state migration 20260824_084 leaves every pre-existing row in.
BACKFILLED_ROW = {
    "permissions_raw": NO_CAPABILITIES_JSON,
    "is_approved": False,
    "revoked_at": None,
}


def test_the_capability_enumeration_is_not_empty():
    """Guards every parametrised test below.

    ``@parametrize`` over an empty sequence collects zero cases and reports as
    passed, so an enumeration that lost its members would turn the refusal
    suite into a suite that asserts nothing at all. This is the assertion that
    fails first when that happens.
    """
    assert len(list(DeviceCapability)) >= 4
    assert KNOWN_CAPABILITIES == frozenset(member.value for member in DeviceCapability)
    assert {"desktop:view", "desktop:input", "terminal", "file_transfer"} <= KNOWN_CAPABILITIES


@pytest.mark.parametrize("capability", list(DeviceCapability))
def test_a_row_backfilled_by_the_migration_is_denied_every_capability(capability):
    """AC: a credential issued before the column existed cannot exercise anything.

    ``BACKFILLED_ROW`` is literally the state ``20260824_084`` writes. If the
    backfill default is ever flipped to a grant, this is the test that goes red.
    """
    assert capability_granted(capability=capability, **BACKFILLED_ROW) is False


@pytest.mark.parametrize("capability", list(DeviceCapability))
def test_the_one_granting_path(capability):
    """The single positive case: approved, un-revoked, and named in the grant set."""
    assert (
        capability_granted(
            capability=capability,
            permissions_raw=serialise_device_permissions([capability]),
            is_approved=True,
            revoked_at=None,
        )
        is True
    )


@pytest.mark.parametrize(
    "unknown",
    [
        "desktop:paint",
        "DESKTOP:VIEW",
        "terminal ",
        "",
        "*",
        None,
        42,
    ],
)
def test_an_unknown_capability_name_denies(unknown):
    """A name the platform does not define is a denial, never a pass-through.

    Includes the near-misses that a fall-through implementation would let
    slip: wrong case, trailing space, a wildcard, a non-string.
    """
    assert (
        capability_granted(
            capability=unknown,
            permissions_raw='["desktop:view", "desktop:input", "terminal", "file_transfer"]',
            is_approved=True,
            revoked_at=None,
        )
        is False
    )


def test_a_capability_added_later_is_denied_for_a_credential_issued_before_it():
    """The compatibility property, exercised the way the future will exercise it.

    A credential minted today can only ever hold names that exist today. When a
    capability is added in a later release, the grant set of every existing
    credential is silently missing it — and must therefore deny it. Simulated
    here by granting the credential everything the platform currently defines
    and then asking for a capability that does not exist yet.
    """
    grant_everything_known = serialise_device_permissions(list(DeviceCapability))
    future_capability = "clipboard:read"
    assert future_capability not in KNOWN_CAPABILITIES, "pick a name this release genuinely does not define"

    assert (
        capability_granted(
            capability=future_capability,
            permissions_raw=grant_everything_known,
            is_approved=True,
            revoked_at=None,
        )
        is False
    )


@pytest.mark.parametrize(
    "permissions_raw",
    [
        None,
        "",
        "not json",
        "{}",
        '{"desktop:view": true}',
        '"desktop:view"',
        "[1, 2, 3]",
        b"\xff\xfe",
        object(),
    ],
)
def test_an_unreadable_grant_set_grants_nothing(permissions_raw):
    """"I cannot tell what this credential was granted" reads as "nothing"."""
    assert (
        capability_granted(
            capability=DeviceCapability.DESKTOP_VIEW,
            permissions_raw=permissions_raw,
            is_approved=True,
            revoked_at=None,
        )
        is False
    )


def test_revocation_denies_a_capability_the_credential_still_holds():
    """``revoked_at`` overrides the grant set — the grant is not erased, it is overruled."""
    granted = serialise_device_permissions([DeviceCapability.TERMINAL])
    assert capability_granted(
        capability=DeviceCapability.TERMINAL, permissions_raw=granted, is_approved=True, revoked_at=None
    )
    assert (
        capability_granted(
            capability=DeviceCapability.TERMINAL,
            permissions_raw=granted,
            is_approved=True,
            revoked_at="2026-08-24T00:00:00+00:00",
        )
        is False
    )


def test_an_unapproved_credential_is_denied_a_capability_it_holds():
    granted = serialise_device_permissions([DeviceCapability.TERMINAL])
    assert (
        capability_granted(
            capability=DeviceCapability.TERMINAL,
            permissions_raw=granted,
            is_approved=False,
            revoked_at=None,
        )
        is False
    )


@pytest.mark.parametrize("truthy_but_not_true", [1, "true", "yes", [1]])
def test_approval_must_be_the_boolean_true_not_merely_truthy(truthy_but_not_true):
    """A column read as ``1`` or ``"true"`` by some other driver must not authorise.

    Accepting anything truthy is how a string column ``"false"`` becomes a
    grant. The predicate demands the actual boolean.
    """
    assert (
        capability_granted(
            capability=DeviceCapability.TERMINAL,
            permissions_raw=serialise_device_permissions([DeviceCapability.TERMINAL]),
            is_approved=truthy_but_not_true,
            revoked_at=None,
        )
        is False
    )


def test_parse_drops_names_the_platform_does_not_define():
    assert parse_device_permissions('["terminal", "clipboard:read"]') == frozenset({"terminal"})


def test_serialise_is_stable_and_drops_unknown_names():
    assert serialise_device_permissions([DeviceCapability.TERMINAL, "clipboard:read"]) == '["terminal"]'
    assert serialise_device_permissions([]) == NO_CAPABILITIES_JSON


def test_missing_capabilities_names_each_shortfall_and_is_empty_only_when_all_hold():
    both = [DeviceCapability.DESKTOP_VIEW, DeviceCapability.DESKTOP_INPUT]
    view_only = serialise_device_permissions([DeviceCapability.DESKTOP_VIEW])

    assert missing_capabilities(required=both, permissions_raw=view_only, is_approved=True, revoked_at=None) == (
        "desktop:input",
    )
    assert (
        missing_capabilities(
            required=both,
            permissions_raw=serialise_device_permissions(both),
            is_approved=True,
            revoked_at=None,
        )
        == ()
    )
    assert missing_capabilities(required=both, **BACKFILLED_ROW) == ("desktop:input", "desktop:view")
