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
import logging
import os
import re
import socket
import time
from pathlib import Path
from typing import Any, Dict, Optional, Set
from urllib.parse import urlparse

import aiohttp
import yaml

from backend.constants.security_constants import SecurityConstants
from backend.security.threat_intelligence import (
    ThreatIntelligenceService,
    get_threat_intelligence_service,
)
from autobot_shared.http_client import get_http_client

logger = logging.getLogger(__name__)

# Issue #380: Pre-compiled regex for domain pattern analysis
_CONSECUTIVE_DIGITS_RE = re.compile(r"\d{4,}")
_MIXED_DIGIT_LETTER_RE = re.compile(r"[0-9]{1,}[a-z]{1,}[0-9]{1,}")


class DomainSecurityConfig:
    """Configuration for domain security settings"""

    def __init__(self, config_path: Optional[str] = None):
        """Initialize domain security config with optional custom path."""
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
            logger.error("Failed to load domain security config: %s", e)
            return self._get_default_config()

    def _get_default_blacklist(self) -> list:
        """Get default blacklist patterns."""
        return [
            "*.malware.com", "*.phishing.net", "*.spam.org", "*.scam.info",
            "*.tk", "*.ml", "*.ga", "*.cf",  # Suspicious TLDs
            "*adult*", "*porn*", "*xxx*",  # Adult content
        ]

    def _get_default_whitelist(self) -> list:
        """Get default whitelist of trusted domains."""
        return [
            "github.com", "stackoverflow.com", "docs.python.org", "python.org",
            "fastapi.tiangolo.com", "vuejs.org", "docker.com", "redis.io",
            "wikipedia.org", "*.wikipedia.org", "archlinux.org", "*.archlinux.org",
            "ubuntu.com", "*.ubuntu.com", "microsoft.com", "*.microsoft.com",
            "mozilla.org", "*.mozilla.org",
        ]

    def _get_default_reputation_services(self) -> dict:
        """Get default reputation services configuration."""
        return {
            "virustotal": {"enabled": False, "api_key": "", "timeout": 5.0, "cache_duration": 7200},
            "urlvoid": {"enabled": False, "api_key": "", "timeout": 5.0, "cache_duration": 7200},
        }

    def _get_default_threat_feeds(self) -> list:
        """Get default threat feed configuration."""
        return [{
            "name": "urlhaus",
            "url": os.getenv("AUTOBOT_URLHAUS_FEED_URL", "https://urlhaus.abuse.ch/downloads/text/"),
            "format": "text", "enabled": True, "update_interval": 3600, "timeout": 10.0,
        }]

    def _get_default_network_validation(self) -> dict:
        """Get default network validation configuration."""
        return {
            "block_private_ips": True, "block_local_ips": True, "block_cloud_metadata": True,
            "allowed_ports": SecurityConstants.ALLOWED_WEB_PORTS,
            "blocked_ip_ranges": SecurityConstants.BLOCKED_IP_RANGES,
        }

    def _get_default_config(self) -> Dict[str, Any]:
        """Default secure configuration for domain security."""
        return {
            "domain_security": {
                "enabled": True, "default_action": "block", "whitelist_mode": False,
                "cache_duration": 3600, "reputation_threshold": 0.7,
                "blacklist": self._get_default_blacklist(),
                "whitelist": self._get_default_whitelist(),
                "reputation_services": self._get_default_reputation_services(),
                "threat_feeds": self._get_default_threat_feeds(),
                "network_validation": self._get_default_network_validation(),
            }
        }


class DomainSecurityManager:
    """Manages domain security validation and threat intelligence"""

    def __init__(self, config: Optional[DomainSecurityConfig] = None):
        """Initialize domain security manager with config and compiled patterns."""
        self.config = config or DomainSecurityConfig()
        self.domain_cache = {}
        self.threat_intelligence = set()
        self.last_threat_update = 0
        self._http_client = get_http_client()  # Use singleton HTTP client

        # Threat intelligence service (lazy initialized)
        self._threat_intel_service: Optional[ThreatIntelligenceService] = None

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
        """Async context manager entry - uses singleton HTTP client"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - cleanup handled by singleton HTTPClientManager"""

    def _create_safety_result(self) -> Dict[str, Any]:
        """Create initial domain safety result structure."""
        return {
            "safe": False, "reason": "unknown", "reputation_score": 0.0,
            "threats_detected": [], "metadata": {},
        }

    def _parse_domain_url(self, url: str, result: Dict) -> tuple:
        """Parse URL and extract domain. Returns (domain, parsed, error_result or None)."""
        parsed = urlparse(url)
        if not parsed.hostname:
            return None, None, {
                "safe": False, "reason": "Invalid URL - no hostname",
                "threats_detected": ["INVALID_URL"],
            }
        domain = parsed.hostname.lower()
        result["metadata"]["domain"] = domain
        result["metadata"]["scheme"] = parsed.scheme
        result["metadata"]["port"] = parsed.port
        return domain, parsed, None

    def _check_domain_cache(self, domain: str) -> Dict[str, Any]:
        """Check if domain result is cached. Returns cached result or None."""
        cache_key = f"domain_{domain}"
        if cache_key in self.domain_cache:
            cached = self.domain_cache[cache_key]
            cache_duration = self.config.config.get("domain_security", {}).get("cache_duration", 3600)
            if time.time() - cached["timestamp"] < cache_duration:
                logger.debug("Using cached domain validation for %s", domain)
                return cached["result"]
        return None

    async def _check_network_access(self, parsed, result: Dict, cache_key: str) -> Dict[str, Any]:
        """Check network access. Returns error result if blocked, None if allowed."""
        network_result = await self._validate_network_access(parsed)
        if not network_result["allowed"]:
            error = {
                "safe": False, "reason": f"Network access blocked: {network_result['reason']}",
                "threats_detected": ["NETWORK_ACCESS_BLOCKED"],
            }
            result.update(error)
            self._cache_result(cache_key, result)
            return result
        return None

    def _check_whitelist_match(self, domain: str, result: Dict, cache_key: str) -> Dict[str, Any]:
        """Check if domain is whitelisted. Returns result if whitelisted, None otherwise."""
        if self._is_whitelisted(domain):
            result.update({
                "safe": True, "reason": "Domain is whitelisted", "reputation_score": 1.0,
                "metadata": {**result["metadata"], "whitelisted": True},
            })
            self._cache_result(cache_key, result)
            return result
        return None

    def _check_blacklist_match(self, domain: str, result: Dict, cache_key: str) -> Dict[str, Any]:
        """Check if domain is blacklisted. Returns result if blacklisted, None otherwise."""
        blacklist_result = self._check_blacklist(domain)
        if blacklist_result["blocked"]:
            result.update({
                "safe": False, "reason": f"Domain is blacklisted: {blacklist_result['reason']}",
                "threats_detected": ["BLACKLISTED_DOMAIN"],
                "metadata": {**result["metadata"], "blacklist_match": blacklist_result["pattern"]},
            })
            self._cache_result(cache_key, result)
            return result
        return None

    async def _check_threat_intelligence_match(self, domain: str, result: Dict, cache_key: str) -> Dict[str, Any]:
        """Check threat intelligence. Returns result if threat found, None otherwise."""
        await self._update_threat_intelligence()
        if domain in self.threat_intelligence:
            result.update({
                "safe": False, "reason": "Domain found in threat intelligence feeds",
                "threats_detected": ["THREAT_INTELLIGENCE"],
                "metadata": {**result["metadata"], "threat_source": "feed"},
            })
            self._cache_result(cache_key, result)
            return result
        return None

    async def _make_final_safety_decision(self, domain: str, result: Dict, cache_key: str) -> Dict[str, Any]:
        """Make final safety decision based on reputation. Returns updated result."""
        reputation_score = await self._check_reputation_services(domain)
        result["reputation_score"] = reputation_score

        domain_config = self.config.config.get("domain_security", {})
        reputation_threshold = domain_config.get("reputation_threshold", 0.7)
        whitelist_mode = domain_config.get("whitelist_mode", False)

        if whitelist_mode:
            result.update({
                "safe": False, "reason": "Whitelist mode enabled - domain not in whitelist",
                "threats_detected": ["NOT_WHITELISTED"],
            })
        elif reputation_score < reputation_threshold:
            result.update({
                "safe": False, "reason": f"Low reputation score: {reputation_score:.2f} < {reputation_threshold}",
                "threats_detected": ["LOW_REPUTATION"],
            })
        else:
            result.update({
                "safe": True, "reason": "Domain passed all security checks",
                "reputation_score": reputation_score,
            })

        self._cache_result(cache_key, result)
        logger.info("Domain validation for %s: safe=%s, reason=%s", domain, result['safe'], result['reason'])
        return result

    async def validate_domain_safety(self, url: str) -> Dict[str, Any]:
        """Comprehensive domain safety validation."""
        result = self._create_safety_result()
        try:
            domain, parsed, error = self._parse_domain_url(url, result)
            if error:
                result.update(error)
                return result

            if cached := self._check_domain_cache(domain):
                return cached

            cache_key = f"domain_{domain}"

            # Step 1: Network validation
            if blocked := await self._check_network_access(parsed, result, cache_key):
                return blocked

            # Step 2: Whitelist check
            if whitelisted := self._check_whitelist_match(domain, result, cache_key):
                return whitelisted

            # Step 3: Blacklist check
            if blacklisted := self._check_blacklist_match(domain, result, cache_key):
                return blacklisted

            # Step 4: Threat intelligence check
            if threat := await self._check_threat_intelligence_match(domain, result, cache_key):
                return threat

            # Step 5-6: Reputation check and final decision
            return await self._make_final_safety_decision(domain, result, cache_key)

        except Exception as e:
            logger.error("Error validating domain %s: %s", url, e)
            result.update({
                "safe": False, "reason": f"Validation error: {str(e)}",
                "threats_detected": ["VALIDATION_ERROR"],
            })
            return result

    def _check_port_allowed(self, port: int) -> Dict[str, Any]:
        """Check if port is allowed. Returns error result if blocked, None if allowed."""
        allowed_ports = self.config.config.get("domain_security", {}).get(
            "network_validation", {}).get("allowed_ports", [80, 443])
        if port not in allowed_ports:
            return {"allowed": False, "reason": f"Port {port} not in allowed ports"}
        return None

    def _resolve_domain_ip(self, domain: str) -> tuple:
        """Resolve domain to IP. Returns (ip_addr, ip_obj, error_result or None)."""
        try:
            ip_addr = socket.gethostbyname(domain)
            ip_obj = ipaddress.ip_address(ip_addr)
            return ip_addr, ip_obj, None
        except Exception as e:
            return None, None, {"allowed": False, "reason": f"DNS resolution failed: {e}"}

    def _check_ip_restrictions(self, ip_addr: str, ip_obj, network_config: dict) -> Dict[str, Any]:
        """Check IP restrictions. Returns error result if blocked, None if allowed."""
        if network_config.get("block_private_ips", True) and ip_obj.is_private:
            return {"allowed": False, "reason": f"Private IP access blocked: {ip_addr}"}
        if network_config.get("block_local_ips", True) and ip_obj.is_loopback:
            return {"allowed": False, "reason": f"Loopback IP access blocked: {ip_addr}"}
        if network_config.get("block_cloud_metadata", True):
            if str(ip_addr) in SecurityConstants.CLOUD_METADATA_IPS:
                return {"allowed": False, "reason": f"Cloud metadata access blocked: {ip_addr}"}
        return None

    def _check_blocked_ip_ranges(self, ip_addr: str, ip_obj, network_config: dict) -> Dict[str, Any]:
        """Check if IP is in blocked ranges. Returns error result if blocked, None if allowed."""
        blocked_ranges = network_config.get("blocked_ip_ranges", [])
        for range_str in blocked_ranges:
            try:
                if ip_obj in ipaddress.ip_network(range_str):
                    return {"allowed": False, "reason": f"IP in blocked range {range_str}: {ip_addr}"}
            except ValueError:
                continue
        return None

    async def _validate_network_access(self, parsed) -> Dict[str, Any]:
        """Validate network-level access permissions."""
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            if error := self._check_port_allowed(port):
                return error

            ip_addr, ip_obj, error = self._resolve_domain_ip(parsed.hostname)
            if error:
                return error

            network_config = self.config.config.get("domain_security", {}).get("network_validation", {})
            if error := self._check_ip_restrictions(ip_addr, ip_obj, network_config):
                return error
            if error := self._check_blocked_ip_ranges(ip_addr, ip_obj, network_config):
                return error

            return {"allowed": True, "reason": "Network access permitted"}
        except Exception as e:
            logger.error("Network validation error for %s: %s", parsed.hostname, e)
            return {"allowed": False, "reason": f"Network validation failed: {e}"}

    def _is_whitelisted(self, domain: str) -> bool:
        """Check if domain matches whitelist patterns"""
        for pattern in self.whitelist_patterns:
            if pattern.match(domain):
                logger.debug("Domain %s matched whitelist pattern: %s", domain, pattern.pattern)
                return True
        return False

    def _check_blacklist(self, domain: str) -> Dict[str, Any]:
        """Check if domain matches blacklist patterns"""
        for pattern in self.blacklist_patterns:
            if pattern.match(domain):
                logger.warning("Domain %s matched blacklist pattern: %s", domain, pattern.pattern)
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

        threat_feeds = self.config.config.get("domain_security", {}).get(
            "threat_feeds", []
        )

        for feed_config in threat_feeds:
            if not feed_config.get("enabled", False):
                continue

            try:
                logger.info("Updating threat intelligence from %s", feed_config['name'])

                async with await self._http_client.get(
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
                logger.warning("Timeout fetching threat feed %s", feed_config['name'])
            except Exception as e:
                logger.error("Error fetching threat feed %s: %s", feed_config['name'], e)

        self.last_threat_update = current_time

    def _extract_domain_from_line(self, line: str) -> str | None:
        """Extract domain from a threat feed line (Issue #315: extracted).

        Args:
            line: Single line from threat feed (URL or domain)

        Returns:
            Lowercase domain name or None if extraction failed
        """
        if line.startswith("http"):
            try:
                parsed = urlparse(line)
                return parsed.hostname.lower() if parsed.hostname else None
            except Exception:
                return None
        return line.lower()

    def _parse_threat_feed(self, content: str, format_type: str) -> Set[str]:
        """Parse threat feed content and extract domains.

        Issue #315: Refactored to use helper method for reduced nesting.
        """
        if format_type != "text":
            return set()

        domains = set()
        for line in content.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            domain = self._extract_domain_from_line(line)
            if domain:
                domains.add(domain)

        return domains

    async def _get_threat_intel_service(self) -> ThreatIntelligenceService:
        """Lazy initialization of threat intelligence service."""
        if self._threat_intel_service is None:
            self._threat_intel_service = await get_threat_intelligence_service()
        return self._threat_intel_service

    async def _check_reputation_services(self, domain: str) -> float:
        """
        Check domain reputation using configured external services.

        Integrates with VirusTotal and URLVoid APIs when configured via environment
        variables (VIRUSTOTAL_API_KEY, URLVOID_API_KEY). Falls back to heuristic-based
        scoring when external services are unavailable.

        Args:
            domain: Domain name to check

        Returns:
            Reputation score from 0.0 (malicious) to 1.0 (safe)
        """
        reputation_services = self.config.config.get("domain_security", {}).get(
            "reputation_services", {}
        )

        # Check if any external services are configured and enabled
        external_services_enabled = any(
            service_config.get("enabled", False)
            for service_config in reputation_services.values()
        )

        if external_services_enabled:
            try:
                # Use threat intelligence service for external API checks
                threat_intel = await self._get_threat_intel_service()

                if threat_intel.is_any_service_configured:
                    # Construct URL from domain for API check
                    url = f"https://{domain}"
                    threat_score = await threat_intel.check_url_reputation(url)

                    if threat_score.sources_checked > 0:
                        logger.info(
                            "External threat intelligence check for %s: score=%.2f, level=%s",
                            domain, threat_score.overall_score, threat_score.threat_level.value
                        )
                        return threat_score.overall_score

                    logger.debug(
                        "No external threat intel results for %s, using heuristics",
                        domain
                    )
            except Exception as e:
                logger.warning(
                    "External threat intelligence check failed for %s: %s",
                    domain, e
                )

        # Fall back to heuristic-based reputation
        return self._calculate_basic_reputation(domain)

    def _calculate_basic_reputation(self, domain: str) -> float:
        """Calculate basic reputation score using heuristics"""
        score = 0.5  # Neutral starting point

        # Domain length heuristic
        if len(domain) < 4:
            score -= 0.2  # Very short domains are suspicious
        elif len(domain) > 63:
            score -= 0.1  # Very long domains can be suspicious

        # Character patterns (Issue #380: use pre-compiled patterns)
        if _CONSECUTIVE_DIGITS_RE.search(domain):
            score -= 0.2  # Domains with many consecutive numbers

        if _MIXED_DIGIT_LETTER_RE.search(domain):
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
        stats = {
            "cache_entries": len(self.domain_cache),
            "threat_domains": len(self.threat_intelligence),
            "last_threat_update": self.last_threat_update,
            "whitelist_patterns": len(self.whitelist_patterns),
            "blacklist_patterns": len(self.blacklist_patterns),
            "security_config": {
                "enabled": (
                    self.config.config.get("domain_security", {}).get("enabled", False)
                ),
                "whitelist_mode": (
                    self.config.config.get("domain_security", {}).get(
                        "whitelist_mode", False
                    )
                ),
                "reputation_threshold": (
                    self.config.config.get("domain_security", {}).get(
                        "reputation_threshold", 0.7
                    )
                ),
            },
            "threat_intelligence_services": {
                "initialized": self._threat_intel_service is not None,
            },
        }

        return stats

    async def get_threat_intel_status(self) -> Dict[str, Any]:
        """Get threat intelligence service status (async)."""
        try:
            threat_intel = await self._get_threat_intel_service()
            return await threat_intel.get_service_status()
        except Exception as e:
            logger.error("Failed to get threat intel status: %s", e)
            return {
                "error": str(e),
                "virustotal": {"configured": False},
                "urlvoid": {"configured": False},
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
