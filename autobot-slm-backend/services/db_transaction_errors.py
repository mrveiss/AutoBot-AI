# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tell a connection-level DB failure apart from a row-level one (#17070).

A row-level failure (IntegrityError, a bad value hitting a constraint) is
safely absorbed by a SAVEPOINT rollback -- the connection is fine, only that
one statement's effects are undone. A connection-level failure (a lost or
timed-out connection) can't be recovered that way: a caller must stop
issuing statements on the session and abort the whole operation rather
than continue against a connection that's already gone.

`describe_connect_failure` says WHERE a connection failed and HOW (#18665): asyncpg's
bare `TimeoutError` named neither, so a firewall dropping container traffic looked like
any other startup crash.
"""

import errno
import re
import socket

from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError


def is_connection_level_db_error(exc: BaseException) -> bool:
    """True when *exc* leaves the connection itself unusable, not just one statement."""
    if isinstance(exc, (TimeoutError, OperationalError, InterfaceError)):
        return True
    return isinstance(exc, DBAPIError) and getattr(exc, "connection_invalidated", False)


def _causes(exc: BaseException) -> list[BaseException]:
    """*exc* and everything it was raised from, outermost first."""
    seen: list[BaseException] = []
    while exc is not None and exc not in seen:
        seen.append(exc)
        # Explicit, not `or`: a falsy exception (custom __bool__/__len__) must still be followed,
        # and `raise ... from None` (__suppress_context__) ends the chain.
        if exc.__cause__ is not None:
            exc = exc.__cause__
        elif not exc.__suppress_context__:
            exc = exc.__context__
        else:
            exc = None
    return seen


def _failure_kind(exc: BaseException) -> str:
    for cause in _causes(exc):
        if isinstance(cause, socket.gaierror):
            return "the host name did not resolve (DNS)"
        # errno only means a socket errno on an OSError; a driver exception may carry its own field.
        if isinstance(cause, ConnectionRefusedError) or (
            isinstance(cause, OSError) and cause.errno == errno.ECONNREFUSED
        ):
            return "the connection was refused (nothing listening there, or the wrong port)"
        if isinstance(cause, TimeoutError):
            return "the connection timed out (no answer: a firewall dropping the traffic, or the host is down)"
    return f"{type(exc).__name__}"


def describe_connect_failure(exc: BaseException, database_url: str) -> str:
    """'cannot reach PostgreSQL at host:port: <timeout | refusal | DNS | type>', never credentials."""
    return f"cannot reach PostgreSQL at {_location(database_url)}: {_failure_kind(exc)}"


_WITHHELD = "the configured host (location withheld: the DSN has unencoded characters before the host)"


def _location(database_url: str) -> str:
    """host:port from a DSN, never any part of the credentials (#18672 review).

    The authority ends at the first '/', '?' or '#' (RFC 3986: those are percent-encoded inside
    a valid password), and the host follows its last '@' -- so an '@' in the query is not the host.
    If an '@' only appears after that cut, a password holds unencoded delimiters and nothing here
    can tell host from secret: the location is withheld rather than guessed.
    """
    rest = database_url.split("://", 1)[-1]
    authority = re.split(r"[/?#]", rest, maxsplit=1)[0]
    if "@" in rest and "@" not in authority:
        return _WITHHELD
    host, port = _split_host_port(authority.rsplit("@", 1)[-1])
    if not re.fullmatch(r"[A-Za-z0-9._-]+|\[[0-9A-Fa-f:.]+\]", host or "") or (port and not port.isdigit()):
        return _WITHHELD
    return f"{host}:{port}" if port else f"{host} (default port)"


def _split_host_port(hostport: str) -> tuple[str, str]:
    """('host', 'port') from 'host[:port]'; a bracketed IPv6 literal keeps its colons ('[::1]', '[::1]:<port>')."""
    if hostport.startswith("["):
        host, bracket, tail = hostport.partition("]")
        return host + bracket, tail[1:] if tail.startswith(":") else tail
    host, _, port = hostport.partition(":")
    return host, port
