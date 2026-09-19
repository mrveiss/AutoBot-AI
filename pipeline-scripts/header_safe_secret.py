# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Refuse a credential that cannot be sent as an HTTP header value (#15204).

``http.client`` validates header values on the way out, and its refusal is::

    ValueError("Invalid header value %r" % value)

The ``%r`` **is** the credential. An unhandled ``ValueError`` in a workflow step
writes its traceback into the CI log, which is readable by far more people than
the secret store is.

The trigger is a malformed, truncated or wrongly-substituted secret rather than
a well-formed one, so this is a conditional disclosure and not a standing one.
That is the reason to fix it rather than shrug: the condition is precisely
"something went wrong with the credential", which is exactly when a system
should be most careful with it. A malformed secret is still a secret — it may be
a valid credential for something else, a correctly-copied token with a stray
character, or a real token that was truncated. The failure mode converts a
configuration mistake into a disclosure.

This module lives on its own so the same check can be applied wherever else a
credential reaches a header, without importing a CI watchdog to get it.
"""

from __future__ import annotations

# The characters http.client refuses. This rejects slightly more than it does —
# http.client permits a newline followed by a space or tab (obs-fold) — because
# no credential this repo sends contains whitespace, so refusing the whole class
# is fail-closed and costs nothing real.
FORBIDDEN = {"\r": "carriage return", "\n": "newline", "\0": "null byte"}


class HeaderUnsafeSecret(ValueError):
    """A credential that cannot be sent as a header value, named without its value."""


def _problem(name: str, fault: str, index: int, length: int) -> str:
    """Describe the defect without ever quoting the value.

    Position and length are deliberate and safe: they are what tells a truncation
    apart from a bad paste, and neither discloses the secret.
    """
    return (
        f"{name} contains a {fault} at position {index} of {length} characters and cannot be sent "
        f"as an HTTP header. The value is not shown. Re-copy the secret."
    )


def require_header_safe(
    value: str,
    name: str = "the credential",
    error_cls: type[Exception] = HeaderUnsafeSecret,
) -> str:
    """Return *value* when it is safe to send as a header, else raise *error_cls*.

    *error_cls* lets a caller raise its own configuration error rather than
    catching and re-raising, so the check adds one line at a call site instead of
    a try block that could be written wrongly.
    """
    if not value:
        raise error_cls(f"{name} is empty")
    for index, char in enumerate(value):
        fault = FORBIDDEN.get(char)
        if fault is not None:
            raise error_cls(_problem(name, fault, index, len(value)))
    try:
        value.encode("latin-1")
    except UnicodeEncodeError as exc:
        # `from None` deliberately: chaining prints UnicodeEncodeError in the
        # traceback, and its own message quotes the offending character.
        raise error_cls(_problem(name, "non-Latin-1 character", exc.start, len(value))) from None
    return value
