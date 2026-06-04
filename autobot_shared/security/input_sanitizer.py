# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Input sanitization utilities (#1721).

Shared helpers for sanitizing user input before use in shell commands,
LDAP queries, regular expressions, and outbound HTTP requests.

Usage:
    from autobot_shared.security.input_sanitizer import (
        sanitize_shell_arg,
        sanitize_ldap_filter,
        escape_regex,
        validate_url,
    )
"""

from __future__ import annotations

import re
import shlex
from typing import Sequence
from urllib.parse import urlparse

# ── Shell ────────────────────────────────────────────────────────────


def sanitize_shell_arg(value: str) -> str:
    """Shell-quote a single argument to prevent injection.

    Returns a shell-escaped string safe for use in command lists.
    """
    return shlex.quote(value)


# ── LDAP ─────────────────────────────────────────────────────────────

_LDAP_ESCAPE_MAP: dict[str, str] = {
    "\\": "\\5c",
    "*": "\\2a",
    "(": "\\28",
    ")": "\\29",
    "\x00": "\\00",
}


def sanitize_ldap_filter(value: str) -> str:
    """Escape special characters for safe use in an LDAP search filter.

    Implements RFC 4515 §3 escaping rules.
    """
    result: list[str] = []
    for ch in value:
        result.append(_LDAP_ESCAPE_MAP.get(ch, ch))
    return "".join(result)


_LDAP_DN_ESCAPE_MAP: dict[str, str] = {
    "\\": "\\5c",
    ",": "\\2c",
    "+": "\\2b",
    '"': "\\22",
    "<": "\\3c",
    ">": "\\3e",
    ";": "\\3b",
    "\x00": "\\00",
    "=": "\\3d",
    " ": "\\20",
    "#": "\\23",
}


def sanitize_ldap_dn(value: str) -> str:
    """Escape special characters for safe use in an LDAP distinguished name.

    Implements RFC 4514 §2.4 escaping rules for DN attribute values.
    """
    result: list[str] = []
    for ch in value:
        result.append(_LDAP_DN_ESCAPE_MAP.get(ch, ch))
    return "".join(result)


# ── Regex ────────────────────────────────────────────────────────────


def escape_regex(value: str) -> str:
    """Escape user input for safe use in a regular expression."""
    return re.escape(value)


# ── URL / SSRF ───────────────────────────────────────────────────────

_DEFAULT_ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})

_PRIVATE_IP_PREFIXES: tuple[str, ...] = (
    "10.",
    "172.16.",
    "172.17.",
    "172.18.",
    "172.19.",
    "172.20.",
    "172.21.",
    "172.22.",
    "172.23.",
    "172.24.",
    "172.25.",
    "172.26.",
    "172.27.",
    "172.28.",
    "172.29.",
    "172.30.",
    "172.31.",
    "192.168.",
    "127.",
    "0.",
    "169.254.",
)


def validate_url(
    url: str,
    *,
    allowed_schemes: frozenset[str] | None = None,
    allow_private: bool = False,
    allowed_hosts: Sequence[str] | None = None,
) -> str:
    """Validate a URL to prevent SSRF attacks.

    Parameters
    ----------
    url:
        The URL to validate.
    allowed_schemes:
        Acceptable URL schemes (default: http, https).
    allow_private:
        When *True*, allow requests to private/internal IPs.
    allowed_hosts:
        Optional allowlist of hostnames. When set, only these hosts
        are permitted.

    Returns
    -------
    str
        The validated URL (unchanged).

    Raises
    ------
    ValueError
        If the URL fails validation.
    """
    schemes = allowed_schemes or _DEFAULT_ALLOWED_SCHEMES

    parsed = urlparse(url)

    if parsed.scheme not in schemes:
        raise ValueError(f"URL scheme '{parsed.scheme}' not allowed " f"(allowed: {', '.join(sorted(schemes))})")

    hostname = parsed.hostname or ""
    if not hostname:
        raise ValueError("URL has no hostname")

    if allowed_hosts is not None:
        if hostname not in allowed_hosts:
            raise ValueError(f"Host '{hostname}' not in allowlist")

    if not allow_private:
        if hostname == "localhost" or hostname.endswith(".local"):
            raise ValueError("Requests to localhost are not allowed")
        for prefix in _PRIVATE_IP_PREFIXES:
            if hostname.startswith(prefix):
                raise ValueError("Requests to private IP ranges are not allowed")
        if hostname == "::1" or hostname.startswith("fd") or hostname.startswith("fe80"):
            raise ValueError("Requests to private IPv6 ranges are not allowed")

    return url


# ── HTML ─────────────────────────────────────────────────────────────

_HTML_ESCAPE_MAP: dict[str, str] = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#x27;",
}


def escape_html(value: str) -> str:
    """Escape HTML special characters to prevent XSS."""
    result = value
    for char, replacement in _HTML_ESCAPE_MAP.items():
        result = result.replace(char, replacement)
    return result
