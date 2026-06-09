# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
OSINT Engine Unit Tests

Issue #1949: Covers source contract, sweep_all partial failure, correlation
rules, timeout enforcement, and Redis caching path.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.autoresearch.osint_engine import (
    CorrelatedSignal,
    CorrelationRule,
    FREDSource,
    GDELTSource,
    NASAFIRMSSource,
    NOAASource,
    OSINTEngine,
    OSINTSource,
    SourceResult,
    _extract_text,
    _infer_domain,
    build_default_engine,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _OKSource(OSINTSource):
    """Test source that always succeeds."""

    def __init__(self, name: str, data: Any = "ok") -> None:
        self._name = name
        self._data = data

    @property
    def name(self) -> str:
        return self._name

    async def sweep(self, client) -> SourceResult:
        return SourceResult(source_name=self._name, data=self._data)


class _FailSource(OSINTSource):
    """Test source that always raises."""

    @property
    def name(self) -> str:
        return "fail_source"

    async def sweep(self, client) -> SourceResult:
        raise RuntimeError("intentional failure")


class _HangSource(OSINTSource):
    """Test source that sleeps forever (for timeout testing)."""

    @property
    def name(self) -> str:
        return "hang_source"

    async def sweep(self, client) -> SourceResult:
        await asyncio.sleep(999)
        return SourceResult(source_name=self.name, data="never")


# ---------------------------------------------------------------------------
# SourceResult tests
# ---------------------------------------------------------------------------


class TestSourceResult:
    def test_success_defaults(self):
        r = SourceResult(source_name="test", data={"k": "v"})
        assert r.success
        assert r.error is None
        assert r.source_name == "test"

    def test_failure_constructor(self):
        r = SourceResult.failure("src", "boom", latency=1.5)
        assert not r.success
        assert r.error == "boom"
        assert r.latency_seconds == 1.5
        assert r.data is None

    def test_to_dict_roundtrip(self):
        r = SourceResult(source_name="x", data=[1, 2, 3], latency_seconds=0.4)
        d = r.to_dict()
        assert d["source_name"] == "x"
        assert d["data"] == [1, 2, 3]
        assert d["success"] is True
        assert d["latency_seconds"] == 0.4


# ---------------------------------------------------------------------------
# CorrelationRule tests
# ---------------------------------------------------------------------------


class TestCorrelationRule:
    def _make_results(self, sources: list[tuple[str, str]]) -> list[SourceResult]:
        """Build SourceResults with (source_name, text_data) tuples."""
        return [SourceResult(source_name=n, data=t) for n, t in sources]

    def test_rule_fires_when_threshold_met(self):
        rule = CorrelationRule(
            domains=["environment", "geopolitics"],
            keywords=["wildfire"],
            threshold=2,
            description="Test rule",
        )
        results = self._make_results(
            [
                ("nasa_firms_fire", "Major wildfire detected in western region"),
                ("gdelt_events", "Coverage of wildfire across multiple countries"),
            ]
        )
        signal = rule.evaluate(results)
        assert signal is not None
        assert len(signal.matching_sources) == 2
        assert signal.confidence == 1.0

    def test_rule_does_not_fire_below_threshold(self):
        rule = CorrelationRule(
            domains=["environment", "geopolitics"],
            keywords=["wildfire"],
            threshold=2,
            description="Test rule",
        )
        results = self._make_results([("nasa_firms_fire", "Major wildfire detected")])
        signal = rule.evaluate(results)
        assert signal is None

    def test_rule_ignores_failed_results(self):
        rule = CorrelationRule(
            domains=["environment"],
            keywords=["fire"],
            threshold=1,
            description="Test rule",
        )
        failed = SourceResult.failure("nasa_firms_fire", "timeout")
        signal = rule.evaluate([failed])
        assert signal is None

    def test_rule_partial_confidence(self):
        rule = CorrelationRule(
            domains=["environment", "geopolitics", "economics"],
            keywords=["storm"],
            threshold=2,
            description="Multi-domain storm rule",
        )
        results = self._make_results(
            [
                ("noaa_weather_alerts", "severe storm warning"),
                ("gdelt_events", "storm coverage across nations"),
            ]
        )
        signal = rule.evaluate(results)
        assert signal is not None
        # 2 of 3 domains matched → confidence = 2/3
        assert abs(signal.confidence - 2 / 3) < 0.01

    def test_correlated_signal_to_dict(self):
        sig = CorrelatedSignal(
            description="desc",
            matching_sources=["a", "b"],
            confidence=0.75,
            domains=["env", "geo"],
            raw_excerpt="excerpt",
        )
        d = sig.to_dict()
        assert d["confidence"] == 0.75
        assert d["matching_sources"] == ["a", "b"]


# ---------------------------------------------------------------------------
# OSINTEngine tests
# ---------------------------------------------------------------------------


class TestOSINTEngine:
    def test_register_source(self):
        engine = OSINTEngine()
        engine.register_source(_OKSource("src_a"))
        assert "src_a" in engine._sources

    def test_register_duplicate_replaces(self, caplog):
        import logging

        engine = OSINTEngine()
        engine.register_source(_OKSource("dup"))
        with caplog.at_level(logging.WARNING):
            engine.register_source(_OKSource("dup"))
        assert "replacing" in caplog.text

    def test_get_source_status_empty(self):
        engine = OSINTEngine()
        assert engine.get_source_status() == {}

    def test_get_source_status_populated(self):
        engine = OSINTEngine()
        engine.register_source(_OKSource("s1"))
        status = engine.get_source_status()
        assert "s1" in status
        assert status["s1"]["registered"] is True
        assert status["s1"]["last_sweep_at"] is None

    @pytest.mark.asyncio
    async def test_sweep_all_empty(self):
        engine = OSINTEngine()
        results = await engine.sweep_all()
        assert results == []

    @pytest.mark.asyncio
    async def test_sweep_all_success(self):
        engine = OSINTEngine()
        engine.register_source(_OKSource("s1", data={"val": 1}))
        engine.register_source(_OKSource("s2", data={"val": 2}))

        with patch.object(engine, "_cache_results", new_callable=AsyncMock):
            results = await engine.sweep_all()

        assert len(results) == 2
        assert all(r.success for r in results)
        names = {r.source_name for r in results}
        assert names == {"s1", "s2"}

    @pytest.mark.asyncio
    async def test_sweep_all_partial_failure(self):
        engine = OSINTEngine()
        engine.register_source(_OKSource("good"))
        engine.register_source(_FailSource())

        with patch.object(engine, "_cache_results", new_callable=AsyncMock):
            results = await engine.sweep_all()

        assert len(results) == 2
        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]
        assert len(successes) == 1
        assert len(failures) == 1
        assert failures[0].source_name == "fail_source"

    @pytest.mark.asyncio
    async def test_sweep_all_timeout_enforcement(self):
        engine = OSINTEngine()
        engine.register_source(_HangSource())

        with patch.object(engine, "_cache_results", new_callable=AsyncMock):
            results = await engine.sweep_all(timeout_per_source=0.05)

        assert len(results) == 1
        assert not results[0].success
        assert "timed out" in results[0].error

    @pytest.mark.asyncio
    async def test_sweep_updates_last_sweep(self):
        engine = OSINTEngine()
        engine.register_source(_OKSource("s"))

        with patch.object(engine, "_cache_results", new_callable=AsyncMock):
            await engine.sweep_all()

        assert engine._last_sweep.get("s") is not None

    def test_correlate_no_rules(self):
        engine = OSINTEngine()
        results = [SourceResult(source_name="x", data="fire wildfire")]
        signals = engine.correlate(results)
        assert signals == []

    def test_correlate_fires(self):
        engine = OSINTEngine()
        engine.register_rule(
            CorrelationRule(
                domains=["environment", "geopolitics"],
                keywords=["wildfire"],
                threshold=2,
                description="Test",
            )
        )
        results = [
            SourceResult(source_name="nasa_firms_fire", data="wildfire detected"),
            SourceResult(source_name="gdelt_events", data="wildfire coverage"),
        ]
        signals = engine.correlate(results)
        assert len(signals) == 1
        assert signals[0].description == "Test"


# ---------------------------------------------------------------------------
# Built-in source contract tests (mocked HTTP)
# ---------------------------------------------------------------------------


class TestSourceContracts:
    """Verify each built-in source parses a mocked HTTP response correctly."""

    def _mock_response(self, text: str = "", status: int = 200) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status
        resp.text = text
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={})
        return resp

    @pytest.mark.asyncio
    async def test_fred_source_success(self):
        csv_text = "DATE,A191RL1Q225SBEA\n2023-01-01,2.1\n2023-04-01,2.4\n2023-07-01,1.9\n2023-10-01,3.1"
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=self._mock_response(csv_text))
        result = await FREDSource().sweep(mock_client)
        assert result.success
        assert isinstance(result.data, list)
        assert len(result.data) <= 4

    @pytest.mark.asyncio
    async def test_fred_source_failure(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("network error"))
        result = await FREDSource().sweep(mock_client)
        assert not result.success
        assert "network error" in result.error

    @pytest.mark.asyncio
    async def test_gdelt_source_success(self):
        txt = (
            "12345 abc123 https://data.gdeltproject.org/gdeltv2/20240101000000.gkg.csv.zip\n"
            "67890 def456 https://data.gdeltproject.org/gdeltv2/20240101000000.export.CSV.zip"
        )
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=self._mock_response(txt))
        result = await GDELTSource().sweep(mock_client)
        assert result.success
        assert result.data["record_count"] == 2

    @pytest.mark.asyncio
    async def test_nasa_firms_success(self):
        csv = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite\n"
        csv += "\n".join(f"34.{i},-118.{i},312.1,0.4,0.4,2024-01-01,0104,N" for i in range(5))
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=self._mock_response(csv))
        result = await NASAFIRMSSource().sweep(mock_client)
        assert result.success
        assert result.data["active_fire_detections"] == 5

    @pytest.mark.asyncio
    async def test_noaa_source_success(self):
        payload = {
            "features": [
                {
                    "properties": {
                        "event": "Tornado Warning",
                        "areaDesc": "Central Kansas",
                        "severity": "Extreme",
                    }
                }
            ]
        }
        mock_resp = self._mock_response()
        mock_resp.json = MagicMock(return_value=payload)
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        result = await NOAASource().sweep(mock_client)
        assert result.success
        assert result.data["total_alerts"] == 1
        assert result.data["alerts"][0]["event"] == "Tornado Warning"

    @pytest.mark.asyncio
    async def test_noaa_source_failure(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("timeout"))
        result = await NOAASource().sweep(mock_client)
        assert not result.success
        assert "timeout" in result.error


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_infer_domain_known(self):
        assert _infer_domain("fred_gdp") == "economics"
        assert _infer_domain("gdelt_events") == "geopolitics"
        assert _infer_domain("nasa_firms_fire") == "environment"
        assert _infer_domain("noaa_weather_alerts") == "environment"

    def test_infer_domain_unknown(self):
        assert _infer_domain("custom_source") == "custom_source"

    def test_extract_text_string(self):
        assert _extract_text("hello world") == "hello world"

    def test_extract_text_dict(self):
        text = _extract_text({"a": "foo", "b": "bar"})
        assert "foo" in text
        assert "bar" in text

    def test_extract_text_list(self):
        text = _extract_text(["alpha", "beta"])
        assert "alpha" in text
        assert "beta" in text

    def test_extract_text_fallback(self):
        assert _extract_text(42) == "42"


# ---------------------------------------------------------------------------
# build_default_engine factory test
# ---------------------------------------------------------------------------


class TestBuildDefaultEngine:
    def test_all_sources_registered(self):
        engine = build_default_engine()
        assert "fred_gdp" in engine._sources
        assert "gdelt_events" in engine._sources
        assert "nasa_firms_fire" in engine._sources
        assert "noaa_weather_alerts" in engine._sources

    def test_rules_registered(self):
        engine = build_default_engine()
        assert len(engine._rules) >= 2
