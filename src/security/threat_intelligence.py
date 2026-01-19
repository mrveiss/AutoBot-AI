# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Threat Intelligence Integration Module

Provides external threat intelligence API integrations for URL/domain validation:
- VirusTotal API for malware/phishing detection
- URLVoid API for domain reputation checking

Features:
- Rate limiting to respect API quotas
- Response caching to reduce API calls
- Graceful degradation when services unavailable
- Async HTTP client for non-blocking operations
"""

import asyncio
import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import aiohttp

from src.utils.http_client import get_http_client

logger = logging.getLogger(__name__)


class ThreatLevel(Enum):
    """Threat level classification"""
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class ThreatScore:
    """Aggregated threat score from multiple sources"""
    virustotal_score: Optional[float] = None
    urlvoid_score: Optional[float] = None
    overall_score: float = 0.5
    threat_level: ThreatLevel = ThreatLevel.UNKNOWN
    details: Dict[str, Any] = field(default_factory=dict)
    sources_checked: int = 0
    cached: bool = False


@dataclass
class RateLimitState:
    """Rate limiter state for API calls"""
    requests_made: int = 0
    window_start: float = field(default_factory=time.time)
    requests_per_minute: int = 4  # Default VirusTotal free tier


class ThreatIntelligenceCache:
    """Thread-safe cache for threat intelligence results"""

    def __init__(self, default_ttl: int = 7200):
        """Initialize cache with default TTL in seconds."""
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._default_ttl = default_ttl
        self._lock = asyncio.Lock()

    def _get_cache_key(self, url: str) -> str:
        """Generate cache key from URL."""
        return hashlib.sha256(url.lower().encode()).hexdigest()[:32]

    async def get(self, url: str) -> Optional[ThreatScore]:
        """Get cached threat score if not expired."""
        async with self._lock:
            cache_key = self._get_cache_key(url)
            if cache_key not in self._cache:
                return None

            entry = self._cache[cache_key]
            if time.time() > entry["expires_at"]:
                del self._cache[cache_key]
                return None

            result = entry["result"]
            result.cached = True
            return result

    async def set(self, url: str, result: ThreatScore, ttl: Optional[int] = None):
        """Cache threat score with TTL."""
        async with self._lock:
            cache_key = self._get_cache_key(url)
            self._cache[cache_key] = {
                "result": result,
                "expires_at": time.time() + (ttl or self._default_ttl),
            }

    async def clear_expired(self):
        """Remove expired entries from cache."""
        async with self._lock:
            current_time = time.time()
            self._cache = {
                k: v for k, v in self._cache.items()
                if v["expires_at"] > current_time
            }


class RateLimiter:
    """Async rate limiter for API calls"""

    def __init__(self, requests_per_minute: int = 4):
        """Initialize rate limiter with requests per minute limit."""
        self._requests_per_minute = requests_per_minute
        self._window_size = 60.0  # 1 minute window
        self._requests: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        """
        Acquire rate limit slot. Returns True if allowed, False if rate limited.
        Blocks if necessary to wait for available slot.
        """
        async with self._lock:
            current_time = time.time()
            window_start = current_time - self._window_size

            # Remove requests outside the current window
            self._requests = [t for t in self._requests if t > window_start]

            if len(self._requests) >= self._requests_per_minute:
                # Calculate wait time until oldest request expires
                wait_time = self._requests[0] - window_start
                if wait_time > 0:
                    logger.debug("Rate limited, waiting %.2f seconds", wait_time)
                    await asyncio.sleep(wait_time)
                    # Re-check after waiting
                    return await self.acquire()

            self._requests.append(current_time)
            return True

    def get_remaining(self) -> int:
        """Get remaining requests in current window."""
        current_time = time.time()
        window_start = current_time - self._window_size
        active_requests = [t for t in self._requests if t > window_start]
        return max(0, self._requests_per_minute - len(active_requests))


class VirusTotalClient:
    """VirusTotal API v3 client for URL/domain reputation checking"""

    BASE_URL = "https://www.virustotal.com/api/v3"

    def __init__(
        self,
        api_key: Optional[str] = None,
        rate_limit: int = 4,
        timeout: float = 10.0,
    ):
        """
        Initialize VirusTotal client.

        Args:
            api_key: VirusTotal API key (from env if not provided)
            rate_limit: Requests per minute (default: 4 for free tier)
            timeout: Request timeout in seconds
        """
        self._api_key = api_key or os.getenv("VIRUSTOTAL_API_KEY", "")
        self._rate_limiter = RateLimiter(rate_limit)
        self._timeout = timeout
        self._http_client = get_http_client()

    @property
    def is_configured(self) -> bool:
        """Check if API key is configured."""
        return bool(self._api_key)

    def _get_url_id(self, url: str) -> str:
        """Generate VirusTotal URL identifier (base64 without padding)."""
        import base64
        return base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")

    async def check_url(self, url: str) -> Dict[str, Any]:
        """
        Check URL reputation using VirusTotal API.

        Args:
            url: URL to check

        Returns:
            Dict with reputation data or error information
        """
        if not self.is_configured:
            return {
                "success": False,
                "error": "VirusTotal API key not configured",
                "score": None,
            }

        try:
            await self._rate_limiter.acquire()

            url_id = self._get_url_id(url)
            endpoint = f"{self.BASE_URL}/urls/{url_id}"

            headers = {
                "x-apikey": self._api_key,
                "Accept": "application/json",
            }

            async with await self._http_client.get(
                endpoint,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self._timeout),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return self._parse_url_response(data)
                elif response.status == 404:
                    # URL not found - submit for analysis
                    return await self._submit_url_for_analysis(url)
                elif response.status == 429:
                    return {
                        "success": False,
                        "error": "VirusTotal rate limit exceeded",
                        "score": None,
                    }
                else:
                    return {
                        "success": False,
                        "error": f"VirusTotal API error: HTTP {response.status}",
                        "score": None,
                    }

        except asyncio.TimeoutError:
            logger.warning("VirusTotal API timeout for URL: %s", url)
            return {"success": False, "error": "Request timeout", "score": None}
        except Exception as e:
            logger.error("VirusTotal API error: %s", e)
            return {"success": False, "error": str(e), "score": None}

    async def _submit_url_for_analysis(self, url: str) -> Dict[str, Any]:
        """Submit URL for analysis if not found in VirusTotal database."""
        try:
            await self._rate_limiter.acquire()

            endpoint = f"{self.BASE_URL}/urls"
            headers = {
                "x-apikey": self._api_key,
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            }

            async with await self._http_client.post(
                endpoint,
                headers=headers,
                data={"url": url},
                timeout=aiohttp.ClientTimeout(total=self._timeout),
            ) as response:
                if response.status in (200, 201):
                    return {
                        "success": True,
                        "score": 0.5,  # Neutral score for new URLs
                        "status": "submitted_for_analysis",
                        "message": "URL submitted for analysis, results pending",
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Failed to submit URL: HTTP {response.status}",
                        "score": None,
                    }
        except Exception as e:
            logger.error("Failed to submit URL to VirusTotal: %s", e)
            return {"success": False, "error": str(e), "score": None}

    def _parse_url_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse VirusTotal URL analysis response."""
        try:
            attributes = data.get("data", {}).get("attributes", {})
            stats = attributes.get("last_analysis_stats", {})

            total_engines = sum(stats.values()) if stats else 0
            malicious = stats.get("malicious", 0)
            suspicious = stats.get("suspicious", 0)

            if total_engines == 0:
                score = 0.5  # Neutral if no analysis available
            else:
                # Calculate score: 1.0 = safe, 0.0 = malicious
                threat_count = malicious + (suspicious * 0.5)
                score = 1.0 - (threat_count / total_engines)
                score = max(0.0, min(1.0, score))

            return {
                "success": True,
                "score": score,
                "stats": stats,
                "total_engines": total_engines,
                "malicious_count": malicious,
                "suspicious_count": suspicious,
                "last_analysis_date": attributes.get("last_analysis_date"),
                "categories": attributes.get("categories", {}),
            }
        except Exception as e:
            logger.error("Failed to parse VirusTotal response: %s", e)
            return {"success": False, "error": str(e), "score": None}


class URLVoidClient:
    """URLVoid API client for domain reputation checking"""

    BASE_URL = "https://api.urlvoid.com/api1000"

    def __init__(
        self,
        api_key: Optional[str] = None,
        rate_limit: int = 10,
        timeout: float = 10.0,
    ):
        """
        Initialize URLVoid client.

        Args:
            api_key: URLVoid API key (from env if not provided)
            rate_limit: Requests per minute
            timeout: Request timeout in seconds
        """
        self._api_key = api_key or os.getenv("URLVOID_API_KEY", "")
        self._rate_limiter = RateLimiter(rate_limit)
        self._timeout = timeout
        self._http_client = get_http_client()

    @property
    def is_configured(self) -> bool:
        """Check if API key is configured."""
        return bool(self._api_key)

    async def check_domain(self, url: str) -> Dict[str, Any]:
        """
        Check domain reputation using URLVoid API.

        Args:
            url: URL or domain to check

        Returns:
            Dict with reputation data or error information
        """
        if not self.is_configured:
            return {
                "success": False,
                "error": "URLVoid API key not configured",
                "score": None,
            }

        try:
            # Extract domain from URL
            parsed = urlparse(url)
            domain = parsed.hostname or url
            domain = domain.lower().strip()

            await self._rate_limiter.acquire()

            endpoint = f"{self.BASE_URL}/{self._api_key}/host/{domain}/"

            async with await self._http_client.get(
                endpoint,
                timeout=aiohttp.ClientTimeout(total=self._timeout),
            ) as response:
                if response.status == 200:
                    # URLVoid returns XML by default, but can return JSON
                    content = await response.text()
                    return self._parse_response(content, domain)
                elif response.status == 429:
                    return {
                        "success": False,
                        "error": "URLVoid rate limit exceeded",
                        "score": None,
                    }
                else:
                    return {
                        "success": False,
                        "error": f"URLVoid API error: HTTP {response.status}",
                        "score": None,
                    }

        except asyncio.TimeoutError:
            logger.warning("URLVoid API timeout for domain: %s", domain)
            return {"success": False, "error": "Request timeout", "score": None}
        except Exception as e:
            logger.error("URLVoid API error: %s", e)
            return {"success": False, "error": str(e), "score": None}

    def _parse_response(self, content: str, domain: str) -> Dict[str, Any]:
        """Parse URLVoid API response (XML format).

        Uses defusedxml to prevent XXE (XML External Entity) attacks.
        """
        try:
            import defusedxml.ElementTree as ET

            root = ET.fromstring(content)

            # Check for error response
            error = root.find(".//error")
            if error is not None:
                return {
                    "success": False,
                    "error": error.text or "Unknown URLVoid error",
                    "score": None,
                }

            # Extract detection information
            detections = root.find(".//detections")
            engines_count = root.find(".//engines_count")

            detection_count = int(detections.text) if detections is not None and detections.text else 0
            total_engines = int(engines_count.text) if engines_count is not None and engines_count.text else 0

            if total_engines == 0:
                score = 0.5  # Neutral if no engines checked
            else:
                # Calculate score: 1.0 = safe, 0.0 = all detections
                score = 1.0 - (detection_count / total_engines)
                score = max(0.0, min(1.0, score))

            # Extract additional information
            blacklists = []
            for blacklist in root.findall(".//blacklist"):
                name = blacklist.find("name")
                if name is not None and name.text:
                    blacklists.append(name.text)

            return {
                "success": True,
                "score": score,
                "domain": domain,
                "detections": detection_count,
                "engines_count": total_engines,
                "blacklists": blacklists,
            }
        except Exception as e:
            # defusedxml raises various exceptions for malformed/malicious XML
            logger.error("Failed to parse URLVoid XML response: %s", e)
            return {"success": False, "error": str(e), "score": None}


class ThreatIntelligenceService:
    """
    Unified threat intelligence service that aggregates results from multiple sources.

    Features:
    - Checks VirusTotal and URLVoid for URL/domain reputation
    - Caches results to reduce API calls
    - Graceful degradation when services are unavailable
    - Aggregates scores into unified threat assessment
    """

    def __init__(
        self,
        virustotal_api_key: Optional[str] = None,
        urlvoid_api_key: Optional[str] = None,
        cache_ttl: int = 7200,
        virustotal_rate_limit: int = 4,
        urlvoid_rate_limit: int = 10,
    ):
        """
        Initialize threat intelligence service.

        Args:
            virustotal_api_key: VirusTotal API key (env: VIRUSTOTAL_API_KEY)
            urlvoid_api_key: URLVoid API key (env: URLVOID_API_KEY)
            cache_ttl: Cache TTL in seconds (default: 2 hours)
            virustotal_rate_limit: VirusTotal requests per minute
            urlvoid_rate_limit: URLVoid requests per minute
        """
        self._cache = ThreatIntelligenceCache(default_ttl=cache_ttl)

        # Get rate limits from environment if not specified
        vt_rate = int(os.getenv("VIRUSTOTAL_RATE_LIMIT", str(virustotal_rate_limit)))
        uv_rate = int(os.getenv("URLVOID_RATE_LIMIT", str(urlvoid_rate_limit)))

        self._virustotal = VirusTotalClient(
            api_key=virustotal_api_key,
            rate_limit=vt_rate,
        )
        self._urlvoid = URLVoidClient(
            api_key=urlvoid_api_key,
            rate_limit=uv_rate,
        )

        logger.info(
            "ThreatIntelligenceService initialized (VT: %s, UV: %s)",
            "configured" if self._virustotal.is_configured else "not configured",
            "configured" if self._urlvoid.is_configured else "not configured",
        )

    @property
    def is_any_service_configured(self) -> bool:
        """Check if at least one service is configured."""
        return self._virustotal.is_configured or self._urlvoid.is_configured

    async def check_url_reputation(self, url: str) -> ThreatScore:
        """
        Check URL reputation using all configured threat intelligence services.

        Args:
            url: URL to check

        Returns:
            ThreatScore with aggregated results
        """
        # Check cache first
        cached_result = await self._cache.get(url)
        if cached_result:
            logger.debug("Using cached threat score for URL: %s", url)
            return cached_result

        # Collect results from configured services
        results: Dict[str, Any] = {}
        scores: list[float] = []
        sources_checked = 0

        # Check VirusTotal
        if self._virustotal.is_configured:
            vt_result = await self._virustotal.check_url(url)
            results["virustotal"] = vt_result
            if vt_result.get("success") and vt_result.get("score") is not None:
                scores.append(vt_result["score"])
                sources_checked += 1

        # Check URLVoid
        if self._urlvoid.is_configured:
            uv_result = await self._urlvoid.check_domain(url)
            results["urlvoid"] = uv_result
            if uv_result.get("success") and uv_result.get("score") is not None:
                scores.append(uv_result["score"])
                sources_checked += 1

        # Calculate overall score
        if scores:
            # Use minimum score (most conservative approach)
            overall_score = min(scores)
        else:
            # No services available - return neutral score
            overall_score = 0.5

        # Determine threat level
        threat_level = self._calculate_threat_level(overall_score)

        # Build result
        threat_score = ThreatScore(
            virustotal_score=results.get("virustotal", {}).get("score"),
            urlvoid_score=results.get("urlvoid", {}).get("score"),
            overall_score=overall_score,
            threat_level=threat_level,
            details=results,
            sources_checked=sources_checked,
            cached=False,
        )

        # Cache the result
        await self._cache.set(url, threat_score)

        logger.info(
            "Threat check for %s: score=%.2f, level=%s, sources=%d",
            url, overall_score, threat_level.value, sources_checked
        )

        return threat_score

    def _calculate_threat_level(self, score: float) -> ThreatLevel:
        """Calculate threat level from score."""
        if score >= 0.9:
            return ThreatLevel.SAFE
        elif score >= 0.7:
            return ThreatLevel.LOW
        elif score >= 0.5:
            return ThreatLevel.MEDIUM
        elif score >= 0.3:
            return ThreatLevel.HIGH
        else:
            return ThreatLevel.CRITICAL

    async def get_service_status(self) -> Dict[str, Any]:
        """Get status of configured threat intelligence services."""
        return {
            "virustotal": {
                "configured": self._virustotal.is_configured,
                "remaining_requests": self._virustotal._rate_limiter.get_remaining(),
            },
            "urlvoid": {
                "configured": self._urlvoid.is_configured,
                "remaining_requests": self._urlvoid._rate_limiter.get_remaining(),
            },
        }


# Module-level singleton for easy access
_threat_intel_service: Optional[ThreatIntelligenceService] = None
_threat_intel_lock = asyncio.Lock()


async def get_threat_intelligence_service() -> ThreatIntelligenceService:
    """Get singleton threat intelligence service instance."""
    global _threat_intel_service
    async with _threat_intel_lock:
        if _threat_intel_service is None:
            _threat_intel_service = ThreatIntelligenceService()
    return _threat_intel_service


async def check_url_threat(url: str) -> ThreatScore:
    """
    Convenience function to check URL threat level.

    Args:
        url: URL to check

    Returns:
        ThreatScore with aggregated threat assessment
    """
    service = await get_threat_intelligence_service()
    return await service.check_url_reputation(url)


if __name__ == "__main__":
    """Test threat intelligence service."""

    async def test_threat_intel():
        logger.info("=== Threat Intelligence Service Test ===\n")

        service = ThreatIntelligenceService()

        # Check service status
        status = await service.get_service_status()
        logger.info("Service Status:")
        for name, info in status.items():
            configured = "✅" if info["configured"] else "❌"
            logger.info("  {name}: {configured} configured")

        if not service.is_any_service_configured:
            logger.info("\n⚠️ No threat intelligence services configured.")
            logger.info("Set VIRUSTOTAL_API_KEY and/or URLVOID_API_KEY environment variables.")
            return

        # Test URLs
        test_urls = [
            "https://google.com",
            "https://github.com",
            "http://example-malware-test.com",
        ]

        logger.info("\nTesting URLs:")
        for url in test_urls:
            logger.info("\n  Checking: {url}")
            result = await service.check_url_reputation(url)
            logger.info("    Overall Score: {result.overall_score:.2f}")
            logger.info("    Threat Level: {result.threat_level.value}")
            logger.info("    Sources Checked: {result.sources_checked}")
            logger.info("    Cached: {result.cached}")

            if result.virustotal_score is not None:
                logger.info("    VirusTotal: {result.virustotal_score:.2f}")
            if result.urlvoid_score is not None:
                logger.info("    URLVoid: {result.urlvoid_score:.2f}")

    asyncio.run(test_threat_intel())
