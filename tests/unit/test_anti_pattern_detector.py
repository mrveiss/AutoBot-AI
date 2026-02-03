# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Anti-Pattern Detection System

Tests the anti-pattern detection functionality including:
- God class detection
- Feature envy detection
- Circular dependency detection
- Long method detection
- Long parameter list detection
- Lazy class detection
- Dead code detection
- Data clump detection
- Severity scoring
- Report generation

Issue: #221
"""

import ast
import os
import sys
from unittest.mock import MagicMock

import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

# Import using sys.path manipulation since directory has dashes
import importlib.util

spec = importlib.util.spec_from_file_location(
    "anti_pattern_detector",
    os.path.join(
        os.path.dirname(__file__),
        "../../tools/code-analysis-suite/src/anti_pattern_detector.py",
    ),
)
anti_pattern_module = importlib.util.module_from_spec(spec)
sys.modules["anti_pattern_detector"] = anti_pattern_module
spec.loader.exec_module(anti_pattern_module)

AntiPatternDetector = anti_pattern_module.AntiPatternDetector
AntiPatternInstance = anti_pattern_module.AntiPatternInstance
AntiPatternReport = anti_pattern_module.AntiPatternReport
AntiPatternType = anti_pattern_module.AntiPatternType
ClassInfo = anti_pattern_module.ClassInfo
ModuleInfo = anti_pattern_module.ModuleInfo
Severity = anti_pattern_module.Severity


class TestSeverity:
    """Test Severity enum."""

    def test_severity_values(self):
        """Verify all severity levels are defined."""
        assert Severity.CRITICAL.value == "critical"
        assert Severity.HIGH.value == "high"
        assert Severity.MEDIUM.value == "medium"
        assert Severity.LOW.value == "low"

    def test_severity_scores(self):
        """Test severity score ordering."""
        assert Severity.CRITICAL.score() > Severity.HIGH.score()
        assert Severity.HIGH.score() > Severity.MEDIUM.score()
        assert Severity.MEDIUM.score() > Severity.LOW.score()

    def test_severity_score_values(self):
        """Test specific severity score values."""
        assert Severity.CRITICAL.score() == 100
        assert Severity.HIGH.score() == 75
        assert Severity.MEDIUM.score() == 50
        assert Severity.LOW.score() == 25


class TestAntiPatternType:
    """Test AntiPatternType enum."""

    def test_all_types_defined(self):
        """Verify all expected anti-pattern types are defined."""
        expected_types = [
            "god_class",
            "feature_envy",
            "circular_dependency",
            "shotgun_surgery",
            "speculative_generality",
            "dead_code",
            "data_clump",
            "long_method",
            "long_parameter_list",
            "primitive_obsession",
            "lazy_class",
            "refused_bequest",
        ]
        actual_types = [t.value for t in AntiPatternType]
        for expected in expected_types:
            assert expected in actual_types, f"Missing type: {expected}"


class TestAntiPatternInstance:
    """Test AntiPatternInstance dataclass."""

    def test_create_instance(self):
        """Test basic instance creation."""
        instance = AntiPatternInstance(
            pattern_type=AntiPatternType.GOD_CLASS,
            severity=Severity.HIGH,
            file_path="/path/to/file.py",
            line_number=10,
            entity_name="LargeClass",
            description="Class has too many methods",
            metrics={"method_count": 25},
            suggestion="Break down the class",
            refactoring_effort="high",
        )

        assert instance.pattern_type == AntiPatternType.GOD_CLASS
        assert instance.severity == Severity.HIGH
        assert instance.file_path == "/path/to/file.py"
        assert instance.line_number == 10
        assert instance.entity_name == "LargeClass"

    def test_to_dict(self):
        """Test serialization to dictionary."""
        instance = AntiPatternInstance(
            pattern_type=AntiPatternType.FEATURE_ENVY,
            severity=Severity.MEDIUM,
            file_path="/path/to/file.py",
            line_number=50,
            entity_name="MyClass.myMethod",
            description="Method envies another class",
            metrics={"external_refs": 10, "self_refs": 2},
            suggestion="Move method to other class",
            refactoring_effort="medium",
            related_entities=["OtherClass"],
        )

        data = instance.to_dict()
        assert data["pattern_type"] == "feature_envy"
        assert data["severity"] == "medium"
        assert data["severity_score"] == 50
        assert data["entity_name"] == "MyClass.myMethod"
        assert data["related_entities"] == ["OtherClass"]


class TestAntiPatternReport:
    """Test AntiPatternReport dataclass."""

    def test_create_report(self):
        """Test basic report creation."""
        report = AntiPatternReport(
            total_issues=5,
            critical_count=1,
            high_count=2,
            medium_count=1,
            low_count=1,
            health_score=65.0,
            anti_patterns=[],
            summary_by_type={"god_class": 1, "feature_envy": 2},
            recommendations=["Fix god classes"],
            analysis_time_seconds=1.5,
        )

        assert report.total_issues == 5
        assert report.critical_count == 1
        assert report.health_score == 65.0

    def test_report_to_dict(self):
        """Test report serialization."""
        report = AntiPatternReport(
            total_issues=3,
            critical_count=0,
            high_count=1,
            medium_count=1,
            low_count=1,
            health_score=85.0,
            anti_patterns=[],
            summary_by_type={"long_method": 2, "lazy_class": 1},
            recommendations=["Shorten methods"],
            analysis_time_seconds=0.75,
        )

        data = report.to_dict()
        assert data["total_issues"] == 3
        assert data["health_score"] == 85.0
        assert "long_method" in data["summary_by_type"]


class TestAntiPatternDetector:
    """Test AntiPatternDetector class."""

    @pytest.fixture
    def detector(self):
        """Create detector instance."""
        return AntiPatternDetector(redis_client=None)

    def test_initialization(self, detector):
        """Test detector initialization."""
        assert detector is not None
        assert detector.GOD_CLASS_METHOD_THRESHOLD == 20
        assert detector.LONG_METHOD_THRESHOLD == 50
        assert detector.LONG_PARAM_LIST_THRESHOLD == 5

    def test_calculate_complexity(self, detector):
        """Test cyclomatic complexity calculation."""
        # Simple function - complexity 1
        simple_code = """
def simple():
    return 42
"""
        tree = ast.parse(simple_code)
        func = tree.body[0]
        assert detector._calculate_complexity(func) == 1

        # Function with if statement - complexity 2
        if_code = """
def with_if(x):
    if x > 0:
        return x
    return 0
"""
        tree = ast.parse(if_code)
        func = tree.body[0]
        assert detector._calculate_complexity(func) >= 2

        # Function with loop - complexity 2
        loop_code = """
def with_loop(items):
    for item in items:
        print(item)
"""
        tree = ast.parse(loop_code)
        func = tree.body[0]
        assert detector._calculate_complexity(func) >= 2

    def test_god_class_score_below_threshold(self, detector):
        """Test god class score for small class."""
        small_class = ClassInfo(
            name="SmallClass",
            file_path="/test.py",
            line_number=1,
            methods=[MagicMock() for _ in range(5)],  # 5 methods
            attributes=set(["attr1", "attr2"]),
            base_classes=[],
            method_calls={},
            external_references={},
            lines_of_code=50,
            complexity=10,
        )

        score = detector._calculate_god_class_score(small_class)
        assert score == 0  # Below all thresholds

    def test_god_class_score_above_threshold(self, detector):
        """Test god class score for large class."""
        large_class = ClassInfo(
            name="GodClass",
            file_path="/test.py",
            line_number=1,
            methods=[MagicMock() for _ in range(30)],  # 30 methods
            attributes=set([f"attr{i}" for i in range(20)]),  # 20 attributes
            base_classes=[],
            method_calls={},
            external_references={},
            lines_of_code=800,  # 800 lines
            complexity=50,
        )

        score = detector._calculate_god_class_score(large_class)
        assert score > 0  # Above thresholds
        assert score <= 100

    def test_god_class_severity(self, detector):
        """Test god class severity determination."""
        # Create mock class info
        mock_class = MagicMock()

        # High score, many methods -> CRITICAL
        # Issue #372: Now uses method_count property instead of len(methods)
        mock_class.method_count = 45
        severity = detector._god_class_severity(75, mock_class)
        assert severity == Severity.CRITICAL

        # Medium score -> HIGH
        mock_class.method_count = 25
        severity = detector._god_class_severity(55, mock_class)
        assert severity == Severity.HIGH

        # Low score -> MEDIUM
        mock_class.method_count = 22
        severity = detector._god_class_severity(35, mock_class)
        assert severity == Severity.MEDIUM

        # Very low score -> LOW
        mock_class.method_count = 21
        severity = detector._god_class_severity(25, mock_class)
        assert severity == Severity.LOW

    def test_find_cycles_no_cycles(self, detector):
        """Test cycle detection with no cycles."""
        graph = {"A": {"B"}, "B": {"C"}, "C": set()}
        cycles = detector._find_all_cycles(graph)
        assert len(cycles) == 0

    def test_find_cycles_with_cycle(self, detector):
        """Test cycle detection with cycles present."""
        graph = {"A": {"B"}, "B": {"C"}, "C": {"A"}}  # Creates cycle A -> B -> C -> A
        cycles = detector._find_all_cycles(graph)
        assert len(cycles) > 0

    def test_generate_report(self, detector):
        """Test report generation."""
        anti_patterns = [
            AntiPatternInstance(
                pattern_type=AntiPatternType.GOD_CLASS,
                severity=Severity.HIGH,
                file_path="/test.py",
                line_number=1,
                entity_name="TestClass",
                description="Large class",
                metrics={},
                suggestion="Refactor",
                refactoring_effort="high",
            ),
            AntiPatternInstance(
                pattern_type=AntiPatternType.LONG_METHOD,
                severity=Severity.MEDIUM,
                file_path="/test.py",
                line_number=50,
                entity_name="TestClass.longMethod",
                description="Long method",
                metrics={},
                suggestion="Extract method",
                refactoring_effort="medium",
            ),
        ]

        report = detector._generate_report(anti_patterns, 1.0)

        assert report.total_issues == 2
        assert report.high_count == 1
        assert report.medium_count == 1
        assert "god_class" in report.summary_by_type
        assert "long_method" in report.summary_by_type
        assert len(report.recommendations) > 0

    def test_health_score_calculation(self, detector):
        """Test health score calculation."""
        # No issues -> score 100
        report = detector._generate_report([], 0.5)
        assert report.health_score == 100

        # Critical issues heavily penalize score
        critical_patterns = [
            AntiPatternInstance(
                pattern_type=AntiPatternType.GOD_CLASS,
                severity=Severity.CRITICAL,
                file_path="/test.py",
                line_number=1,
                entity_name="Test",
                description="Test",
                metrics={},
                suggestion="Test",
                refactoring_effort="high",
            )
            for _ in range(3)
        ]
        report = detector._generate_report(critical_patterns, 0.5)
        assert report.health_score < 50  # 3 critical = -60 points


class TestAntiPatternDetectorAsync:
    """Async tests for AntiPatternDetector."""

    @pytest.fixture
    def detector(self):
        """Create detector instance."""
        return AntiPatternDetector(redis_client=None)

    @pytest.mark.asyncio
    async def test_detect_god_classes(self, detector):
        """Test god class detection."""
        # Set up a class that exceeds thresholds
        detector.classes = {
            "module.GodClass": ClassInfo(
                name="GodClass",
                file_path="/test.py",
                line_number=1,
                methods=[MagicMock() for _ in range(25)],
                attributes=set([f"attr{i}" for i in range(18)]),
                base_classes=[],
                method_calls={},
                external_references={},
                lines_of_code=600,
                complexity=40,
            )
        }

        issues = await detector._detect_god_classes()
        assert len(issues) > 0
        assert issues[0].pattern_type == AntiPatternType.GOD_CLASS

    @pytest.mark.asyncio
    async def test_detect_long_methods(self, detector):
        """Test long method detection."""
        # Create a mock method that exceeds threshold
        mock_method = MagicMock()
        mock_method.name = "longMethod"
        mock_method.lineno = 10
        mock_method.end_lineno = 100  # 90 lines

        detector.classes = {
            "module.TestClass": ClassInfo(
                name="TestClass",
                file_path="/test.py",
                line_number=1,
                methods=[mock_method],
                attributes=set(),
                base_classes=[],
                method_calls={},
                external_references={},
                lines_of_code=100,
                complexity=10,
            )
        }

        issues = await detector._detect_long_methods()
        assert len(issues) > 0
        assert issues[0].pattern_type == AntiPatternType.LONG_METHOD

    @pytest.mark.asyncio
    async def test_detect_long_parameter_lists(self, detector):
        """Test long parameter list detection."""
        # Create mock method with many parameters
        mock_method = MagicMock()
        mock_method.name = "methodWithManyParams"
        mock_method.lineno = 10
        mock_method.args = MagicMock()

        # Create 8 parameters (exceeds threshold of 5)
        mock_params = []
        for i in range(8):
            arg = MagicMock()
            arg.arg = f"param{i}"
            mock_params.append(arg)

        mock_method.args.args = mock_params

        detector.classes = {
            "module.TestClass": ClassInfo(
                name="TestClass",
                file_path="/test.py",
                line_number=1,
                methods=[mock_method],
                attributes=set(),
                base_classes=[],
                method_calls={},
                external_references={},
                lines_of_code=50,
                complexity=5,
            )
        }

        issues = await detector._detect_long_parameter_lists()
        assert len(issues) > 0
        assert issues[0].pattern_type == AntiPatternType.LONG_PARAMETER_LIST

    @pytest.mark.asyncio
    async def test_detect_circular_dependencies(self, detector):
        """Test circular dependency detection."""
        # Set up modules with circular imports
        detector.modules = {
            "module_a": ModuleInfo(
                name="module_a",
                file_path="/module_a.py",
                imports=["module_b"],
                classes=[],
                functions=[],
            ),
            "module_b": ModuleInfo(
                name="module_b",
                file_path="/module_b.py",
                imports=["module_a"],  # Creates cycle
                classes=[],
                functions=[],
            ),
        }

        issues = await detector._detect_circular_dependencies()
        assert len(issues) > 0
        assert issues[0].pattern_type == AntiPatternType.CIRCULAR_DEPENDENCY

    @pytest.mark.asyncio
    async def test_detect_lazy_classes(self, detector):
        """Test lazy class detection."""
        # Create a mock method - use spec to avoid string issues
        mock_method = MagicMock(spec=ast.FunctionDef)
        mock_method.name = "only_method"

        detector.classes = {
            "module.LazyClass": ClassInfo(
                name="LazyClass",
                file_path="/test.py",
                line_number=1,
                methods=[mock_method],
                attributes=set(),
                base_classes=[],  # Not Enum or Exception
                method_calls={},
                external_references={},
                lines_of_code=15,
                complexity=2,
            )
        }

        issues = await detector._detect_lazy_classes()
        assert len(issues) > 0
        assert issues[0].pattern_type == AntiPatternType.LAZY_CLASS


class TestRecommendations:
    """Test recommendation generation."""

    @pytest.fixture
    def detector(self):
        """Create detector instance."""
        return AntiPatternDetector(redis_client=None)

    def test_recommendations_for_god_class(self, detector):
        """Test recommendations include god class advice."""
        summary = {AntiPatternType.GOD_CLASS.value: 1}
        recs = detector._generate_recommendations([], summary)
        assert any("God Class" in r for r in recs)

    def test_recommendations_for_circular_deps(self, detector):
        """Test recommendations include circular dependency advice."""
        summary = {AntiPatternType.CIRCULAR_DEPENDENCY.value: 1}
        recs = detector._generate_recommendations([], summary)
        assert any("Circular" in r for r in recs)

    def test_recommendations_for_feature_envy(self, detector):
        """Test recommendations include feature envy advice."""
        summary = {AntiPatternType.FEATURE_ENVY.value: 1}
        recs = detector._generate_recommendations([], summary)
        assert any("Envy" in r for r in recs)

    def test_recommendations_empty_codebase(self, detector):
        """Test recommendations for clean codebase."""
        summary = {}
        recs = detector._generate_recommendations([], summary)
        assert any("healthy" in r.lower() for r in recs)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
