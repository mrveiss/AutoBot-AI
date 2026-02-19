# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
A2A Agent Card Fetcher Service (Issue #962).

Periodically fetches /.well-known/agent.json from backend nodes and
stores the result in Node.extra_data["a2a_card"] so the SLM dashboard
can display each node's published A2A capabilities.

Only nodes with the "backend" role are queried (port 8443 HTTPS).
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Only nodes with this role expose the A2A endpoint
_A2A_ROLE = "backend"
_A2A_PORT = 8443
_WELL_KNOWN_PATH = "/.well-known/agent.json"
_FETCH_TIMEOUT = 10  # seconds
_REFRESH_INTERVAL = 300  # 5 minutes


async def _fetch_one(ip_address: str) -> Optional[Dict[str, Any]]:
    """
    Fetch the A2A agent card from a single node.

    Returns the parsed JSON dict, or None on any error.
    """
    import ssl

    import aiohttp

    url = f"https://{ip_address}:{_A2A_PORT}{_WELL_KNOWN_PATH}"
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE
    try:
        timeout = aiohttp.ClientTimeout(total=_FETCH_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, ssl=ssl_ctx) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
                logger.debug("A2A card HTTP %s from %s", resp.status, ip_address)
                return None
    except Exception as exc:
        logger.debug("A2A card fetch failed for %s: %s", ip_address, exc)
        return None


async def _store_card(db, node, card: Optional[Dict[str, Any]]) -> None:
    """Persist the fetched card into Node.extra_data."""
    from models.database import Node
    from sqlalchemy import update

    extra = dict(node.extra_data or {})
    extra["a2a_card"] = card
    extra["a2a_card_fetched_at"] = datetime.now(timezone.utc).isoformat()
    await db.execute(
        update(Node).where(Node.node_id == node.node_id).values(extra_data=extra)
    )
    await db.commit()


async def fetch_card_for_node(node_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch and store the A2A card for a single node by node_id.

    Returns the card dict on success, None otherwise.
    """
    from models.database import Node
    from services.database import db_service
    from sqlalchemy import select

    async with db_service.get_session() as db:
        result = await db.execute(select(Node).where(Node.node_id == node_id))
        node = result.scalar_one_or_none()
        if node is None:
            logger.warning("A2A card fetch: node %s not found", node_id)
            return None

        roles = node.roles or []
        if _A2A_ROLE not in roles:
            logger.debug("Node %s has no '%s' role, skipping", node_id, _A2A_ROLE)
            return None

        card = await _fetch_one(node.ip_address)
        await _store_card(db, node, card)
        return card


async def _refresh_all_backend_nodes() -> None:
    """Fetch A2A cards for every online backend node."""
    from models.database import Node
    from services.database import db_service
    from sqlalchemy import select

    async with db_service.get_session() as db:
        result = await db.execute(
            select(Node).where(Node.status.in_(["online", "enrolled"]))
        )
        nodes = result.scalars().all()

    backend_nodes = [n for n in nodes if _A2A_ROLE in (n.roles or [])]
    if not backend_nodes:
        return

    logger.debug("Refreshing A2A cards for %d backend node(s)", len(backend_nodes))
    tasks = [fetch_card_for_node(n.node_id) for n in backend_nodes]
    await asyncio.gather(*tasks, return_exceptions=True)


async def _card_refresh_loop(interval: int) -> None:
    """Background loop — runs forever until cancelled."""
    logger.info("A2A card refresh loop started (interval=%ds)", interval)
    while True:
        try:
            await _refresh_all_backend_nodes()
        except Exception as exc:
            logger.error("A2A card refresh error: %s", exc)
        await asyncio.sleep(interval)


def start_card_refresh_task(interval: int = _REFRESH_INTERVAL) -> asyncio.Task:
    """
    Start the A2A card refresh background task.

    Args:
        interval: Seconds between full-fleet refresh runs.

    Returns:
        The asyncio Task object (cancel it on shutdown).
    """
    return asyncio.create_task(_card_refresh_loop(interval))
