# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
SCIM 2.0 Inbound Provisioning

RFC 7644 compliant endpoints for IdP-pushed user/group lifecycle.
Mounts at /scim/v2 (registered without /api prefix so IdPs can reach it directly).

Bearer-token auth: SCIM clients (Okta/Entra/Google) authenticate with the
'scim_bearer_token' key from SystemSecret (AES-GCM encrypted at rest).
The token is seeded once on first startup; admins retrieve it via the
SLM secrets UI or CLI.

Group→role: delegates entirely to SSOService._sync_idp_groups_to_roles
via _resolve_managed_roles + UserService.assign_role / revoke_role so
the identical reconcile logic runs for both SSO logins and SCIM pushes.
"""

import logging
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import SystemSecret
from services.database import db_service
from services.encryption import decrypt_data
from user_management.database import get_slm_session
from user_management.models import Role, User, UserRole
from user_management.services.base_service import TenantContext
from user_management.services.user_service import DuplicateUserError, UserNotFoundError, UserService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scim/v2", tags=["scim"])

# SCIM 2.0 schema URNs (RFC 7643)
_SCIM_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
_SCIM_GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"
_SCIM_LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
_SCIM_ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"

# SystemSecret key for the SCIM bearer token (not a credential — key name only)
_SCIM_TOKEN_KEY = "scim_bearer_token"  # nosec B105


# ---------------------------------------------------------------------------
# Dependency: SLM DB session
# ---------------------------------------------------------------------------


async def _get_slm_db() -> AsyncSession:
    async with get_slm_session() as session:
        yield session


# ---------------------------------------------------------------------------
# Bearer-token authentication
# ---------------------------------------------------------------------------


async def _load_scim_token() -> str | None:
    """Load the SCIM bearer token from SystemSecret (main SLM DB, AES-GCM encrypted)."""
    try:
        async with db_service.session() as db:
            result = await db.execute(select(SystemSecret).where(SystemSecret.key == _SCIM_TOKEN_KEY))
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return decrypt_data(row.encrypted_value)
    except Exception:
        logger.warning("Could not load SCIM bearer token from SystemSecret")
        return None


async def _require_scim_bearer(request: Request) -> None:
    """FastAPI dependency: validates the SCIM IdP bearer token."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_scim_error("Bearer token required", "invalidCredentials"),
            headers={"WWW-Authenticate": "Bearer"},
        )
    provided = auth_header[len("bearer ") :].strip()
    expected = await _load_scim_token()
    if not expected or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_scim_error("Invalid bearer token", "invalidCredentials"),
            headers={"WWW-Authenticate": "Bearer"},
        )


# ---------------------------------------------------------------------------
# SCIM response helpers
# ---------------------------------------------------------------------------


def _scim_error(detail: str, scim_type: str = "invalidValue", status_code: int = 400) -> dict:
    return {"schemas": [_SCIM_ERROR_SCHEMA], "detail": detail, "scimType": scim_type, "status": str(status_code)}


def _user_to_scim(user: User, base_url: str) -> dict:
    """Serialise a User ORM instance to a SCIM 2.0 User resource dict."""
    name_parts = (user.display_name or user.username).split(" ", 1)
    given = name_parts[0]
    family = name_parts[1] if len(name_parts) > 1 else ""
    return {
        "schemas": [_SCIM_USER_SCHEMA],
        "id": str(user.id),
        "userName": user.username,
        "name": {"givenName": given, "familyName": family},
        "emails": [{"value": user.email, "primary": True}],
        "active": user.is_active,
        "externalId": getattr(user, "scim_external_id", None) or "",
        "meta": {
            "resourceType": "User",
            "created": _fmt_dt(user.created_at),
            "lastModified": _fmt_dt(user.updated_at or user.created_at),
            "location": f"{base_url}/scim/v2/Users/{user.id}",
        },
    }


def _group_scim(group_id: str, display_name: str, members: list[dict], base_url: str) -> dict:
    return {
        "schemas": [_SCIM_GROUP_SCHEMA],
        "id": group_id,
        "displayName": display_name,
        "members": members,
        "meta": {
            "resourceType": "Group",
            "location": f"{base_url}/scim/v2/Groups/{group_id}",
        },
    }


def _fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _base_url(request: Request) -> str:
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.url.netloc) or request.url.netloc
    return f"{scheme}://{host}"


# ---------------------------------------------------------------------------
# SCIM /Users
# ---------------------------------------------------------------------------


def _extract_scim_user_fields(body: dict) -> dict:
    """Parse a SCIM User body into UserService-compatible kwargs."""
    username = body.get("userName", "")
    emails = body.get("emails", [])
    primary_email = next((e["value"] for e in emails if e.get("primary")), None)
    if not primary_email and emails:
        primary_email = emails[0].get("value")
    name = body.get("name", {})
    given = name.get("givenName", "")
    family = name.get("familyName", "")
    display = f"{given} {family}".strip() or username
    return {
        "username": username,
        "email": primary_email or f"{username}@scim.local",
        "display_name": display,
        "external_id": body.get("externalId", ""),
        "active": body.get("active", True),
    }


@router.post("/Users", dependencies=[Depends(_require_scim_bearer)], status_code=201)
async def scim_create_user(request: Request, db: AsyncSession = Depends(_get_slm_db)) -> JSONResponse:
    """POST /scim/v2/Users — provision a new user from an IdP push."""
    body: dict = await request.json()
    fields = _extract_scim_user_fields(body)
    context = TenantContext(is_platform_admin=True)
    user_svc = UserService(db, context)
    try:
        user = await user_svc.create_user(
            email=fields["email"],
            username=fields["username"],
            display_name=fields["display_name"],
        )
        if not fields["active"]:
            await user_svc.deactivate_user(user.id)
        await db.commit()
    except DuplicateUserError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_scim_error(str(exc), "uniqueness", 409),
        ) from exc
    return JSONResponse(status_code=201, content=_user_to_scim(user, _base_url(request)))


@router.get("/Users/{user_id}", dependencies=[Depends(_require_scim_bearer)])
async def scim_get_user(user_id: str, request: Request, db: AsyncSession = Depends(_get_slm_db)) -> JSONResponse:
    """GET /scim/v2/Users/{id} — fetch a single SCIM user."""
    try:
        uid = uuid.UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=_scim_error("Not found", "invalidValue", 404)) from exc
    context = TenantContext(is_platform_admin=True)
    user = await UserService(db, context).get_user(uid)
    if not user:
        raise HTTPException(status_code=404, detail=_scim_error("User not found", "invalidValue", 404))
    return JSONResponse(content=_user_to_scim(user, _base_url(request)))


@router.get("/Users", dependencies=[Depends(_require_scim_bearer)])
async def scim_list_users(
    request: Request,
    filter: str | None = Query(default=None),
    startIndex: int = Query(default=1, ge=1),
    count: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(_get_slm_db),
) -> JSONResponse:
    """GET /scim/v2/Users?filter=userName eq "x" — list or search users."""
    context = TenantContext(is_platform_admin=True)
    user_svc = UserService(db, context)

    if filter:
        user = await _apply_scim_filter(filter, user_svc)
        resources = [_user_to_scim(user, _base_url(request))] if user else []
        return JSONResponse(content=_list_response(resources, len(resources), 1, len(resources)))

    offset = max(startIndex - 1, 0)
    users, total = await user_svc.list_users(limit=count, offset=offset, include_inactive=True)
    resources = [_user_to_scim(u, _base_url(request)) for u in users]
    return JSONResponse(content=_list_response(resources, total, startIndex, count))


async def _apply_scim_filter(filter_str: str, user_svc: UserService) -> User | None:
    """Support 'userName eq "value"' and 'emails.value eq "x"' SCIM filters."""
    lower = filter_str.strip().lower()
    if lower.startswith("username eq "):
        value = filter_str.split('"')[1] if '"' in filter_str else filter_str.split("'")[1]
        return await user_svc.get_user_by_username(value)
    if lower.startswith("emails.value eq ") or lower.startswith("email eq "):
        value = filter_str.split('"')[1] if '"' in filter_str else filter_str.split("'")[1]
        return await user_svc.get_user_by_email(value)
    return None


def _list_response(resources: list, total: int, start: int, count: int) -> dict:
    return {
        "schemas": [_SCIM_LIST_SCHEMA],
        "totalResults": total,
        "startIndex": start,
        "itemsPerPage": count,
        "Resources": resources,
    }


@router.put("/Users/{user_id}", dependencies=[Depends(_require_scim_bearer)])
async def scim_replace_user(user_id: str, request: Request, db: AsyncSession = Depends(_get_slm_db)) -> JSONResponse:
    """PUT /scim/v2/Users/{id} — full replace (update profile + active flag)."""
    body: dict = await request.json()
    user = await _get_user_or_404(user_id, db)
    fields = _extract_scim_user_fields(body)
    context = TenantContext(is_platform_admin=True)
    user_svc = UserService(db, context)
    await user_svc.update_user(user.id, email=fields["email"], display_name=fields["display_name"])
    await _apply_active_flag(user, fields["active"], user_svc)
    await db.commit()
    updated = await user_svc.get_user(user.id)
    return JSONResponse(content=_user_to_scim(updated, _base_url(request)))


@router.patch("/Users/{user_id}", dependencies=[Depends(_require_scim_bearer)])
async def scim_patch_user(user_id: str, request: Request, db: AsyncSession = Depends(_get_slm_db)) -> JSONResponse:
    """PATCH /scim/v2/Users/{id} — partial update; active:false = deprovisioning."""
    body: dict = await request.json()
    user = await _get_user_or_404(user_id, db)
    context = TenantContext(is_platform_admin=True)
    user_svc = UserService(db, context)
    await _apply_patch_ops(body.get("Operations", []), user, user_svc)
    await db.commit()
    updated = await user_svc.get_user(user.id)
    return JSONResponse(content=_user_to_scim(updated, _base_url(request)))


async def _apply_patch_ops(ops: list[dict], user: User, user_svc: UserService) -> None:
    """Apply SCIM PATCH Operations list (add/replace/remove)."""
    for op in ops:
        path = (op.get("path") or "").lower()
        value = op.get("value")
        if path == "active" or (not path and isinstance(value, dict) and "active" in value):
            active_val = value if isinstance(value, bool) else (value or {}).get("active", True)
            await _apply_active_flag(user, bool(active_val), user_svc)
        elif path in ("displayname", "name.formatted"):
            await user_svc.update_user(user.id, display_name=str(value))
        elif path == "emails" and isinstance(value, list) and value:
            email = value[0].get("value", "")
            if email:
                try:
                    await user_svc.update_user(user.id, email=email)
                except DuplicateUserError:
                    pass


async def _apply_active_flag(user: User, active: bool, user_svc: UserService) -> None:
    if not active and user.is_active:
        await user_svc.deactivate_user(user.id)
    elif active and not user.is_active:
        await user_svc.activate_user(user.id)


@router.delete("/Users/{user_id}", dependencies=[Depends(_require_scim_bearer)], status_code=204)
async def scim_delete_user(user_id: str, db: AsyncSession = Depends(_get_slm_db)):
    """DELETE /scim/v2/Users/{id} — deactivate/soft-delete a user."""
    user = await _get_user_or_404(user_id, db)
    context = TenantContext(is_platform_admin=True)
    user_svc = UserService(db, context)
    await user_svc.delete_user(user.id, hard_delete=False)
    await db.commit()


async def _get_user_or_404(user_id: str, db: AsyncSession) -> User:
    try:
        uid = uuid.UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=_scim_error("Not found", "invalidValue", 404)) from exc
    context = TenantContext(is_platform_admin=True)
    user = await UserService(db, context).get_user(uid)
    if not user:
        raise HTTPException(status_code=404, detail=_scim_error("User not found", "invalidValue", 404))
    return user


# ---------------------------------------------------------------------------
# SCIM /Groups
# ---------------------------------------------------------------------------


def _scim_group_id(role: Role) -> str:
    """Stable SCIM group ID derived from the Role UUID."""
    return str(role.id)


async def _get_first_active_provider(db: AsyncSession):
    """Return the first active SSO provider or None (for group_mapping context)."""
    from user_management.models.sso import SSOProvider

    result = await db.execute(select(SSOProvider).where(SSOProvider.is_active.is_(True)).limit(1))
    return result.scalar_one_or_none()


@router.post("/Groups", dependencies=[Depends(_require_scim_bearer)], status_code=201)
async def scim_create_group(request: Request, db: AsyncSession = Depends(_get_slm_db)) -> JSONResponse:
    """POST /scim/v2/Groups — map a SCIM group push to an AutoBot RBAC role."""
    body: dict = await request.json()
    display_name: str = body.get("displayName", "")
    if not display_name:
        raise HTTPException(status_code=400, detail=_scim_error("displayName required", "invalidValue"))
    members: list[dict] = body.get("members", [])

    role = await _resolve_role_by_name(display_name, db)
    if not role:
        raise HTTPException(
            status_code=404,
            detail=_scim_error(f"No AutoBot role matches group '{display_name}'", "invalidValue", 404),
        )

    await _sync_group_members(role, members, db)
    await db.commit()
    return JSONResponse(
        status_code=201,
        content=_group_scim(str(role.id), display_name, members, _base_url(request)),
    )


@router.get("/Groups/{group_id}", dependencies=[Depends(_require_scim_bearer)])
async def scim_get_group(group_id: str, request: Request, db: AsyncSession = Depends(_get_slm_db)) -> JSONResponse:
    """GET /scim/v2/Groups/{id} — fetch a SCIM group (mapped to an RBAC role)."""
    try:
        gid = uuid.UUID(group_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=_scim_error("Not found", "invalidValue", 404)) from exc
    role = await _get_role_by_id(gid, db)
    if not role:
        raise HTTPException(status_code=404, detail=_scim_error("Group not found", "invalidValue", 404))
    members = await _role_members_scim(role, db)
    return JSONResponse(content=_group_scim(str(role.id), role.name, members, _base_url(request)))


@router.get("/Groups", dependencies=[Depends(_require_scim_bearer)])
async def scim_list_groups(
    request: Request,
    filter: str | None = Query(default=None),
    startIndex: int = Query(default=1, ge=1),
    count: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(_get_slm_db),
) -> JSONResponse:
    """GET /scim/v2/Groups — list AutoBot RBAC roles as SCIM groups."""
    result = await db.execute(select(Role).offset(max(startIndex - 1, 0)).limit(count))
    roles = list(result.scalars().all())
    total_result = await db.execute(select(func.count(Role.id)))
    total = total_result.scalar() or 0

    resources = []
    for role in roles:
        members = await _role_members_scim(role, db)
        resources.append(_group_scim(str(role.id), role.name, members, _base_url(request)))
    return JSONResponse(content=_list_response(resources, total, startIndex, count))


@router.put("/Groups/{group_id}", dependencies=[Depends(_require_scim_bearer)])
async def scim_replace_group(group_id: str, request: Request, db: AsyncSession = Depends(_get_slm_db)) -> JSONResponse:
    """PUT /scim/v2/Groups/{id} — replace group membership (assign/revoke role)."""
    body: dict = await request.json()
    role = await _get_group_or_404(group_id, db)
    members: list[dict] = body.get("members", [])
    await _sync_group_members(role, members, db)
    await db.commit()
    return JSONResponse(content=_group_scim(str(role.id), role.name, members, _base_url(request)))


@router.patch("/Groups/{group_id}", dependencies=[Depends(_require_scim_bearer)])
async def scim_patch_group(group_id: str, request: Request, db: AsyncSession = Depends(_get_slm_db)) -> JSONResponse:
    """PATCH /scim/v2/Groups/{id} — partial membership update."""
    body: dict = await request.json()
    role = await _get_group_or_404(group_id, db)
    context = TenantContext(is_platform_admin=True)
    user_svc = UserService(db, context)
    for op in body.get("Operations", []):
        op_type = (op.get("op") or "").lower()
        members_val = op.get("value", [])
        if op_type in ("add", "replace") and isinstance(members_val, list):
            for m in members_val:
                await _assign_role_to_member(m, role, user_svc)
        elif op_type == "remove" and isinstance(members_val, list):
            for m in members_val:
                await _revoke_role_from_member(m, role, user_svc)
    await db.commit()
    members = await _role_members_scim(role, db)
    return JSONResponse(content=_group_scim(str(role.id), role.name, members, _base_url(request)))


# ---------------------------------------------------------------------------
# Group helper utilities
# ---------------------------------------------------------------------------


async def _resolve_role_by_name(name: str, db: AsyncSession) -> Role | None:
    result = await db.execute(select(Role).where(Role.name == name))
    return result.scalar_one_or_none()


async def _get_role_by_id(role_id: uuid.UUID, db: AsyncSession) -> Role | None:
    result = await db.execute(select(Role).where(Role.id == role_id))
    return result.scalar_one_or_none()


async def _get_group_or_404(group_id: str, db: AsyncSession) -> Role:
    try:
        gid = uuid.UUID(group_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=_scim_error("Not found", "invalidValue", 404)) from exc
    role = await _get_role_by_id(gid, db)
    if not role:
        raise HTTPException(status_code=404, detail=_scim_error("Group not found", "invalidValue", 404))
    return role


async def _role_members_scim(role: Role, db: AsyncSession) -> list[dict]:
    result = await db.execute(select(UserRole).where(UserRole.role_id == role.id))
    user_roles = list(result.scalars().all())
    return [{"value": str(ur.user_id), "$ref": f"../Users/{ur.user_id}"} for ur in user_roles]


async def _sync_group_members(role: Role, members: list[dict], db: AsyncSession) -> None:
    """Reconcile the role's membership to exactly the provided members list."""
    context = TenantContext(is_platform_admin=True)
    user_svc = UserService(db, context)
    wanted_ids: set[uuid.UUID] = set()
    for m in members:
        try:
            wanted_ids.add(uuid.UUID(m.get("value", "")))
        except (ValueError, TypeError):
            pass

    existing_result = await db.execute(select(UserRole).where(UserRole.role_id == role.id))
    existing_ids = {ur.user_id for ur in existing_result.scalars().all()}

    for uid in wanted_ids - existing_ids:
        await user_svc.assign_role(uid, role.id)
    for uid in existing_ids - wanted_ids:
        await user_svc.revoke_role(uid, role.id)


async def _assign_role_to_member(member: dict, role: Role, user_svc: UserService) -> None:
    try:
        uid = uuid.UUID(member.get("value", ""))
        await user_svc.assign_role(uid, role.id)
    except (ValueError, TypeError, UserNotFoundError):
        pass


async def _revoke_role_from_member(member: dict, role: Role, user_svc: UserService) -> None:
    try:
        uid = uuid.UUID(member.get("value", ""))
        await user_svc.revoke_role(uid, role.id)
    except (ValueError, TypeError, UserNotFoundError):
        pass
