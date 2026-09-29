# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The secret's own scope is asked, and asked correctly (#16982).

`accessible_vaults()` says which vaults a principal reaches;
`Secret.is_accessible_by` says whether a secret's scope admits them. Only the
first was ever asked, so a SESSION-scoped secret sitting in a reachable vault was
readable by anyone who reached the vault. The vault grant is necessary, not
sufficient.

These are unit tests of `_scope_permits`, which is where the composition lives.
The coordinator's own tests need Postgres and skip without it, so the two cases
that could be got wrong in opposite directions are pinned here where they run.
"""

from __future__ import annotations

import uuid

import pytest

from models.secret import Secret
from services.secrets_authz import PrincipalFacts
from services.secrets_coordinator import SecretsCoordinator

_USER = uuid.uuid4()
_OTHER = uuid.uuid4()
_COMPANY = uuid.uuid4()
_TEAM = str(uuid.uuid4())


async def _async(value):
    """A coroutine returning *value*, so a sync lambda can stand in for `_facts`."""
    return value


def _facts(*, companies=(), teams=()) -> PrincipalFacts:
    return PrincipalFacts(
        user_id=str(_USER),
        team_ids=frozenset(teams),
        company_roles={str(c): "admin" for c in companies},
    )


def _secret(**kw) -> Secret:
    defaults = {"owner_id": _OTHER, "org_id": None, "session_id": None, "team_ids": [], "shared_with": []}
    defaults.update(kw)
    return Secret(**defaults)


class TestTheOrgArgumentIsNeitherTautologyNorRefusal:
    """The one decision the ruling left open, and both wrong answers.

    `PrincipalFacts.company_roles` is a mapping, so a principal may hold several
    companies while `is_accessible_by` takes one.
    """

    def test_an_organization_secret_is_refused_when_the_principal_lacks_that_company(self):
        """Passing the secret's own org unconditionally would be a HOLE.

        The shared rule is `resource.company_id == principal.company_id`, so
        handing it the secret's own company makes the comparison tautological and
        every ORGANIZATION secret readable by anyone who reaches the vault.
        """
        secret = _secret(scope="organization", org_id=_COMPANY)

        assert not SecretsCoordinator._scope_permits(secret, _facts(companies=()), None)

    def test_an_organization_secret_is_admitted_when_the_principal_holds_that_company(self):
        """And passing None would be the opposite failure: every ORG secret unreadable."""
        secret = _secret(scope="organization", org_id=_COMPANY)

        assert SecretsCoordinator._scope_permits(secret, _facts(companies=(_COMPANY,)), None)

    def test_holding_a_different_company_does_not_admit(self):
        """A multi-company principal is admitted by the secret's company, not by any."""
        secret = _secret(scope="organization", org_id=_COMPANY)

        assert not SecretsCoordinator._scope_permits(secret, _facts(companies=(uuid.uuid4(),)), None)


class TestSessionScopeIsAskedNotAssumed:
    """The defect #16982 reported, at the level where it was reachable."""

    def test_a_session_secret_is_refused_without_a_matching_session(self):
        secret = _secret(scope="session", session_id="sess-A")

        assert not SecretsCoordinator._scope_permits(secret, _facts(), None)
        assert not SecretsCoordinator._scope_permits(secret, _facts(), "sess-B")

    def test_a_session_secret_is_admitted_with_its_own_session(self):
        """The contrast case: threading the id must actually admit the right caller."""
        secret = _secret(scope="session", session_id="sess-A")

        assert SecretsCoordinator._scope_permits(secret, _facts(), "sess-A")


class TestTheOrdinaryCasesStillPass:
    """None of the above may cost an owner or a team member their own secret."""

    def test_the_owner_reads_their_own(self):
        secret = _secret(scope="user", owner_id=_USER)

        assert SecretsCoordinator._scope_permits(secret, _facts(), None)

    def test_a_team_member_reads_a_group_secret(self):
        secret = _secret(scope="group", team_ids=[_TEAM])

        assert SecretsCoordinator._scope_permits(secret, _facts(teams=(_TEAM,)), None)

    def test_a_non_member_does_not_read_a_group_secret(self):
        secret = _secret(scope="group", team_ids=[_TEAM])

        assert not SecretsCoordinator._scope_permits(secret, _facts(teams=()), None)


class TestTheReadPathActuallyAsksIt:
    """`_scope_permits` being correct is worth nothing if `read` never calls it.

    The wiring guard pins that `is_accessible_by` is *referenced* from a
    production module, and a reference is not a reachable call -- mutating the
    coordinator to `return True` above the call left that guard green. This is
    the missing half, and it runs without Postgres, unlike the coordinator's own
    tests.
    """

    class _FakeService:
        def __init__(self):
            self.read_calls = 0
            self.listed = []

        async def read(self, session, *, secret_id, accessible_vaults):
            self.read_calls += 1
            return b"plaintext"

        async def list_for_vaults(self, session, *, accessible_vaults):
            return list(self.listed)

    class _FakeSession:
        def __init__(self, secret):
            self._secret = secret

        async def get(self, _model, _pk):
            return self._secret

    async def test_read_refuses_when_the_scope_does_not_permit(self, monkeypatch):
        from services.envelope_secrets_service import SecretAccessError

        service = self._FakeService()
        coord = SecretsCoordinator(service)
        monkeypatch.setattr(coord, "_facts", lambda *a, **k: _async(_facts()))
        monkeypatch.setattr(SecretsCoordinator, "_scope_permits", staticmethod(lambda *a: False))

        with pytest.raises(SecretAccessError):
            await coord.read(
                self._FakeSession(_secret(scope="session", session_id="s")),
                user_id=_USER,
                permissions=set(),
                secret_id=uuid.uuid4(),
            )

        assert service.read_calls == 0, "the value was decrypted despite the scope refusing"

    async def test_read_proceeds_when_the_scope_permits(self, monkeypatch):
        """The contrast case: the check must not refuse everyone."""
        service = self._FakeService()
        coord = SecretsCoordinator(service)
        monkeypatch.setattr(coord, "_facts", lambda *a, **k: _async(_facts()))
        monkeypatch.setattr(SecretsCoordinator, "_scope_permits", staticmethod(lambda *a: True))

        value = await coord.read(
            self._FakeSession(_secret(scope="user", owner_id=_USER)),
            user_id=_USER,
            permissions=set(),
            secret_id=uuid.uuid4(),
        )

        assert value == b"plaintext"
        assert service.read_calls == 1

    async def test_list_filters_on_the_scope(self, monkeypatch):
        service = self._FakeService()
        service.listed = [_secret(scope="user", owner_id=_USER), _secret(scope="session", session_id="s")]
        coord = SecretsCoordinator(service)
        monkeypatch.setattr(coord, "_facts", lambda *a, **k: _async(_facts()))
        monkeypatch.setattr(SecretsCoordinator, "_scope_permits", staticmethod(lambda s, *a: s.scope == "user"))

        kept = await coord.list(self._FakeSession(None), user_id=_USER, permissions=set())

        assert [s.scope for s in kept] == ["user"], "list returned a secret the scope refused"


def test_the_secrets_api_passes_no_session_and_that_is_deliberate():
    """Recorded as an assertion because `api/envelope_secrets.py` cannot hold a comment.

    That module sits at a frozen ceiling of 615 lines, so the seven-line note
    explaining this did not fit -- and a test is the better home anyway, because
    a comment cannot fail when someone "fixes" the omission by threading the
    wrong thing.

    The decision: `read_secret` and `list_secrets` pass no `session_id` because
    that API has no session context to pass. `session` in those handlers is the
    SQLAlchemy `AsyncSession`, not a scope session, and the two are easy to
    confuse. The consequence is deliberate: a SESSION-scoped secret is not
    reachable through those routes, because the scope check compares the secret's
    own session to the caller's and this caller has none.

    If a route ever does hold a session it must pass it -- and this test should
    then be narrowed to the routes that still do not, rather than deleted.
    """
    import ast
    from pathlib import Path

    import api.envelope_secrets as mod

    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"read", "list"}
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "coordinator"
    ]
    assert len(calls) == 2, f"expected the read and list coordinator calls, found {len(calls)}"
    for call in calls:
        passed = {kw.arg for kw in call.keywords}
        assert "session_id" not in passed, (
            f"api/envelope_secrets.py:{call.lineno} now passes session_id. If that API gained a "
            "session context, good -- narrow this test to the routes that still have none. If it "
            "passes the DB session by mistake, that is a scope check reading the wrong value."
        )
