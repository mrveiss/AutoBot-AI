# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Bug Prediction System (Issue #224)

Tests cover:
- Risk factor scoring
- File risk assessment
- Directory analysis
- Prevention tip generation
- Test suggestion generation
- Heatmap generation
- Convenience functions
"""

from datetime import datetime
from pathlib import Path

import pytest
from code_intelligence.bug_predictor import (
    BugPredictor,
    FileRiskAssessment,
    PredictionResult,
    RiskFactor,
    RiskFactorScore,
    RiskLevel,
    get_risk_factors,
    get_risk_levels,
    predict_bugs,
)

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def predictor():
    """Create a BugPredictor instance."""
    return BugPredictor()


@pytest.fixture
def sample_python_file(tmp_path):
    """Create a sample Python file for testing."""
    content = '''
def simple_function():
    """Simple docstring."""
    return 42

def complex_function(x, y, z):
    """Complex function with nesting."""
    if x > 0:
        if y > 0:
            if z > 0:
                for i in range(10):
                    for j in range(10):
                        print(i, j)
            else:
                return -1
        else:
            return -2
    else:
        return -3

class MyClass:
    def __init__(self):
        self.value = 0

    def method(self):
        return self.value
'''
    file_path = tmp_path / "sample.py"
    file_path.write_text(content)
    return file_path


@pytest.fixture
def complex_python_file(tmp_path):
    """Create a complex Python file for testing."""
    content = "import os\nimport sys\nimport json\nimport logging\n"
    content += "import pathlib\nimport datetime\nimport subprocess\n"
    content += "from typing import Any, Optional, List, Dict\n"
    content += "from dataclasses import dataclass\n\n"

    # Add many functions
    for i in range(25):
        content += f'''
def function_{i}(arg1, arg2):
    """Function {i} docstring."""
    if arg1 > 0:
        for j in range(10):
            if arg2 > j:
                try:
                    result = arg1 + arg2
                except Exception:
                    pass
    return None
'''
    file_path = tmp_path / "complex.py"
    file_path.write_text(content)
    return file_path


# ============================================================================
# Test RiskFactorScore
# ============================================================================


class TestRiskFactorScore:
    """Tests for RiskFactorScore dataclass."""

    def test_weighted_score_calculation(self):
        """Test weighted score property."""
        score = RiskFactorScore(
            factor=RiskFactor.COMPLEXITY, score=80.0, weight=0.2, details="High"
        )
        assert score.weighted_score == 16.0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        score = RiskFactorScore(
            factor=RiskFactor.BUG_HISTORY,
            score=60.0,
            weight=0.25,
            details="6 bug fixes",
        )
        result = score.to_dict()

        assert result["factor"] == "bug_history"
        assert result["score"] == 60.0
        assert result["weight"] == 0.25
        assert result["weighted_score"] == 15.0
        assert result["details"] == "6 bug fixes"


# ============================================================================
# Test FileRiskAssessment
# ============================================================================


class TestFileRiskAssessment:
    """Tests for FileRiskAssessment dataclass."""

    def test_basic_assessment(self):
        """Test basic assessment creation."""
        assessment = FileRiskAssessment(
            file_path="src/test.py",
            risk_score=65.0,
            risk_level=RiskLevel.HIGH,
        )
        assert assessment.file_path == "src/test.py"
        assert assessment.risk_score == 65.0
        assert assessment.risk_level == RiskLevel.HIGH

    def test_to_dict(self):
        """Test conversion to dictionary."""
        assessment = FileRiskAssessment(
            file_path="src/example.py",
            risk_score=75.0,
            risk_level=RiskLevel.HIGH,
            factor_scores=[
                RiskFactorScore(factor=RiskFactor.COMPLEXITY, score=80.0, weight=0.15)
            ],
            bug_count_history=5,
            prevention_tips=["Add tests"],
            suggested_tests=["Test edge cases"],
            recommendation="Review this file",
        )
        result = assessment.to_dict()

        assert result["file_path"] == "src/example.py"
        assert result["risk_score"] == 75.0
        assert result["risk_level"] == "high"
        assert "complexity" in result["factors"]
        assert len(result["factor_details"]) == 1
        assert result["bug_count_history"] == 5
        assert "Add tests" in result["prevention_tips"]


# ============================================================================
# Test BugPredictor Initialization
# ============================================================================


class TestBugPredictorInit:
    """Tests for BugPredictor initialization."""

    def test_default_initialization(self):
        """Test default initialization."""
        predictor = BugPredictor()
        assert predictor.project_root == Path.cwd()
        assert len(predictor.weights) == 10
        assert "fix" in predictor.bug_keywords

    def test_custom_project_root(self, tmp_path):
        """Test custom project root."""
        predictor = BugPredictor(project_root=str(tmp_path))
        assert predictor.project_root == tmp_path

    def test_custom_weights(self):
        """Test custom weights."""
        custom_weights = {RiskFactor.COMPLEXITY: 0.5, RiskFactor.BUG_HISTORY: 0.5}
        predictor = BugPredictor(weights=custom_weights)
        assert predictor.weights[RiskFactor.COMPLEXITY] == 0.5

    def test_custom_bug_keywords(self):
        """Test custom bug keywords."""
        predictor = BugPredictor(bug_keywords=["defect", "problem"])
        assert "defect" in predictor.bug_keywords
        assert "fix" not in predictor.bug_keywords


# ============================================================================
# Test Complexity Analysis
# ============================================================================


class TestComplexityAnalysis:
    """Tests for complexity analysis."""

    def test_simple_file_complexity(self, predictor, sample_python_file):
        """Test complexity analysis on simple file."""
        result = predictor._analyze_complexity(sample_python_file)

        assert "overall" in result
        assert "cyclomatic" in result
        assert "nesting" in result
        assert result["functions"] > 0
        assert result["lines"] > 0

    def test_complex_file_complexity(self, predictor, complex_python_file):
        """Test complexity analysis on complex file."""
        result = predictor._analyze_complexity(complex_python_file)

        assert result["functions"] >= 20
        assert result["overall"] > 50  # Should be higher complexity

    def test_nonexistent_file(self, predictor, tmp_path):
        """Test complexity analysis on non-existent file."""
        result = predictor._analyze_complexity(tmp_path / "nonexistent.py")

        assert result["overall"] == 30.0  # Default value
        assert result["lines"] == 0

    def test_nesting_depth_detection(self, predictor, sample_python_file):
        """Test nesting depth detection."""
        result = predictor._analyze_complexity(sample_python_file)

        # Sample file has nested loops
        assert result["max_depth"] >= 3


# ============================================================================
# Test File Size Scoring
# ============================================================================


class TestFileSizeScoring:
    """Tests for file size scoring."""

    def test_small_file(self, predictor, tmp_path):
        """Test small file scoring."""
        small_file = tmp_path / "small.py"
        small_file.write_text("x = 1\n" * 50)

        result = predictor._calculate_file_size_score(small_file)
        # Line count includes trailing empty line from split
        assert result["lines"] >= 50
        assert result["score"] == 10

    def test_medium_file(self, predictor, tmp_path):
        """Test medium file scoring."""
        medium_file = tmp_path / "medium.py"
        medium_file.write_text("x = 1\n" * 200)

        result = predictor._calculate_file_size_score(medium_file)
        assert result["lines"] >= 200
        assert result["score"] == 25

    def test_large_file(self, predictor, tmp_path):
        """Test large file scoring."""
        large_file = tmp_path / "large.py"
        large_file.write_text("x = 1\n" * 600)

        result = predictor._calculate_file_size_score(large_file)
        assert result["lines"] >= 600
        assert result["score"] == 75


# ============================================================================
# Test Dependency Analysis
# ============================================================================


class TestDependencyAnalysis:
    """Tests for dependency analysis."""

    def test_few_imports(self, predictor, tmp_path):
        """Test file with few imports."""
        file_path = tmp_path / "few_imports.py"
        file_path.write_text("import os\nimport sys\n\ndef main(): pass")

        result = predictor._analyze_dependencies(file_path)
        assert result["count"] == 2
        assert result["score"] == 10

    def test_many_imports(self, predictor, tmp_path):
        """Test file with many imports."""
        imports = "\n".join([f"import module_{i}" for i in range(25)])
        file_path = tmp_path / "many_imports.py"
        file_path.write_text(imports)

        result = predictor._analyze_dependencies(file_path)
        assert result["count"] >= 20
        assert result["score"] >= 75


# ============================================================================
# Test Risk Level Calculation
# ============================================================================


class TestRiskLevelCalculation:
    """Tests for risk level calculation."""

    def test_critical_level(self, predictor):
        """Test critical risk level."""
        assert predictor._get_risk_level(85.0) == RiskLevel.CRITICAL

    def test_high_level(self, predictor):
        """Test high risk level."""
        assert predictor._get_risk_level(65.0) == RiskLevel.HIGH

    def test_medium_level(self, predictor):
        """Test medium risk level."""
        assert predictor._get_risk_level(45.0) == RiskLevel.MEDIUM

    def test_low_level(self, predictor):
        """Test low risk level."""
        assert predictor._get_risk_level(25.0) == RiskLevel.LOW

    def test_minimal_level(self, predictor):
        """Test minimal risk level."""
        assert predictor._get_risk_level(10.0) == RiskLevel.MINIMAL

    def test_boundary_values(self, predictor):
        """Test boundary values."""
        assert predictor._get_risk_level(80.0) == RiskLevel.CRITICAL
        assert predictor._get_risk_level(79.9) == RiskLevel.HIGH
        assert predictor._get_risk_level(60.0) == RiskLevel.HIGH
        assert predictor._get_risk_level(59.9) == RiskLevel.MEDIUM


# ============================================================================
# Test Prevention Tips Generation
# ============================================================================


class TestPreventionTips:
    """Tests for prevention tip generation."""

    def test_generates_tips_for_high_scores(self, predictor):
        """Test tip generation for high-score factors."""
        scores = [
            RiskFactorScore(factor=RiskFactor.COMPLEXITY, score=75.0, weight=0.15),
            RiskFactorScore(factor=RiskFactor.BUG_HISTORY, score=80.0, weight=0.25),
        ]
        tips = predictor._generate_prevention_tips(scores)

        assert len(tips) > 0
        assert len(tips) <= 5

    def test_no_tips_for_low_scores(self, predictor):
        """Test no tips for low-score factors."""
        scores = [
            RiskFactorScore(factor=RiskFactor.COMPLEXITY, score=20.0, weight=0.15),
            RiskFactorScore(factor=RiskFactor.BUG_HISTORY, score=30.0, weight=0.25),
        ]
        tips = predictor._generate_prevention_tips(scores)

        assert len(tips) == 0


# ============================================================================
# Test Test Suggestions
# ============================================================================


class TestSuggestions:
    """Tests for test suggestion generation."""

    def test_suggestions_for_high_complexity(self, predictor):
        """Test suggestions for high complexity."""
        scores = [
            RiskFactorScore(factor=RiskFactor.COMPLEXITY, score=70.0, weight=0.15),
        ]
        suggestions = predictor._generate_test_suggestions("module.py", scores)

        assert len(suggestions) > 0
        assert any("boundary" in s.lower() for s in suggestions)

    def test_suggestions_for_bug_history(self, predictor):
        """Test suggestions for bug history."""
        scores = [
            RiskFactorScore(factor=RiskFactor.BUG_HISTORY, score=80.0, weight=0.25),
        ]
        suggestions = predictor._generate_test_suggestions("buggy.py", scores)

        assert len(suggestions) > 0
        assert any("bug" in s.lower() for s in suggestions)


# ============================================================================
# Test File Analysis
# ============================================================================


class TestFileAnalysis:
    """Tests for file analysis."""

    def test_analyze_simple_file(self, sample_python_file, tmp_path):
        """Test analysis of simple file."""
        # Create predictor with tmp_path as root
        predictor = BugPredictor(project_root=str(tmp_path))
        predictor._bug_history_cache = {}
        predictor._change_freq_cache = {}

        assessment = predictor.analyze_file(str(sample_python_file))

        assert isinstance(assessment, FileRiskAssessment)
        assert assessment.risk_score >= 0
        assert assessment.risk_score <= 100
        assert len(assessment.factor_scores) > 0

    def test_analyze_complex_file(self, complex_python_file, tmp_path):
        """Test analysis of complex file."""
        predictor = BugPredictor(project_root=str(tmp_path))
        predictor._bug_history_cache = {}
        predictor._change_freq_cache = {}

        assessment = predictor.analyze_file(str(complex_python_file))

        # Complex file should have higher risk
        assert assessment.risk_score > 20

    def test_assessment_has_recommendation(self, sample_python_file, tmp_path):
        """Test assessment includes recommendation."""
        predictor = BugPredictor(project_root=str(tmp_path))
        predictor._bug_history_cache = {}
        predictor._change_freq_cache = {}

        assessment = predictor.analyze_file(str(sample_python_file))

        assert assessment.recommendation != ""


# ============================================================================
# Test Directory Analysis
# ============================================================================


class TestDirectoryAnalysis:
    """Tests for directory analysis."""

    def test_analyze_directory(self, predictor, tmp_path):
        """Test directory analysis."""
        # Create some test files
        for i in range(5):
            (tmp_path / f"file_{i}.py").write_text(f"x = {i}\n" * 50)

        predictor._bug_history_cache = {}
        predictor._change_freq_cache = {}
        predictor.project_root = tmp_path

        result = predictor.analyze_directory(str(tmp_path), limit=10)

        assert isinstance(result, PredictionResult)
        assert result.analyzed_files == 5
        assert len(result.file_assessments) == 5

    def test_analyze_empty_directory(self, predictor, tmp_path):
        """Test analysis of empty directory."""
        predictor._bug_history_cache = {}
        predictor._change_freq_cache = {}

        result = predictor.analyze_directory(str(tmp_path))

        assert result.analyzed_files == 0
        assert result.total_files == 0

    def test_risk_distribution(self, predictor, tmp_path):
        """Test risk distribution calculation."""
        for i in range(3):
            (tmp_path / f"test_{i}.py").write_text("x = 1\n" * 100)

        predictor._bug_history_cache = {}
        predictor._change_freq_cache = {}
        predictor.project_root = tmp_path

        result = predictor.analyze_directory(str(tmp_path))

        # All risk levels should be present in distribution
        assert "critical" in result.risk_distribution
        assert "high" in result.risk_distribution
        assert "medium" in result.risk_distribution


# ============================================================================
# Test Heatmap Generation
# ============================================================================


class TestHeatmapGeneration:
    """Tests for heatmap generation."""

    def test_flat_heatmap(self, predictor, tmp_path):
        """Test flat heatmap generation."""
        (tmp_path / "test.py").write_text("x = 1\n" * 50)
        predictor._bug_history_cache = {}
        predictor._change_freq_cache = {}
        predictor.project_root = tmp_path

        heatmap = predictor.generate_heatmap(str(tmp_path), grouping="flat")

        assert heatmap["grouping"] == "flat"
        assert "data" in heatmap
        assert "legend" in heatmap

    def test_directory_heatmap(self, predictor, tmp_path):
        """Test directory-grouped heatmap."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "test.py").write_text("x = 1")
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_file.py").write_text("y = 2")

        predictor._bug_history_cache = {}
        predictor._change_freq_cache = {}
        predictor.project_root = tmp_path

        heatmap = predictor.generate_heatmap(str(tmp_path), grouping="directory")

        assert heatmap["grouping"] == "directory"
        assert len(heatmap["data"]) >= 1

    def test_heatmap_legend(self, predictor, tmp_path):
        """Test heatmap legend structure."""
        (tmp_path / "test.py").write_text("x = 1")
        predictor._bug_history_cache = {}
        predictor._change_freq_cache = {}
        predictor.project_root = tmp_path

        heatmap = predictor.generate_heatmap(str(tmp_path))

        legend = heatmap["legend"]
        assert "critical" in legend
        assert "high" in legend
        assert legend["critical"]["min"] == 80


# ============================================================================
# Test High Risk Files
# ============================================================================


class TestHighRiskFiles:
    """Tests for high risk file retrieval."""

    def test_get_high_risk_files(self, predictor, tmp_path):
        """Test getting high risk files."""
        # Create files with varying complexity
        (tmp_path / "simple.py").write_text("x = 1")
        complex_content = "import os\n" * 30 + "def f():\n" * 25
        (tmp_path / "complex.py").write_text(complex_content)

        predictor._bug_history_cache = {}
        predictor._change_freq_cache = {}
        predictor.project_root = tmp_path

        high_risk = predictor.get_high_risk_files(str(tmp_path), threshold=40)

        assert isinstance(high_risk, list)


# ============================================================================
# Test Cache Management
# ============================================================================


class TestCacheManagement:
    """Tests for cache management."""

    def test_clear_cache(self, predictor):
        """Test cache clearing."""
        predictor._bug_history_cache = {"file.py": []}
        predictor._change_freq_cache = {"file.py": 5}
        predictor._author_stats_cache = {"author": {}}

        predictor.clear_cache()

        assert predictor._bug_history_cache is None
        assert predictor._change_freq_cache is None
        assert predictor._author_stats_cache is None


# ============================================================================
# Test Convenience Functions
# ============================================================================


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_predict_bugs(self, tmp_path):
        """Test predict_bugs function."""
        (tmp_path / "test.py").write_text("x = 1")

        result = predict_bugs(str(tmp_path), limit=5)

        assert isinstance(result, PredictionResult)

    def test_get_risk_factors(self):
        """Test get_risk_factors function."""
        factors = get_risk_factors()

        assert len(factors) == 10
        assert all("name" in f for f in factors)
        assert all("weight" in f for f in factors)
        assert all("description" in f for f in factors)

    def test_get_risk_levels(self):
        """Test get_risk_levels function."""
        levels = get_risk_levels()

        assert len(levels) == 5
        assert levels[0]["level"] == "critical"
        assert levels[0]["min_score"] == 80


# ============================================================================
# Test PredictionResult
# ============================================================================


class TestPredictionResult:
    """Tests for PredictionResult dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        result = PredictionResult(
            timestamp=datetime.now(),
            total_files=100,
            analyzed_files=50,
            high_risk_count=10,
            predicted_bugs=5,
            accuracy_score=75.0,
            risk_distribution={"critical": 2, "high": 8},
            file_assessments=[],
            top_risk_factors=[("complexity", 500.0)],
        )
        data = result.to_dict()

        assert data["total_files"] == 100
        assert data["analyzed_files"] == 50
        assert data["high_risk_count"] == 10
        assert "timestamp" in data


# ============================================================================
# Test Recommendation Generation
# ============================================================================


class TestRecommendationGeneration:
    """Tests for recommendation generation."""

    def test_critical_recommendation(self, predictor):
        """Test critical risk recommendation."""
        rec = predictor._generate_recommendation(85.0, [])
        assert "CRITICAL" in rec

    def test_high_recommendation(self, predictor):
        """Test high risk recommendation."""
        rec = predictor._generate_recommendation(65.0, [])
        assert "HIGH RISK" in rec

    def test_moderate_recommendation(self, predictor):
        """Test moderate risk recommendation."""
        rec = predictor._generate_recommendation(45.0, [])
        assert "MODERATE" in rec

    def test_low_recommendation(self, predictor):
        """Test low risk recommendation."""
        rec = predictor._generate_recommendation(25.0, [])
        assert "LOW RISK" in rec

    def test_minimal_recommendation(self, predictor):
        """Test minimal risk recommendation."""
        rec = predictor._generate_recommendation(10.0, [])
        assert "MINIMAL" in rec


# ============================================================================
# Test Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_file(self, tmp_path):
        """Test analysis of empty file."""
        empty_file = tmp_path / "empty.py"
        empty_file.write_text("")
        predictor = BugPredictor(project_root=str(tmp_path))
        predictor._bug_history_cache = {}
        predictor._change_freq_cache = {}

        assessment = predictor.analyze_file(str(empty_file))

        assert assessment.risk_score >= 0

    def test_binary_file_handling(self, tmp_path):
        """Test handling of binary-like content."""
        binary_file = tmp_path / "binary.py"
        binary_file.write_bytes(b"\x00\x01\x02\x03")
        predictor = BugPredictor(project_root=str(tmp_path))
        predictor._bug_history_cache = {}
        predictor._change_freq_cache = {}

        # Should not raise exception
        assessment = predictor.analyze_file(str(binary_file))
        assert assessment is not None

    def test_unicode_content(self, tmp_path):
        """Test handling of unicode content."""
        unicode_file = tmp_path / "unicode.py"
        unicode_file.write_text("# 日本語コメント\nx = '中文'\n")
        predictor = BugPredictor(project_root=str(tmp_path))
        predictor._bug_history_cache = {}
        predictor._change_freq_cache = {}

        assessment = predictor.analyze_file(str(unicode_file))
        assert assessment is not None

    def test_very_deep_nesting(self, tmp_path):
        """Test detection of very deep nesting."""
        content = "def f():\n"
        for i in range(10):
            content += "    " * (i + 1) + f"if x{i}:\n"
        content += "    " * 11 + "pass\n"

        deep_file = tmp_path / "deep.py"
        deep_file.write_text(content)
        predictor = BugPredictor(project_root=str(tmp_path))
        predictor._bug_history_cache = {}
        predictor._change_freq_cache = {}

        result = predictor._analyze_complexity(deep_file)
        assert result["max_depth"] >= 5
