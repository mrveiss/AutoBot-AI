#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Security Constants for AutoBot
===============================

RFC-defined security-related constants including blocked IP ranges,
security headers, and other security configuration values.

These constants represent universally blocked IP ranges as defined by IETF RFCs
and are used throughout the application for security validation.

References:
- RFC 1918: Private Address Space
- RFC 5735: Special Use IPv4 Addresses
- RFC 6890: Special-Purpose IP Address Registries
"""

from typing import Dict, List


class SecurityConstants:
    """RFC-defined security constants for network validation and blocking"""

    # Blocked IP Ranges (CIDR notation)
    # These are standard RFC-defined ranges that should be blocked in production
    BLOCKED_IP_RANGES: List[str] = [
        "0.0.0.0/8",  # RFC 1122 - Current network (only valid as source)
        "10.0.0.0/8",  # RFC 1918 - Private network Class A
        "127.0.0.0/8",  # RFC 1122 - Loopback addresses
        "169.254.0.0/16",  # RFC 3927 - Link-local addresses
        "172.16.0.0/12",  # RFC 1918 - Private network Class B
        "192.168.0.0/16",  # RFC 1918 - Private network Class C
        "224.0.0.0/4",  # RFC 5771 - Multicast addresses
        "240.0.0.0/4",  # RFC 1112 - Reserved addresses
    ]

    # Cloud metadata service IPs (used for SSRF prevention)
    CLOUD_METADATA_IPS: List[str] = [
        "169.254.169.254",  # AWS, Azure, GCP metadata service
        "169.254.169.253",  # AWS link-local
        "100.100.100.200",  # Alibaba Cloud metadata
        "192.0.0.192",  # Reserved (sometimes used by cloud providers)
    ]

    # Default allowed ports for web research
    ALLOWED_WEB_PORTS: List[int] = [80, 443, 8080, 8443]

    # Security header defaults
    DEFAULT_SECURITY_HEADERS: Dict[str, str] = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Content-Security-Policy": "default-src 'self'",
    }

    # Browser User-Agent strings for web automation
    DEFAULT_USER_AGENT: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    # User-Agent rotation pool for fingerprint randomization
    USER_AGENT_POOL: List[str] = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        " (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0)"
        " Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0)"
        " Gecko/20100101 Firefox/121.0",
    ]
