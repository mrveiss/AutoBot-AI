# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Who a message is really on behalf of, carried across every relay (#16950).

``MessageHeader.sender`` is each hop's own identity: ``send_message`` restamps it,
correctly, on every send. That made the originator unrecoverable. Agent B, handling
agent A's request, sends C a *new* message with B as sender, and C cannot tell B's
own request from one B is making for A. Authorization needs exactly that (#16946 §3).

Two header fields carry it:

- ``originator``: set once, on the first send of a chain, and never overwritten by a
  relay.
- ``chain``: every hop's id in order, originator first, for audit and cycle detection.

Relays are made structural rather than left to each agent's discipline. While an
agent handles an inbound request it runs inside :func:`acting_for`, and
:func:`stamp` reads the inherited origin from a context variable. So any message
the agent sends while doing that work continues the chain, including messages sent
through helpers that never saw the inbound one.

Trust boundary (#16946, owner decision 4): nothing here authenticates these fields.
Until #16962 adds per-agent keys and a MAC over the header, a process with write
access to the agent bus's Redis can forge them. This fixes the confused deputy
(well-behaved agents acting with their own authority on another's behalf), not
raw-bus forgery.
"""

from __future__ import annotations

import contextlib
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator, Tuple


@dataclass(frozen=True)
class Origin:
    """The originator of a chain, and the hops it has crossed so far."""

    originator: str
    chain: Tuple[str, ...]


#: The origin of the request the current task is handling, if any.
_CURRENT: ContextVar[Origin | None] = ContextVar("agent_message_origin", default=None)


def current_origin() -> Origin | None:
    """The origin this task is acting for, or None outside a handled request."""
    return _CURRENT.get()


@contextlib.contextmanager
def acting_for(origin: Origin) -> Iterator[None]:
    """Run the enclosed work on behalf of *origin*, so messages it sends continue that chain."""
    token = _CURRENT.set(origin)
    try:
        yield
    finally:
        _CURRENT.reset(token)


def stamp(header: Any, hop_id: str) -> None:
    """Record *hop_id* as this send's hop. The originator is set once and never overwritten.

    A header that already names an originator is a relay the caller built
    deliberately, and keeps it. Otherwise the originator comes from the request being
    handled, if there is one, and failing that this hop starts a new chain.
    """
    if header.originator is None:
        inherited = current_origin()
        header.originator = inherited.originator if inherited else hop_id
        header.chain = list(inherited.chain) if inherited else []
    if not header.chain or header.chain[-1] != hop_id:
        header.chain = [*header.chain, hop_id]


def _sender_id(sender: Any) -> str | None:
    """The sender's agent id: an ``AgentIdentity`` locally, a plain dict after a Redis round trip."""
    if sender is None:
        return None
    if isinstance(sender, dict):
        return sender.get("agent_id")
    return getattr(sender, "agent_id", None)


def origin_of(header: Any) -> Origin | None:
    """The origin an inbound header carries, or None when it names no one at all.

    A header without an originator comes from a sender that predates this field. Its
    sender is then the only principal known, and is treated as the originator,
    never as nobody.
    """
    sender_id = _sender_id(header.sender)
    originator = header.originator or sender_id
    if originator is None:
        return None
    chain = tuple(header.chain) if header.chain else ((sender_id,) if sender_id else ())
    return Origin(originator=originator, chain=chain)
