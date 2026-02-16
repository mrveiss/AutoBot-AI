# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Threat Intelligence module.

Tests cover:
- VirusTotal API client with mocked responses
- URLVoid API client with mocked responses
- Rate limiting functionality
- Caching mechanism
- ThreatIntelligenceService aggregation
- Graceful degradation when APIs unavailable
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.security.threat_intelligence import (
    RateLimiter,
    ThreatIntelligenceCache,
    ThreatIntelligenceService,
    ThreatLevel,
    ThreatScore,
    URLVoidClient,
    VirusTotalClient,
)


class TestThreatScore:
    """Tests for ThreatScore dataclass"""

    def test_default_values(self):
        """Test default ThreatScore initialization."""
        score = ThreatScore()
        assert score.virustotal_score is None
        assert score.urlvoid_score is None
        assert score.overall_score == 0.5
        assert score.threat_level == ThreatLevel.UNKNOWN
        assert score.sources_checked == 0
        assert score.cached is False

    def test_custom_values(self):
        """Test ThreatScore with custom values."""
        score = ThreatScore(
            virustotal_score=0.9,
            urlvoid_score=0.85,
            overall_score=0.85,
            threat_level=ThreatLevel.LOW,
            sources_checked=2,
        )
        assert score.virustotal_score == 0.9
        assert score.urlvoid_score == 0.85
        assert score.overall_score == 0.85
        assert score.threat_level == ThreatLevel.LOW
        assert score.sources_checked == 2


class TestThreatLevel:
    """Tests for ThreatLevel enum"""

    def test_threat_levels(self):
        """Test all threat level values."""
        assert ThreatLevel.SAFE.value == "safe"
        assert ThreatLevel.LOW.value == "low"
        assert ThreatLevel.MEDIUM.value == "medium"
        assert ThreatLevel.HIGH.value == "high"
        assert ThreatLevel.CRITICAL.value == "critical"
        assert ThreatLevel.UNKNOWN.value == "unknown"


class TestRateLimiter:
    """Tests for RateLimiter class"""

    @pytest.mark.asyncio
    async def test_acquire_within_limit(self):
        """Test acquiring slots within rate limit."""
        limiter = RateLimiter(requests_per_minute=10)

        # Should allow 10 requests
        for _ in range(10):
            result = await limiter.acquire()
            assert result is True

    @pytest.mark.asyncio
    async def test_get_remaining(self):
        """Test getting remaining requests."""
        limiter = RateLimiter(requests_per_minute=5)

        assert limiter.get_remaining() == 5

        await limiter.acquire()
        assert limiter.get_remaining() == 4

        await limiter.acquire()
        assert limiter.get_remaining() == 3


class TestThreatIntelligenceCache:
    """Tests for ThreatIntelligenceCache class"""

    @pytest.mark.asyncio
    async def test_cache_set_and_get(self):
        """Test basic cache set and get operations."""
        cache = ThreatIntelligenceCache(default_ttl=3600)

        test_score = ThreatScore(
            overall_score=0.9,
            threat_level=ThreatLevel.SAFE,
        )

        await cache.set("https://example.com", test_score)
        result = await cache.get("https://example.com")

        assert result is not None
        assert result.overall_score == 0.9
        assert result.cached is True  # Should be marked as cached

    @pytest.mark.asyncio
    async def test_cache_miss(self):
        """Test cache miss for non-existent URL."""
        cache = ThreatIntelligenceCache()

        result = await cache.get("https://nonexistent.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_expiration(self):
        """Test cache entry expiration."""
        cache = ThreatIntelligenceCache(default_ttl=1)  # 1 second TTL

        test_score = ThreatScore(overall_score=0.9)
        await cache.set("https://example.com", test_score)

        # Should be in cache
        result = await cache.get("https://example.com")
        assert result is not None

        # Wait for expiration
        await asyncio.sleep(1.1)

        # Should be expired
        result = await cache.get("https://example.com")
        assert result is None

    @pytest.mark.asyncio
    async def test_clear_expired(self):
        """Test clearing expired entries."""
        cache = ThreatIntelligenceCache(default_ttl=1)

        await cache.set("https://example1.com", ThreatScore())
        await cache.set("https://example2.com", ThreatScore())

        # Wait for expiration
        await asyncio.sleep(1.1)

        # Add fresh entry
        await cache.set("https://example3.com", ThreatScore(), ttl=3600)

        await cache.clear_expired()

        # Only example3.com should remain
        assert await cache.get("https://example1.com") is None
        assert await cache.get("https://example2.com") is None
        assert await cache.get("https://example3.com") is not None


class TestVirusTotalClient:
    """Tests for VirusTotal API client"""

    def test_is_configured_with_key(self):
        """Test is_configured returns True when API key is set."""
        client = VirusTotalClient(api_key="test-api-key")
        assert client.is_configured is True

    def test_is_configured_without_key(self):
        """Test is_configured returns False without API key."""
        with patch.dict("os.environ", {"VIRUSTOTAL_API_KEY": ""}):
            client = VirusTotalClient(api_key="")
            assert client.is_configured is False

    @pytest.mark.asyncio
    async def test_check_url_not_configured(self):
        """Test check_url returns error when not configured."""
        client = VirusTotalClient(api_key="")

        result = await client.check_url("https://example.com")

        assert result["success"] is False
        assert "not configured" in result["error"]
        assert result["score"] is None

    def test_get_url_id(self):
        """Test URL ID generation for VirusTotal."""
        client = VirusTotalClient(api_key="test")
        url_id = client._get_url_id("https://example.com")

        # URL ID should be base64 encoded without padding
        assert isinstance(url_id, str)
        assert "=" not in url_id  # No padding

    @pytest.mark.asyncio
    async def test_check_url_success(self):
        """Test successful URL check with mocked response."""
        client = VirusTotalClient(api_key="test-key")

        mock_response = {
            "data": {
                "attributes": {
                    "last_analysis_stats": {
                        "harmless": 70,
                        "malicious": 0,
                        "suspicious": 2,
                        "undetected": 8,
                    },
                    "last_analysis_date": 1700000000,
                    "categories": {"category1": "technology"},
                }
            }
        }

        mock_http_response = AsyncMock()
        mock_http_response.status = 200
        mock_http_response.json = AsyncMock(return_value=mock_response)
        mock_http_response.__aenter__ = AsyncMock(return_value=mock_http_response)
        mock_http_response.__aexit__ = AsyncMock()

        mock_http_client = MagicMock()
        mock_http_client.get = AsyncMock(return_value=mock_http_response)

        with patch.object(client, "_http_client", mock_http_client):
            result = await client.check_url("https://example.com")

        assert result["success"] is True
        assert result["score"] is not None
        assert 0.0 <= result["score"] <= 1.0
        assert result["malicious_count"] == 0
        assert result["suspicious_count"] == 2

    @pytest.mark.asyncio
    async def test_check_url_rate_limited(self):
        """Test rate limit response handling."""
        client = VirusTotalClient(api_key="test-key")

        mock_http_response = AsyncMock()
        mock_http_response.status = 429
        mock_http_response.__aenter__ = AsyncMock(return_value=mock_http_response)
        mock_http_response.__aexit__ = AsyncMock()

        mock_http_client = MagicMock()
        mock_http_client.get = AsyncMock(return_value=mock_http_response)

        with patch.object(client, "_http_client", mock_http_client):
            result = await client.check_url("https://example.com")

        assert result["success"] is False
        assert "rate limit" in result["error"].lower()


class TestURLVoidClient:
    """Tests for URLVoid API client"""

    def test_is_configured_with_key(self):
        """Test is_configured returns True when API key is set."""
        client = URLVoidClient(api_key="test-api-key")
        assert client.is_configured is True

    def test_is_configured_without_key(self):
        """Test is_configured returns False without API key."""
        with patch.dict("os.environ", {"URLVOID_API_KEY": ""}):
            client = URLVoidClient(api_key="")
            assert client.is_configured is False

    @pytest.mark.asyncio
    async def test_check_domain_not_configured(self):
        """Test check_domain returns error when not configured."""
        client = URLVoidClient(api_key="")

        result = await client.check_domain("https://example.com")

        assert result["success"] is False
        assert "not configured" in result["error"]
        assert result["score"] is None

    def test_parse_xml_response_success(self):
        """Test parsing successful URLVoid XML response using defusedxml."""
        client = URLVoidClient(api_key="test")

        xml_response = """<?xml version="1.0" encoding="UTF-8"?>
        <response>
            <details>
                <host>example.com</host>
            </details>
            <detections>0</detections>
            <engines_count>40</engines_count>
            <blacklists>
            </blacklists>
        </response>
        """

        result = client._parse_response(xml_response, "example.com")

        assert result["success"] is True
        assert result["score"] == 1.0  # No detections
        assert result["detections"] == 0
        assert result["engines_count"] == 40

    def test_parse_xml_response_with_detections(self):
        """Test parsing URLVoid response with detections."""
        client = URLVoidClient(api_key="test")

        xml_response = """<?xml version="1.0" encoding="UTF-8"?>
        <response>
            <details>
                <host>malicious.com</host>
            </details>
            <detections>5</detections>
            <engines_count>40</engines_count>
            <blacklists>
                <blacklist><name>SpamHaus</name></blacklist>
                <blacklist><name>MalwarePatrol</name></blacklist>
            </blacklists>
        </response>
        """

        result = client._parse_response(xml_response, "malicious.com")

        assert result["success"] is True
        assert result["score"] == 0.875  # (40-5)/40
        assert result["detections"] == 5
        assert len(result["blacklists"]) == 2

    def test_xxe_attack_protection(self):
        """Test that XXE attacks are blocked by defusedxml."""
        client = URLVoidClient(api_key="test")

        # XXE attack payload attempting to read /etc/passwd
        xxe_payload = """<?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE response [
            <!ENTITY xxe SYSTEM "file:///etc/passwd">
        ]>
        <response>
            <details>
                <host>&xxe;</host>
            </details>
            <detections>0</detections>
            <engines_count>40</engines_count>
        </response>
        """

        result = client._parse_response(xxe_payload, "example.com")

        # defusedxml should reject this and return an error
        assert result["success"] is False
        assert result["score"] is None


class TestThreatIntelligenceService:
    """Tests for ThreatIntelligenceService class"""

    def test_init_default(self):
        """Test default initialization."""
        with patch.dict(
            "os.environ",
            {
                "VIRUSTOTAL_API_KEY": "",
                "URLVOID_API_KEY": "",
            },
        ):
            service = ThreatIntelligenceService()
            assert service.is_any_service_configured is False

    def test_init_with_api_keys(self):
        """Test initialization with API keys."""
        service = ThreatIntelligenceService(
            virustotal_api_key="vt-key",
            urlvoid_api_key="uv-key",
        )
        assert service.is_any_service_configured is True

    def test_calculate_threat_level(self):
        """Test threat level calculation from score."""
        service = ThreatIntelligenceService()

        assert service._calculate_threat_level(0.95) == ThreatLevel.SAFE
        assert service._calculate_threat_level(0.80) == ThreatLevel.LOW
        assert service._calculate_threat_level(0.60) == ThreatLevel.MEDIUM
        assert service._calculate_threat_level(0.40) == ThreatLevel.HIGH
        assert service._calculate_threat_level(0.20) == ThreatLevel.CRITICAL

    @pytest.mark.asyncio
    async def test_check_url_no_services(self):
        """Test URL check when no services configured."""
        with patch.dict(
            "os.environ",
            {
                "VIRUSTOTAL_API_KEY": "",
                "URLVOID_API_KEY": "",
            },
        ):
            service = ThreatIntelligenceService()
            result = await service.check_url_reputation("https://example.com")

            assert result.overall_score == 0.5  # Neutral
            assert result.sources_checked == 0

    @pytest.mark.asyncio
    async def test_check_url_cached(self):
        """Test URL check returns cached result."""
        service = ThreatIntelligenceService()

        # Pre-populate cache
        cached_score = ThreatScore(
            overall_score=0.9,
            threat_level=ThreatLevel.SAFE,
            sources_checked=2,
        )
        await service._cache.set("https://example.com", cached_score)

        result = await service.check_url_reputation("https://example.com")

        assert result.overall_score == 0.9
        assert result.cached is True

    @pytest.mark.asyncio
    async def test_get_service_status(self):
        """Test getting service status."""
        service = ThreatIntelligenceService(
            virustotal_api_key="vt-key",
            urlvoid_api_key="",
        )

        status = await service.get_service_status()

        assert "virustotal" in status
        assert "urlvoid" in status
        assert status["virustotal"]["configured"] is True
        assert status["urlvoid"]["configured"] is False

    @pytest.mark.asyncio
    async def test_check_url_aggregation(self):
        """Test URL check aggregates results from multiple sources."""
        service = ThreatIntelligenceService(
            virustotal_api_key="vt-key",
            urlvoid_api_key="uv-key",
        )

        # Mock VirusTotal response
        vt_result = {"success": True, "score": 0.9}
        service._virustotal.check_url = AsyncMock(return_value=vt_result)

        # Mock URLVoid response
        uv_result = {"success": True, "score": 0.8}
        service._urlvoid.check_domain = AsyncMock(return_value=uv_result)

        result = await service.check_url_reputation("https://example.com")

        # Should use minimum score (most conservative)
        assert result.overall_score == 0.8
        assert result.virustotal_score == 0.9
        assert result.urlvoid_score == 0.8
        assert result.sources_checked == 2


class TestGracefulDegradation:
    """Tests for graceful degradation behavior"""

    @pytest.mark.asyncio
    async def test_virustotal_timeout_fallback(self):
        """Test handling of VirusTotal timeout."""
        service = ThreatIntelligenceService(
            virustotal_api_key="vt-key",
            urlvoid_api_key="",
        )

        # Mock timeout
        service._virustotal.check_url = AsyncMock(
            return_value={"success": False, "error": "Request timeout", "score": None}
        )

        result = await service.check_url_reputation("https://example.com")

        # Should return neutral score on failure
        assert result.overall_score == 0.5
        assert result.sources_checked == 0

    @pytest.mark.asyncio
    async def test_partial_service_success(self):
        """Test handling when only one service succeeds."""
        service = ThreatIntelligenceService(
            virustotal_api_key="vt-key",
            urlvoid_api_key="uv-key",
        )

        # VT succeeds
        service._virustotal.check_url = AsyncMock(
            return_value={"success": True, "score": 0.85}
        )

        # URLVoid fails
        service._urlvoid.check_domain = AsyncMock(
            return_value={"success": False, "error": "API error", "score": None}
        )

        result = await service.check_url_reputation("https://example.com")

        assert result.overall_score == 0.85
        assert result.virustotal_score == 0.85
        assert result.urlvoid_score is None
        assert result.sources_checked == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
