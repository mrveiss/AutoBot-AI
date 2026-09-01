# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Response shapes for the two chat-session read routes (#15138).

Both routes' envelopes and the rows inside them, together: ``sessions`` and
``messages`` were declared ``List[Any]``, so the backend described the envelope
and said nothing about a row. Keeping the pair in one module means the envelope
and the row it contains are edited in the same place.

Their own module because ``api/schemas_chat.py`` sits at its recorded size
ceiling and a grandfathered file may not grow (#14236). That constraint pushed
these somewhere better than it would have gone otherwise: these describe the
*rows* two routes return, while ``schemas_chat`` describes the envelopes, and
the two are edited for different reasons.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict


class SessionMessage(BaseModel):
    """One row of ``SessionMessagesData.messages`` (#15138).

    Keys mirror ``ChatHistoryManager._build_message_dict``. Every field is
    optional and ``extra="allow"`` is set on purpose: this route serialises
    dictionaries assembled in several places over several years, and a model
    that dropped an unlisted key would silently truncate a response that
    currently round-trips intact. The point of declaring it is that the
    contract becomes *readable* and a client can be generated from it —
    not to start rejecting payloads the API already emits.
    """

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    sender: str | None = None
    text: str | None = None
    messageType: str | None = None
    metadata: Dict[str, Any] | None = None
    timestamp: str | None = None
    sources: List[Any] | None = None
    # Present only when the message carried them (#13692 tool markers, authored
    # messages); absent keys are not nulls in the emitted dict.
    toolMarkers: List[Any] | None = None
    authorId: str | None = None


class SessionSummary(BaseModel):
    """One row of ``SessionListData.sessions`` (#15138).

    Keys mirror ``_build_session_entry``. Several are deliberate duplicates
    (``id``/``chatId``, ``title``/``name``, ``createdAt``/``createdTime``,
    ``updatedAt``/``lastModified``) that the frontend reads under both spellings;
    they are declared rather than tidied, because narrowing the payload is a
    separate decision from describing it.
    """

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    chatId: str | None = None
    title: str | None = None
    name: str | None = None
    messages: List[Any] | None = None
    messageCount: int | None = None
    createdAt: str | None = None
    createdTime: str | None = None
    updatedAt: str | None = None
    lastModified: str | None = None
    # #13948: the unambiguous ordering key — the ISO fields above are naive
    # local time and collide across a DST fallback.
    updatedAtEpoch: float | None = None
    isActive: bool | None = None
    fileSize: int | None = None
    fast_mode: bool | None = None
    # #12685: first-class tenancy scoping, not a title parse.
    companyId: str | None = None
    sessionKind: str | None = None


class SessionMessagesData(BaseModel):
    """data payload for GET /chat/sessions/{session_id}."""

    messages: List[SessionMessage]
    session_id: str
    total_count: int
    page: int
    per_page: int


class SessionListData(BaseModel):
    """data payload for GET /chat/sessions (all scope variants).

    The ``scope``, ``org_id``, and ``team_id`` fields are only present when
    the request uses scope=org or scope=team query params.
    ``intentional_empty`` is set when the authenticated user has zero sessions.
    """

    sessions: List[SessionSummary]
    count: int
    scope: str | None = None
    org_id: str | None = None
    team_id: str | None = None
    intentional_empty: bool | None = None
