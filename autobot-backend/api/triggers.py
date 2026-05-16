# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Triggers API (#2139)

FastAPI endpoints for event-driven workflow trigger management.

Routes:
  POST   /api/triggers               — register a new trigger
  GET    /api/triggers               — list all triggers (optional ?workflow_id=)
  DELETE /api/triggers/{trigger_id}  — unregister a trigger
  POST   /api/triggers/webhook/{trigger_id} — receive an external webhook event
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from api.schemas_agent import WebhookAcceptedResponse
from api.schemas_workflows import (
    TriggerCreateRequest,
    TriggerCreateResponse,
    TriggerListResponse,
)
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.trigger_service import (
    TriggerConfig,
    TriggerDefinition,
    TriggerService,
    TriggerType,
)

logger = get_logger(__name__)

router = APIRouter(tags=["triggers"])

# ---------------------------------------------------------------------------
# Singleton service — initialised lazily; launcher wired by lifespan caller
# ---------------------------------------------------------------------------

_service: TriggerService | None = None


def get_trigger_service() -> TriggerService:
    """Return (and lazily create) the module-level TriggerService singleton."""
    global _service
    if _service is None:
        _service = TriggerService()
    return _service


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/triggers",
    response_model=TriggerCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new event-driven trigger",
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_trigger",
    error_code_prefix="TRIGGERS",
)
async def create_trigger(
    request: TriggerCreateRequest,
    current_user: dict = Depends(get_current_user),
) -> TriggerCreateResponse:
    """
    Register a workflow trigger.

    Returns the new trigger_id and, for WEBHOOK triggers, the URL path
    to send events to.
    """
    service = get_trigger_service()
    config = TriggerConfig(
        trigger_type=request.trigger_type,
        workflow_id=request.workflow_id,
        config=request.config,
        conditions=request.conditions,
        enabled=request.enabled,
    )

    try:
        trigger_id = await service.register_trigger(config)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)  # user-facing validation error
        ) from exc

    webhook_url: str | None = None
    if request.trigger_type == TriggerType.WEBHOOK:
        webhook_url = service.get_webhook_url_path(trigger_id)

    logger.info(
        "Trigger created: id=%s type=%s by_user=%s",
        trigger_id,
        request.trigger_type.value,
        current_user.get("username", "unknown"),
    )
    return TriggerCreateResponse(trigger_id=trigger_id, webhook_url=webhook_url)


@router.get(
    "/triggers",
    response_model=TriggerListResponse,
    summary="List all registered triggers",
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_triggers",
    error_code_prefix="TRIGGERS",
)
async def list_triggers(
    workflow_id: str | None = None,
    current_user: dict = Depends(get_current_user),
) -> TriggerListResponse:
    """
    List all triggers, optionally filtered by workflow_id.

    Returns serialised TriggerDefinition objects (HMAC secrets excluded).
    """
    service = get_trigger_service()
    triggers: List[TriggerDefinition] = await service.list_triggers(workflow_id=workflow_id)
    serialised = [t.to_dict() for t in triggers]
    return TriggerListResponse(triggers=serialised, total=len(serialised))


@router.delete(
    "/triggers/{trigger_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unregister a trigger",
    response_model=None,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_trigger",
    error_code_prefix="TRIGGERS",
)
async def delete_trigger(
    trigger_id: str,
    current_user: dict = Depends(get_current_user),
) -> None:
    """
    Unregister a trigger by ID.

    Cancels any associated background task and removes the persisted record
    from Redis.  Returns 404 when the trigger does not exist.
    """
    service = get_trigger_service()
    existing = await service._load_trigger(trigger_id)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trigger '{trigger_id}' not found",
        )

    await service.unregister_trigger(trigger_id)
    logger.info(
        "Trigger deleted: id=%s by_user=%s",
        trigger_id,
        current_user.get("username", "unknown"),
    )


@router.post(
    "/triggers/webhook/{trigger_id}",
    status_code=status.HTTP_200_OK,
    summary="Receive an external webhook event",
    response_model=WebhookAcceptedResponse,
)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="receive_webhook",
    error_code_prefix="TRIGGERS",
)
async def receive_webhook(
    trigger_id: str,
    request: Request,
    x_autobot_signature: str | None = Header(default=None, alias="X-AutoBot-Signature"),
) -> Dict[str, str]:
    """
    Entry point for external webhook events.

    If the trigger was created with ``secret_validation=true`` (default),
    the caller must include a ``X-AutoBot-Signature: sha256=<hmac>`` header
    computed over the raw request body using the trigger's secret.

    Returns ``{"status": "accepted"}`` when the trigger fires or conditions
    are not met; returns 404 when the trigger does not exist.
    """
    service = get_trigger_service()

    tdef = await service._load_trigger(trigger_id)
    if tdef is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trigger '{trigger_id}' not found",
        )

    if tdef.trigger_type != TriggerType.WEBHOOK:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Trigger '{trigger_id}' is not a WEBHOOK trigger",
        )

    body = await request.body()

    # Validate HMAC signature when secret_validation is enabled (default)
    if tdef.config.get("secret_validation", True):
        if not x_autobot_signature:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-AutoBot-Signature header",
            )
        valid = await service.validate_webhook_signature(trigger_id, body, x_autobot_signature)
        if not valid:
            logger.warning("Invalid webhook signature for trigger %s", trigger_id)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )

    import json as _json

    try:
        payload: Dict[str, Any] = _json.loads(body) if body else {}
    except _json.JSONDecodeError:
        payload = {"raw_body": body.decode(errors="replace")}

    payload.setdefault("trigger_type", "webhook")

    fired = await service.fire_trigger(trigger_id, payload)
    logger.info("Webhook received: trigger=%s fired=%s", trigger_id, fired)
    return {"status": "accepted"}
