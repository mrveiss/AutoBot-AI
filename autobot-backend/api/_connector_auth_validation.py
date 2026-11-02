# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Connector create's auth check, split out of the frozen ``api/knowledge_connectors.py`` (#19714)."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from autobot_shared.auth import validate_config_against_schema
from knowledge.connectors.registry import ConnectorRegistry
from knowledge.schemas.connectors import CreateConnectorRequest


def validated_connector_auth(request: CreateConnectorRequest) -> tuple[Any, Any, str | None]:
    """The connector class, its auth schema and that schema's name, after checking the request (#8145)."""
    klass = ConnectorRegistry.get_registered_class(request.connector_type)
    if klass is None:
        raise HTTPException(
            status_code=422,
            detail="connector_type '%s' is not registered" % request.connector_type,
        )
    # Issue #8145: validate config against the connector's declared auth schema.
    # Skip when a secret_id is supplied: the OAuth flow already obtained and
    # stored the credential, so it is intentionally absent from the config.
    auth_cls = klass.auth_schema()
    auth_type: str | None = None
    if auth_cls is not None:
        auth_type = auth_cls.__name__
        if not request.secret_id:
            errors = validate_config_against_schema(auth_cls, request.config)
            if errors:
                raise HTTPException(
                    status_code=422,
                    detail="Auth config invalid for %s: %s" % (auth_type, "; ".join(errors)),
                )
    return klass, auth_cls, auth_type
