# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
URL validation service for preventing SSRF attacks
"""

import ipaddress
import socket
from typing import List, Optional
from urllib.parse import urlparse

from src.constants.network_constants import NetworkConstants
from src.constants.security_constants import SecurityConstants

# Issue #380: Module-level tuple for URL scheme validation
_VALID_URL_SCHEMES = ("http://", "https://")


class URLValidator:
    """Validates URLs to prevent SSRF attacks"""

    ALLOWED_SCHEMES = ["http", "https"]
    FORBIDDEN_HOSTS = [
        NetworkConstants.LOCALHOST_NAME,
        NetworkConstants.LOCALHOST_IP,
        NetworkConstants.BIND_ALL_INTERFACES,
        NetworkConstants.LOCALHOST_IPV6,
        SecurityConstants.CLOUD_METADATA_IPS[0],  # AWS metadata endpoint
        "metadata.google.internal",  # GCP metadata endpoint
    ]

    # Private IP ranges - converted from SecurityConstants.BLOCKED_IP_RANGES
    PRIVATE_IP_RANGES = [
        ipaddress.ip_network(cidr) for cidr in SecurityConstants.BLOCKED_IP_RANGES
    ] + [
        ipaddress.ip_network("fc00::/7"),  # IPv6 unique local
        ipaddress.ip_network("fe80::/10"),  # IPv6 link local
    ]

    def __init__(self, allowed_domains: Optional[List[str]] = None):
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
                if not any(
                    hostname.endswith(domain) for domain in self.allowed_domains
                ):
                    return False, f"Domain {hostname} not in allowed list"

            # Resolve hostname to IP and check if it's private
            try:
                # Get IP address
                ip_addr = socket.gethostbyname(hostname)
                ip_obj = ipaddress.ip_address(ip_addr)

                # Check if IP is private or loopback
                if ip_obj.is_private or ip_obj.is_loopback:
                    return False, f"Private/loopback IP address: {ip_addr}"

                # Check against private IP ranges
                for private_range in self.PRIVATE_IP_RANGES:
                    if ip_obj in private_range:
                        return (
                            False,
                            f"IP {ip_addr} is in private range {private_range}",
                        )

            except socket.gaierror:
                # If hostname doesn't resolve, it might be invalid
                return False, f"Cannot resolve hostname: {hostname}"
            except Exception as e:
                return False, f"Error validating hostname: {str(e)}"

            return True, ""

        except Exception as e:
            return False, f"Invalid URL: {str(e)}"

    def sanitize_url(self, url: str) -> Optional[str]:
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
