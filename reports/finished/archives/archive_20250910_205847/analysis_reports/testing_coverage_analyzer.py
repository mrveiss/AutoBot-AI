"""
Testing Coverage Gap Analyzer using Redis and NPU acceleration
Analyzes codebase for testing gaps, missing test patterns, and coverage issues
"""

import ast
import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any, Union

from src.utils.redis_client import get_redis_client
from src.config import config

logger = logging.getLogger(__name__)


@dataclass
class CodeFunction:
    """Represents a function in the codebase"""
    file_path: str
    name: str
    line_number: int
    parameters: List[str]
    return_type: Optional[str]
    is_async: bool
    complexity: int
    is_public: bool  # Not starting with _
    has_docstring: bool
    calls_external_apis: bool
    has_database_operations: bool
    has_file_operations: bool


@dataclass
class TestFunction:
    """Represents a test function"""
    file_path: str
    name: str
    line_number: int
    target_function: Optional[str]
    test_type: str  # unit, integration, e2e
    has_assertions: bool
    has_mocking: bool
    has_setup_teardown: bool
    covers_edge_cases: bool


@dataclass
class CoverageGap:
    """Represents a testing coverage gap"""
    gap_type: str  # untested_function, missing_edge_cases, no_integration_tests
    severity: str  # critical, high, medium, low
    description: str
    affected_functions: List[CodeFunction]
    suggested_tests: List[str]
    priority_score: int


@dataclass
class TestingMetrics:
    """Testing coverage metrics"""
    total_functions: int
    tested_functions: int
    untested_functions: int
    test_coverage_percentage: float
    critical_untested_functions: int
    missing_integration_tests: int
    missing_edge_case_tests: int


class TestingCoverageAnalyzer:
    """Analyzes testing coverage and identifies gaps"""
    
    def __init__(self, redis_client=None):
        self.redis_client = redis_client or get_redis_client(async_client=True)
        self.config = config
        
        # Caching keys
        self.COVERAGE_KEY = "testing_analysis:coverage"
        self.GAPS_KEY = "testing_analysis:gaps"
        
        # Test file patterns
        self.test_patterns = [
            r'test_.*\.py$',
            r'.*_test\.py$',
            r'tests/.*\.py$'
        ]
        
        # Test function patterns
        self.test_function_patterns = [
            r'^test_',
            r'_test$',
            r'^should_'
        ]
        
        logger.info("Testing Coverage Analyzer initialized")
    
    async def analyze_testing_coverage(self, root_path: str = ".", patterns: List[str] = None) -> Dict[str, Any]:
        """Analyze testing coverage and identify gaps"""
        
        start_time = time.time()
        patterns = patterns or ["**/*.py"]
        
        # Clear previous analysis cache
        await self._clear_cache()
        
        logger.info(f"Analyzing testing coverage in {root_path}")
        
        # Discover all functions
        logger.info("Discovering all functions in codebase")
        all_functions = await self._discover_all_functions(root_path, patterns)
        logger.info(f"Found {len(all_functions)} functions")
        
        # Discover all test functions
        logger.info("Discovering test functions")
        test_functions = await self._discover_test_functions(root_path, patterns)
        logger.info(f"Found {len(test_functions)} test functions")
        
        # Analyze coverage gaps
        logger.info("Analyzing coverage gaps")
        coverage_gaps = await self._analyze_coverage_gaps(all_functions, test_functions)
        
        # Calculate testing metrics
        metrics = self._calculate_testing_metrics(all_functions, test_functions, coverage_gaps)
        
        # Generate test recommendations
        recommendations = await self._generate_test_recommendations(coverage_gaps)
        
        analysis_time = time.time() - start_time
        
        results = {
            "total_functions": len(all_functions),
            "total_tests": len(test_functions),
            "coverage_gaps": len(coverage_gaps),
            "test_coverage_percentage": metrics.test_coverage_percentage,
            "analysis_time_seconds": analysis_time,
            "functions": [self._serialize_function(f) for f in all_functions],
            "test_functions": [self._serialize_test_function(t) for t in test_functions],
            "coverage_gaps": [self._serialize_coverage_gap(g) for g in coverage_gaps],
            "recommendations": recommendations,
            "metrics": {
                "total_functions": metrics.total_functions,
                "tested_functions": metrics.tested_functions,
                "untested_functions": metrics.untested_functions,
                "test_coverage_percentage": metrics.test_coverage_percentage,
                "critical_untested_functions": metrics.critical_untested_functions,
                "missing_integration_tests": metrics.missing_integration_tests,
                "missing_edge_case_tests": metrics.missing_edge_case_tests,
            }
        }
        
        # Cache results
        await self._cache_results(results)
        
        logger.info(f"Testing coverage analysis complete in {analysis_time:.2f}s")
        return results
    
    async def _discover_all_functions(self, root_path: str, patterns: List[str]) -> List[CodeFunction]:
        """Discover all functions in the codebase"""
        
        functions = []
        root = Path(root_path)
        
        for pattern in patterns:
            for file_path in root.glob(pattern):
                if file_path.is_file() and not self._should_skip_file(file_path) and not self._is_test_file(file_path):
                    try:
                        file_functions = await self._extract_functions_from_file(str(file_path))
                        functions.extend(file_functions)
                    except Exception as e:
                        logger.warning(f"Failed to extract functions from {file_path}: {e}")
        
        return functions
    
    async def _discover_test_functions(self, root_path: str, patterns: List[str]) -> List[TestFunction]:
        """Discover all test functions"""
        
        test_functions = []
        root = Path(root_path)
        
        for pattern in patterns:
            for file_path in root.glob(pattern):
                if file_path.is_file() and self._is_test_file(file_path):
                    try:
                        file_tests = await self._extract_test_functions_from_file(str(file_path))
                        test_functions.extend(file_tests)
                    except Exception as e:
                        logger.warning(f"Failed to extract test functions from {file_path}: {e}")
        
        return test_functions
    
    def _should_skip_file(self, file_path: Path) -> bool:
        """Check if file should be skipped"""
        skip_patterns = [
            "__pycache__", ".git", "node_modules", ".venv", "venv",
            ".pyc", "analyzer", "__init__.py"
        ]
        
        path_str = str(file_path)
        return any(pattern in path_str for pattern in skip_patterns)
    
    def _is_test_file(self, file_path: Path) -> bool:
        """Check if file is a test file"""
        path_str = str(file_path)
        return any(re.search(pattern, path_str) for pattern in self.test_patterns)
    
    async def _extract_functions_from_file(self, file_path: str) -> List[CodeFunction]:
        """Extract functions from a file"""
        
        functions = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content, filename=file_path)
            
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    func = self._analyze_function(node, file_path, content)
                    if func:
                        functions.append(func)
        
        except SyntaxError:
            # Skip files with syntax errors
            pass
        except Exception as e:
            logger.error(f"Error extracting functions from {file_path}: {e}")
        
        return functions
    
    def _analyze_function(self, node: ast.AST, file_path: str, content: str) -> Optional[CodeFunction]:
        """Analyze a function node"""
        
        try:
            # Extract parameters
            parameters = []
            if hasattr(node, 'args'):
                for arg in node.args.args:
                    if arg.arg != 'self':
                        parameters.append(arg.arg)
            
            # Extract return type
            return_type = None
            if hasattr(node, 'returns') and node.returns:
                return_type = ast.unparse(node.returns) if hasattr(ast, 'unparse') else str(node.returns)
            
            # Check if function is async
            is_async = isinstance(node, ast.AsyncFunctionDef)
            
            # Calculate complexity (simplified)
            complexity = self._calculate_function_complexity(node)
            
            # Check if public function (not starting with _)
            is_public = not node.name.startswith('_')
            
            # Check if has docstring
            has_docstring = ast.get_docstring(node) is not None
            
            # Check for external API calls
            calls_external_apis = self._function_calls_external_apis(node)
            
            # Check for database operations
            has_database_operations = self._function_has_database_ops(node)
            
            # Check for file operations
            has_file_operations = self._function_has_file_ops(node)
            
            return CodeFunction(
                file_path=file_path,
                name=node.name,
                line_number=node.lineno,
                parameters=parameters,
                return_type=return_type,
                is_async=is_async,
                complexity=complexity,
                is_public=is_public,
                has_docstring=has_docstring,
                calls_external_apis=calls_external_apis,
                has_database_operations=has_database_operations,
                has_file_operations=has_file_operations
            )
            
        except Exception as e:
            logger.error(f"Error analyzing function {node.name}: {e}")
            return None
    
    def _calculate_function_complexity(self, node: ast.AST) -> int:
        """Calculate cyclomatic complexity"""
        complexity = 1  # Base complexity
        
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For)):
                complexity += 1
            elif isinstance(child, ast.ExceptHandler):
                complexity += 1
            elif isinstance(child, (ast.And, ast.Or)):
                complexity += 1
        
        return complexity
    
    def _function_calls_external_apis(self, node: ast.AST) -> bool:
        """Check if function calls external APIs"""
        external_patterns = ['requests.', 'urllib.', 'httpx.', 'aiohttp.']
        
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                call_str = ast.unparse(child) if hasattr(ast, 'unparse') else str(child)
                if any(pattern in call_str for pattern in external_patterns):
                    return True
        
        return False
    
    def _function_has_database_ops(self, node: ast.AST) -> bool:
        """Check if function has database operations"""
        db_patterns = ['execute', 'query', 'insert', 'update', 'delete', 'cursor', 'session']
        
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                call_str = ast.unparse(child) if hasattr(ast, 'unparse') else str(child)
                if any(pattern in call_str.lower() for pattern in db_patterns):
                    return True
        
        return False
    
    def _function_has_file_ops(self, node: ast.AST) -> bool:
        """Check if function has file operations"""
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name) and child.func.id == 'open':
                    return True
                elif isinstance(child.func, ast.Attribute) and child.func.attr in ['read', 'write', 'close']:
                    return True
        
        return False
    
    async def _extract_test_functions_from_file(self, file_path: str) -> List[TestFunction]:
        """Extract test functions from a test file"""
        
        test_functions = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content, filename=file_path)
            
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if self._is_test_function(node.name):
                        test_func = self._analyze_test_function(node, file_path, content)
                        if test_func:
                            test_functions.append(test_func)
        
        except SyntaxError:
            # Skip files with syntax errors
            pass
        except Exception as e:
            logger.error(f"Error extracting test functions from {file_path}: {e}")
        
        return test_functions
    
    def _is_test_function(self, function_name: str) -> bool:
        """Check if function name indicates it's a test"""
        return any(re.search(pattern, function_name) for pattern in self.test_function_patterns)
    
    def _analyze_test_function(self, node: ast.AST, file_path: str, content: str) -> Optional[TestFunction]:
        """Analyze a test function"""
        
        try:
            # Try to determine target function from test name
            target_function = self._extract_target_function_from_name(node.name)
            
            # Determine test type based on content and location
            test_type = self._determine_test_type(node, file_path, content)
            
            # Check for assertions
            has_assertions = self._test_has_assertions(node)
            
            # Check for mocking
            has_mocking = self._test_has_mocking(node, content)
            
            # Check for setup/teardown
            has_setup_teardown = self._test_has_setup_teardown(node, content)
            
            # Check if covers edge cases (heuristic)
            covers_edge_cases = self._test_covers_edge_cases(node, content)
            
            return TestFunction(
                file_path=file_path,
                name=node.name,
                line_number=node.lineno,
                target_function=target_function,
                test_type=test_type,
                has_assertions=has_assertions,
                has_mocking=has_mocking,
                has_setup_teardown=has_setup_teardown,
                covers_edge_cases=covers_edge_cases
            )
            
        except Exception as e:
            logger.error(f"Error analyzing test function {node.name}: {e}")
            return None
    
    def _extract_target_function_from_name(self, test_name: str) -> Optional[str]:
        """Extract target function from test name"""
        # Remove test prefixes
        cleaned_name = test_name
        
        if cleaned_name.startswith('test_'):
            cleaned_name = cleaned_name[5:]
        elif cleaned_name.startswith('should_'):
            cleaned_name = cleaned_name[7:]
        elif cleaned_name.endswith('_test'):
            cleaned_name = cleaned_name[:-5]
        
        return cleaned_name if cleaned_name != test_name else None
    
    def _determine_test_type(self, node: ast.AST, file_path: str, content: str) -> str:
        """Determine test type (unit, integration, e2e)"""
        
        # Check file path for indicators
        if 'integration' in file_path.lower():
            return 'integration'
        elif 'e2e' in file_path.lower() or 'end_to_end' in file_path.lower():
            return 'e2e'
        
        # Check function content for indicators
        function_content = ast.unparse(node) if hasattr(ast, 'unparse') else str(node)
        
        if any(indicator in function_content.lower() for indicator in ['database', 'db', 'api', 'request']):
            return 'integration'
        elif any(indicator in function_content.lower() for indicator in ['selenium', 'playwright', 'browser']):
            return 'e2e'
        else:
            return 'unit'
    
    def _test_has_assertions(self, node: ast.AST) -> bool:
        """Check if test has assertions"""
        for child in ast.walk(node):
            if isinstance(child, ast.Assert):
                return True
            elif isinstance(child, ast.Call):
                call_str = ast.unparse(child) if hasattr(ast, 'unparse') else str(child)
                if any(assert_pattern in call_str for assert_pattern in ['assert', 'expect', 'should']):
                    return True
        
        return False
    
    def _test_has_mocking(self, node: ast.AST, content: str) -> bool:
        """Check if test uses mocking"""
        function_content = ast.unparse(node) if hasattr(ast, 'unparse') else str(node)
        mock_patterns = ['mock', 'patch', 'Mock', 'MagicMock', 'stub']
        
        return any(pattern in function_content for pattern in mock_patterns)
    
    def _test_has_setup_teardown(self, node: ast.AST, content: str) -> bool:
        """Check if test has setup/teardown"""
        function_content = ast.unparse(node) if hasattr(ast, 'unparse') else str(node)
        setup_patterns = ['setUp', 'tearDown', 'setup', 'teardown', 'beforeEach', 'afterEach']
        
        return any(pattern in function_content for pattern in setup_patterns)
    
    def _test_covers_edge_cases(self, node: ast.AST, content: str) -> bool:
        """Check if test covers edge cases (heuristic)"""
        function_content = ast.unparse(node) if hasattr(ast, 'unparse') else str(node)
        edge_case_indicators = [
            'edge', 'boundary', 'limit', 'empty', 'null', 'none', 'zero',
            'negative', 'invalid', 'error', 'exception', 'fail'
        ]
        
        return any(indicator in function_content.lower() for indicator in edge_case_indicators)
    
    async def _analyze_coverage_gaps(self, functions: List[CodeFunction], tests: List[TestFunction]) -> List[CoverageGap]:
        """Analyze coverage gaps between functions and tests"""
        
        gaps = []
        
        # Create mapping of tested functions
        tested_functions = set()
        for test in tests:
            if test.target_function:
                tested_functions.add(test.target_function)
        
        # Find untested functions
        untested_functions = []
        for func in functions:
            if func.name not in tested_functions and func.is_public:
                untested_functions.append(func)
        
        # Categorize untested functions by severity
        critical_untested = [f for f in untested_functions if self._is_critical_function(f)]
        high_priority_untested = [f for f in untested_functions if self._is_high_priority_function(f)]
        
        # Create coverage gaps
        if critical_untested:
            gaps.append(CoverageGap(
                gap_type='critical_untested_functions',
                severity='critical',
                description=f"{len(critical_untested)} critical functions lack tests",
                affected_functions=critical_untested,
                suggested_tests=self._suggest_tests_for_functions(critical_untested),
                priority_score=100
            ))
        
        if high_priority_untested:
            gaps.append(CoverageGap(
                gap_type='high_priority_untested_functions',
                severity='high',
                description=f"{len(high_priority_untested)} high-priority functions lack tests",
                affected_functions=high_priority_untested,
                suggested_tests=self._suggest_tests_for_functions(high_priority_untested),
                priority_score=80
            ))
        
        # Check for missing integration tests
        functions_needing_integration_tests = [
            f for f in functions 
            if (f.calls_external_apis or f.has_database_operations) and f.is_public
        ]
        
        integration_tests = [t for t in tests if t.test_type == 'integration']
        
        if len(functions_needing_integration_tests) > len(integration_tests):
            gaps.append(CoverageGap(
                gap_type='missing_integration_tests',
                severity='high',
                description=f"Missing integration tests for {len(functions_needing_integration_tests)} functions with external dependencies",
                affected_functions=functions_needing_integration_tests,
                suggested_tests=self._suggest_integration_tests(functions_needing_integration_tests),
                priority_score=75
            ))
        
        # Check for missing edge case tests
        complex_functions = [f for f in functions if f.complexity > 5 and f.is_public]
        edge_case_tests = [t for t in tests if t.covers_edge_cases]
        
        if len(complex_functions) > len(edge_case_tests):
            gaps.append(CoverageGap(
                gap_type='missing_edge_case_tests',
                severity='medium',
                description=f"Missing edge case tests for {len(complex_functions)} complex functions",
                affected_functions=complex_functions,
                suggested_tests=self._suggest_edge_case_tests(complex_functions),
                priority_score=60
            ))
        
        return gaps
    
    def _is_critical_function(self, func: CodeFunction) -> bool:
        """Check if function is critical and needs testing"""
        return (
            func.calls_external_apis or
            func.has_database_operations or
            func.has_file_operations or
            func.complexity > 8 or
            'auth' in func.name.lower() or
            'security' in func.name.lower()
        )
    
    def _is_high_priority_function(self, func: CodeFunction) -> bool:
        """Check if function is high priority for testing"""
        return (
            func.complexity > 3 or
            len(func.parameters) > 3 or
            func.is_async or
            'process' in func.name.lower() or
            'handle' in func.name.lower() or
            'execute' in func.name.lower()
        )
    
    def _suggest_tests_for_functions(self, functions: List[CodeFunction]) -> List[str]:
        """Suggest tests for functions"""
        suggestions = []
        
        for func in functions[:5]:  # Limit to first 5
            test_name = f"test_{func.name}"
            test_description = f"Unit test for {func.name}() function"
            
            if func.is_async:
                test_description += " (async test required)"
            if func.calls_external_apis:
                test_description += " (mock external APIs)"
            if func.has_database_operations:
                test_description += " (mock database)"
            
            suggestions.append(f"{test_name}: {test_description}")
        
        return suggestions
    
    def _suggest_integration_tests(self, functions: List[CodeFunction]) -> List[str]:
        """Suggest integration tests"""
        suggestions = []
        
        api_functions = [f for f in functions if f.calls_external_apis]
        db_functions = [f for f in functions if f.has_database_operations]
        
        if api_functions:
            suggestions.append("test_api_integration: Integration tests for API calls with real/test endpoints")
        
        if db_functions:
            suggestions.append("test_database_integration: Integration tests with test database")
        
        suggestions.append("test_end_to_end_workflow: Full workflow integration test")
        
        return suggestions
    
    def _suggest_edge_case_tests(self, functions: List[CodeFunction]) -> List[str]:
        """Suggest edge case tests"""
        suggestions = []
        
        for func in functions[:3]:  # Limit to first 3
            suggestions.append(f"test_{func.name}_with_empty_input: Test with empty/null inputs")
            suggestions.append(f"test_{func.name}_with_invalid_input: Test with invalid inputs")
            
            if func.complexity > 8:
                suggestions.append(f"test_{func.name}_boundary_conditions: Test boundary conditions")
        
        return suggestions
    
    def _calculate_testing_metrics(self, functions: List[CodeFunction], 
                                 tests: List[TestFunction], 
                                 gaps: List[CoverageGap]) -> TestingMetrics:
        """Calculate testing metrics"""
        
        # Count tested functions
        tested_function_names = set()
        for test in tests:
            if test.target_function:
                tested_function_names.add(test.target_function)
        
        public_functions = [f for f in functions if f.is_public]
        tested_functions = len([f for f in public_functions if f.name in tested_function_names])
        untested_functions = len(public_functions) - tested_functions
        
        test_coverage_percentage = (tested_functions / len(public_functions) * 100) if public_functions else 0
        
        # Count critical untested functions
        critical_untested = 0
        for gap in gaps:
            if gap.gap_type == 'critical_untested_functions':
                critical_untested = len(gap.affected_functions)
        
        # Count missing integration/edge case tests
        missing_integration_tests = 0
        missing_edge_case_tests = 0
        
        for gap in gaps:
            if gap.gap_type == 'missing_integration_tests':
                missing_integration_tests = len(gap.affected_functions)
            elif gap.gap_type == 'missing_edge_case_tests':
                missing_edge_case_tests = len(gap.affected_functions)
        
        return TestingMetrics(
            total_functions=len(public_functions),
            tested_functions=tested_functions,
            untested_functions=untested_functions,
            test_coverage_percentage=round(test_coverage_percentage, 1),
            critical_untested_functions=critical_untested,
            missing_integration_tests=missing_integration_tests,
            missing_edge_case_tests=missing_edge_case_tests
        )
    
    async def _generate_test_recommendations(self, gaps: List[CoverageGap]) -> List[str]:
        """Generate test improvement recommendations"""
        
        recommendations = []
        
        # Sort gaps by priority
        gaps.sort(key=lambda g: g.priority_score, reverse=True)
        
        for gap in gaps:
            if gap.gap_type == 'critical_untested_functions':
                recommendations.append(f"HIGH PRIORITY: Write unit tests for {len(gap.affected_functions)} critical functions")
            
            elif gap.gap_type == 'missing_integration_tests':
                recommendations.append(f"Add integration tests for functions with external dependencies")
            
            elif gap.gap_type == 'missing_edge_case_tests':
                recommendations.append(f"Add edge case and boundary condition tests for complex functions")
            
            else:
                recommendations.append(f"Address {gap.gap_type}: {gap.description}")
        
        # Add general recommendations
        recommendations.append("Set up automated test coverage reporting")
        recommendations.append("Implement test-driven development (TDD) for new features")
        recommendations.append("Add continuous integration (CI) to run tests on commits")
        
        return recommendations
    
    def _serialize_function(self, func: CodeFunction) -> Dict[str, Any]:
        """Serialize function for output"""
        return {
            "file": func.file_path,
            "name": func.name,
            "line": func.line_number,
            "parameters": func.parameters,
            "return_type": func.return_type,
            "is_async": func.is_async,
            "complexity": func.complexity,
            "is_public": func.is_public,
            "has_docstring": func.has_docstring,
            "calls_external_apis": func.calls_external_apis,
            "has_database_operations": func.has_database_operations,
            "has_file_operations": func.has_file_operations
        }
    
    def _serialize_test_function(self, test: TestFunction) -> Dict[str, Any]:
        """Serialize test function for output"""
        return {
            "file": test.file_path,
            "name": test.name,
            "line": test.line_number,
            "target_function": test.target_function,
            "test_type": test.test_type,
            "has_assertions": test.has_assertions,
            "has_mocking": test.has_mocking,
            "has_setup_teardown": test.has_setup_teardown,
            "covers_edge_cases": test.covers_edge_cases
        }
    
    def _serialize_coverage_gap(self, gap: CoverageGap) -> Dict[str, Any]:
        """Serialize coverage gap for output"""
        return {
            "type": gap.gap_type,
            "severity": gap.severity,
            "description": gap.description,
            "affected_functions_count": len(gap.affected_functions),
            "suggested_tests": gap.suggested_tests,
            "priority_score": gap.priority_score
        }
    
    async def _cache_results(self, results: Dict[str, Any]):
        """Cache analysis results in Redis"""
        if self.redis_client:
            try:
                key = self.COVERAGE_KEY
                value = json.dumps(results, default=str)
                await self.redis_client.setex(key, 3600, value)
            except Exception as e:
                logger.warning(f"Failed to cache results: {e}")
    
    async def _clear_cache(self):
        """Clear analysis cache"""
        if self.redis_client:
            try:
                cursor = 0
                while True:
                    cursor, keys = await self.redis_client.scan(
                        cursor,
                        match="testing_analysis:*",
                        count=100
                    )
                    if keys:
                        await self.redis_client.delete(*keys)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.warning(f"Failed to clear cache: {e}")


async def main():
    """Example usage of testing coverage analyzer"""
    
    analyzer = TestingCoverageAnalyzer()
    
    # Analyze testing coverage
    results = await analyzer.analyze_testing_coverage(
        root_path=".",
        patterns=["src/**/*.py", "backend/**/*.py", "tests/**/*.py"]
    )
    
    # Print summary
    print(f"\n=== Testing Coverage Analysis Results ===")
    print(f"Total functions: {results['total_functions']}")
    print(f"Total tests: {results['total_tests']}")
    print(f"Test coverage: {results['test_coverage_percentage']}%")
    print(f"Coverage gaps found: {results['coverage_gaps']}")
    print(f"Analysis time: {results['analysis_time_seconds']:.2f}s")
    
    # Print detailed metrics
    metrics = results['metrics']
    print(f"\n=== Detailed Metrics ===")
    print(f"Tested functions: {metrics['tested_functions']}")
    print(f"Untested functions: {metrics['untested_functions']}")
    print(f"Critical untested functions: {metrics['critical_untested_functions']}")
    print(f"Missing integration tests: {metrics['missing_integration_tests']}")
    print(f"Missing edge case tests: {metrics['missing_edge_case_tests']}")
    
    # Print coverage gaps
    if results['coverage_gaps']:
        print(f"\n=== Coverage Gaps ===")
        for gap in results['coverage_gaps']:
            print(f"{gap['type']} ({gap['severity']}): {gap['description']}")
            print(f"  Affects {gap['affected_functions_count']} functions")
            print(f"  Priority score: {gap['priority_score']}")
    
    # Print recommendations
    if results['recommendations']:
        print(f"\n=== Testing Recommendations ===")
        for i, rec in enumerate(results['recommendations'], 1):
            print(f"{i}. {rec}")


if __name__ == "__main__":
    asyncio.run(main())