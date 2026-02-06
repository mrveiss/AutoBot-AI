# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Domain Reputation Service for Enterprise Security
Integrates with VirusTotal, URLVoid, and threat intelligence feeds
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional
from urllib.parse import urlparse

import aiohttp
import yaml
from cachetools import TTLCache

from constants.path_constants import PATH
from autobot_shared.http_client import get_http_client

logger = logging.getLogger(__name__)


class DomainReputationService:
    """
    Enterprise-grade domain reputation service with multiple threat intelligence sources
    """

    def __init__(
        self,
        config_path: str = str(
            PATH.get_config_path("security", "domain_security.yaml")
        ),
    ):
        """Initialize domain reputation service with config, caches, and threat feeds."""
        self.config_path = config_path
        self.config = self._load_config()

        # Initialize caches
        cache_size = self.config.get("performance", {}).get("max_cache_size", 1000)
        cache_ttl = self.config.get("domain_security", {}).get("cache_duration", 3600)

        self.reputation_cache = TTLCache(maxsize=cache_size, ttl=cache_ttl)
        self.threat_feed_cache = TTLCache(maxsize=cache_size * 2, ttl=cache_ttl)

        # Initialize threat feeds
        self.threat_feeds = {}
        self._initialize_threat_feeds()

        # Statistics tracking
        self.stats = {
            "total_checks": 0,
            "cache_hits": 0,
            "virustotal_queries": 0,
            "urlvoid_queries": 0,
            "threat_feed_matches": 0,
            "blocked_domains": 0,
        }

        logger.info("Domain Reputation Service initialized")

    def _load_config(self) -> Dict:
        """Load domain security configuration"""
        try:
            with open(self.config_path, "r") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error("Failed to load domain security config: %s", e)
            return self._get_default_config()

    def _get_default_config(self) -> Dict:
        """Return default configuration if config file fails to load"""
        return {
            "domain_security": {
                "enabled": True,
                "default_action": "warn",
                "reputation_threshold": 0.7,
                "cache_duration": 3600,
            },
            "reputation_services": {
                "virustotal": {"enabled": False, "timeout": 5.0},
                "urlvoid": {"enabled": False, "timeout": 5.0},
            },
        }

    def _initialize_threat_feeds(self):
        """Initialize threat intelligence feeds"""
        threat_feeds = self.config.get("domain_security", {}).get("threat_feeds", [])

        for feed_config in threat_feeds:
            if not feed_config.get("enabled", False):
                continue

            feed_name = feed_config["name"]
            self.threat_feeds[feed_name] = {
                "config": feed_config,
                "last_update": 0,
                "data": set(),
            }

            # Schedule initial feed update
            asyncio.create_task(self._update_threat_feed(feed_name))

    def _parse_text_feed(self, content: str) -> set:
        """Parse text format threat feed (Issue #315 - extracted helper)."""
        return set(
            line.strip()
            for line in content.split("\n")
            if line.strip() and not line.startswith("#")
        )

    def _parse_feed_content(self, content: str, feed_format: str) -> Optional[set]:
        """Parse feed content based on format (Issue #315 - extracted helper)."""
        format_parsers = {
            "text": self._parse_text_feed,
            "csv": self._parse_csv_feed,
        }
        parser = format_parsers.get(feed_format)
        if parser:
            return parser(content)
        logger.warning("Unknown feed format: %s", feed_format)
        return None

    def _should_update_feed(self, feed_info: dict, config: dict) -> bool:
        """Check if feed update is needed (Issue #315 - extracted helper)."""
        update_interval = config.get("update_interval", 3600)
        return time.time() - feed_info["last_update"] >= update_interval

    async def _update_threat_feed(self, feed_name: str):
        """Update a threat intelligence feed (Issue #315 - refactored)."""
        try:
            feed_info = self.threat_feeds[feed_name]
            config = feed_info["config"]

            if not self._should_update_feed(feed_info, config):
                return

            logger.info("Updating threat feed: %s", feed_name)

            http_client = get_http_client()
            timeout = aiohttp.ClientTimeout(total=config.get("timeout", 10))
            async with await http_client.get(config["url"], timeout=timeout) as response:
                if response.status != 200:
                    logger.error("Failed to update %s: HTTP %s", feed_name, response.status)
                    return

                content = await response.text()
                domains = self._parse_feed_content(content, config["format"])

                if domains is not None:
                    feed_info["data"] = domains
                    feed_info["last_update"] = time.time()
                    logger.info("Updated %s: %s entries", feed_name, len(domains))

        except Exception as e:
            logger.error("Error updating threat feed %s: %s", feed_name, e)

    def _parse_csv_feed(self, content: str) -> set:
        """Parse CSV format threat feed"""
        # Implementation depends on specific CSV structure
        # This is a basic example for common formats
        domains = set()
        lines = content.split("\n")

        for line in lines[1:]:  # Skip header
            if line.strip():
                parts = line.split(",")
                if len(parts) > 0:
                    domain = parts[0].strip().strip('"')
                    if self._is_valid_domain(domain):
                        domains.add(domain)

        return domains

    def _is_valid_domain(self, domain: str) -> bool:
        """Basic domain validation"""
        if not domain or len(domain) < 4:
            return False
        if domain.startswith(".") or domain.endswith("."):
            return False
        if "." not in domain:
            return False
        return True

    async def check_domain_reputation(
        self, domain: str, context: Optional[Dict] = None
    ) -> Dict:
        """
        Comprehensive domain reputation check using multiple sources

        Returns:
            Dict with reputation assessment and details
        """
        self.stats["total_checks"] += 1

        # Normalize domain
        domain = domain.lower().strip()
        parsed = urlparse(f"http://{domain}")
        domain = parsed.netloc or parsed.path

        # Check cache first
        cache_key = f"reputation:{domain}"
        if cache_key in self.reputation_cache:
            self.stats["cache_hits"] += 1
            cached_result = self.reputation_cache[cache_key]
            cached_result["source"] = "cache"
            return cached_result

        # Perform comprehensive reputation check
        result = await self._perform_reputation_check(domain, context)

        # Cache result
        self.reputation_cache[cache_key] = result

        return result

    async def _perform_reputation_check(
        self, domain: str, context: Optional[Dict]
    ) -> Dict:
        """Perform multi-source reputation check"""
        checks = {
            "domain": domain,
            "timestamp": time.time(),
            "reputation_score": 1.0,  # Start with clean score
            "risk_level": "unknown",
            "threats_detected": [],
            "sources_checked": [],
            "details": {},
        }

        # 1. Check threat intelligence feeds
        feed_threats = self._check_threat_feeds(domain)
        if feed_threats:
            checks["threats_detected"].extend(feed_threats)
            checks["reputation_score"] -= 0.8  # Major penalty for known threats
            self.stats["threat_feed_matches"] += 1

        # 2. Check pattern-based rules
        pattern_threats = self._check_domain_patterns(domain)
        if pattern_threats:
            checks["threats_detected"].extend(pattern_threats)
            checks[
                "reputation_score"
            ] -= 0.3  # Moderate penalty for suspicious patterns

        # 3. Check external reputation services
        external_results = await self._check_external_services(domain)
        checks["details"]["external_services"] = external_results

        for service, result in external_results.items():
            checks["sources_checked"].append(service)
            if result.get("malicious", False):
                checks["threats_detected"].append(f"{service}_malicious")
                checks["reputation_score"] -= 0.6
            elif result.get("suspicious", False):
                checks["threats_detected"].append(f"{service}_suspicious")
                checks["reputation_score"] -= 0.3

        # 4. Determine final risk level and action
        checks["reputation_score"] = max(0.0, checks["reputation_score"])
        checks["risk_level"] = self._calculate_risk_level(checks["reputation_score"])
        checks["action"] = self._determine_action(checks)

        # 5. Log security event if threats detected
        if checks["threats_detected"]:
            self._log_security_event(domain, checks, context)

        return checks

    def _check_threat_feeds(self, domain: str) -> List[str]:
        """Check domain against threat intelligence feeds"""
        threats = []

        for feed_name, feed_info in self.threat_feeds.items():
            if domain in feed_info["data"]:
                threats.append(f"threat_feed_{feed_name}")
                logger.warning("Domain %s found in threat feed: %s", domain, feed_name)

        return threats

    def _check_domain_patterns(self, domain: str) -> List[str]:
        """Check domain against suspicious patterns"""
        threats = []

        config = self.config.get("domain_security", {})

        # Check blacklist patterns
        blacklist = config.get("blacklist", [])
        for pattern in blacklist:
            if self._match_pattern(domain, pattern):
                threats.append(f"blacklist_pattern_{pattern}")
                logger.warning("Domain %s matches blacklist pattern: %s", domain, pattern)

        # Check for suspicious characteristics
        if self._is_suspicious_domain(domain):
            threats.append("suspicious_characteristics")

        return threats

    def _match_pattern(self, domain: str, pattern: str) -> bool:
        """Match domain against wildcard pattern"""
        if "*" in pattern:
            # Simple wildcard matching
            if pattern.startswith("*"):
                return domain.endswith(pattern[1:])
            elif pattern.endswith("*"):
                return domain.startswith(pattern[:-1])
            else:
                # Pattern contains * in middle
                parts = pattern.split("*")
                if len(parts) == 2:
                    return domain.startswith(parts[0]) and domain.endswith(parts[1])
        else:
            return domain == pattern

        return False

    def _is_suspicious_domain(self, domain: str) -> bool:
        """Detect suspicious domain characteristics"""
        suspicious_indicators = [
            len(domain) > 50,  # Unusually long domain
            domain.count("-") > 4,  # Many hyphens
            domain.count(".") > 3,  # Many subdomains
            any(char.isdigit() for char in domain.split(".")[0])
            and len(domain.split(".")[0]) > 8,  # Long subdomain with numbers
            domain.count("0") + domain.count("1")
            > len(domain) * 0.3,  # Too many 0s and 1s
        ]

        return sum(suspicious_indicators) >= 2

    async def _check_external_services(self, domain: str) -> Dict:
        """Check external reputation services"""
        results = {}

        # VirusTotal check
        if self._is_service_enabled("virustotal"):
            vt_result = await self._check_virustotal(domain)
            if vt_result:
                results["virustotal"] = vt_result
                self.stats["virustotal_queries"] += 1

        # URLVoid check
        if self._is_service_enabled("urlvoid"):
            uv_result = await self._check_urlvoid(domain)
            if uv_result:
                results["urlvoid"] = uv_result
                self.stats["urlvoid_queries"] += 1

        return results

    def _is_service_enabled(self, service_name: str) -> bool:
        """Check if external service is enabled and configured"""
        services = self.config.get("domain_security", {}).get("reputation_services", {})
        service_config = services.get(service_name, {})

        return service_config.get("enabled", False) and service_config.get(
            "api_key", ""
        )

    async def _check_virustotal(self, domain: str) -> Optional[Dict]:
        """Check domain reputation with VirusTotal API"""
        try:
            config = self.config["domain_security"]["reputation_services"]["virustotal"]
            api_key = config.get("api_key", "")

            if not api_key:
                return None

            url = "https://www.virustotal.com/vtapi/v2/domain/report"
            params = {"apikey": api_key, "domain": domain}

            http_client = get_http_client()
            timeout = aiohttp.ClientTimeout(total=config.get("timeout", 5.0))
            async with await http_client.get(url, params=params, timeout=timeout) as response:
                if response.status == 200:
                    data = await response.json()

                    # Parse VirusTotal response
                    positives = data.get("positives", 0)
                    total = data.get("total", 0)

                    return {
                        "service": "virustotal",
                        "positives": positives,
                        "total": total,
                        "malicious": positives > 0,
                        "suspicious": (
                            positives > total * 0.1 if total > 0 else False
                        ),
                        "reputation_score": (
                            max(0, 1 - (positives / total)) if total > 0 else 1.0
                        ),
                        "raw_response": data,
                    }
                else:
                    logger.error("VirusTotal API error: HTTP %s", response.status)

        except Exception as e:
            logger.error("VirusTotal check failed for %s: %s", domain, e)

        return None

    async def _check_urlvoid(self, domain: str) -> Optional[Dict]:
        """Check domain reputation with URLVoid API"""
        try:
            config = self.config["domain_security"]["reputation_services"]["urlvoid"]
            api_key = config.get("api_key", "")

            if not api_key:
                return None

            url = f"http://api.urlvoid.com/1000/{api_key}/host/{domain}/"

            http_client = get_http_client()
            timeout = aiohttp.ClientTimeout(total=config.get("timeout", 5.0))
            async with await http_client.get(url, timeout=timeout) as response:
                if response.status == 200:
                    # URLVoid returns XML, parse accordingly
                    content = await response.text()
                    # Basic parsing - in production, use proper XML parser

                    malicious = "blacklisted" in content.lower()
                    suspicious = "suspicious" in content.lower()

                    return {
                        "service": "urlvoid",
                        "malicious": malicious,
                        "suspicious": suspicious,
                        "reputation_score": (
                            0.0 if malicious else 0.5 if suspicious else 1.0
                        ),
                        "raw_response": content[:500],  # Truncated for storage
                    }
                else:
                    logger.error("URLVoid API error: HTTP %s", response.status)

        except Exception as e:
            logger.error("URLVoid check failed for %s: %s", domain, e)

        return None

    def _calculate_risk_level(self, reputation_score: float) -> str:
        """Calculate risk level based on reputation score"""
        if reputation_score >= 0.8:
            return "low"
        elif reputation_score >= 0.6:
            return "medium"
        elif reputation_score >= 0.3:
            return "high"
        else:
            return "critical"

    def _determine_action(self, checks: Dict) -> str:
        """Determine action based on reputation assessment"""
        threshold = self.config.get("domain_security", {}).get(
            "reputation_threshold", 0.7
        )
        default_action = self.config.get("domain_security", {}).get(
            "default_action", "warn"
        )

        if checks["reputation_score"] < threshold:
            if checks["risk_level"] == "critical":
                return "block"
            elif checks["risk_level"] == "high":
                return "block" if default_action == "block" else "warn"
            else:
                return "warn"

        return "allow"

    def _log_security_event(self, domain: str, checks: Dict, context: Optional[Dict]):
        """Log security event for threat detection"""
        if checks["action"] == "block":
            self.stats["blocked_domains"] += 1

        # This would integrate with the enterprise audit logger
        logger.warning("Domain security event: %s | ", domain)

    def get_statistics(self) -> Dict:
        """Get service statistics"""
        return {
            **self.stats,
            "cache_size": len(self.reputation_cache),
            "threat_feeds_loaded": len(self.threat_feeds),
            "cache_hit_rate": (
                self.stats["cache_hits"] / max(1, self.stats["total_checks"])
            ),
        }

    async def bulk_check_domains(
        self, domains: List[str], context: Optional[Dict] = None
    ) -> List[Dict]:
        """Check multiple domains concurrently"""
        max_concurrent = self.config.get("performance", {}).get("concurrent_checks", 5)
        semaphore = asyncio.Semaphore(max_concurrent)

        async def check_single(domain):
            """Check single domain with semaphore-controlled concurrency."""
            async with semaphore:
                return await self.check_domain_reputation(domain, context)

        tasks = [check_single(domain) for domain in domains]
        return await asyncio.gather(*tasks, return_exceptions=True)

    def is_domain_blocked(self, domain: str) -> bool:
        """Quick check if domain should be blocked based on cached data"""
        cache_key = f"reputation:{domain.lower().strip()}"

        if cache_key in self.reputation_cache:
            cached_result = self.reputation_cache[cache_key]
            return cached_result.get("action") == "block"

        # If not cached, perform basic pattern check
        threats = self._check_domain_patterns(domain)
        return len(threats) > 0
