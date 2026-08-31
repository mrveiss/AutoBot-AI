# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for the legacy Redis chat-secrets API surface (api/secrets.py).

Pins the GET /api/secrets/types response (scope + type option lists) so the
#11759 rename of the chat-secrets scope enum (``SecretScope`` ->
``ChatSecretScope``) provably does not change any served values, and asserts
the renamed enum stays distinct from the canonical authorization
``ScopeLevel`` (#11290).
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.schemas_system import ChatSecretScope
from autobot_shared.scoping.scope_level import ScopeLevel
from autobot_shared.status_enums import SecretType

# Exact response content served by GET /api/secrets/types — order and
# strings pinned; the #11759 rename must not change any of this.
EXPECTED_SCOPES = [
    {"value": "chat", "label": "Chat"},
    {"value": "general", "label": "General"},
    {"value": "user", "label": "User"},
    {"value": "session", "label": "Session"},
    {"value": "shared", "label": "Shared"},
    {"value": "group", "label": "Group"},
    {"value": "organization", "label": "Organization"},
]

# What GET /api/secrets/types serves: the CONCRETE taxonomy, in declaration
# order. #13846 unioned three forked secret-kind enums, so this gained
# `oauth_refresh_token` (which the DB row could always store but the API
# vocabulary could not express) and `connector_oauth_token` (which was a bare
# string in credential_store.py, belonging to no enum at all).
#
# `any` is deliberately absent: it is a requirement wildcard, never a storable
# kind, and the endpoint serves SecretType.concrete() rather than the whole
# enum. test_secret_type_values_pinned below pins that difference explicitly.
EXPECTED_TYPES = [
    {"value": "ssh_key", "label": "Ssh Key"},
    {"value": "password", "label": "Password"},
    {"value": "api_key", "label": "Api Key"},
    {"value": "token", "label": "Token"},
    {"value": "oauth_refresh_token", "label": "Oauth Refresh Token"},
    {"value": "connector_oauth_token", "label": "Connector Oauth Token"},
    {"value": "certificate", "label": "Certificate"},
    {"value": "database_url", "label": "Database Url"},
    {"value": "infrastructure_host", "label": "Infrastructure Host"},
    {"value": "other", "label": "Other"},
]

# The wildcard, kept out of everything the API serves or accepts (#13846).
EXPECTED_WILDCARD = "any"


class TestChatSecretScopeEnum:
    """The chat-secrets scope enum after the #11759 rename."""

    def test_members_and_values_pinned(self):
        assert [(m.name, m.value) for m in ChatSecretScope] == [
            ("CHAT", "chat"),
            ("GENERAL", "general"),
            ("USER", "user"),
            ("SESSION", "session"),
            ("SHARED", "shared"),
            ("GROUP", "group"),
            ("ORGANIZATION", "organization"),
        ]

    def test_distinct_from_canonical_scope_level(self):
        """ChatSecretScope must never be conflated with ScopeLevel (#11759)."""
        assert ChatSecretScope is not ScopeLevel
        assert "chat" not in {level.value for level in ScopeLevel}
        assert "workflow" not in {scope.value for scope in ChatSecretScope}

    def test_secret_type_values_pinned(self):
        """The enum carries the wildcard; the endpoint does not.

        #13846: these are two different populations on purpose. Asserting the
        enum equals the served list would have hidden exactly the thing worth
        pinning -- that `any` exists as a requirement vocabulary member and is
        excluded from every storable/presentable surface.
        """
        assert [t.value for t in SecretType] == [t["value"] for t in EXPECTED_TYPES] + [EXPECTED_WILDCARD]
        assert [t.value for t in SecretType.concrete()] == [t["value"] for t in EXPECTED_TYPES]
        assert EXPECTED_WILDCARD not in {t.value for t in SecretType.concrete()}

    def test_the_oauth_kinds_are_expressible(self):
        """#13846's functional gap: neither kind could be named before.

        `OAUTH_REFRESH_TOKEN` existed only on the persisted enum, so the API
        vocabulary could not express it; `connector_oauth_token` was a bare
        string that belonged to no enum at all.
        """
        assert SecretType.OAUTH_REFRESH_TOKEN.value == "oauth_refresh_token"
        assert SecretType.CONNECTOR_OAUTH_TOKEN.value == "connector_oauth_token"
        served = {t["value"] for t in EXPECTED_TYPES}
        assert {"oauth_refresh_token", "connector_oauth_token"} <= served


@pytest.mark.asyncio
async def test_get_secret_types_response_pinned():
    """GET /api/secrets/types serves identical content after the rename."""
    from api.secrets import get_secret_types

    response = await get_secret_types(admin_check=True)
    assert response.status_code == 200
    payload = json.loads(response.body)
    assert payload == {"types": EXPECTED_TYPES, "scopes": EXPECTED_SCOPES}


class TestCheckRateLimit:
    """check_rate_limit() delegates to the shared RateLimiter's custom
    single-window mode (window=60s, max=30) — migrated off the retired
    local in-memory class (#12646). No coverage previously existed."""

    def _fake_request(self, host: str) -> MagicMock:
        from fastapi import Request

        request = MagicMock(spec=Request)
        request.client = MagicMock(host=host)
        request.headers = {}
        return request

    @pytest.mark.asyncio
    async def test_allows_when_under_limit(self):
        from api.secrets import check_rate_limit

        with patch("autobot_shared.rate_limiter.get_async_redis_client", AsyncMock(return_value=None)):
            await check_rate_limit(self._fake_request("203.0.113.5"))  # must not raise

    @pytest.mark.asyncio
    async def test_raises_429_with_retry_after_when_denied(self):
        from fastapi import HTTPException

        from api.secrets import RATE_LIMIT_WINDOW, check_rate_limit

        redis = AsyncMock()
        redis.eval = AsyncMock(return_value=[0, "5"])

        with patch("autobot_shared.rate_limiter.get_async_redis_client", AsyncMock(return_value=redis)):
            with pytest.raises(HTTPException) as exc_info:
                await check_rate_limit(self._fake_request("203.0.113.6"))

        assert exc_info.value.status_code == 429
        assert exc_info.value.headers["Retry-After"] == str(RATE_LIMIT_WINDOW)


class TestGetSecretDualRead:
    """``_get_secret_dual_read`` (#10088 Task 3): unified store first, legacy file fallback.

    Mocks ``load_imported_json_secret`` directly — no Postgres needed here; the envelope
    read itself is covered by the Postgres-gated ``tests/migrations/test_json_secrets_importer.py``.
    """

    @pytest.mark.asyncio
    async def test_returns_unified_secret_without_touching_legacy_file(self):
        from api.secrets import _get_secret_dual_read

        unified = {"id": "s1", "scope": "general", "chat_id": None, "value": "v"}
        with (
            patch("api.secrets.load_imported_json_secret", AsyncMock(return_value=unified)),
            patch("api.secrets.secrets_manager") as legacy,
        ):
            result = await _get_secret_dual_read("s1", chat_id=None)
        assert result == unified
        legacy.get_secret.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_to_legacy_file_when_not_yet_imported(self):
        from api.secrets import _get_secret_dual_read

        legacy_result = {"id": "s2", "scope": "general", "value": "v2"}
        with (
            patch("api.secrets.load_imported_json_secret", AsyncMock(return_value=None)),
            patch("api.secrets.secrets_manager") as legacy,
        ):
            legacy.get_secret = MagicMock(return_value=legacy_result)
            result = await _get_secret_dual_read("s2", chat_id=None)
        assert result == legacy_result
        legacy.get_secret.assert_called_once_with("s2", chat_id=None)

    @pytest.mark.asyncio
    async def test_chat_scope_mismatch_denied_even_via_unified_store(self):
        from api.secrets import _get_secret_dual_read

        unified = {"id": "s3", "scope": "chat", "chat_id": "chat-a", "value": "v3"}
        with patch("api.secrets.load_imported_json_secret", AsyncMock(return_value=unified)):
            with pytest.raises(PermissionError):
                await _get_secret_dual_read("s3", chat_id="chat-b")


# ---------------------------------------------------------------------------
# #14974 — the wildcard must not be advertised where it is refused
# ---------------------------------------------------------------------------
#
# `SecretType.ANY` is a quantifier over the taxonomy, not a kind of credential.
# It is legal in the requirement layer (`AgentSecretMapping`, resolved by
# `SecretType.expand`) and illegal at the secrets API boundary, where a secret
# has exactly one kind. Before #14974 the boundary *declared* it and *refused*
# it: the generated client type offered "any" on the request body and the
# server answered 422. These tests pin both halves to the same population, so
# neither can widen without the other.


def _secrets_app():
    """A real app carrying the real secrets router, admin check overridden.

    Drives what a caller actually gets — the served OpenAPI document and real
    request validation — rather than the enum in isolation.
    """
    from fastapi import FastAPI

    from api.secrets import router
    from auth_middleware import check_admin_permission

    app = FastAPI()
    app.include_router(router, prefix="/api/secrets")
    app.dependency_overrides[check_admin_permission] = lambda: True
    return app


def _served_type_schema():
    """The `type` property of SecretCreateRequest as the OpenAPI document serves it."""
    schema = _secrets_app().openapi()["components"]["schemas"]["SecretCreateRequest"]
    return schema["properties"]["type"]


class TestTheWildcardIsNotAdvertised:
    """#14974: the declared secret type must equal the accepted secret type."""

    def test_served_schema_offers_only_the_concrete_taxonomy(self):
        """The generated client type is the narrowing, not a superset of it."""
        served = _served_type_schema()
        assert served["enum"] == [member.value for member in SecretType.concrete()]
        assert EXPECTED_WILDCARD not in served["enum"]
        # Inline, not a `$ref` to the whole enum — a `$ref` would drag the
        # wildcard back in however the schema was narrowed alongside it.
        assert "$ref" not in served
        assert "allOf" not in served

    def test_served_schema_is_derived_not_hand_listed(self):
        """A kind added to the enum reaches the API with no second edit.

        Hand-listing the members here is the drift #13846 was filed about, so
        this asserts the served list tracks `SecretType.concrete()` exactly —
        including order — rather than a copy that can silently fall behind.
        """
        served = _served_type_schema()
        assert served["enum"] == [t["value"] for t in EXPECTED_TYPES]
        assert len(served["enum"]) == len(SecretType) - 1

    def test_no_reachable_property_anywhere_offers_the_wildcard(self):
        """Nothing a caller can send or receive names "any" as a kind.

        Resolves `$ref` before looking: a property pointing at the canonical
        enum advertises the wildcard just as loudly as an inline copy of it.
        """
        schemas = _secrets_app().openapi()["components"]["schemas"]

        def _values(spec):
            ref = spec.get("$ref", "")
            target = schemas.get(ref.rsplit("/", 1)[-1], {}) if ref else spec
            return target.get("enum") or []

        offenders = [
            f"{name}.{prop}"
            for name, body in schemas.items()
            for prop, spec in (body.get("properties") or {}).items()
            if EXPECTED_WILDCARD in _values(spec)
        ]
        assert offenders == []

    def test_post_refuses_the_wildcard_as_a_body_field_error(self):
        """POST /api/secrets/ answers 422 and blames the `type` field."""
        from fastapi.testclient import TestClient

        with TestClient(_secrets_app()) as client:
            response = client.post(
                "/api/secrets/",
                json={
                    "name": "wildcard_attempt",
                    "type": EXPECTED_WILDCARD,
                    "scope": ChatSecretScope.GENERAL.value,
                    "value": "irrelevant",
                },
            )
        assert response.status_code == 422
        locations = [tuple(error["loc"]) for error in response.json()["detail"]]
        assert ("body", "type") in locations

    def test_post_still_accepts_every_concrete_kind(self):
        """The runtime narrowing refuses only the wildcard — not one real kind.

        `AfterValidator` sits on every secret-classifying field, so a check
        that grew past `ANY` would silently make real credential kinds
        unstorable. Over-narrowing the *advertised* enum is a different
        failure, caught by the two schema tests above.
        """
        from fastapi.testclient import TestClient

        for member in SecretType.concrete():
            with (
                patch("api.secrets.check_rate_limit", AsyncMock(return_value=None)),
                patch("api.secrets._mirror_llm_provider_key", AsyncMock(return_value=None)),
                patch("api.secrets.audit_log", MagicMock()),
                patch("api.secrets.audit_record", MagicMock()),
                patch("api.secrets.get_auth_middleware", MagicMock()),
                patch("api.secrets.secrets_manager") as manager,
            ):
                manager.create_secret = MagicMock(side_effect=_stored_secret)
                with TestClient(_secrets_app()) as client:
                    response = client.post(
                        "/api/secrets/",
                        json={
                            "name": f"concrete_{member.value}",
                            "type": member.value,
                            "scope": ChatSecretScope.GENERAL.value,
                            "value": "irrelevant",
                        },
                    )
            assert response.status_code == 201, f"{member.value}: {response.text}"
            assert response.json()["secret"]["type"] == member.value

    def test_a_stored_wildcard_row_fails_to_parse(self):
        """`SecretModel` is also the parse boundary over persisted rows.

        `update_secret` rebuilds a `SecretModel` straight from the stored row,
        so a row carrying "any" — however it got there — must fail loudly
        rather than be served back as a secret of kind "any".
        """
        from pydantic import ValidationError

        from api.schemas_system import SecretModel

        row = {
            "name": "smuggled",
            "type": EXPECTED_WILDCARD,
            "scope": ChatSecretScope.GENERAL.value,
        }
        with pytest.raises(ValidationError):
            SecretModel(**row)

        row["type"] = SecretType.API_KEY.value
        assert SecretModel(**row).type is SecretType.API_KEY


def _stored_secret(request):
    """Stand in for the encrypting store: echo the validated request back."""
    return request.to_secret_model()
