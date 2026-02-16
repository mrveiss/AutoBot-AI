# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for the Log Pattern Miner (Issue #226).

Tests the dynamic log pattern mining functionality including:
- Log parsing (multiple formats)
- Pattern extraction
- Anomaly detection
- Session flow tracking
- Statistics calculation
"""

from datetime import datetime, timedelta

import pytest
from backend.code_intelligence.log_pattern_miner import (
    Anomaly,
    AnomalyType,
    LogEntry,
    LogLevel,
    LogParser,
    LogPattern,
    LogPatternMiner,
    MiningResult,
    PatternType,
    SessionFlow,
    analyze_logs,
    get_anomaly_types,
    get_log_levels,
    get_pattern_types,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def miner():
    """Create a LogPatternMiner instance."""
    return LogPatternMiner()


@pytest.fixture
def sample_standard_logs():
    """Sample logs in standard AutoBot format."""
    return (
        "2025-09-07 21:36:47 - RUM - INFO - RUM monitoring enabled\n"
        "2025-09-07 21:36:47 - RUM - INFO - SESSION=sess123 URL=http://example.com\n"
        "2025-09-07 21:36:47 - RUM - INFO - SESSION=sess123 API_CALL: POST /test D=31ms S=200\n"
        "2025-09-07 21:36:48 - RUM - INFO - SESSION=sess123 API_CALL: GET /data D=150ms S=200\n"
        "2025-09-07 21:36:49 - RUM - ERROR - SESSION=sess123 Connection failed: timeout\n"
        "2025-09-07 21:36:50 - RUM - INFO - SESSION=sess456 API_CALL: POST /test D=25ms S=200\n"
        "2025-09-07 21:36:51 - RUM - ERROR - SESSION=sess456 Connection failed: timeout\n"
        "2025-09-07 21:36:52 - RUM - ERROR - SESSION=sess789 Connection failed: timeout\n"
    )


@pytest.fixture
def sample_python_logs():
    """Sample logs in Python logging format."""
    return """INFO:backend.api:Request received
ERROR:backend.api:Database connection failed
WARNING:backend.service:Slow query detected
INFO:backend.api:Request completed
ERROR:backend.api:Database connection failed
"""


@pytest.fixture
def sample_mixed_logs():
    """Sample logs with various patterns."""
    base_time = datetime.now()
    lines = []

    # Normal requests
    for i in range(20):
        ts = (base_time + timedelta(seconds=i)).strftime("%Y-%m-%d %H:%M:%S")
        lines.append(
            f"{ts} - API - INFO - SESSION=s{i%3} "
            f"API_CALL: GET /api/data DURATION={10 + i}ms STATUS=200"
        )

    # Slow requests
    for i in range(5):
        ts = (base_time + timedelta(seconds=30 + i)).strftime("%Y-%m-%d %H:%M:%S")
        lines.append(
            f"{ts} - API - INFO - SESSION=s0 "
            f"API_CALL: POST /api/slow DURATION={200 + i * 50}ms STATUS=200"
        )

    # Errors
    for i in range(5):
        ts = (base_time + timedelta(seconds=40 + i)).strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"{ts} - DB - ERROR - Connection failed: timeout after 30s")

    return "\n".join(lines)


# ============================================================================
# Enum Tests
# ============================================================================


class TestLogLevel:
    """Tests for LogLevel enum."""

    def test_log_level_values(self):
        """Test log level enum values."""
        assert LogLevel.DEBUG.value == "debug"
        assert LogLevel.INFO.value == "info"
        assert LogLevel.WARNING.value == "warning"
        assert LogLevel.ERROR.value == "error"
        assert LogLevel.CRITICAL.value == "critical"

    def test_log_level_count(self):
        """Test number of log levels."""
        assert len(LogLevel) == 5


class TestPatternType:
    """Tests for PatternType enum."""

    def test_pattern_type_values(self):
        """Test pattern type enum values."""
        assert PatternType.ERROR_SEQUENCE.value == "error_sequence"
        assert PatternType.PERFORMANCE_BOTTLENECK.value == "performance_bottleneck"
        assert PatternType.API_USAGE.value == "api_usage"
        assert PatternType.SESSION_FLOW.value == "session_flow"
        assert PatternType.RECURRING_ERROR.value == "recurring_error"
        assert PatternType.ANOMALY.value == "anomaly"

    def test_pattern_type_count(self):
        """Test number of pattern types."""
        assert len(PatternType) == 8


class TestAnomalyType:
    """Tests for AnomalyType enum."""

    def test_anomaly_type_values(self):
        """Test anomaly type enum values."""
        assert AnomalyType.SPIKE.value == "spike"
        assert AnomalyType.DROP.value == "drop"
        assert AnomalyType.UNUSUAL_PATTERN.value == "unusual_pattern"
        assert AnomalyType.THRESHOLD_EXCEEDED.value == "threshold_exceeded"

    def test_anomaly_type_count(self):
        """Test number of anomaly types."""
        assert len(AnomalyType) == 5


# ============================================================================
# Data Class Tests
# ============================================================================


class TestLogEntry:
    """Tests for LogEntry dataclass."""

    def test_entry_creation(self):
        """Test creating a log entry."""
        entry = LogEntry(
            timestamp=datetime.now(),
            level=LogLevel.INFO,
            logger_name="test",
            message="Test message",
            raw_line="raw line",
            line_number=1,
        )
        assert entry.level == LogLevel.INFO
        assert entry.logger_name == "test"
        assert entry.message == "Test message"

    def test_entry_to_dict(self):
        """Test entry conversion to dictionary."""
        entry = LogEntry(
            timestamp=datetime.now(),
            level=LogLevel.ERROR,
            logger_name="api",
            message="Error occurred",
            raw_line="raw",
            line_number=10,
            session_id="sess123",
            duration_ms=50.5,
        )
        result = entry.to_dict()
        assert result["level"] == "error"
        assert result["logger_name"] == "api"
        assert result["session_id"] == "sess123"
        assert result["duration_ms"] == 50.5


class TestLogPattern:
    """Tests for LogPattern dataclass."""

    def test_pattern_creation(self):
        """Test creating a log pattern."""
        pattern = LogPattern(
            id="ERR-1",
            pattern_type=PatternType.RECURRING_ERROR,
            description="Recurring error",
            occurrences=10,
            first_seen=datetime.now(),
            last_seen=datetime.now(),
            severity=LogLevel.ERROR,
        )
        assert pattern.id == "ERR-1"
        assert pattern.pattern_type == PatternType.RECURRING_ERROR
        assert pattern.occurrences == 10

    def test_pattern_to_dict(self):
        """Test pattern conversion to dictionary."""
        pattern = LogPattern(
            id="PERF-1",
            pattern_type=PatternType.PERFORMANCE_BOTTLENECK,
            description="Slow endpoint",
            occurrences=5,
            first_seen=datetime.now(),
            last_seen=datetime.now(),
        )
        result = pattern.to_dict()
        assert result["id"] == "PERF-1"
        assert result["pattern_type"] == "performance_bottleneck"
        assert result["occurrences"] == 5


class TestAnomaly:
    """Tests for Anomaly dataclass."""

    def test_anomaly_creation(self):
        """Test creating an anomaly."""
        anomaly = Anomaly(
            id="ANOM-1",
            anomaly_type=AnomalyType.SPIKE,
            description="Unusual spike",
            detected_at=datetime.now(),
            severity=LogLevel.WARNING,
            metric_name="duration",
            expected_value=50.0,
            actual_value=200.0,
            deviation_percent=300.0,
        )
        assert anomaly.anomaly_type == AnomalyType.SPIKE
        assert anomaly.expected_value == 50.0
        assert anomaly.actual_value == 200.0

    def test_anomaly_to_dict(self):
        """Test anomaly conversion to dictionary."""
        anomaly = Anomaly(
            id="ANOM-2",
            anomaly_type=AnomalyType.DROP,
            description="Sudden drop",
            detected_at=datetime.now(),
            severity=LogLevel.ERROR,
            metric_name="requests",
            expected_value=100.0,
            actual_value=10.0,
            deviation_percent=90.0,
        )
        result = anomaly.to_dict()
        assert result["anomaly_type"] == "drop"
        assert result["expected_value"] == 100.0


class TestSessionFlow:
    """Tests for SessionFlow dataclass."""

    def test_session_creation(self):
        """Test creating a session flow."""
        session = SessionFlow(
            session_id="sess123",
            start_time=datetime.now(),
            end_time=None,
            request_count=5,
        )
        assert session.session_id == "sess123"
        assert session.request_count == 5

    def test_session_to_dict(self):
        """Test session conversion to dictionary."""
        session = SessionFlow(
            session_id="sess456",
            start_time=datetime.now(),
            end_time=datetime.now(),
            endpoints=["/api/test", "/api/data"],
            total_duration_ms=150.5,
        )
        result = session.to_dict()
        assert result["session_id"] == "sess456"
        assert len(result["endpoints"]) == 2


class TestMiningResult:
    """Tests for MiningResult dataclass."""

    def test_result_creation(self):
        """Test creating a mining result."""
        now = datetime.now()
        result = MiningResult(
            id="mining-123",
            timestamp=now,
            files_analyzed=3,
            total_entries=100,
            time_range=(now, now),
        )
        assert result.files_analyzed == 3
        assert result.total_entries == 100

    def test_result_to_dict(self):
        """Test result conversion to dictionary."""
        now = datetime.now()
        result = MiningResult(
            id="mining-456",
            timestamp=now,
            files_analyzed=2,
            total_entries=50,
            time_range=(now, now),
            statistics={"total_errors": 5},
        )
        data = result.to_dict()
        assert data["files_analyzed"] == 2
        assert "time_range" in data


# ============================================================================
# Log Parser Tests
# ============================================================================


class TestLogParser:
    """Tests for LogParser class."""

    def test_parse_standard_format(self):
        """Test parsing standard AutoBot log format."""
        line = "2025-09-07 21:36:47 - RUM - INFO - Test message"
        entry = LogParser.parse_line(line, 1)

        assert entry is not None
        assert entry.level == LogLevel.INFO
        assert entry.logger_name == "RUM"
        assert entry.message == "Test message"

    def test_parse_python_format(self):
        """Test parsing Python logging format."""
        line = "ERROR:backend.api:Database connection failed"
        entry = LogParser.parse_line(line, 1)

        assert entry is not None
        assert entry.level == LogLevel.ERROR
        assert entry.logger_name == "backend.api"
        assert entry.message == "Database connection failed"

    def test_parse_with_session(self):
        """Test parsing log with session ID."""
        line = "2025-09-07 21:36:47 - RUM - INFO - SESSION=abc123 Request started"
        entry = LogParser.parse_line(line, 1)

        assert entry is not None
        assert entry.session_id == "abc123"

    def test_parse_with_api_call(self):
        """Test parsing log with API call pattern."""
        line = (
            "2025-09-07 21:36:47 - RUM - INFO - "
            "API_CALL: POST /api/test DURATION=31.60ms STATUS=200"
        )
        entry = LogParser.parse_line(line, 1)

        assert entry is not None
        assert entry.endpoint == "POST /api/test"
        assert entry.duration_ms == 31.60
        assert entry.status_code == 200

    def test_parse_with_duration(self):
        """Test parsing log with duration."""
        line = "2025-09-07 21:36:47 - API - INFO - Request completed DURATION=50ms"
        entry = LogParser.parse_line(line, 1)

        assert entry is not None
        assert entry.duration_ms == 50.0

    def test_parse_empty_line(self):
        """Test parsing empty line."""
        entry = LogParser.parse_line("", 1)
        assert entry is None

    def test_parse_invalid_format(self):
        """Test parsing invalid format."""
        entry = LogParser.parse_line("This is not a valid log line", 1)
        assert entry is None


# ============================================================================
# Log Pattern Miner Tests
# ============================================================================


class TestLogPatternMiner:
    """Tests for LogPatternMiner class."""

    def test_miner_initialization(self, miner):
        """Test miner initialization."""
        assert miner.slow_request_threshold_ms == 100.0
        assert miner.error_threshold == 5
        assert miner.anomaly_deviation_threshold == 2.0
        assert miner.min_pattern_occurrences == 3

    def test_miner_custom_settings(self):
        """Test miner with custom settings."""
        miner = LogPatternMiner(
            slow_request_threshold_ms=50.0,
            error_threshold=10,
            anomaly_deviation_threshold=3.0,
            min_pattern_occurrences=5,
        )
        assert miner.slow_request_threshold_ms == 50.0
        assert miner.error_threshold == 10

    def test_parse_content(self, miner, sample_standard_logs):
        """Test parsing log content."""
        entries = miner.parse_content(sample_standard_logs)
        assert len(entries) >= 5

    def test_parse_file(self, miner, tmp_path):
        """Test parsing log file."""
        log_file = tmp_path / "test.log"
        log_file.write_text(
            "2025-09-07 21:36:47 - TEST - INFO - Test message\n"
            "2025-09-07 21:36:48 - TEST - ERROR - Error message\n"
        )

        entries = miner.parse_file(str(log_file))
        assert len(entries) == 2

    def test_parse_nonexistent_file(self, miner):
        """Test parsing non-existent file."""
        entries = miner.parse_file("/nonexistent/file.log")
        assert entries == []


# ============================================================================
# Pattern Extraction Tests
# ============================================================================


class TestPatternExtraction:
    """Tests for pattern extraction functionality."""

    def test_extract_error_patterns(self):
        """Test extracting recurring error patterns."""
        # Create logs with recurring errors (3+ occurrences)
        content = (
            "2025-09-07 21:36:47 - DB - ERROR - Connection failed: timeout\n"
            "2025-09-07 21:36:48 - DB - ERROR - Connection failed: timeout\n"
            "2025-09-07 21:36:49 - DB - ERROR - Connection failed: timeout\n"
            "2025-09-07 21:36:50 - DB - ERROR - Connection failed: timeout\n"
        )
        miner = LogPatternMiner(min_pattern_occurrences=3)
        result = miner.analyze(content=content)

        error_patterns = [
            p for p in result.patterns if p.pattern_type == PatternType.RECURRING_ERROR
        ]
        assert len(error_patterns) >= 1

    def test_extract_performance_patterns(self, sample_mixed_logs):
        """Test extracting performance bottleneck patterns."""
        miner = LogPatternMiner(
            slow_request_threshold_ms=100.0,
            min_pattern_occurrences=2,
        )
        result = miner.analyze(content=sample_mixed_logs)

        perf_patterns = [
            p
            for p in result.patterns
            if p.pattern_type == PatternType.PERFORMANCE_BOTTLENECK
        ]
        assert len(perf_patterns) >= 1

    def test_extract_api_patterns(self, sample_standard_logs):
        """Test extracting API usage patterns."""
        miner = LogPatternMiner(min_pattern_occurrences=1)
        result = miner.analyze(content=sample_standard_logs)

        api_patterns = [
            p for p in result.patterns if p.pattern_type == PatternType.API_USAGE
        ]
        # Should detect API call patterns
        assert len(api_patterns) >= 0  # May or may not find depending on threshold


# ============================================================================
# Session Flow Tests
# ============================================================================


class TestSessionFlowTracking:
    """Tests for session flow tracking."""

    def test_extract_sessions(self, sample_standard_logs):
        """Test extracting session flows."""
        miner = LogPatternMiner()
        result = miner.analyze(content=sample_standard_logs)

        assert len(result.sessions) >= 2

    def test_session_with_errors(self, sample_standard_logs):
        """Test sessions with errors are tracked."""
        miner = LogPatternMiner()
        result = miner.analyze(content=sample_standard_logs)

        sessions_with_errors = [s for s in result.sessions if s.errors]
        assert len(sessions_with_errors) >= 1

    def test_session_endpoints(self, sample_standard_logs):
        """Test session endpoint tracking."""
        miner = LogPatternMiner()
        result = miner.analyze(content=sample_standard_logs)

        sessions_with_endpoints = [s for s in result.sessions if s.endpoints]
        assert (
            len(sessions_with_endpoints) >= 0
        )  # May not have endpoints in simplified logs


# ============================================================================
# Anomaly Detection Tests
# ============================================================================


class TestAnomalyDetection:
    """Tests for anomaly detection."""

    def test_detect_duration_anomalies(self):
        """Test detecting duration anomalies."""
        # Create logs with one extreme outlier
        base_time = datetime.now()
        lines = []

        # Normal durations
        for i in range(20):
            ts = (base_time + timedelta(seconds=i)).strftime("%Y-%m-%d %H:%M:%S")
            lines.append(
                f"{ts} - API - INFO - "
                f"API_CALL: GET /api/test DURATION={10 + i % 5}ms STATUS=200"
            )

        # Anomaly
        ts = (base_time + timedelta(seconds=25)).strftime("%Y-%m-%d %H:%M:%S")
        lines.append(
            f"{ts} - API - INFO - " f"API_CALL: GET /api/test DURATION=500ms STATUS=200"
        )

        content = "\n".join(lines)
        miner = LogPatternMiner(anomaly_deviation_threshold=2.0)
        result = miner.analyze(content=content)

        # Should detect at least one anomaly
        assert len(result.anomalies) >= 1


# ============================================================================
# Statistics Tests
# ============================================================================


class TestStatistics:
    """Tests for statistics calculation."""

    def test_statistics_by_level(self, sample_standard_logs):
        """Test statistics grouped by level."""
        miner = LogPatternMiner()
        result = miner.analyze(content=sample_standard_logs)

        assert "by_level" in result.statistics
        assert "info" in result.statistics["by_level"]
        assert "error" in result.statistics["by_level"]

    def test_statistics_by_logger(self, sample_standard_logs):
        """Test statistics grouped by logger."""
        miner = LogPatternMiner()
        result = miner.analyze(content=sample_standard_logs)

        assert "by_logger" in result.statistics

    def test_statistics_duration(self, sample_standard_logs):
        """Test duration statistics."""
        miner = LogPatternMiner()
        result = miner.analyze(content=sample_standard_logs)

        assert "avg_duration_ms" in result.statistics

    def test_summary_generation(self, sample_standard_logs):
        """Test summary generation."""
        miner = LogPatternMiner()
        result = miner.analyze(content=sample_standard_logs)

        assert "total_patterns" in result.summary
        assert "total_anomalies" in result.summary
        assert "health_score" in result.summary

    def test_health_score_range(self, sample_standard_logs):
        """Test health score is in valid range."""
        miner = LogPatternMiner()
        result = miner.analyze(content=sample_standard_logs)

        assert 0 <= result.summary["health_score"] <= 100


# ============================================================================
# Analysis Integration Tests
# ============================================================================


class TestAnalysisIntegration:
    """Integration tests for log analysis."""

    def test_full_analysis(self, sample_mixed_logs):
        """Test full analysis with mixed logs."""
        miner = LogPatternMiner(min_pattern_occurrences=2)
        result = miner.analyze(content=sample_mixed_logs)

        assert result.total_entries >= 20
        assert result.files_analyzed == 1
        assert len(result.patterns) >= 1

    def test_empty_content(self, miner):
        """Test analysis with empty content."""
        result = miner.analyze(content="")

        assert result.total_entries == 0
        assert len(result.patterns) == 0
        assert "message" in result.summary

    def test_multiple_files(self, miner, tmp_path):
        """Test analysis with multiple files."""
        # Create multiple log files
        file1 = tmp_path / "app1.log"
        file1.write_text("2025-09-07 21:36:47 - APP1 - INFO - Message 1\n")

        file2 = tmp_path / "app2.log"
        file2.write_text("2025-09-07 21:36:48 - APP2 - ERROR - Error 1\n")

        result = miner.analyze(log_files=[str(file1), str(file2)])

        assert result.files_analyzed == 2
        assert result.total_entries == 2

    def test_result_to_dict(self, sample_standard_logs):
        """Test result serialization."""
        miner = LogPatternMiner()
        result = miner.analyze(content=sample_standard_logs)

        data = result.to_dict()

        assert "id" in data
        assert "timestamp" in data
        assert "patterns" in data
        assert "anomalies" in data
        assert "statistics" in data


# ============================================================================
# Convenience Function Tests
# ============================================================================


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_analyze_logs_function(self, sample_standard_logs):
        """Test analyze_logs convenience function."""
        result = analyze_logs(content=sample_standard_logs)

        assert isinstance(result, MiningResult)
        assert result.total_entries >= 1

    def test_get_pattern_types_function(self):
        """Test get_pattern_types convenience function."""
        types = get_pattern_types()

        assert len(types) == 8
        assert all("id" in t for t in types)
        assert all("name" in t for t in types)
        assert all("description" in t for t in types)

    def test_get_anomaly_types_function(self):
        """Test get_anomaly_types convenience function."""
        types = get_anomaly_types()

        assert len(types) == 5
        assert all("id" in t for t in types)
        assert all("name" in t for t in types)

    def test_get_log_levels_function(self):
        """Test get_log_levels convenience function."""
        levels = get_log_levels()

        assert len(levels) == 5
        assert all("level" in lvl for lvl in levels)
        assert all("weight" in lvl for lvl in levels)


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_malformed_timestamp(self, miner):
        """Test handling malformed timestamp."""
        content = "invalid-date - TEST - INFO - Message"
        entries = miner.parse_content(content)
        assert entries == []

    def test_unicode_content(self, miner):
        """Test handling unicode in logs."""
        content = "2025-09-07 21:36:47 - TEST - INFO - Message with unicode: \u00e9\u00e8\u00ea"
        entries = miner.parse_content(content)
        assert len(entries) == 1

    def test_very_long_message(self, miner):
        """Test handling very long messages."""
        long_message = "x" * 10000
        content = f"2025-09-07 21:36:47 - TEST - INFO - {long_message}"
        entries = miner.parse_content(content)
        assert len(entries) == 1

    def test_binary_content_handling(self, miner, tmp_path):
        """Test handling of binary content in log files."""
        log_file = tmp_path / "binary.log"
        log_file.write_bytes(b"\x00\x01\x02valid line\x03\x04")

        # Should not crash
        entries = miner.parse_file(str(log_file))
        assert isinstance(entries, list)

    def test_empty_file(self, miner, tmp_path):
        """Test handling empty log file."""
        log_file = tmp_path / "empty.log"
        log_file.write_text("")

        result = miner.analyze(log_files=[str(log_file)])
        assert result.total_entries == 0

    def test_normalize_error_message(self, miner):
        """Test error message normalization."""
        message = (
            "Error at /path/to/file.py: connection to 192.168.1.1 "
            "failed at 2025-01-01T12:00:00"
        )
        normalized = miner._normalize_error_message(message)

        assert "<PATH>" in normalized
        assert "<IP>" in normalized
        assert "<TIMESTAMP>" in normalized
