# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
URL validation service for preventing SSRF attacks

Delegates SSRF DNS-resolution checks to autobot_shared.url_safety for
consistency across the codebase per #6533.
"""

from typing import List
from urllib.parse import urlparse

from autobot_shared.url_safety import is_public_url, resolve_safe_ip_async
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
        """Resolve *host* to one public IP literal (SSRF / DNS-rebind guard).

        Delegates to :func:`autobot_shared.url_safety.resolve_safe_ip_async`, the
        one implementation of the address rules (#6533, #18731), which also enforces
        ``timeout`` on the lookup itself. Raises ``ValueError`` on a DNS timeout,
        an unresolvable host, a non-public address, or no usable address.
        """
        return await resolve_safe_ip_async(host, timeout=timeout)
