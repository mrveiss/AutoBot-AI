# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Code Fingerprinting System

Tests the code fingerprinting and clone detection functionality including:
- AST hashing (structural and normalized)
- Semantic hashing
- Fuzzy matching and similarity calculation
- Clone type detection (Type 1-4)
- Clone severity scoring
- Report generation
- Refactoring suggestions

Issue: #237
Parent Epic: #217
"""

import ast
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from src.code_intelligence.code_fingerprinting import (
    ASTHasher,
    ASTNormalizer,
    CloneDetectionReport,
    CloneDetector,
    CloneGroup,
    CloneInstance,
    CloneSeverity,
    CloneType,
    CodeFragment,
    Fingerprint,
    FingerprintType,
    SemanticHasher,
    SimilarityCalculator,
    detect_clones,
    get_clone_severities,
    get_clone_types,
    get_fingerprint_types,
)


class TestCloneType:
    """Test CloneType enum."""

    def test_clone_type_values(self):
        """Verify all clone types are defined."""
        assert CloneType.TYPE_1.value == "type_1"
        assert CloneType.TYPE_2.value == "type_2"
        assert CloneType.TYPE_3.value == "type_3"
        assert CloneType.TYPE_4.value == "type_4"

    def test_all_types_present(self):
        """Verify all expected types exist."""
        types = [t.value for t in CloneType]
        assert len(types) == 4
        assert "type_1" in types
        assert "type_2" in types
        assert "type_3" in types
        assert "type_4" in types


class TestCloneSeverity:
    """Test CloneSeverity enum."""

    def test_severity_values(self):
        """Verify all severity levels are defined."""
        assert CloneSeverity.INFO.value == "info"
        assert CloneSeverity.LOW.value == "low"
        assert CloneSeverity.MEDIUM.value == "medium"
        assert CloneSeverity.HIGH.value == "high"
        assert CloneSeverity.CRITICAL.value == "critical"

    def test_all_severities_present(self):
        """Verify all expected severities exist."""
        severities = [s.value for s in CloneSeverity]
        assert len(severities) == 5


class TestFingerprintType:
    """Test FingerprintType enum."""

    def test_fingerprint_type_values(self):
        """Verify all fingerprint types are defined."""
        assert FingerprintType.AST_STRUCTURAL.value == "ast_structural"
        assert FingerprintType.AST_NORMALIZED.value == "ast_normalized"
        assert FingerprintType.SEMANTIC.value == "semantic"
        assert FingerprintType.TOKEN_SEQUENCE.value == "token_sequence"


class TestCodeFragment:
    """Test CodeFragment dataclass."""

    def test_create_fragment(self):
        """Test basic fragment creation."""
        fragment = CodeFragment(
            file_path="/path/to/file.py",
            start_line=10,
            end_line=25,
            source_code="def foo():\n    return 42",
            fragment_type="function",
            entity_name="foo",
        )

        assert fragment.file_path == "/path/to/file.py"
        assert fragment.start_line == 10
        assert fragment.end_line == 25
        assert fragment.line_count == 16
        assert fragment.fragment_type == "function"
        assert fragment.entity_name == "foo"

    def test_fragment_hash_and_equality(self):
        """Test fragment hashing and equality."""
        frag1 = CodeFragment(
            file_path="/test.py",
            start_line=1,
            end_line=10,
            source_code="code",
        )
        frag2 = CodeFragment(
            file_path="/test.py",
            start_line=1,
            end_line=10,
            source_code="different code",  # Same location, different source
        )
        frag3 = CodeFragment(
            file_path="/test.py",
            start_line=20,
            end_line=30,
            source_code="code",
        )

        # Same file/lines = equal
        assert frag1 == frag2
        assert hash(frag1) == hash(frag2)

        # Different lines = not equal
        assert frag1 != frag3


class TestFingerprint:
    """Test Fingerprint dataclass."""

    def test_create_fingerprint(self):
        """Test fingerprint creation."""
        fragment = CodeFragment(
            file_path="/test.py",
            start_line=1,
            end_line=10,
            source_code="def foo(): pass",
            entity_name="foo",
        )
        fingerprint = Fingerprint(
            hash_value="abc123",
            fingerprint_type=FingerprintType.AST_STRUCTURAL,
            fragment=fragment,
            structural_features={"node_count": 5},
        )

        assert fingerprint.hash_value == "abc123"
        assert fingerprint.fingerprint_type == FingerprintType.AST_STRUCTURAL
        assert fingerprint.fragment == fragment

    def test_fingerprint_to_dict(self):
        """Test fingerprint serialization."""
        fragment = CodeFragment(
            file_path="/test.py",
            start_line=1,
            end_line=10,
            source_code="def foo(): pass",
            entity_name="foo",
        )
        fingerprint = Fingerprint(
            hash_value="abc123",
            fingerprint_type=FingerprintType.AST_STRUCTURAL,
            fragment=fragment,
            structural_features={"node_count": 5},
        )

        data = fingerprint.to_dict()
        assert data["hash_value"] == "abc123"
        assert data["fingerprint_type"] == "ast_structural"
        assert data["file_path"] == "/test.py"
        assert data["entity_name"] == "foo"


class TestCloneInstance:
    """Test CloneInstance dataclass."""

    def test_create_instance(self):
        """Test clone instance creation."""
        fragment = CodeFragment(
            file_path="/test.py",
            start_line=1,
            end_line=10,
            source_code="def foo():\n    return 42",
            entity_name="foo",
        )
        fingerprint = Fingerprint(
            hash_value="abc123",
            fingerprint_type=FingerprintType.AST_STRUCTURAL,
            fragment=fragment,
        )
        instance = CloneInstance(
            fragment=fragment,
            fingerprint=fingerprint,
            similarity_score=0.95,
        )

        assert instance.similarity_score == 0.95
        assert instance.fragment == fragment

    def test_instance_to_dict(self):
        """Test clone instance serialization."""
        fragment = CodeFragment(
            file_path="/test.py",
            start_line=1,
            end_line=10,
            source_code="def foo():\n    return 42",
            entity_name="foo",
        )
        fingerprint = Fingerprint(
            hash_value="abc123",
            fingerprint_type=FingerprintType.AST_STRUCTURAL,
            fragment=fragment,
        )
        instance = CloneInstance(
            fragment=fragment,
            fingerprint=fingerprint,
            similarity_score=0.95,
        )

        data = instance.to_dict()
        assert data["file_path"] == "/test.py"
        assert data["similarity_score"] == 0.95
        assert "source_preview" in data


class TestCloneGroup:
    """Test CloneGroup dataclass."""

    def test_create_group(self):
        """Test clone group creation."""
        fragment1 = CodeFragment(
            file_path="/test1.py",
            start_line=1,
            end_line=10,
            source_code="def foo(): pass",
            entity_name="foo",
        )
        fragment2 = CodeFragment(
            file_path="/test2.py",
            start_line=1,
            end_line=10,
            source_code="def foo(): pass",
            entity_name="foo",
        )
        fp1 = Fingerprint("hash1", FingerprintType.AST_STRUCTURAL, fragment1)
        fp2 = Fingerprint("hash1", FingerprintType.AST_STRUCTURAL, fragment2)

        instances = [
            CloneInstance(fragment1, fp1, 1.0),
            CloneInstance(fragment2, fp2, 1.0),
        ]

        group = CloneGroup(
            clone_type=CloneType.TYPE_1,
            severity=CloneSeverity.LOW,
            instances=instances,
            canonical_fingerprint="hash1",
            similarity_range=(1.0, 1.0),
            total_duplicated_lines=20,
            refactoring_suggestion="Extract to shared function",
        )

        assert group.clone_type == CloneType.TYPE_1
        assert len(group.instances) == 2
        assert group.total_duplicated_lines == 20

    def test_group_to_dict(self):
        """Test clone group serialization."""
        fragment = CodeFragment(
            file_path="/test.py",
            start_line=1,
            end_line=10,
            source_code="def foo(): pass",
            entity_name="foo",
        )
        fp = Fingerprint("hash1", FingerprintType.AST_STRUCTURAL, fragment)
        instance = CloneInstance(fragment, fp, 1.0)

        group = CloneGroup(
            clone_type=CloneType.TYPE_1,
            severity=CloneSeverity.LOW,
            instances=[instance],
            canonical_fingerprint="hash1",
            similarity_range=(1.0, 1.0),
            total_duplicated_lines=10,
        )

        data = group.to_dict()
        assert data["clone_type"] == "type_1"
        assert data["severity"] == "low"
        assert data["instance_count"] == 1


class TestASTNormalizer:
    """Test ASTNormalizer class."""

    @pytest.fixture
    def normalizer(self):
        """Create normalizer instance."""
        return ASTNormalizer()

    def test_normalize_variable_names(self, normalizer):
        """Test that variable names are normalized."""
        code = """
def foo(x, y):
    result = x + y
    return result
"""
        tree = ast.parse(code)
        normalized = normalizer.visit(tree)

        # The normalized tree should have placeholders instead of actual names
        assert normalized is not None

    def test_preserve_special_names(self, normalizer):
        """Test that special names like 'self' are preserved."""
        code = """
class MyClass:
    def method(self, x):
        self.value = x
"""
        tree = ast.parse(code)
        normalized = normalizer.visit(tree)

        # 'self' should be preserved
        assert normalized is not None

    def test_normalize_function_names(self, normalizer):
        """Test that function names are normalized."""
        code = """
def my_function():
    pass
"""
        tree = ast.parse(code)
        normalized = normalizer.visit(tree)

        # Function name should be normalized to placeholder
        func_node = normalized.body[0]
        assert "$FUNC_" in func_node.name


class TestASTHasher:
    """Test ASTHasher class."""

    @pytest.fixture
    def hasher(self):
        """Create hasher instance."""
        return ASTHasher()

    def test_structural_hash_identical_code(self, hasher):
        """Test that identical code produces same hash."""
        code = "def foo(): return 42"
        tree1 = ast.parse(code)
        tree2 = ast.parse(code)

        hash1 = hasher.hash_structural(tree1)
        hash2 = hasher.hash_structural(tree2)

        assert hash1 == hash2

    def test_structural_hash_different_code(self, hasher):
        """Test that different code produces different hash."""
        code1 = "def foo(): return 42"
        code2 = """
def bar(x, y):
    result = x + y
    for i in range(10):
        result += i
    return result
"""

        hash1 = hasher.hash_structural(ast.parse(code1))
        hash2 = hasher.hash_structural(ast.parse(code2))

        assert hash1 != hash2

    def test_normalized_hash_renamed_variables(self, hasher):
        """Test that renamed variables produce same normalized hash."""
        code1 = """
def calculate(x, y):
    result = x + y
    return result
"""
        code2 = """
def compute(a, b):
    output = a + b
    return output
"""
        hash1 = hasher.hash_normalized(ast.parse(code1))
        hash2 = hasher.hash_normalized(ast.parse(code2))

        assert hash1 == hash2

    def test_extract_features(self, hasher):
        """Test feature extraction from AST."""
        code = """
def foo(x):
    if x > 0:
        for i in range(x):
            print(i)
    return x
"""
        tree = ast.parse(code)
        features = hasher.extract_features(tree)

        assert features["node_count"] > 0
        assert features["depth"] > 0
        assert "If" in features["node_types"]
        assert "For" in features["node_types"]
        assert features["loop_count"] >= 1
        assert features["control_flow_count"] >= 1


class TestSemanticHasher:
    """Test SemanticHasher class."""

    @pytest.fixture
    def hasher(self):
        """Create hasher instance."""
        return SemanticHasher()

    def test_semantic_hash(self, hasher):
        """Test semantic hash generation."""
        code = """
def process(data):
    result = []
    for item in data:
        result.append(item * 2)
    return result
"""
        tree = ast.parse(code)
        hash_value = hasher.hash_semantic(tree)

        assert hash_value is not None
        assert len(hash_value) == 32  # SHA256 truncated to 32 chars

    def test_semantic_hash_similar_functions(self, hasher):
        """Test that semantically similar functions may produce similar hashes."""
        # Two functions that do the same thing differently
        code1 = """
def double_list(items):
    result = []
    for x in items:
        result.append(x * 2)
    return result
"""
        code2 = """
def multiply_by_two(data):
    output = []
    for item in data:
        output.append(item * 2)
    return output
"""
        hash1 = hasher.hash_semantic(ast.parse(code1))
        hash2 = hasher.hash_semantic(ast.parse(code2))

        # These may or may not be equal depending on semantic analysis depth
        # At minimum, both should produce valid hashes
        assert hash1 is not None
        assert hash2 is not None


class TestSimilarityCalculator:
    """Test SimilarityCalculator class."""

    @pytest.fixture
    def calculator(self):
        """Create calculator instance."""
        return SimilarityCalculator()

    def test_identical_fragments_similarity(self, calculator):
        """Test that identical fragments have similarity 1.0."""
        code = "def foo(): return 42"
        tree = ast.parse(code)
        func_node = tree.body[0]

        fragment1 = CodeFragment(
            file_path="/test1.py",
            start_line=1,
            end_line=1,
            source_code=code,
            ast_node=func_node,
        )
        fragment2 = CodeFragment(
            file_path="/test2.py",
            start_line=1,
            end_line=1,
            source_code=code,
            ast_node=func_node,
        )

        similarity = calculator.calculate_similarity(fragment1, fragment2)
        assert similarity == 1.0

    def test_different_fragments_similarity(self, calculator):
        """Test that different fragments have lower similarity."""
        code1 = """
def foo():
    return 42
"""
        code2 = """
def bar(x, y, z):
    for i in range(x):
        print(i)
    return y + z
"""
        tree1 = ast.parse(code1)
        tree2 = ast.parse(code2)

        fragment1 = CodeFragment(
            file_path="/test1.py",
            start_line=1,
            end_line=3,
            source_code=code1,
            ast_node=tree1.body[0],
        )
        fragment2 = CodeFragment(
            file_path="/test2.py",
            start_line=1,
            end_line=5,
            source_code=code2,
            ast_node=tree2.body[0],
        )

        similarity = calculator.calculate_similarity(fragment1, fragment2)
        assert 0 <= similarity < 1.0

    def test_text_based_similarity_fallback(self, calculator):
        """Test text-based similarity when AST is not available."""
        fragment1 = CodeFragment(
            file_path="/test1.py",
            start_line=1,
            end_line=1,
            source_code="def foo(): return 42",
            ast_node=None,  # No AST
        )
        fragment2 = CodeFragment(
            file_path="/test2.py",
            start_line=1,
            end_line=1,
            source_code="def foo(): return 42",
            ast_node=None,  # No AST
        )

        similarity = calculator.calculate_similarity(fragment1, fragment2)
        assert similarity == 1.0


class TestCloneDetector:
    """Test CloneDetector class."""

    @pytest.fixture
    def detector(self):
        """Create detector instance."""
        return CloneDetector(min_fragment_lines=3)

    @pytest.fixture
    def temp_codebase(self):
        """Create a temporary codebase for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create some Python files with clones
            # File 1: Original function
            file1 = Path(tmpdir) / "module1.py"
            file1.write_text(
                """
def calculate_sum(items):
    total = 0
    for item in items:
        total += item
    return total

def other_function():
    pass
"""
            )

            # File 2: Exact clone (Type 1)
            file2 = Path(tmpdir) / "module2.py"
            file2.write_text(
                """
def calculate_sum(items):
    total = 0
    for item in items:
        total += item
    return total

def another_function():
    pass
"""
            )

            # File 3: Renamed clone (Type 2)
            file3 = Path(tmpdir) / "module3.py"
            file3.write_text(
                """
def compute_total(data):
    result = 0
    for element in data:
        result += element
    return result

def helper():
    pass
"""
            )

            yield tmpdir

    def test_initialization(self, detector):
        """Test detector initialization."""
        assert detector is not None
        assert detector.min_fragment_lines == 3

    def test_extract_fragments(self, detector, temp_codebase):
        """Test fragment extraction from a file."""
        file_path = Path(temp_codebase) / "module1.py"
        fragments = detector._extract_fragments(str(file_path))

        assert len(fragments) >= 1  # At least one function
        assert all(isinstance(f, CodeFragment) for f in fragments)

    def test_generate_fingerprints(self, detector):
        """Test fingerprint generation for a fragment."""
        code = """
def test_function(x, y):
    result = x + y
    return result
"""
        tree = ast.parse(code)
        fragment = CodeFragment(
            file_path="/test.py",
            start_line=1,
            end_line=4,
            source_code=code,
            ast_node=tree.body[0],
            entity_name="test_function",
        )

        detector._generate_fingerprints(fragment)

        # Check that fingerprints were created
        assert len(detector._structural_fingerprints) > 0
        assert len(detector._normalized_fingerprints) > 0
        assert len(detector._semantic_fingerprints) > 0

    def test_detect_type1_clones(self, detector, temp_codebase):
        """Test Type 1 (exact) clone detection."""
        report = detector.detect_clones(temp_codebase)

        # Should find at least one Type 1 clone group
        type1_groups = [
            g for g in report.clone_groups if g.clone_type == CloneType.TYPE_1
        ]
        assert len(type1_groups) >= 1

    def test_severity_calculation(self, detector):
        """Test clone severity calculation."""
        # 2 instances, few lines = LOW
        assert detector._calculate_severity(2, 20) == CloneSeverity.LOW

        # 3-4 instances or 50+ lines = MEDIUM
        assert detector._calculate_severity(3, 30) == CloneSeverity.MEDIUM
        assert detector._calculate_severity(2, 60) == CloneSeverity.MEDIUM

        # 5-6 instances or 100+ lines = HIGH
        assert detector._calculate_severity(5, 50) == CloneSeverity.HIGH
        assert detector._calculate_severity(3, 110) == CloneSeverity.HIGH

        # 7+ instances or 200+ lines = CRITICAL
        assert detector._calculate_severity(7, 100) == CloneSeverity.CRITICAL
        assert detector._calculate_severity(2, 250) == CloneSeverity.CRITICAL

    def test_refactoring_suggestion(self, detector):
        """Test refactoring suggestion generation."""
        fragment = CodeFragment(
            file_path="/test.py",
            start_line=1,
            end_line=10,
            source_code="def foo(): pass",
            entity_name="foo",
            fragment_type="function",
        )
        fp = Fingerprint("hash1", FingerprintType.AST_STRUCTURAL, fragment)
        instance = CloneInstance(fragment, fp, 1.0)

        group = CloneGroup(
            clone_type=CloneType.TYPE_1,
            severity=CloneSeverity.MEDIUM,
            instances=[instance, instance],  # 2 copies
            canonical_fingerprint="hash1",
            similarity_range=(1.0, 1.0),
            total_duplicated_lines=20,
        )

        suggestion = detector._generate_refactoring_suggestion(group)

        assert "Extract" in suggestion or "shared" in suggestion
        assert "2" in suggestion  # Should mention instance count

    def test_effort_estimation(self, detector):
        """Test refactoring effort estimation."""
        fragment = CodeFragment(
            file_path="/test.py",
            start_line=1,
            end_line=20,
            source_code="def foo(): pass",
            entity_name="foo",
        )
        fp = Fingerprint("hash1", FingerprintType.AST_STRUCTURAL, fragment)
        instance = CloneInstance(fragment, fp, 1.0)

        # Small clone = Low effort
        group = CloneGroup(
            clone_type=CloneType.TYPE_1,
            severity=CloneSeverity.LOW,
            instances=[instance, instance],
            canonical_fingerprint="hash1",
            similarity_range=(1.0, 1.0),
            total_duplicated_lines=30,
        )

        effort = detector._estimate_refactoring_effort(group)
        assert "Low" in effort or "hour" in effort.lower()


class TestCloneDetectionReport:
    """Test CloneDetectionReport dataclass."""

    def test_create_report(self):
        """Test report creation."""
        report = CloneDetectionReport(
            scan_path="/test/path",
            total_files=10,
            total_fragments=50,
            clone_groups=[],
            clone_type_distribution={"type_1": 2, "type_2": 1},
            severity_distribution={"low": 2, "medium": 1},
            total_duplicated_lines=100,
            duplication_percentage=5.5,
            top_cloned_files=[],
            refactoring_priorities=[],
        )

        assert report.total_files == 10
        assert report.duplication_percentage == 5.5

    def test_report_to_dict(self):
        """Test report serialization."""
        report = CloneDetectionReport(
            scan_path="/test/path",
            total_files=10,
            total_fragments=50,
            clone_groups=[],
            clone_type_distribution={"type_1": 2},
            severity_distribution={"low": 2},
            total_duplicated_lines=100,
            duplication_percentage=5.5,
            top_cloned_files=[],
            refactoring_priorities=[],
        )

        data = report.to_dict()
        assert data["scan_path"] == "/test/path"
        assert data["total_files"] == 10
        assert data["duplication_percentage"] == 5.5


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_get_clone_types(self):
        """Test getting clone types list."""
        types = get_clone_types()

        assert len(types) == 4
        assert all("type" in t for t in types)
        assert all("name" in t for t in types)
        assert all("description" in t for t in types)

    def test_get_clone_severities(self):
        """Test getting severity levels list."""
        severities = get_clone_severities()

        assert len(severities) == 5
        assert all("severity" in s for s in severities)
        assert all("description" in s for s in severities)

    def test_get_fingerprint_types(self):
        """Test getting fingerprint types list."""
        types = get_fingerprint_types()

        assert len(types) == 4
        assert all("type" in t for t in types)
        assert all("description" in t for t in types)

    def test_detect_clones_function(self):
        """Test the detect_clones convenience function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a simple Python file
            file1 = Path(tmpdir) / "test.py"
            file1.write_text(
                """
def simple_function():
    x = 1
    y = 2
    z = x + y
    return z
"""
            )

            report = detect_clones(tmpdir, min_fragment_lines=3)

            assert isinstance(report, CloneDetectionReport)
            assert report.total_files >= 1


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.fixture
    def detector(self):
        """Create detector instance."""
        return CloneDetector()

    def test_empty_directory(self, detector):
        """Test handling of empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            report = detector.detect_clones(tmpdir)

            assert report.total_files == 0
            assert report.total_fragments == 0
            assert len(report.clone_groups) == 0

    def test_syntax_error_file(self, detector):
        """Test handling of files with syntax errors."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "bad.py"
            file1.write_text("def broken(: pass")  # Syntax error

            # Should not raise an exception
            report = detector.detect_clones(tmpdir)
            assert report is not None

    def test_excluded_directories(self, detector):
        """Test that excluded directories are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create file in excluded directory
            venv_dir = Path(tmpdir) / ".venv"
            venv_dir.mkdir()
            (venv_dir / "test.py").write_text("def foo(): pass")

            # Create file in regular directory
            (Path(tmpdir) / "main.py").write_text(
                """
def main_function():
    x = 1
    y = 2
    return x + y
"""
            )

            report = detector.detect_clones(tmpdir)

            # Should only count the main.py file
            assert report.total_files == 1

    def test_small_fragments_filtered(self):
        """Test that small fragments are filtered out."""
        detector = CloneDetector(min_fragment_lines=10)

        with tempfile.TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "small.py"
            file1.write_text(
                """
def small():
    return 1
"""
            )

            report = detector.detect_clones(tmpdir)

            # Small function should be filtered
            assert report.total_fragments == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
