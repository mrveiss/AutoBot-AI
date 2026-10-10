# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/knowledge/connectors/egress.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The three connector egress policies, in one place (#13625, #17576, Rule 8).

Split out of ``base.py``: the policies are a distinct concern from the connector
base class, they are read by modules that need nothing else from it, and ``base.py``
is a grandfathered file that may not grow. ``base.py`` re-exports all three, so
existing importers are unaffected.

Rule 8 turns on where the URL came from, and the three cases are genuinely
different — which is why each is named rather than passed as a bare bool at the
call site.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse


def instance_host_egress() -> bool:
    """Egress policy for an **operator-configured instance host** (#13625, Rule 8).

    Returns the deployment's private-network opt-in, so a self-hosted
    Confluence/GitLab/Nextcloud on an RFC-1918 address is reachable when the
    operator has enabled it. Loopback, link-local (incl. cloud metadata),
    multicast, reserved and unspecified stay refused either way.

    Pass the result as ``guard_egress=`` to the shared HTTP client.
    """
    from autobot_shared.ssot_config import config

    return bool(config.feature.connector_private_network_egress)


# Egress policy for a URL that did NOT come from operator configuration —
# anything read out of a document, an API response, or a user request. Always
# public-only: the instance host's exemption must never extend to content it
# serves, or a document becomes an SSRF vector into the operator's network.
CONTENT_URL_EGRESS = False


# Egress policy for a **vendor SaaS API** whose host comes from connector config
# with a vendor constant as the default — Google Drive, Microsoft Graph, Notion,
# Slack. Public-only, and deliberately NOT instance_host_egress(): those four are
# hosted services with no self-hosted deployment, so no legitimate configuration
# points them at a private address, while an illegitimate one would reach the
# operator's network carrying the connector's credentials. The constant default is
# what made this class read as a fixed endpoint and kept it out of #13625's audit
# — the override key is one ``cfg.get`` away from invisible (#17576).
VENDOR_API_EGRESS = False


def next_link_on_base(link: object, base: str, logger: logging.Logger) -> str | None:
    """A server-supplied next-page URL, only if it stays under *base* (#17576).

    Such a link is requested with the connector's credentials, and the egress
    guard only demands a *public* host, so an unchecked link lets a malicious or
    compromised response send the bearer token to any public host. Anything that
    is not ``base + "/"`` followed by a path (a lookalike prefix, a userinfo
    trick, a scheme downgrade) ends paging: ``None`` is returned, and the host
    alone (never the token or the query) is logged at WARNING.
    """
    if not link:
        return None
    if isinstance(link, str) and link.startswith(base.rstrip("/") + "/"):
        return link
    host = urlparse(link).hostname if isinstance(link, str) else None
    logger.warning("Refusing a next-page link outside the configured API base (host: %s); paging stopped", host)
    return None
