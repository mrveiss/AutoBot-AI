# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Domain Security Manager for AutoBot Web Research

Provides comprehensive domain validation, reputation checking, and threat intelligence
integration to ensure safe web research operations.
"""

import asyncio
import ipaddress
import json
import logging
import re
import socket
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import aiohttp
import yaml

from src.constants.network_constants import NetworkConstants
from src.constants.security_constants import SecurityConstants

logger = logging.getLogger(__name__)


class DomainSecurityConfig:
    """Configuration for domain security settings"""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or "config/security/domain_security.yaml"
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load domain security configuration"""
        config_file = Path(self.config_path)
        if not config_file.exists():
            return self._get_default_config()

        try:
            with open(config_file, "r") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Failed to load domain security config: {e}")
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """Default secure configuration for domain security"""
        return {
            "domain_security": {
                "enabled": True,
                "default_action": "block",  # block, allow, warn
                "whitelist_mode": False,
                "cache_duration": 3600,  # 1 hour
                "reputation_threshold": 0.7,  # 0.0 = unsafe, 1.0 = safe
                "blacklist": [
                    # Known malicious domain patterns
                    "*.malware.com",
                    "*.phishing.net",
                    "*.spam.org",
                    "*.scam.info",
                    # Suspicious TLDs
                    "*.tk",
                    "*.ml",
                    "*.ga",
                    "*.cf",
                    # Adult content (basic patterns)
                    "*adult*",
                    "*porn*",
                    "*xxx*",
                ],
                "whitelist": [
                    # Trusted domains for research
                    "github.com",
                    "stackoverflow.com",
                    "docs.python.org",
                    "python.org",
                    "fastapi.tiangolo.com",
                    "vuejs.org",
                    "docker.com",
                    "redis.io",
                    "wikipedia.org",
                    "*.wikipedia.org",
                    "archlinux.org",
                    "*.archlinux.org",
                    "ubuntu.com",
                    "*.ubuntu.com",
                    "microsoft.com",
                    "*.microsoft.com",
                    "mozilla.org",
                    "*.mozilla.org",
                ],
                "reputation_services": {
                    "virustotal": {
                        "enabled": False,  # Requires API key
                        "api_key": "",
                        "timeout": 5.0,
                        "cache_duration": 7200,
                    },
                    "urlvoid": {
                        "enabled": False,  # Requires API key
                        "api_key": "",
                        "timeout": 5.0,
                        "cache_duration": 7200,
                    },
                },
                "threat_feeds": [
                    {
                        "name": "urlhaus",
                        "url": "https://urlhaus.abuse.ch/downloads/text/",
                        "format": "text",
                        "enabled": True,
                        "update_interval": 3600,
                        "timeout": 10.0,
                    }
                ],
                "network_validation": {
                    "block_private_ips": True,
                    "block_local_ips": True,
                    "block_cloud_metadata": True,
                    "allowed_ports": SecurityConstants.ALLOWED_WEB_PORTS,
                    "blocked_ip_ranges": SecurityConstants.BLOCKED_IP_RANGES,
                },
            }
        }


class DomainSecurityManager:
    """Manages domain security validation and threat intelligence"""

    def __init__(self, config: Optional[DomainSecurityConfig] = None):
        self.config = config or DomainSecurityConfig()
        self.domain_cache = {}
        self.threat_intelligence = set()
        self.last_threat_update = 0
        self.session: Optional[aiohttp.ClientSession] = None

        # Precompile regex patterns for performance
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile domain patterns for efficient matching"""
        self.blacklist_patterns = []
        self.whitelist_patterns = []

        # Compile blacklist patterns
        for pattern in self.config.config.get("domain_security", {}).get(
            "blacklist", []
        ):
            regex_pattern = pattern.replace("*", ".*").replace(".", "\\.")
            self.blacklist_patterns.append(
                re.compile(f"^{regex_pattern}$", re.IGNORECASE)
            )

        # Compile whitelist patterns
        for pattern in self.config.config.get("domain_security", {}).get(
            "whitelist", []
        ):
            regex_pattern = pattern.replace("*", ".*").replace(".", "\\.")
            self.whitelist_patterns.append(
                re.compile(f"^{regex_pattern}$", re.IGNORECASE)
            )

    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30.0),
            headers={
                "User-Agent": "AutoBot-Security/1.0 (+https://autobot.internal/security)"
            },
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()

    async def validate_domain_safety(self, url: str) -> Dict[str, Any]:
        """
        Comprehensive domain safety validation

        Returns:
            Dict containing:
            - safe: bool - Whether domain is safe to access
            - reason: str - Reason for the decision
            - reputation_score: float - Domain reputation (0.0-1.0)
            - threats_detected: List[str] - List of detected threats
            - metadata: Dict - Additional metadata
        """
        result = {
            "safe": False,
            "reason": "unknown",
            "reputation_score": 0.0,
            "threats_detected": [],
            "metadata": {},
        }

        try:
            # Parse URL
            parsed = urlparse(url)
            if not parsed.hostname:
                result.update(
                    {
                        "safe": False,
                        "reason": "Invalid URL - no hostname",
                        "threats_detected": ["INVALID_URL"],
                    }
                )
                return result

            domain = parsed.hostname.lower()
            result["metadata"]["domain"] = domain
            result["metadata"]["scheme"] = parsed.scheme
            result["metadata"]["port"] = parsed.port

            # Check cache first
            cache_key = f"domain_{domain}"
            if cache_key in self.domain_cache:
                cached = self.domain_cache[cache_key]
                if time.time() - cached["timestamp"] < self.config.config.get(
                    "domain_security", {}
                ).get("cache_duration", 3600):
                    logger.debug(f"Using cached domain validation for {domain}")
                    return cached["result"]

            # Step 1: Network validation
            network_result = await self._validate_network_access(parsed)
            if not network_result["allowed"]:
                result.update(
                    {
                        "safe": False,
                        "reason": f"Network access blocked: {network_result['reason']}",
                        "threats_detected": ["NETWORK_ACCESS_BLOCKED"],
                    }
                )
                self._cache_result(cache_key, result)
                return result

            # Step 2: Whitelist check (if in whitelist mode or domain is whitelisted)
            if self._is_whitelisted(domain):
                result.update(
                    {
                        "safe": True,
                        "reason": "Domain is whitelisted",
                        "reputation_score": 1.0,
                        "metadata": {**result["metadata"], "whitelisted": True},
                    }
                )
                self._cache_result(cache_key, result)
                return result

            # Step 3: Blacklist check
            blacklist_result = self._check_blacklist(domain)
            if blacklist_result["blocked"]:
                result.update(
                    {
                        "safe": False,
                        "reason": f"Domain is blacklisted: {blacklist_result['reason']}",
                        "threats_detected": ["BLACKLISTED_DOMAIN"],
                        "metadata": {
                            **result["metadata"],
                            "blacklist_match": blacklist_result["pattern"],
                        },
                    }
                )
                self._cache_result(cache_key, result)
                return result

            # Step 4: Threat intelligence check
            await self._update_threat_intelligence()
            if domain in self.threat_intelligence:
                result.update(
                    {
                        "safe": False,
                        "reason": "Domain found in threat intelligence feeds",
                        "threats_detected": ["THREAT_INTELLIGENCE"],
                        "metadata": {**result["metadata"], "threat_source": "feed"},
                    }
                )
                self._cache_result(cache_key, result)
                return result

            # Step 5: Reputation services check (if enabled and configured)
            reputation_score = await self._check_reputation_services(domain)
            result["reputation_score"] = reputation_score

            # Step 6: Make final decision
            reputation_threshold = self.config.config.get("domain_security", {}).get(
                "reputation_threshold", 0.7
            )
            whitelist_mode = self.config.config.get("domain_security", {}).get(
                "whitelist_mode", False
            )

            if whitelist_mode:
                # In whitelist mode, block everything not explicitly allowed
                result.update(
                    {
                        "safe": False,
                        "reason": "Whitelist mode enabled - domain not in whitelist",
                        "threats_detected": ["NOT_WHITELISTED"],
                    }
                )
            elif reputation_score < reputation_threshold:
                result.update(
                    {
                        "safe": False,
                        "reason": f"Low reputation score: {reputation_score:.2f} < {reputation_threshold}",
                        "threats_detected": ["LOW_REPUTATION"],
                    }
                )
            else:
                result.update(
                    {
                        "safe": True,
                        "reason": "Domain passed all security checks",
                        "reputation_score": reputation_score,
                    }
                )

            # Cache the result
            self._cache_result(cache_key, result)

            logger.info(
                f"Domain validation for {domain}: safe={result['safe']}, reason={result['reason']}"
            )
            return result

        except Exception as e:
            logger.error(f"Error validating domain {url}: {e}")
            result.update(
                {
                    "safe": False,
                    "reason": f"Validation error: {str(e)}",
                    "threats_detected": ["VALIDATION_ERROR"],
                }
            )
            return result

    async def _validate_network_access(self, parsed) -> Dict[str, Any]:
        """Validate network-level access permissions"""
        result = {"allowed": False, "reason": "unknown"}

        try:
            domain = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == "https" else 80)

            # Check port restrictions
            allowed_ports = (
                self.config.config.get("domain_security", {})
                .get("network_validation", {})
                .get("allowed_ports", [80, 443])
            )
            if port not in allowed_ports:
                return {"allowed": False, "reason": f"Port {port} not in allowed ports"}

            # Resolve domain to IP
            try:
                ip_addr = socket.gethostbyname(domain)
                ip_obj = ipaddress.ip_address(ip_addr)
            except Exception as e:
                return {"allowed": False, "reason": f"DNS resolution failed: {e}"}

            # Check IP restrictions
            network_config = self.config.config.get("domain_security", {}).get(
                "network_validation", {}
            )

            if network_config.get("block_private_ips", True) and ip_obj.is_private:
                return {
                    "allowed": False,
                    "reason": f"Private IP access blocked: {ip_addr}",
                }

            if network_config.get("block_local_ips", True) and ip_obj.is_loopback:
                return {
                    "allowed": False,
                    "reason": f"Loopback IP access blocked: {ip_addr}",
                }

            # Check cloud metadata endpoints
            if network_config.get("block_cloud_metadata", True):
                if str(ip_addr) in SecurityConstants.CLOUD_METADATA_IPS:
                    return {
                        "allowed": False,
                        "reason": f"Cloud metadata access blocked: {ip_addr}",
                    }

            # Check blocked IP ranges
            blocked_ranges = network_config.get("blocked_ip_ranges", [])
            for range_str in blocked_ranges:
                try:
                    if ip_obj in ipaddress.ip_network(range_str):
                        return {
                            "allowed": False,
                            "reason": f"IP in blocked range {range_str}: {ip_addr}",
                        }
                except ValueError:
                    continue  # Invalid range format, skip

            return {"allowed": True, "reason": "Network access permitted"}

        except Exception as e:
            logger.error(f"Network validation error for {parsed.hostname}: {e}")
            return {"allowed": False, "reason": f"Network validation failed: {e}"}

    def _is_whitelisted(self, domain: str) -> bool:
        """Check if domain matches whitelist patterns"""
        for pattern in self.whitelist_patterns:
            if pattern.match(domain):
                logger.debug(
                    f"Domain {domain} matched whitelist pattern: {pattern.pattern}"
                )
                return True
        return False

    def _check_blacklist(self, domain: str) -> Dict[str, Any]:
        """Check if domain matches blacklist patterns"""
        for pattern in self.blacklist_patterns:
            if pattern.match(domain):
                logger.warning(
                    f"Domain {domain} matched blacklist pattern: {pattern.pattern}"
                )
                return {
                    "blocked": True,
                    "reason": "Domain matches blacklist pattern",
                    "pattern": pattern.pattern,
                }
        return {"blocked": False, "reason": "No blacklist match"}

    async def _update_threat_intelligence(self):
        """Update threat intelligence from configured feeds"""
        current_time = time.time()
        update_interval = 3600  # 1 hour default

        if current_time - self.last_threat_update < update_interval:
            return  # Too soon to update

        if not self.session:
            return  # No session available

        threat_feeds = self.config.config.get("domain_security", {}).get(
            "threat_feeds", []
        )

        for feed_config in threat_feeds:
            if not feed_config.get("enabled", False):
                continue

            try:
                logger.info(f"Updating threat intelligence from {feed_config['name']}")

                async with self.session.get(
                    feed_config["url"],
                    timeout=aiohttp.ClientTimeout(
                        total=feed_config.get("timeout", 10.0)
                    ),
                ) as response:
                    if response.status == 200:
                        content = await response.text()
                        domains = self._parse_threat_feed(
                            content, feed_config["format"]
                        )
                        self.threat_intelligence.update(domains)
                        logger.info(
                            f"Updated {len(domains)} threat domains from {feed_config['name']}"
                        )
                    else:
                        logger.warning(
                            f"Failed to fetch threat feed {feed_config['name']}: HTTP {response.status}"
                        )

            except asyncio.TimeoutError:
                logger.warning(f"Timeout fetching threat feed {feed_config['name']}")
            except Exception as e:
                logger.error(f"Error fetching threat feed {feed_config['name']}: {e}")

        self.last_threat_update = current_time

    def _parse_threat_feed(self, content: str, format_type: str) -> Set[str]:
        """Parse threat feed content and extract domains"""
        domains = set()

        if format_type == "text":
            for line in content.split("\n"):
                line = line.strip()
                if line and not line.startswith("#"):
                    # Extract domain from URL or use as-is
                    if line.startswith("http"):
                        try:
                            parsed = urlparse(line)
                            if parsed.hostname:
                                domains.add(parsed.hostname.lower())
                        except Exception:
                            continue
                    else:
                        domains.add(line.lower())

        return domains

    async def _check_reputation_services(self, domain: str) -> float:
        """Check domain reputation using configured services"""
        reputation_services = self.config.config.get("domain_security", {}).get(
            "reputation_services", {}
        )

        # For now, return neutral score if no services configured
        # TODO: Implement VirusTotal, URLVoid integration when API keys are available
        for service_name, service_config in reputation_services.items():
            if service_config.get("enabled", False) and service_config.get("api_key"):
                logger.debug(
                    f"Reputation service {service_name} configured but not implemented yet"
                )

        # Default reputation based on basic heuristics
        return self._calculate_basic_reputation(domain)

    def _calculate_basic_reputation(self, domain: str) -> float:
        """Calculate basic reputation score using heuristics"""
        score = 0.5  # Neutral starting point

        # Domain length heuristic
        if len(domain) < 4:
            score -= 0.2  # Very short domains are suspicious
        elif len(domain) > 63:
            score -= 0.1  # Very long domains can be suspicious

        # Character patterns
        if re.search(r"\d{4,}", domain):
            score -= 0.2  # Domains with many consecutive numbers

        if re.search(r"[0-9]{1,}[a-z]{1,}[0-9]{1,}", domain):
            score -= 0.1  # Mixed numbers and letters pattern

        # Suspicious keywords
        suspicious_keywords = [
            "secure",
            "bank",
            "update",
            "verify",
            "confirm",
            "urgent",
        ]
        for keyword in suspicious_keywords:
            if keyword in domain.lower():
                score -= 0.3
                break

        # TLD reputation
        suspicious_tlds = [".tk", ".ml", ".ga", ".cf"]
        for tld in suspicious_tlds:
            if domain.endswith(tld):
                score -= 0.4
                break

        # Ensure score is in valid range
        return max(0.0, min(1.0, score))

    def _cache_result(self, cache_key: str, result: Dict[str, Any]):
        """Cache domain validation result"""
        self.domain_cache[cache_key] = {"result": result, "timestamp": time.time()}

        # Clean old cache entries (simple cleanup)
        if len(self.domain_cache) > 1000:
            cutoff_time = time.time() - self.config.config.get(
                "domain_security", {}
            ).get("cache_duration", 3600)
            self.domain_cache = {
                k: v
                for k, v in self.domain_cache.items()
                if v["timestamp"] > cutoff_time
            }

    async def validate_url_safety(self, url: str) -> Dict[str, Any]:
        """High-level URL safety validation (wrapper for domain validation)"""
        return await self.validate_domain_safety(url)

    def get_security_stats(self) -> Dict[str, Any]:
        """Get security statistics and metrics"""
        return {
            "cache_entries": len(self.domain_cache),
            "threat_domains": len(self.threat_intelligence),
            "last_threat_update": self.last_threat_update,
            "whitelist_patterns": len(self.whitelist_patterns),
            "blacklist_patterns": len(self.blacklist_patterns),
            "security_config": {
                "enabled": self.config.config.get("domain_security", {}).get(
                    "enabled", False
                ),
                "whitelist_mode": self.config.config.get("domain_security", {}).get(
                    "whitelist_mode", False
                ),
                "reputation_threshold": self.config.config.get(
                    "domain_security", {}
                ).get("reputation_threshold", 0.7),
            },
        }


# Convenience function for easy access
async def validate_url_safety(
    url: str, config: Optional[DomainSecurityConfig] = None
) -> Dict[str, Any]:
    """Standalone function to validate URL safety"""
    async with DomainSecurityManager(config) as manager:
        return await manager.validate_url_safety(url)


# Create default instance
_default_manager = None
_default_manager_lock = asyncio.Lock()


async def get_domain_security_manager() -> DomainSecurityManager:
    """Get shared domain security manager instance"""
    global _default_manager
    async with _default_manager_lock:
        if _default_manager is None:
            _default_manager = DomainSecurityManager()
    return _default_manager
