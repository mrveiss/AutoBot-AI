# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A startup DB failure names the host and port it tried, and how it failed (#18665).

The external Docker test (2026-10-17) logged only asyncpg's bare TimeoutError and restarted
12 times; the cause was a host firewall dropping container traffic, and nothing pointed there.
"""

import errno
import socket

from services.db_transaction_errors import describe_connect_failure

#: A fake credential, assembled at runtime: the point is to prove it never reaches the message.
_USER, _PASSWORD = "dbuser", "fixture-" + "pw" * 4  # pragma: allowlist secret -- fake fixture value


def _url(host: str, port: str = "") -> str:
    userinfo = f"{_USER}:{_PASSWORD}"
    return f"postgresql+asyncpg://{userinfo}@{host}{port}/autobot_slm"


def _chained(outer: BaseException, inner: BaseException) -> BaseException:
    outer.__cause__ = inner
    return outer


def test_a_timeout_names_host_port_and_says_timed_out() -> None:
    message = describe_connect_failure(TimeoutError(), _url("autobot-postgres", ":5433"))
    assert message.startswith("cannot reach PostgreSQL at autobot-postgres:5433: ")
    assert "timed out" in message and "firewall" in message


def test_a_refusal_found_down_the_cause_chain_says_refused() -> None:
    exc = _chained(RuntimeError("connection failed"), ConnectionRefusedError(111, "Connection refused"))
    assert "refused" in describe_connect_failure(exc, _url("autobot-postgres"))


def test_an_unresolvable_host_says_dns() -> None:
    exc = _chained(OSError("connect"), socket.gaierror(-2, "Name or service not known"))
    assert "did not resolve (DNS)" in describe_connect_failure(exc, _url("autobot-postgres"))


def test_credentials_never_appear() -> None:
    for exc in (TimeoutError(), ConnectionRefusedError(), ValueError("boom")):
        message = describe_connect_failure(exc, _url("autobot-postgres", ":5433"))
        assert _PASSWORD not in message and _USER not in message, message


def test_the_default_port_and_an_unknown_failure() -> None:
    message = describe_connect_failure(ValueError("boom"), _url("db-host"))
    assert message == "cannot reach PostgreSQL at db-host (default port): ValueError"


def test_a_password_with_unencoded_delimiters_is_withheld_never_leaked() -> None:
    """A '/', '?' or '#' inside a password ends the authority early (RFC 3986), so host and secret
    cannot be told apart: the location is withheld, and no credential is printed."""
    for odd in ("a/b", "a?b", "a#b"):
        url = f"postgresql+asyncpg://{_USER}:{odd}{_PASSWORD}@autobot-postgres:5433/autobot_slm"
        message = describe_connect_failure(TimeoutError(), url)
        assert "location withheld" in message, message
        assert _USER not in message and _PASSWORD not in message and odd not in message, message


def test_an_at_sign_in_the_password_or_the_query_is_never_the_host() -> None:
    in_password = f"postgresql+asyncpg://{_USER}:a@b{_PASSWORD}@autobot-postgres:5433/autobot_slm"
    in_query = f"postgresql+asyncpg://{_USER}:{_PASSWORD}@autobot-postgres:5433/autobot_slm?x=a@b"
    for url in (in_password, in_query):
        message = describe_connect_failure(TimeoutError(), url)
        assert message.startswith("cannot reach PostgreSQL at autobot-postgres:5433: "), message
        assert _USER not in message and _PASSWORD not in message, message


class _Falsy(Exception):
    def __bool__(self):
        return False


def test_the_cause_chain_is_followed_through_a_falsy_exception() -> None:
    """CodeRabbit: `cause or context` skipped a falsy exception; the walk is explicit now."""
    outer = RuntimeError("outer")
    middle = _Falsy("middle")
    middle.__cause__ = ConnectionRefusedError(111, "refused")
    outer.__cause__ = middle
    assert "refused" in describe_connect_failure(outer, _url("autobot-postgres"))


def test_raise_from_none_ends_the_chain() -> None:
    outer = RuntimeError("outer")
    outer.__context__ = TimeoutError()
    outer.__suppress_context__ = True
    assert describe_connect_failure(outer, _url("db-host")).endswith(": RuntimeError")


def test_an_errno_refusal_counts_only_on_an_oserror() -> None:
    """A plain OSError with ECONNREFUSED is a refusal; a driver exception that merely carries an
    `errno` field of the same value is not."""
    assert "refused" in describe_connect_failure(OSError(errno.ECONNREFUSED, "refused"), _url("db-host"))

    ECONNREFUSED = errno.ECONNREFUSED

    class _DriverError(Exception):
        errno = ECONNREFUSED

    message = describe_connect_failure(_DriverError(), _url("db-host"))
    assert "refused" not in message and message.endswith(": _DriverError")


def test_a_bracketed_ipv6_host_with_and_without_a_port() -> None:
    assert describe_connect_failure(ValueError(), _url("[::1]")).startswith(
        "cannot reach PostgreSQL at [::1] (default port): "
    )
    assert describe_connect_failure(ValueError(), _url("[::1]", ":5432")).startswith(
        "cannot reach PostgreSQL at [::1]:5432: "
    )
