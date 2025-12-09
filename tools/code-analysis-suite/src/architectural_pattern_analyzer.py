"""
Architectural Pattern Analyzer using Redis and NPU acceleration
Analyzes codebase for architectural patterns, design issues, and structural improvements
"""

import ast
import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any

from src.utils.redis_client import get_redis_client
from src.unified_config import UnifiedConfig


# Initialize unified config
config = UnifiedConfig()

# Issue #380: Module-level tuples for AST node type checks
_FUNC_OR_CLASS_TYPES = (ast.FunctionDef, ast.ClassDef)
_COMPLEXITY_BRANCH_TYPES = (ast.If, ast.While, ast.For, ast.ExceptHandler)
_BOOLEAN_OP_TYPES = (ast.And, ast.Or)
logger = logging.getLogger(__name__)


@dataclass
class ArchitecturalComponent:
    """Represents an architectural component in the codebase"""
    file_path: str
    component_type: str  # class, module, function, service
    name: str
    line_number: int
    dependencies: List[str]
    interfaces: List[str]
    is_abstract: bool
    coupling_score: int  # Number of dependencies
    cohesion_score: float  # Internal relationship strength
    complexity_score: int
    patterns: List[str]  # Detected patterns (singleton, factory, etc.)


@dataclass
class ArchitecturalIssue:
    """Represents an architectural issue or anti-pattern"""
    issue_type: str  # tight_coupling, god_class, circular_dependency, etc.
    severity: str  # critical, high, medium, low
    description: str
    affected_components: List[ArchitecturalComponent]
    suggestion: str
    refactoring_effort: str  # low, medium, high
    pattern_violation: Optional[str]


@dataclass
class ArchitecturalMetrics:
    """Architectural quality metrics"""
    total_components: int
    architecture_score: float  # 0-100
    coupling_score: float
    cohesion_score: float
    pattern_adherence_score: float
    maintainability_index: float
    abstraction_score: float
    instability_score: float


class ArchitecturalPatternAnalyzer:
    """Analyzes architectural patterns and design quality"""

    def __init__(self, redis_client=None):
        self.redis_client = redis_client or get_redis_client(async_client=True)
        self.config = config

        # Caching keys
        self.ARCHITECTURE_KEY = "architecture_analysis:components"
        self.ISSUES_KEY = "architecture_analysis:issues"

        # Design patterns to detect
        self.pattern_signatures = {
            'singleton': [
                (r'class\s+\w+.*?:\s*\n.*?__new__\s*\(.*?\)', 'Singleton pattern detected'),
                (r'_instance\s*=\s*None', 'Singleton instance variable'),
            ],
            'factory': [
                (r'def\s+create_\w+\s*\(', 'Factory method pattern'),
                (r'class\s+\w*Factory\w*', 'Factory class pattern'),
            ],
            'observer': [
                (r'def\s+(?:add_|remove_)(?:observer|listener)', 'Observer pattern'),
                (r'def\s+notify\s*\(', 'Observer notification method'),
            ],
            'decorator': [
                (r'@\w+', 'Decorator pattern usage'),
                (r'def\s+\w+\s*\(.*?\).*?->.*?:', 'Potential decorator'),
            ],
            'adapter': [
                (r'class\s+\w*Adapter\w*', 'Adapter pattern'),
                (r'def\s+adapt\s*\(', 'Adapter method'),
            ],
            'facade': [
                (r'class\s+\w*Facade\w*', 'Facade pattern'),
                (r'def\s+simplified_\w+', 'Facade method'),
            ]
        }

        # Anti-patterns to detect
        self.anti_patterns = {
            'god_class': [
                (r'class\s+\w+.*?:(?:.*?\n){100,}', 'Large class (potential God class)'),
            ],
            'feature_envy': [
                (r'def\s+\w+\s*\([^)]*\):.*?other\.\w+.*?other\.\w+.*?other\.\w+', 'Feature envy detected'),
            ],
            'data_class': [
                (r'class\s+\w+.*?:(?:\s*\n\s*def\s+__init__.*?\n(?:\s*self\.\w+.*?\n){3,})', 'Data class pattern'),
            ],
            'circular_import': [
                (r'from\s+(\w+)\s+import.*?\n.*?from\s+\1\s+import', 'Potential circular import'),
            ]
        }

        logger.info("Architectural Pattern Analyzer initialized")

    async def analyze_architecture(self, root_path: str = ".", patterns: List[str] = None) -> Dict[str, Any]:
        """Analyze architectural patterns and design quality"""

        start_time = time.time()
        patterns = patterns or ["**/*.py"]

        # Clear previous analysis cache
        await self._clear_cache()

        logger.info(f"Analyzing architectural patterns in {root_path}")

        # Discover architectural components
        logger.info("Discovering architectural components")
        components = await self._discover_components(root_path, patterns)
        logger.info(f"Found {len(components)} architectural components")

        # Analyze dependencies and relationships
        logger.info("Analyzing dependencies and relationships")
        dependencies = await self._analyze_dependencies(components)

        # Detect design patterns
        logger.info("Detecting design patterns")
        detected_patterns = await self._detect_patterns(root_path, patterns)

        # Identify architectural issues
        logger.info("Identifying architectural issues")
        issues = await self._identify_architectural_issues(components, dependencies)

        # Calculate architectural metrics
        metrics = self._calculate_architectural_metrics(components, issues)

        # Generate improvement recommendations
        recommendations = await self._generate_architecture_recommendations(issues)

        analysis_time = time.time() - start_time

        results = {
            "total_components": len(components),
            "architectural_issues": len(issues),
            "design_patterns_found": len(detected_patterns),
            "architecture_score": metrics.architecture_score,
            "analysis_time_seconds": analysis_time,
            "components": [self._serialize_component(c) for c in components],
            "architectural_issues": [self._serialize_issue(issue) for issue in issues],
            "detected_patterns": detected_patterns,
            "recommendations": recommendations,
            "metrics": {
                "total_components": metrics.total_components,
                "architecture_score": metrics.architecture_score,
                "coupling_score": metrics.coupling_score,
                "cohesion_score": metrics.cohesion_score,
                "pattern_adherence_score": metrics.pattern_adherence_score,
                "maintainability_index": metrics.maintainability_index,
                "abstraction_score": metrics.abstraction_score,
                "instability_score": metrics.instability_score,
            }
        }

        # Cache results
        await self._cache_results(results)

        logger.info(f"Architectural analysis complete in {analysis_time:.2f}s")
        return results

    async def _discover_components(self, root_path: str, patterns: List[str]) -> List[ArchitecturalComponent]:
        """Discover architectural components in the codebase"""
        # (Issue #315 - refactored) Reduced nesting by extracting file processing
        components = []
        root = Path(root_path)

        for pattern in patterns:
            for file_path in root.glob(pattern):
                await self._process_file_for_components(file_path, components)

        return components

    async def _process_file_for_components(self, file_path: Path, components: List[ArchitecturalComponent]) -> None:
        """Process a single file to extract components (Issue #315 - extracted)"""
        if not file_path.is_file() or self._should_skip_file(file_path):
            return

        try:
            file_components = await self._extract_components_from_file(str(file_path))
            components.extend(file_components)
        except Exception as e:
            logger.warning(f"Failed to extract components from {file_path}: {e}")

    def _should_skip_file(self, file_path: Path) -> bool:
        """Check if file should be skipped"""
        skip_patterns = [
            "__pycache__", ".git", "node_modules", ".venv", "venv",
            "test_", "_test.py", ".pyc", "analyzer"
        ]

        path_str = str(file_path)
        return any(pattern in path_str for pattern in skip_patterns)

    async def _extract_components_from_file(self, file_path: str) -> List[ArchitecturalComponent]:
        """Extract architectural components from a file"""
        # (Issue #315 - refactored) Reduced nesting by extracting component analysis
        components = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            tree = ast.parse(content, filename=file_path)
            self._extract_nodes_from_tree(tree, file_path, content, components)

            # Module-level component
            module_component = self._analyze_module_component(file_path, tree, content)
            if module_component:
                components.append(module_component)

        except SyntaxError:
            # Skip files with syntax errors
            pass
        except Exception as e:
            logger.error(f"Error extracting components from {file_path}: {e}")

        return components

    def _extract_nodes_from_tree(self, tree: ast.AST, file_path: str, content: str,
                                 components: List[ArchitecturalComponent]) -> None:
        """Extract class and function nodes from AST tree (Issue #340 - refactored)"""
        for node in ast.walk(tree):
            component = self._extract_single_node(node, tree, file_path, content)
            if component:
                components.append(component)

    def _extract_single_node(self, node: ast.AST, tree: ast.AST, file_path: str,
                            content: str) -> Optional[ArchitecturalComponent]:
        """Extract a single node as a component (Issue #340 - extracted)"""
        if isinstance(node, ast.ClassDef):
            return self._analyze_class_component(node, file_path, content)
        if isinstance(node, ast.FunctionDef) and not self._is_method(node, tree):
            return self._analyze_function_component(node, file_path, content)
        return None

    def _analyze_class_component(self, node: ast.ClassDef, file_path: str, content: str) -> Optional[ArchitecturalComponent]:
        """Analyze a class as an architectural component"""

        try:
            # Extract dependencies from imports and method calls
            dependencies = self._extract_class_dependencies(node, content)

            # Extract interfaces (methods)
            interfaces = [method.name for method in node.body if isinstance(method, ast.FunctionDef)]

            # Check if abstract
            is_abstract = self._is_abstract_class(node)

            # Calculate coupling (dependencies)
            coupling_score = len(dependencies)

            # Calculate cohesion (method relationships)
            cohesion_score = self._calculate_class_cohesion(node)

            # Calculate complexity
            complexity_score = self._calculate_class_complexity(node)

            # Detect patterns
            patterns = self._detect_class_patterns(node, content)

            return ArchitecturalComponent(
                file_path=file_path,
                component_type="class",
                name=node.name,
                line_number=node.lineno,
                dependencies=dependencies,
                interfaces=interfaces,
                is_abstract=is_abstract,
                coupling_score=coupling_score,
                cohesion_score=cohesion_score,
                complexity_score=complexity_score,
                patterns=patterns
            )

        except Exception as e:
            logger.error(f"Error analyzing class {node.name}: {e}")
            return None

    def _analyze_function_component(self, node: ast.FunctionDef, file_path: str, content: str) -> Optional[ArchitecturalComponent]:
        """Analyze a function as an architectural component"""

        try:
            # Extract dependencies
            dependencies = self._extract_function_dependencies(node, content)

            # Function parameters as interfaces
            interfaces = [arg.arg for arg in node.args.args]

            return ArchitecturalComponent(
                file_path=file_path,
                component_type="function",
                name=node.name,
                line_number=node.lineno,
                dependencies=dependencies,
                interfaces=interfaces,
                is_abstract=False,
                coupling_score=len(dependencies),
                cohesion_score=1.0,  # Functions are inherently cohesive
                complexity_score=self._calculate_function_complexity(node),
                patterns=[]
            )

        except Exception as e:
            logger.error(f"Error analyzing function {node.name}: {e}")
            return None

    def _analyze_module_component(self, file_path: str, tree: ast.AST, content: str) -> Optional[ArchitecturalComponent]:
        """Analyze a module as an architectural component (Issue #340 - refactored)"""
        try:
            dependencies = self._extract_module_dependencies(tree)
            interfaces = self._extract_public_interfaces(tree)
            module_name = Path(file_path).stem

            return ArchitecturalComponent(
                file_path=file_path,
                component_type="module",
                name=module_name,
                line_number=1,
                dependencies=list(set(dependencies)),
                interfaces=interfaces,
                is_abstract=False,
                coupling_score=len(set(dependencies)),
                cohesion_score=self._calculate_module_cohesion(tree),
                complexity_score=len(interfaces),
                patterns=[]
            )
        except Exception as e:
            logger.error(f"Error analyzing module {file_path}: {e}")
            return None

    def _extract_module_dependencies(self, tree: ast.AST) -> List[str]:
        """Extract module-level dependencies (Issue #340 - extracted)"""
        dependencies = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                dependencies.extend([alias.name for alias in node.names])
            elif isinstance(node, ast.ImportFrom) and node.module:
                dependencies.append(node.module)
        return dependencies

    def _extract_public_interfaces(self, tree: ast.AST) -> List[str]:
        """Extract public functions/classes as interfaces (Issue #340 - extracted)"""
        return [
            node.name for node in ast.walk(tree)
            if isinstance(node, _FUNC_OR_CLASS_TYPES) and not node.name.startswith('_')  # Issue #380
        ]

    def _extract_class_dependencies(self, node: ast.ClassDef, content: str) -> List[str]:
        """Extract dependencies for a class"""
        # (Issue #315 - refactored) Reduced nesting by extracting dependency extraction
        dependencies = []

        # Base classes
        dependencies.extend(self._extract_base_class_dependencies(node))

        # Method calls and attribute access
        dependencies.extend(self._extract_call_dependencies(node))

        return list(set(dependencies))

    def _extract_base_class_dependencies(self, node: ast.ClassDef) -> List[str]:
        """Extract base class dependencies (Issue #315 - extracted)"""
        return [base.id for base in node.bases if isinstance(base, ast.Name)]

    def _extract_call_dependencies(self, node: ast.AST) -> List[str]:
        """Extract dependencies from function/method calls (Issue #315 - extracted)"""
        dependencies = []
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue

            if isinstance(child.func, ast.Name):
                dependencies.append(child.func.id)
            elif isinstance(child.func, ast.Attribute) and isinstance(child.func.value, ast.Name):
                dependencies.append(child.func.value.id)

        return dependencies

    def _extract_function_dependencies(self, node: ast.FunctionDef, content: str) -> List[str]:
        """Extract dependencies for a function"""
        # (Issue #315 - refactored) Reuse _extract_call_dependencies to reduce nesting
        return list(set(self._extract_call_dependencies(node)))

    def _is_abstract_class(self, node: ast.ClassDef) -> bool:
        """Check if a class is abstract (Issue #340 - refactored)"""
        return self._has_abc_base(node) or self._has_abstract_method(node)

    def _has_abc_base(self, node: ast.ClassDef) -> bool:
        """Check for ABC inheritance (Issue #340 - extracted)"""
        return any(
            isinstance(base, ast.Name) and 'ABC' in base.id
            for base in node.bases
        )

    def _has_abstract_method(self, node: ast.ClassDef) -> bool:
        """Check for abstract methods (Issue #340 - extracted)"""
        for method in node.body:
            if not isinstance(method, ast.FunctionDef):
                continue
            if self._is_abstractmethod_decorated(method):
                return True
        return False

    def _is_abstractmethod_decorated(self, method: ast.FunctionDef) -> bool:
        """Check if method has abstractmethod decorator (Issue #340 - extracted)"""
        return any(
            isinstance(dec, ast.Name) and dec.id == 'abstractmethod'
            for dec in method.decorator_list
        )

    def _is_method(self, node: ast.FunctionDef, tree: ast.AST) -> bool:
        """Check if a function is a method (inside a class)"""
        for parent in ast.walk(tree):
            if isinstance(parent, ast.ClassDef):
                if node in parent.body:
                    return True
        return False

    def _calculate_class_cohesion(self, node: ast.ClassDef) -> float:
        """Calculate class cohesion using method interactions (Issue #340 - refactored)"""
        methods = [n for n in node.body if isinstance(n, ast.FunctionDef)]
        if len(methods) <= 1:
            return 1.0

        attribute_refs = self._collect_attribute_references(methods)
        if not attribute_refs:
            return 0.5  # Neutral cohesion

        return self._compute_cohesion_ratio(attribute_refs)

    def _collect_attribute_references(self, methods: List[ast.FunctionDef]) -> Dict[str, List[str]]:
        """Collect attribute references from methods (Issue #340 - extracted)"""
        attribute_refs: Dict[str, List[str]] = {}
        for method in methods:
            self._collect_self_attributes(method, attribute_refs)
        return attribute_refs

    def _collect_self_attributes(self, method: ast.FunctionDef, attribute_refs: Dict[str, List[str]]) -> None:
        """Collect self.* attribute references (Issue #340 - extracted)"""
        for child in ast.walk(method):
            if not self._is_self_attribute(child):
                continue
            attr_name = child.attr
            if attr_name not in attribute_refs:
                attribute_refs[attr_name] = []
            attribute_refs[attr_name].append(method.name)

    def _is_self_attribute(self, node: ast.AST) -> bool:
        """Check if node is a self.* attribute access (Issue #340 - extracted)"""
        return (isinstance(node, ast.Attribute) and
                isinstance(node.value, ast.Name) and
                node.value.id == 'self')

    def _compute_cohesion_ratio(self, attribute_refs: Dict[str, List[str]]) -> float:
        """Compute cohesion ratio from attribute references (Issue #340 - extracted)"""
        shared_attributes = sum(1 for methods_list in attribute_refs.values() if len(methods_list) > 1)
        total_attributes = len(attribute_refs)
        return shared_attributes / total_attributes if total_attributes > 0 else 0.5

    def _calculate_module_cohesion(self, tree: ast.AST) -> float:
        """Calculate module cohesion"""
        # Simple heuristic: ratio of internal calls to total calls
        internal_calls = 0
        external_calls = 0

        # Get all defined names in the module
        defined_names = set()
        for node in ast.walk(tree):
            if isinstance(node, _FUNC_OR_CLASS_TYPES):  # Issue #380
                defined_names.add(node.name)

        # Count internal vs external calls
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in defined_names:
                    internal_calls += 1
                else:
                    external_calls += 1

        total_calls = internal_calls + external_calls
        return internal_calls / total_calls if total_calls > 0 else 1.0

    def _calculate_class_complexity(self, node: ast.ClassDef) -> int:
        """Calculate class complexity"""
        # (Issue #315 - refactored) Reduced nesting by extracting attribute counting
        complexity = 0

        # Count methods
        methods = [n for n in node.body if isinstance(n, ast.FunctionDef)]
        complexity += len(methods)

        # Count attributes
        complexity += self._count_class_attributes(methods)

        return complexity

    def _count_class_attributes(self, methods: List[ast.FunctionDef]) -> int:
        """Count class attributes defined in __init__ (Issue #315 - extracted)"""
        count = 0
        for method in methods:
            if method.name != '__init__':
                continue

            for child in ast.walk(method):
                if isinstance(child, ast.Assign):
                    count += self._count_attribute_assignments(child)

        return count

    def _count_attribute_assignments(self, assign_node: ast.Assign) -> int:
        """Count attribute assignments in an assign node (Issue #315 - extracted)"""
        return sum(1 for target in assign_node.targets if isinstance(target, ast.Attribute))

    def _calculate_function_complexity(self, node: ast.FunctionDef) -> int:
        """Calculate function complexity"""
        complexity = 1  # Base complexity

        for child in ast.walk(node):
            # Issue #380: Use module-level constants
            if isinstance(child, _COMPLEXITY_BRANCH_TYPES):
                complexity += 1
            elif isinstance(child, _BOOLEAN_OP_TYPES):
                complexity += 1

        return complexity

    def _detect_class_patterns(self, node: ast.ClassDef, content: str) -> List[str]:
        """Detect design patterns in a class"""
        patterns = []
        class_content = ast.unparse(node) if hasattr(ast, 'unparse') else str(node)

        # Check each pattern
        for pattern_name, pattern_sigs in self.pattern_signatures.items():
            for pattern, description in pattern_sigs:
                if re.search(pattern, class_content, re.MULTILINE | re.IGNORECASE):
                    if pattern_name not in patterns:
                        patterns.append(pattern_name)

        return patterns

    async def _detect_patterns(self, root_path: str, patterns: List[str]) -> List[Dict[str, Any]]:
        """Detect design patterns across the codebase"""
        # (Issue #315 - refactored) Reduced nesting by extracting pattern scanning
        detected_patterns = []
        root = Path(root_path)

        for pattern in patterns:
            for file_path in root.glob(pattern):
                await self._scan_file_for_patterns(file_path, detected_patterns)

        return detected_patterns

    async def _scan_file_for_patterns(self, file_path: Path,
                                     detected_patterns: List[Dict[str, Any]]) -> None:
        """Scan a single file for design patterns (Issue #315 - extracted)"""
        if not file_path.is_file() or self._should_skip_file(file_path):
            return

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            self._find_patterns_in_content(file_path, content, detected_patterns)
        except Exception as e:
            logger.warning(f"Failed to scan patterns in {file_path}: {e}")

    def _find_patterns_in_content(self, file_path: Path, content: str,
                                 detected_patterns: List[Dict[str, Any]]) -> None:
        """Find pattern matches in file content (Issue #315 - extracted)"""
        for pattern_name, pattern_sigs in self.pattern_signatures.items():
            for regex_pattern, description in pattern_sigs:
                self._match_pattern(file_path, content, pattern_name, regex_pattern,
                                  description, detected_patterns)

    def _match_pattern(self, file_path: Path, content: str, pattern_name: str,
                      regex_pattern: str, description: str,
                      detected_patterns: List[Dict[str, Any]]) -> None:
        """Match a single pattern and record matches (Issue #315 - extracted)"""
        for match in re.finditer(regex_pattern, content, re.MULTILINE | re.IGNORECASE):
            line_num = content[:match.start()].count('\n') + 1
            detected_patterns.append({
                'pattern': pattern_name,
                'file': str(file_path),
                'line': line_num,
                'description': description,
                'code_snippet': match.group(0)[:100]
            })

    async def _analyze_dependencies(self, components: List[ArchitecturalComponent]) -> Dict[str, List[str]]:
        """Analyze dependencies between components"""

        dependencies = {}

        for component in components:
            dependencies[component.name] = component.dependencies

        return dependencies

    async def _identify_architectural_issues(self, components: List[ArchitecturalComponent],
                                           dependencies: Dict[str, List[str]]) -> List[ArchitecturalIssue]:
        """Identify architectural issues and anti-patterns"""

        issues = []

        # Identify God classes
        god_classes = [c for c in components if c.component_type == "class" and c.complexity_score > 50]
        if god_classes:
            issues.append(ArchitecturalIssue(
                issue_type="god_class",
                severity="high",
                description=f"Found {len(god_classes)} potential God classes with high complexity",
                affected_components=god_classes,
                suggestion="Break down large classes into smaller, more focused classes",
                refactoring_effort="high",
                pattern_violation="Single Responsibility Principle"
            ))

        # Identify high coupling
        high_coupling = [c for c in components if c.coupling_score > 10]
        if high_coupling:
            issues.append(ArchitecturalIssue(
                issue_type="tight_coupling",
                severity="medium",
                description=f"Found {len(high_coupling)} components with high coupling",
                affected_components=high_coupling,
                suggestion="Reduce dependencies through dependency injection or interfaces",
                refactoring_effort="medium",
                pattern_violation="Dependency Inversion Principle"
            ))

        # Identify low cohesion
        low_cohesion = [c for c in components if c.component_type == "class" and c.cohesion_score < 0.3]
        if low_cohesion:
            issues.append(ArchitecturalIssue(
                issue_type="low_cohesion",
                severity="medium",
                description=f"Found {len(low_cohesion)} classes with low cohesion",
                affected_components=low_cohesion,
                suggestion="Reorganize class methods to increase internal relatedness",
                refactoring_effort="medium",
                pattern_violation="Single Responsibility Principle"
            ))

        # Check for circular dependencies
        circular_deps = self._detect_circular_dependencies(dependencies)
        if circular_deps:
            affected = [c for c in components if c.name in circular_deps]
            issues.append(ArchitecturalIssue(
                issue_type="circular_dependency",
                severity="high",
                description=f"Found circular dependencies between {len(circular_deps)} components",
                affected_components=affected,
                suggestion="Break circular dependencies using interfaces or dependency injection",
                refactoring_effort="high",
                pattern_violation="Acyclic Dependencies Principle"
            ))

        return issues

    def _detect_circular_dependencies(self, dependencies: Dict[str, List[str]]) -> List[str]:
        """Detect circular dependencies using DFS"""
        visited = set()
        rec_stack = set()
        circular = []

        def dfs(node):
            if node in rec_stack:
                return True
            if node in visited:
                return False

            visited.add(node)
            rec_stack.add(node)

            for neighbor in dependencies.get(node, []):
                if neighbor in dependencies and dfs(neighbor):
                    circular.append(node)
                    return True

            rec_stack.remove(node)
            return False

        for node in dependencies:
            if node not in visited:
                dfs(node)

        return circular

    def _calculate_architectural_metrics(self, components: List[ArchitecturalComponent],
                                       issues: List[ArchitecturalIssue]) -> ArchitecturalMetrics:
        """Calculate architectural quality metrics"""

        if not components:
            return ArchitecturalMetrics(0, 0, 0, 0, 0, 0, 0, 0)

        # Average coupling
        avg_coupling = sum(c.coupling_score for c in components) / len(components)
        coupling_score = max(0, 100 - (avg_coupling * 5))  # Lower coupling is better

        # Average cohesion
        class_components = [c for c in components if c.component_type == "class"]
        avg_cohesion = sum(c.cohesion_score for c in class_components) / len(class_components) if class_components else 0
        cohesion_score = avg_cohesion * 100

        # Pattern adherence (fewer issues = better adherence)
        critical_issues = len([i for i in issues if i.severity == "critical"])
        high_issues = len([i for i in issues if i.severity == "high"])
        pattern_adherence = max(0, 100 - (critical_issues * 20 + high_issues * 10))

        # Maintainability index (simplified)
        avg_complexity = sum(c.complexity_score for c in components) / len(components)
        maintainability = max(0, 100 - (avg_complexity * 2))

        # Abstraction score (ratio of abstract to concrete classes)
        abstract_classes = len([c for c in components if c.component_type == "class" and c.is_abstract])
        total_classes = len([c for c in components if c.component_type == "class"])
        abstraction_score = (abstract_classes / total_classes * 100) if total_classes > 0 else 0

        # Instability score (dependencies out vs dependencies in)
        # Simplified calculation
        instability_score = min(100, avg_coupling * 10)

        # Overall architecture score (weighted average)
        architecture_score = (
            coupling_score * 0.25 +
            cohesion_score * 0.25 +
            pattern_adherence * 0.3 +
            maintainability * 0.2
        )

        return ArchitecturalMetrics(
            total_components=len(components),
            architecture_score=round(architecture_score, 2),
            coupling_score=round(coupling_score, 2),
            cohesion_score=round(cohesion_score, 2),
            pattern_adherence_score=round(pattern_adherence, 2),
            maintainability_index=round(maintainability, 2),
            abstraction_score=round(abstraction_score, 2),
            instability_score=round(instability_score, 2)
        )

    async def _generate_architecture_recommendations(self, issues: List[ArchitecturalIssue]) -> List[str]:
        """Generate architectural improvement recommendations"""

        recommendations = []

        # Group by issue type
        by_type = {}
        for issue in issues:
            if issue.issue_type not in by_type:
                by_type[issue.issue_type] = []
            by_type[issue.issue_type].append(issue)

        # Generate specific recommendations
        if 'god_class' in by_type:
            recommendations.append("Break down God classes using Single Responsibility Principle")

        if 'tight_coupling' in by_type:
            recommendations.append("Reduce coupling through dependency injection and interface segregation")

        if 'low_cohesion' in by_type:
            recommendations.append("Increase cohesion by grouping related functionality together")

        if 'circular_dependency' in by_type:
            recommendations.append("Eliminate circular dependencies using dependency inversion")

        # General recommendations
        recommendations.extend([
            "Apply SOLID principles consistently across the codebase",
            "Use design patterns appropriately to solve common problems",
            "Implement proper layered architecture with clear boundaries",
            "Add architectural tests to enforce design constraints"
        ])

        return recommendations

    def _serialize_component(self, component: ArchitecturalComponent) -> Dict[str, Any]:
        """Serialize component for output"""
        return {
            "file": component.file_path,
            "type": component.component_type,
            "name": component.name,
            "line": component.line_number,
            "dependencies": component.dependencies,
            "interfaces": component.interfaces,
            "is_abstract": component.is_abstract,
            "coupling_score": component.coupling_score,
            "cohesion_score": component.cohesion_score,
            "complexity_score": component.complexity_score,
            "patterns": component.patterns
        }

    def _serialize_issue(self, issue: ArchitecturalIssue) -> Dict[str, Any]:
        """Serialize issue for output"""
        return {
            "type": issue.issue_type,
            "severity": issue.severity,
            "description": issue.description,
            "affected_components_count": len(issue.affected_components),
            "suggestion": issue.suggestion,
            "refactoring_effort": issue.refactoring_effort,
            "pattern_violation": issue.pattern_violation
        }

    async def _cache_results(self, results: Dict[str, Any]):
        """Cache analysis results in Redis"""
        if self.redis_client:
            try:
                key = self.ARCHITECTURE_KEY
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
                        match="architecture_analysis:*",
                        count=100
                    )
                    if keys:
                        await self.redis_client.delete(*keys)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.warning(f"Failed to clear cache: {e}")


async def main():
    """Example usage of architectural pattern analyzer"""

    analyzer = ArchitecturalPatternAnalyzer()

    # Analyze architectural patterns
    results = await analyzer.analyze_architecture(
        root_path=".",
        patterns=["src/**/*.py", "backend/**/*.py"]
    )

    # Print summary
    print(f"\n=== Architectural Pattern Analysis Results ===")
    print(f"Total components: {results['total_components']}")
    print(f"Architectural issues: {results['architectural_issues']}")
    print(f"Design patterns found: {results['design_patterns_found']}")
    print(f"Architecture score: {results['architecture_score']}/100")
    print(f"Analysis time: {results['analysis_time_seconds']:.2f}s")

    # Print detailed metrics
    metrics = results['metrics']
    print(f"\n=== Architectural Metrics ===")
    print(f"Coupling score: {metrics['coupling_score']}/100 (lower is better)")
    print(f"Cohesion score: {metrics['cohesion_score']}/100")
    print(f"Pattern adherence: {metrics['pattern_adherence_score']}/100")
    print(f"Maintainability index: {metrics['maintainability_index']}/100")
    print(f"Abstraction score: {metrics['abstraction_score']}/100")
    print(f"Instability score: {metrics['instability_score']}/100")

    # Print detected patterns
    print(f"\n=== Detected Design Patterns ===")
    pattern_counts = {}
    for pattern in results['detected_patterns']:
        pattern_name = pattern['pattern']
        pattern_counts[pattern_name] = pattern_counts.get(pattern_name, 0) + 1

    for pattern, count in pattern_counts.items():
        print(f"{pattern.title()}: {count} instances")

    # Print architectural issues
    if results['architectural_issues']:
        print(f"\n=== Architectural Issues ===")
        for issue in results['architectural_issues']:
            print(f"{issue['type']} ({issue['severity']}): {issue['description']}")
            print(f"  Affects {issue['affected_components_count']} components")
            print(f"  Suggestion: {issue['suggestion']}")
            print(f"  Refactoring effort: {issue['refactoring_effort']}")

    # Print recommendations
    if results['recommendations']:
        print(f"\n=== Architecture Recommendations ===")
        for i, rec in enumerate(results['recommendations'], 1):
            print(f"{i}. {rec}")


if __name__ == "__main__":
    asyncio.run(main())
