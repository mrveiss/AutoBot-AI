# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
URL validation service for preventing SSRF attacks

Delegates SSRF DNS-resolution checks to autobot_shared.url_safety for
consistency across the codebase per #6533.
"""

import asyncio
import ipaddress
import socket
from typing import List
from urllib.parse import urlparse

from autobot_shared.url_safety import is_public_url
from constants.network_constants import NetworkConstants

# Issue #380: Module-level tuple for URL scheme validation
_VALID_URL_SCHEMES = ("http://", "https://")


class URLValidator:
    """Validates URLs to prevent SSRF attacks.

    Delegates DNS-resolving SSRF checks to autobot_shared.url_safety for
    consistency per #6533. This class preserves backward compatibility.
    """

    ALLOWED_SCHEMES = ["http", "https"]
    FORBIDDEN_HOSTS = [
        NetworkConstants.LOCALHOST_NAME,
        NetworkConstants.LOCALHOST_IP,
        NetworkConstants.BIND_ALL_INTERFACES,
        NetworkConstants.LOCALHOST_IPV6,
        "metadata.google.internal",  # GCP metadata endpoint (also caught by is_public_url)
    ]

    def __init__(self, allowed_domains: List[str] | None = None) -> None:
        """
        Initialize URL validator

        Args:
            allowed_domains: Optional list of allowed domains (e.g., ['github.com', 'docs.python.org'])
        """
        self.allowed_domains = allowed_domains or []

    def is_safe_url(self, url: str) -> tuple[bool, str]:
        """
        Validate if a URL is safe from SSRF attacks

        Args:
            url: URL to validate

        Returns:
            Tuple of (is_safe, error_message)
        """
        try:
            parsed = urlparse(url)

            # Check scheme
            if parsed.scheme not in self.ALLOWED_SCHEMES:
                return (
                    False,
                    f"Invalid scheme: {parsed.scheme}. Only {', '.join(self.ALLOWED_SCHEMES)} allowed.",
                )

            # Check for empty hostname
            if not parsed.hostname:
                return False, "No hostname provided"

            hostname = parsed.hostname.lower()

            # Check against forbidden hosts
            if hostname in self.FORBIDDEN_HOSTS:
                return False, f"Forbidden hostname: {hostname}"

            # Check if domain allowlist is configured
            if self.allowed_domains:
                if not any(hostname.endswith(domain) for domain in self.allowed_domains):
                    return False, f"Domain {hostname} not in allowed list"

            # Delegate SSRF check to shared implementation
            if not is_public_url(url):
                return False, f"URL resolves to a non-public address: {hostname}"

            return True, ""

        except Exception as exc:
            return False, f"Error validating URL: {exc}"

    def sanitize_url(self, url: str) -> str | None:
        """
        Sanitize and validate a URL, returning None if invalid

        Args:
            url: URL to sanitize

        Returns:
            Sanitized URL or None if invalid
        """
        # Basic cleanup
        url = url.strip()

        # Add scheme if missing (Issue #380: use module-level tuple)
        if not url.startswith(_VALID_URL_SCHEMES):
            url = "https://" + url

        # Validate
        is_safe, _ = self.is_safe_url(url)
        return url if is_safe else None

    @staticmethod
    async def resolve_safe_ip(host: str, timeout: float = 2.0) -> str:
        """
        Async DNS resolution that rejects non-public addresses (SSRF guard).
        Returns a single IP literal for direct connection, defeating DNS rebind
        attacks where a second resolution might redirect to a private address.

        Issue #6533: consolidates SSRF guards across marketplace_sources,
        media/link/pipeline, a2a/capability_verifier, and api/knowledge.

        Blocks: loopback, RFC1918, link-local (incl. cloud metadata IPs),
        IPv6 unique-local, multicast, reserved, unspecified.

        Args:
            host: hostname to resolve
            timeout: DNS timeout in seconds (default 2.0)

        Returns:
            A single safe public IP address as a string

        Raises:
            ValueError: if the hostname cannot be resolved, resolves to no
                usable IPs, or resolves to a non-public address
        """
        try:
            loop = asyncio.get_event_loop()
            infos = await asyncio.wait_for(loop.getaddrinfo(host, None, type=socket.SOCK_STREAM), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise ValueError(f"DNS resolution timeout for {host}") from exc
        except (socket.gaierror, OSError) as exc:
            raise ValueError(f"Cannot resolve hostname {host}: {exc}") from exc

        safe_ip: str | None = None
        for info in infos:
            ip_str = info[4][0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue

            if (
                ip.is_loopback
                or ip.is_private
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                raise ValueError(f"Hostname {host} resolves to a non-public address: {ip_str}")

            # Pick the first global address; caller will connect to it explicitly
            if safe_ip is None:
                safe_ip = ip_str

        if safe_ip is None:
            raise ValueError(f"Hostname {host} has no usable IP addresses")

        return safe_ip
