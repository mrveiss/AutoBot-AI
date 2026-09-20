#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The three (plus one) kinds an `AgentIdentity` can be (#16946, #16947).

Split out of `protocols.agent_communication` rather than defined there: that
module is at its size-ratchet ceiling, and `protocols.agent_presence` (the
live registry) needs this enum too -- a shared leaf module avoids a circular
import between the two.
"""

from enum import Enum


class AgentKind(str, Enum):
    """Which of AutoBot's three internal agent populations an identity belongs to.

    COMPANY_OS: an org-chart agent (`models.agent_org.AgentOrgNode`), scoped
    to the company that hired it.

    AI_STACK: a chat/RAG/system-command role agent (`agents.agent_client`),
    a process-global singleton serving every tenant -- `tenant_id` is always
    `None` for this kind.

    SESSION: a live interactive or terminal session
    (`services.agent_terminal.models.AgentTerminalSession`).

    EXTERNAL: an admitted A2A peer. Carries identity for attribution and for
    the cross-hop permission-intersection rule (#16946 owner decision 3) --
    it is never discoverable and never appears in presence (#16947).
    """

    COMPANY_OS = "company_os"
    AI_STACK = "ai_stack"
    SESSION = "session"
    EXTERNAL = "external"
