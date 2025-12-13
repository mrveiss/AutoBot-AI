# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Automated Documentation Generator

Automatically generates documentation based on code patterns and implementation.
Analyzes code structure, extracts patterns, and creates comprehensive documentation.

Part of EPIC #217 - Advanced Code Intelligence Methods (Issue #241).

Features:
- Code structure analysis (classes, functions, modules)
- Docstring extraction and enhancement
- API documentation generation
- Pattern explanation and examples
- Architecture documentation
- Markdown and HTML output formats
- Diagram generation (Mermaid syntax)

Documentation Types:
- API documentation
- Pattern guides
- Architecture docs
- Setup instructions
- Module overviews
"""

import ast
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozenset for enum base class checking
_ENUM_BASE_CLASSES: FrozenSet[str] = frozenset({"Enum", "IntEnum", "StrEnum"})
_ABSTRACT_DECORATORS: FrozenSet[str] = frozenset({"ABC", "abstractmethod"})
_SELF_CLS_ARGS: FrozenSet[str] = frozenset({"self", "cls"})
_SKIP_INHERITANCE_BASES: FrozenSet[str] = frozenset({"object", "ABC", "Enum"})

# Issue #380: Module-level tuple for function definition AST nodes
_FUNCTION_DEF_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)
_IMPORT_TYPES = (ast.Import, ast.ImportFrom)
_SEQUENCE_TYPES = (ast.List, ast.Tuple)

# Issue #380: Pre-compiled regex patterns for markdown-to-HTML conversion
_MD_H5_RE = re.compile(r"^##### (.+)$", re.MULTILINE)
_MD_H4_RE = re.compile(r"^#### (.+)$", re.MULTILINE)
_MD_H3_RE = re.compile(r"^### (.+)$", re.MULTILINE)
_MD_H2_RE = re.compile(r"^## (.+)$", re.MULTILINE)
_MD_H1_RE = re.compile(r"^# (.+)$", re.MULTILINE)
_MD_CODE_BLOCK_RE = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)
_MD_INLINE_CODE_RE = re.compile(r"`([^`]+)`")
_MD_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_MD_LIST_ITEM_RE = re.compile(r"^- (.+)$", re.MULTILINE)
_MD_HR_RE = re.compile(r"^---$", re.MULTILINE)

# Issue #380: Pre-compiled regex patterns for version/author extraction
_VERSION_RE = re.compile(r'__version__\s*=\s*["\']([^"\']+)["\']')
_SETUP_VERSION_RE = re.compile(r'version\s*=\s*["\']([^"\']+)["\']')
_AUTHOR_RE = re.compile(r'__author__\s*=\s*["\']([^"\']+)["\']')


# =============================================================================
# Enums
# =============================================================================


class DocFormat(Enum):
    """Output format for generated documentation."""

    MARKDOWN = "markdown"
    HTML = "html"
    RST = "rst"
    PLAINTEXT = "plaintext"


class DocSection(Enum):
    """Types of documentation sections."""

    OVERVIEW = "overview"
    INSTALLATION = "installation"
    QUICK_START = "quick_start"
    API_REFERENCE = "api_reference"
    EXAMPLES = "examples"
    CONFIGURATION = "configuration"
    ARCHITECTURE = "architecture"
    PATTERNS = "patterns"
    TROUBLESHOOTING = "troubleshooting"
    CHANGELOG = "changelog"
    CONTRIBUTING = "contributing"


class ElementType(Enum):
    """Types of code elements that can be documented."""

    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    PROPERTY = "property"
    VARIABLE = "variable"
    CONSTANT = "constant"
    ENUM = "enum"
    DATACLASS = "dataclass"
    DECORATOR = "decorator"


class DocCompleteness(Enum):
    """Level of documentation completeness."""

    NONE = "none"
    MINIMAL = "minimal"
    PARTIAL = "partial"
    COMPLETE = "complete"
    COMPREHENSIVE = "comprehensive"


class DiagramType(Enum):
    """Types of diagrams that can be generated."""

    CLASS_DIAGRAM = "class_diagram"
    SEQUENCE_DIAGRAM = "sequence_diagram"
    FLOWCHART = "flowchart"
    ENTITY_RELATIONSHIP = "entity_relationship"
    STATE_DIAGRAM = "state_diagram"
    MODULE_DEPENDENCY = "module_dependency"


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ParameterDoc:
    """Documentation for a function/method parameter."""

    name: str
    type_hint: Optional[str] = None
    description: Optional[str] = None
    default_value: Optional[str] = None
    is_optional: bool = False
    is_keyword_only: bool = False
    is_positional_only: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "type_hint": self.type_hint,
            "description": self.description,
            "default_value": self.default_value,
            "is_optional": self.is_optional,
            "is_keyword_only": self.is_keyword_only,
            "is_positional_only": self.is_positional_only,
        }


@dataclass
class ReturnDoc:
    """Documentation for a function/method return value."""

    type_hint: Optional[str] = None
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "type_hint": self.type_hint,
            "description": self.description,
        }


@dataclass
class ExceptionDoc:
    """Documentation for an exception that can be raised."""

    exception_type: str
    description: Optional[str] = None
    conditions: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "exception_type": self.exception_type,
            "description": self.description,
            "conditions": self.conditions,
        }


@dataclass
class ExampleDoc:
    """Documentation for a code example."""

    code: str
    description: Optional[str] = None
    language: str = "python"
    output: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "code": self.code,
            "description": self.description,
            "language": self.language,
            "output": self.output,
        }


@dataclass
class FunctionDoc:
    """Complete documentation for a function or method."""

    name: str
    element_type: ElementType
    signature: str
    docstring: Optional[str] = None
    description: Optional[str] = None
    parameters: List[ParameterDoc] = field(default_factory=list)
    returns: Optional[ReturnDoc] = None
    exceptions: List[ExceptionDoc] = field(default_factory=list)
    examples: List[ExampleDoc] = field(default_factory=list)
    decorators: List[str] = field(default_factory=list)
    is_async: bool = False
    is_static: bool = False
    is_classmethod: bool = False
    is_property: bool = False
    is_abstract: bool = False
    line_number: int = 0
    completeness: DocCompleteness = DocCompleteness.NONE

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "element_type": self.element_type.value,
            "signature": self.signature,
            "docstring": self.docstring,
            "description": self.description,
            "parameters": [p.to_dict() for p in self.parameters],
            "returns": self.returns.to_dict() if self.returns else None,
            "exceptions": [e.to_dict() for e in self.exceptions],
            "examples": [e.to_dict() for e in self.examples],
            "decorators": self.decorators,
            "is_async": self.is_async,
            "is_static": self.is_static,
            "is_classmethod": self.is_classmethod,
            "is_property": self.is_property,
            "is_abstract": self.is_abstract,
            "line_number": self.line_number,
            "completeness": self.completeness.value,
        }

    def update_parameter_description(self, param_name: str, description: str) -> None:
        """
        Update parameter description.

        Args:
            param_name: Name of parameter to update
            description: New description text
        """
        for param in self.parameters:
            if param.name == param_name:
                param.description = description
                break

    def calculate_completeness(self) -> DocCompleteness:
        """
        Calculate documentation completeness for this function.

        Returns:
            DocCompleteness level based on available documentation
        """
        score = 0

        if self.docstring:
            score += 1
        if self.description:
            score += 1
        if all(p.description for p in self.parameters):
            score += 1
        if self.returns and self.returns.description:
            score += 1
        if self.examples:
            score += 1

        if score == 0:
            return DocCompleteness.NONE
        elif score == 1:
            return DocCompleteness.MINIMAL
        elif score <= 3:
            return DocCompleteness.PARTIAL
        elif score == 4:
            return DocCompleteness.COMPLETE
        else:
            return DocCompleteness.COMPREHENSIVE


@dataclass
class ClassDoc:
    """Complete documentation for a class."""

    name: str
    docstring: Optional[str] = None
    description: Optional[str] = None
    base_classes: List[str] = field(default_factory=list)
    methods: List[FunctionDoc] = field(default_factory=list)
    properties: List[FunctionDoc] = field(default_factory=list)
    class_variables: Dict[str, str] = field(default_factory=dict)
    instance_variables: Dict[str, str] = field(default_factory=dict)
    decorators: List[str] = field(default_factory=list)
    is_dataclass: bool = False
    is_enum: bool = False
    is_abstract: bool = False
    examples: List[ExampleDoc] = field(default_factory=list)
    line_number: int = 0
    completeness: DocCompleteness = DocCompleteness.NONE

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "docstring": self.docstring,
            "description": self.description,
            "base_classes": self.base_classes,
            "methods": [m.to_dict() for m in self.methods],
            "properties": [p.to_dict() for p in self.properties],
            "class_variables": self.class_variables,
            "instance_variables": self.instance_variables,
            "decorators": self.decorators,
            "is_dataclass": self.is_dataclass,
            "is_enum": self.is_enum,
            "is_abstract": self.is_abstract,
            "examples": [e.to_dict() for e in self.examples],
            "line_number": self.line_number,
            "completeness": self.completeness.value,
        }

    def add_base_class(self, base_name: str) -> None:
        """Add a base class to this class."""
        self.base_classes.append(base_name)

    def add_decorator(self, decorator_name: str) -> None:
        """
        Add a decorator and update class flags.

        Args:
            decorator_name: Name of the decorator
        """
        self.decorators.append(decorator_name)
        if decorator_name == "dataclass":
            self.is_dataclass = True
        elif decorator_name in _ABSTRACT_DECORATORS:
            self.is_abstract = True

    def check_enum_inheritance(self) -> None:
        """Check if this class inherits from Enum and set flag."""
        if any(base in _ENUM_BASE_CLASSES for base in self.base_classes):
            self.is_enum = True

    def add_method(self, method_doc: FunctionDoc) -> None:
        """
        Add a method or property to this class.

        Args:
            method_doc: Function documentation to add
        """
        if method_doc.is_property:
            self.properties.append(method_doc)
        else:
            self.methods.append(method_doc)

    def add_class_variable(self, var_name: str, var_type: str = "Unknown") -> None:
        """
        Add a class variable.

        Args:
            var_name: Variable name
            var_type: Type hint or "Unknown"
        """
        self.class_variables[var_name] = var_type

    def calculate_completeness(self) -> DocCompleteness:
        """
        Calculate documentation completeness for this class.

        Returns:
            DocCompleteness level based on available documentation
        """
        score = 0

        if self.docstring:
            score += 1
        if self.description:
            score += 1
        if self.examples:
            score += 1

        method_scores = [m.completeness.value for m in self.methods]
        if method_scores:
            avg_score = sum(
                {"none": 0, "minimal": 1, "partial": 2, "complete": 3, "comprehensive": 4}[s]
                for s in method_scores
            ) / len(method_scores)
            score += int(avg_score)

        if score == 0:
            return DocCompleteness.NONE
        elif score == 1:
            return DocCompleteness.MINIMAL
        elif score <= 3:
            return DocCompleteness.PARTIAL
        elif score <= 5:
            return DocCompleteness.COMPLETE
        else:
            return DocCompleteness.COMPREHENSIVE


@dataclass
class ModuleDoc:
    """Complete documentation for a module."""

    name: str
    file_path: str
    docstring: Optional[str] = None
    description: Optional[str] = None
    classes: List[ClassDoc] = field(default_factory=list)
    functions: List[FunctionDoc] = field(default_factory=list)
    constants: Dict[str, str] = field(default_factory=dict)
    imports: List[str] = field(default_factory=list)
    exports: List[str] = field(default_factory=list)  # __all__
    dependencies: List[str] = field(default_factory=list)
    examples: List[ExampleDoc] = field(default_factory=list)
    line_count: int = 0
    completeness: DocCompleteness = DocCompleteness.NONE

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "file_path": self.file_path,
            "docstring": self.docstring,
            "description": self.description,
            "classes": [c.to_dict() for c in self.classes],
            "functions": [f.to_dict() for f in self.functions],
            "constants": self.constants,
            "imports": self.imports,
            "exports": self.exports,
            "dependencies": self.dependencies,
            "examples": [e.to_dict() for e in self.examples],
            "line_count": self.line_count,
            "completeness": self.completeness.value,
        }

    def add_constant(self, name: str, value: str) -> None:
        """
        Add a module-level constant.

        Args:
            name: Constant name
            value: Constant value
        """
        self.constants[name] = value

    def add_import(self, import_statement: str) -> None:
        """
        Add an import statement.

        Args:
            import_statement: Import to add
        """
        self.imports.append(import_statement)

    def calculate_completeness(self) -> DocCompleteness:
        """
        Calculate documentation completeness for this module.

        Returns:
            DocCompleteness level based on available documentation
        """
        score = 0

        if self.docstring:
            score += 1
        if self.description:
            score += 1
        if self.examples:
            score += 1

        all_completeness = []
        for cls in self.classes:
            all_completeness.append(cls.completeness.value)
        for func in self.functions:
            all_completeness.append(func.completeness.value)

        if all_completeness:
            avg_score = sum(
                {"none": 0, "minimal": 1, "partial": 2, "complete": 3, "comprehensive": 4}[s]
                for s in all_completeness
            ) / len(all_completeness)
            score += int(avg_score)

        if score == 0:
            return DocCompleteness.NONE
        elif score == 1:
            return DocCompleteness.MINIMAL
        elif score <= 3:
            return DocCompleteness.PARTIAL
        elif score <= 5:
            return DocCompleteness.COMPLETE
        else:
            return DocCompleteness.COMPREHENSIVE


@dataclass
class PackageDoc:
    """Complete documentation for a package."""

    name: str
    path: str
    modules: List[ModuleDoc] = field(default_factory=list)
    subpackages: List["PackageDoc"] = field(default_factory=list)
    readme_content: Optional[str] = None
    init_docstring: Optional[str] = None
    version: Optional[str] = None
    author: Optional[str] = None
    description: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "path": self.path,
            "modules": [m.to_dict() for m in self.modules],
            "subpackages": [s.to_dict() for s in self.subpackages],
            "readme_content": self.readme_content,
            "init_docstring": self.init_docstring,
            "version": self.version,
            "author": self.author,
            "description": self.description,
        }


@dataclass
class DiagramSpec:
    """Specification for generating a diagram."""

    diagram_type: DiagramType
    title: str
    elements: List[Dict[str, Any]] = field(default_factory=list)
    relationships: List[Tuple[str, str, str]] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_mermaid(self) -> str:
        """Generate Mermaid diagram syntax."""
        if self.diagram_type == DiagramType.CLASS_DIAGRAM:
            return self._to_class_diagram()
        elif self.diagram_type == DiagramType.FLOWCHART:
            return self._to_flowchart()
        elif self.diagram_type == DiagramType.SEQUENCE_DIAGRAM:
            return self._to_sequence_diagram()
        elif self.diagram_type == DiagramType.MODULE_DEPENDENCY:
            return self._to_dependency_graph()
        else:
            return f"graph TD\n    A[{self.title}]"

    def _to_class_diagram(self) -> str:
        """Generate class diagram in Mermaid syntax."""
        lines = ["classDiagram"]

        for elem in self.elements:
            class_name = elem.get("name", "Unknown")
            lines.append(f"    class {class_name} {{")
            for attr in elem.get("attributes", []):
                lines.append(f"        {attr}")
            for method in elem.get("methods", []):
                lines.append(f"        {method}()")
            lines.append("    }")

        for src, dest, rel_type in self.relationships:
            if rel_type == "inherits":
                lines.append(f"    {dest} <|-- {src}")
            elif rel_type == "uses":
                lines.append(f"    {src} --> {dest}")
            elif rel_type == "composes":
                lines.append(f"    {src} *-- {dest}")

        return "\n".join(lines)

    def _to_flowchart(self) -> str:
        """Generate flowchart in Mermaid syntax."""
        lines = ["flowchart TD"]

        for elem in self.elements:
            node_id = elem.get("id", "node")
            label = elem.get("label", node_id)
            shape = elem.get("shape", "rectangle")

            if shape == "diamond":
                lines.append(f"    {node_id}{{{label}}}")
            elif shape == "circle":
                lines.append(f"    {node_id}(({label}))")
            else:
                lines.append(f"    {node_id}[{label}]")

        for src, dest, label in self.relationships:
            if label:
                lines.append(f"    {src} -->|{label}| {dest}")
            else:
                lines.append(f"    {src} --> {dest}")

        return "\n".join(lines)

    def _to_sequence_diagram(self) -> str:
        """Generate sequence diagram in Mermaid syntax."""
        lines = ["sequenceDiagram"]

        for elem in self.elements:
            participant = elem.get("name", "Unknown")
            alias = elem.get("alias", participant)
            lines.append(f"    participant {alias} as {participant}")

        for src, dest, message in self.relationships:
            lines.append(f"    {src}->>+{dest}: {message}")

        return "\n".join(lines)

    def _to_dependency_graph(self) -> str:
        """Generate module dependency graph in Mermaid syntax."""
        lines = ["flowchart LR"]

        for elem in self.elements:
            module_id = elem.get("id", "").replace(".", "_")
            module_name = elem.get("name", module_id)
            lines.append(f"    {module_id}[{module_name}]")

        for src, dest, _ in self.relationships:
            src_id = src.replace(".", "_")
            dest_id = dest.replace(".", "_")
            lines.append(f"    {src_id} --> {dest_id}")

        return "\n".join(lines)


@dataclass
class GeneratedDoc:
    """Result of documentation generation."""

    title: str
    content: str
    format: DocFormat
    sections: List[DocSection]
    generated_at: datetime = field(default_factory=datetime.now)
    source_files: List[str] = field(default_factory=list)
    diagrams: List[DiagramSpec] = field(default_factory=list)
    word_count: int = 0
    completeness_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "title": self.title,
            "content": self.content,
            "format": self.format.value,
            "sections": [s.value for s in self.sections],
            "generated_at": self.generated_at.isoformat(),
            "source_files": self.source_files,
            "diagrams": [d.to_mermaid() for d in self.diagrams],
            "word_count": self.word_count,
            "completeness_score": self.completeness_score,
        }


# =============================================================================
# Documentation Generator
# =============================================================================


class DocGenerator:
    """
    Automated Documentation Generator.

    Analyzes code structure, extracts patterns, and generates comprehensive
    documentation in various formats.

    Features:
    - Parse Python modules, classes, and functions
    - Extract and enhance docstrings
    - Generate API documentation
    - Create architecture diagrams
    - Produce pattern explanations
    - Output in Markdown, HTML, or RST

    Example:
        >>> generator = DocGenerator()
        >>> module_doc = generator.analyze_module('path/to/module.py')
        >>> markdown = generator.generate_api_docs([module_doc])
        >>> print(markdown)
    """

    # Google-style docstring patterns
    DOCSTRING_SECTIONS = {
        "args": re.compile(r"^\s*(Args?|Arguments?|Parameters?):\s*$", re.IGNORECASE),
        "returns": re.compile(r"^\s*(Returns?|Yields?):\s*$", re.IGNORECASE),
        "raises": re.compile(r"^\s*(Raises?|Exceptions?|Throws?):\s*$", re.IGNORECASE),
        "examples": re.compile(r"^\s*(Examples?|Usage):\s*$", re.IGNORECASE),
        "notes": re.compile(r"^\s*(Notes?|See Also|Warning|Todo):\s*$", re.IGNORECASE),
        "attributes": re.compile(r"^\s*(Attributes?|Properties):\s*$", re.IGNORECASE),
    }

    # Type annotation extraction patterns
    TYPE_PATTERNS = {
        "param": re.compile(r"(\w+)\s*\(([^)]+)\):\s*(.*)"),
        "simple": re.compile(r"(\w+):\s*(.*)"),
        "type_only": re.compile(r"([^:]+):\s*(.*)"),
    }

    def __init__(
        self,
        include_private: bool = False,
        include_dunder: bool = False,
        max_depth: int = 10,
    ):
        """
        Initialize the documentation generator.

        Args:
            include_private: Include private members (_prefix)
            include_dunder: Include dunder methods (__name__)
            max_depth: Maximum recursion depth for package traversal
        """
        self.include_private = include_private
        self.include_dunder = include_dunder
        self.max_depth = max_depth
        self._analyzed_files: Set[str] = set()

    def _validate_module_path(self, file_path: str) -> Optional[str]:
        """Validate module path exists and is a Python file (Issue #315 - extracted helper).

        Args:
            file_path: Path to validate

        Returns:
            Absolute path if valid, None otherwise
        """
        abs_path = os.path.abspath(file_path)

        if not os.path.exists(abs_path):
            logger.error(f"File not found: {abs_path}")
            return None

        if not abs_path.endswith(".py"):
            logger.warning(f"Not a Python file: {abs_path}")
            return None

        return abs_path

    def _read_and_parse_module(self, file_path: str) -> Optional[Tuple[str, ast.Module]]:
        """Read and parse a Python module (Issue #315 - extracted helper).

        Args:
            file_path: Path to the Python file

        Returns:
            Tuple of (source, ast) or None on error
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
        except OSError as e:
            logger.error(f"Failed to read file {file_path}: {e}")
            return None

        try:
            tree = ast.parse(source, filename=file_path)
            return (source, tree)
        except SyntaxError as e:
            logger.error(f"Syntax error in {file_path}: {e}")
            return None

    def _process_module_node(
        self, node: ast.AST, source: str, module_doc: "ModuleDoc"
    ) -> None:
        """Process a single top-level module node (Issue #315 - extracted helper).

        Args:
            node: AST node to process
            source: Module source code
            module_doc: ModuleDoc to populate
        """
        if isinstance(node, ast.ClassDef):
            class_doc = self._analyze_class(node, source)
            if class_doc and self._should_include(class_doc.name):
                module_doc.classes.append(class_doc)
            return

        if isinstance(node, _FUNCTION_DEF_TYPES):  # Issue #380
            func_doc = self._analyze_function(node, source)
            if func_doc and self._should_include(func_doc.name):
                module_doc.functions.append(func_doc)
            return

        if isinstance(node, ast.Assign):
            self._process_module_constants(node, module_doc)
            return

        if isinstance(node, _IMPORT_TYPES):  # Issue #380
            for import_stmt in self._extract_imports(node):
                module_doc.add_import(import_stmt)

    def _process_module_constants(self, node: ast.Assign, module_doc: "ModuleDoc") -> None:
        """Extract constants from assignment node (Issue #315 - extracted helper).

        Args:
            node: Assignment AST node
            module_doc: ModuleDoc to populate
        """
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if not target.id.isupper():
                continue
            value = self._get_node_value(node.value)
            module_doc.add_constant(target.id, value)

    def analyze_module(self, file_path: str) -> Optional[ModuleDoc]:
        """
        Analyze a Python module and extract documentation.

        Args:
            file_path: Path to the Python file

        Returns:
            ModuleDoc containing extracted documentation, or None if parse fails
        """
        validated_path = self._validate_module_path(file_path)
        if validated_path is None:
            return None

        parsed = self._read_and_parse_module(validated_path)
        if parsed is None:
            return None

        source, tree = parsed
        module_name = os.path.splitext(os.path.basename(validated_path))[0]
        module_doc = ModuleDoc(
            name=module_name,
            file_path=validated_path,
            docstring=ast.get_docstring(tree),
            line_count=len(source.splitlines()),
        )

        if module_doc.docstring:
            module_doc.description = self._extract_description(module_doc.docstring)

        for node in ast.iter_child_nodes(tree):
            self._process_module_node(node, source, module_doc)

        module_doc.exports = self._extract_all_exports(tree)
        module_doc.dependencies = self._extract_dependencies(module_doc.imports)
        module_doc.completeness = module_doc.calculate_completeness()

        self._analyzed_files.add(validated_path)
        return module_doc

    # Issue #315 - Standard README file names to check
    _README_NAMES = ["README.md", "README.rst", "README.txt", "README"]

    def _load_readme_content(self, package_path: str) -> Optional[str]:
        """Load README content if available (Issue #315 - extracted helper)."""
        for readme_name in self._README_NAMES:
            readme_path = os.path.join(package_path, readme_name)
            if os.path.exists(readme_path):
                try:
                    with open(readme_path, "r", encoding="utf-8") as f:
                        return f.read()
                except OSError:
                    pass
        return None

    def _process_package_item(
        self, item: str, package_path: str, package_doc: "PackageDoc", depth: int
    ) -> None:
        """Process a single item in package directory (Issue #315 - extracted helper)."""
        item_path = os.path.join(package_path, item)

        if os.path.isfile(item_path) and item.endswith(".py") and item != "__init__.py":
            module_doc = self.analyze_module(item_path)
            if module_doc:
                package_doc.modules.append(module_doc)
        elif os.path.isdir(item_path):
            if os.path.exists(os.path.join(item_path, "__init__.py")):
                subpackage = self.analyze_package(item_path, depth + 1)
                if subpackage:
                    package_doc.subpackages.append(subpackage)

    def analyze_package(
        self, package_path: str, depth: int = 0
    ) -> Optional[PackageDoc]:
        """Analyze a Python package and all its modules (Issue #315 - refactored)."""
        if depth > self.max_depth:
            logger.warning(f"Max depth reached for package: {package_path}")
            return None

        package_path = os.path.abspath(package_path)

        if not os.path.isdir(package_path):
            logger.error(f"Not a directory: {package_path}")
            return None

        init_file = os.path.join(package_path, "__init__.py")
        if not os.path.exists(init_file):
            logger.warning(f"Not a Python package (no __init__.py): {package_path}")
            return None

        package_name = os.path.basename(package_path)
        package_doc = PackageDoc(name=package_name, path=package_path)

        # Read __init__.py docstring
        init_module = self.analyze_module(init_file)
        if init_module:
            package_doc.init_docstring = init_module.docstring

        # Load README content
        package_doc.readme_content = self._load_readme_content(package_path)

        # Process all items in package
        for item in os.listdir(package_path):
            self._process_package_item(item, package_path, package_doc, depth)

        # Extract version and author
        package_doc.version = self._extract_version(package_path)
        package_doc.author = self._extract_author(package_path)

        return package_doc

    def _process_class_body_item(
        self, item: ast.AST, source: str, class_doc: "ClassDoc"
    ) -> None:
        """Process a single class body item (Issue #315 - extracted helper).

        Args:
            item: AST node from class body
            source: Module source code
            class_doc: ClassDoc to populate
        """
        if isinstance(item, _FUNCTION_DEF_TYPES):  # Issue #380
            if not self._should_include(item.name):
                return
            func_doc = self._analyze_function(item, source)
            if func_doc:
                class_doc.add_method(func_doc)
            return

        if isinstance(item, ast.AnnAssign):
            self._process_annotated_class_var(item, class_doc)
            return

        if isinstance(item, ast.Assign):
            self._process_unannotated_class_var(item, class_doc)

    def _process_annotated_class_var(
        self, item: ast.AnnAssign, class_doc: "ClassDoc"
    ) -> None:
        """Process annotated class variable (Issue #315 - extracted helper)."""
        if not isinstance(item.target, ast.Name):
            return
        var_name = item.target.id
        var_type = self._get_node_name(item.annotation) if item.annotation else "Any"
        class_doc.add_class_variable(var_name, var_type)

    def _process_unannotated_class_var(
        self, item: ast.Assign, class_doc: "ClassDoc"
    ) -> None:
        """Process unannotated class variable (Issue #315 - extracted helper)."""
        for target in item.targets:
            if isinstance(target, ast.Name):
                class_doc.add_class_variable(target.id)

    def _analyze_class(self, node: ast.ClassDef, source: str) -> ClassDoc:
        """Analyze a class definition and extract documentation."""
        class_doc = ClassDoc(
            name=node.name,
            docstring=ast.get_docstring(node),
            line_number=node.lineno,
        )

        for base in node.bases:
            class_doc.add_base_class(self._get_node_name(base))

        for decorator in node.decorator_list:
            dec_name = self._get_node_name(decorator)
            class_doc.add_decorator(dec_name)

        class_doc.check_enum_inheritance()

        if class_doc.docstring:
            class_doc.description = self._extract_description(class_doc.docstring)

        for item in node.body:
            self._process_class_body_item(item, source, class_doc)

        class_doc.completeness = class_doc.calculate_completeness()
        return class_doc

    # Decorator attribute mappings (Issue #315 - data-driven to avoid nesting)
    _DECORATOR_ATTR_MAP = {
        "staticmethod": ("is_static", True),
        "classmethod": ("is_classmethod", True),
        "abstractmethod": ("is_abstract", True),
    }

    def _process_function_decorator(self, dec_name: str, func_doc: "FunctionDoc") -> None:
        """Process a single function decorator (Issue #315 - extracted helper).

        Args:
            dec_name: Name of the decorator
            func_doc: FunctionDoc to update
        """
        func_doc.decorators.append(dec_name)

        # Handle property decorator specially (sets two attributes)
        if dec_name == "property":
            func_doc.is_property = True
            func_doc.element_type = ElementType.PROPERTY
            return

        # Use lookup for simple attribute decorators
        if dec_name in self._DECORATOR_ATTR_MAP:
            attr_name, attr_value = self._DECORATOR_ATTR_MAP[dec_name]
            setattr(func_doc, attr_name, attr_value)

    def _analyze_function(
        self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef], source: str
    ) -> FunctionDoc:
        """Analyze a function/method definition and extract documentation."""
        is_async = isinstance(node, ast.AsyncFunctionDef)
        element_type = ElementType.METHOD if self._is_method(node) else ElementType.FUNCTION

        func_doc = FunctionDoc(
            name=node.name,
            element_type=element_type,
            signature=self._build_signature(node),
            docstring=ast.get_docstring(node),
            is_async=is_async,
            line_number=node.lineno,
        )

        for decorator in node.decorator_list:
            dec_name = self._get_node_name(decorator)
            self._process_function_decorator(dec_name, func_doc)

        func_doc.parameters = self._extract_parameters(node)

        if node.returns:
            func_doc.returns = ReturnDoc(type_hint=self._get_node_name(node.returns))

        if func_doc.docstring:
            func_doc.description = self._extract_description(func_doc.docstring)
            self._enhance_from_docstring(func_doc)

        func_doc.completeness = func_doc.calculate_completeness()
        return func_doc

    def _extract_parameters(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> List[ParameterDoc]:
        """Extract parameter documentation from function definition."""
        params = []
        args = node.args

        # Regular arguments
        defaults_offset = len(args.args) - len(args.defaults)

        for i, arg in enumerate(args.args):
            if arg.arg in _SELF_CLS_ARGS:
                continue

            param = ParameterDoc(
                name=arg.arg,
                type_hint=self._get_node_name(arg.annotation) if arg.annotation else None,
            )

            # Check for default value
            default_idx = i - defaults_offset
            if default_idx >= 0 and default_idx < len(args.defaults):
                param.default_value = self._get_node_value(args.defaults[default_idx])
                param.is_optional = True

            params.append(param)

        # Positional-only arguments (Python 3.8+)
        for arg in args.posonlyargs:
            param = ParameterDoc(
                name=arg.arg,
                type_hint=self._get_node_name(arg.annotation) if arg.annotation else None,
                is_positional_only=True,
            )
            params.append(param)

        # Keyword-only arguments
        kw_defaults_map = {i: d for i, d in enumerate(args.kw_defaults) if d is not None}

        for i, arg in enumerate(args.kwonlyargs):
            param = ParameterDoc(
                name=arg.arg,
                type_hint=self._get_node_name(arg.annotation) if arg.annotation else None,
                is_keyword_only=True,
            )
            if i in kw_defaults_map:
                param.default_value = self._get_node_value(kw_defaults_map[i])
                param.is_optional = True
            params.append(param)

        return params

    def _enhance_from_docstring(self, func_doc: FunctionDoc) -> None:
        """Parse Google-style docstring to enhance parameter/return documentation."""
        if not func_doc.docstring:
            return

        lines = func_doc.docstring.split("\n")
        current_section = None
        current_content: List[str] = []

        for line in lines:
            # Check for section headers
            section_found = False
            for section_name, pattern in self.DOCSTRING_SECTIONS.items():
                if pattern.match(line):
                    # Process previous section
                    self._process_docstring_section(
                        func_doc, current_section, current_content
                    )
                    current_section = section_name
                    current_content = []
                    section_found = True
                    break

            if not section_found and current_section:
                current_content.append(line)

        # Process final section
        self._process_docstring_section(func_doc, current_section, current_content)

    def _process_docstring_section(
        self, func_doc: FunctionDoc, section: Optional[str], content: List[str]
    ) -> None:
        """Process a docstring section and update function documentation."""
        if not section or not content:
            return

        if section == "args":
            self._parse_args_section(func_doc, content)
        elif section == "returns":
            self._parse_returns_section(func_doc, content)
        elif section == "raises":
            self._parse_raises_section(func_doc, content)
        elif section == "examples":
            self._parse_examples_section(func_doc, content)

    def _parse_args_section(self, func_doc: FunctionDoc, lines: List[str]) -> None:
        """Parse Args section of docstring."""
        current_param: Optional[str] = None
        current_desc: List[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Check for new parameter
            match = self.TYPE_PATTERNS["param"].match(stripped)
            if match:
                # Save previous parameter
                if current_param:
                    self._update_param_description(
                        func_doc, current_param, " ".join(current_desc)
                    )
                current_param = match.group(1)
                current_desc = [match.group(3)]
                continue

            match = self.TYPE_PATTERNS["simple"].match(stripped)
            if match and not stripped.startswith(" "):
                if current_param:
                    self._update_param_description(
                        func_doc, current_param, " ".join(current_desc)
                    )
                current_param = match.group(1)
                current_desc = [match.group(2)]
                continue

            # Continuation of description
            if current_param:
                current_desc.append(stripped)

        # Save last parameter
        if current_param:
            self._update_param_description(
                func_doc, current_param, " ".join(current_desc)
            )

    def _parse_returns_section(self, func_doc: FunctionDoc, lines: List[str]) -> None:
        """Parse Returns section of docstring."""
        description = " ".join(line.strip() for line in lines if line.strip())
        if description:
            if func_doc.returns:
                func_doc.returns.description = description
            else:
                func_doc.returns = ReturnDoc(description=description)

    def _parse_raises_section(self, func_doc: FunctionDoc, lines: List[str]) -> None:
        """Parse Raises section of docstring."""
        current_exc: Optional[str] = None
        current_desc: List[str] = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            match = self.TYPE_PATTERNS["type_only"].match(stripped)
            if match:
                if current_exc:
                    func_doc.exceptions.append(
                        ExceptionDoc(
                            exception_type=current_exc,
                            description=" ".join(current_desc),
                        )
                    )
                current_exc = match.group(1).strip()
                current_desc = [match.group(2)]
            elif current_exc:
                current_desc.append(stripped)

        if current_exc:
            func_doc.exceptions.append(
                ExceptionDoc(
                    exception_type=current_exc,
                    description=" ".join(current_desc),
                )
            )

    def _is_code_start(self, stripped: str) -> bool:
        """Check if line starts a code example (Issue #315 - extracted helper)."""
        return stripped.startswith(">>>") or stripped.startswith("...")

    def _extract_code_content(self, stripped: str) -> str:
        """Extract code content from doctest line (Issue #315 - extracted helper)."""
        return stripped[4:] if len(stripped) > 4 else ""

    def _finalize_code_block(
        self, func_doc: FunctionDoc, code_lines: List[str]
    ) -> List[str]:
        """Add code block to examples and reset (Issue #315 - extracted helper)."""
        if code_lines:
            func_doc.examples.append(ExampleDoc(code="\n".join(code_lines)))
        return []

    def _parse_examples_section(self, func_doc: FunctionDoc, lines: List[str]) -> None:
        """Parse Examples section of docstring (Issue #315 - refactored)."""
        code_lines: List[str] = []
        in_code_block = False

        for line in lines:
            stripped = line.strip()
            if self._is_code_start(stripped):
                in_code_block = True
                code_lines.append(self._extract_code_content(stripped))
            elif in_code_block:
                if stripped.startswith("    "):
                    code_lines.append(stripped)
                elif not stripped:
                    code_lines = self._finalize_code_block(func_doc, code_lines)
                    in_code_block = False

        self._finalize_code_block(func_doc, code_lines)

    def _update_param_description(
        self, func_doc: FunctionDoc, param_name: str, description: str
    ) -> None:
        """Update parameter description in function documentation."""
        func_doc.update_parameter_description(param_name, description)

    def _should_include(self, name: str) -> bool:
        """Check if a name should be included based on settings."""
        if name.startswith("__") and name.endswith("__"):
            return self.include_dunder
        if name.startswith("_"):
            return self.include_private
        return True

    def _is_method(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> bool:
        """Check if a function is a method (has self/cls parameter)."""
        if node.args.args:
            first_arg = node.args.args[0].arg
            return first_arg in _SELF_CLS_ARGS
        return False

    def _build_signature(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> str:
        """Build function signature string."""
        params = []

        for arg in node.args.args:
            if arg.arg in _SELF_CLS_ARGS:
                continue
            param_str = arg.arg
            if arg.annotation:
                param_str += f": {self._get_node_name(arg.annotation)}"
            params.append(param_str)

        for arg in node.args.kwonlyargs:
            param_str = arg.arg
            if arg.annotation:
                param_str += f": {self._get_node_name(arg.annotation)}"
            params.append(param_str)

        signature = f"({', '.join(params)})"

        if node.returns:
            signature += f" -> {self._get_node_name(node.returns)}"

        return signature

    def _get_node_name(self, node: Optional[ast.AST]) -> str:
        """Get the name representation of an AST node."""
        if node is None:
            return "None"
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{self._get_node_name(node.value)}.{node.attr}"
        if isinstance(node, ast.Subscript):
            return f"{self._get_node_name(node.value)}[{self._get_node_name(node.slice)}]"
        if isinstance(node, ast.Constant):
            return repr(node.value)
        if isinstance(node, ast.Tuple):
            return f"({', '.join(self._get_node_name(e) for e in node.elts)})"
        if isinstance(node, ast.List):
            return f"[{', '.join(self._get_node_name(e) for e in node.elts)}]"
        if isinstance(node, ast.Call):
            return self._get_node_name(node.func)
        if isinstance(node, ast.BinOp):
            return f"{self._get_node_name(node.left)} | {self._get_node_name(node.right)}"
        return str(type(node).__name__)

    def _get_node_value(self, node: Optional[ast.AST]) -> str:
        """Get the value representation of an AST node."""
        if node is None:
            return "None"
        if isinstance(node, ast.Constant):
            return repr(node.value)
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.List):
            return f"[{', '.join(self._get_node_value(e) for e in node.elts)}]"
        if isinstance(node, ast.Dict):
            items = [
                f"{self._get_node_value(k)}: {self._get_node_value(v)}"
                for k, v in zip(node.keys, node.values)
            ]
            return "{" + ", ".join(items) + "}"
        if isinstance(node, ast.Tuple):
            return f"({', '.join(self._get_node_value(e) for e in node.elts)})"
        if isinstance(node, ast.Call):
            return f"{self._get_node_name(node.func)}(...)"
        return "..."

    def _extract_description(self, docstring: str) -> str:
        """Extract the description (first paragraph) from a docstring."""
        if not docstring:
            return ""

        lines = docstring.strip().split("\n")
        description_lines = []

        for line in lines:
            stripped = line.strip()
            # Stop at section headers or empty lines after content
            if any(p.match(stripped) for p in self.DOCSTRING_SECTIONS.values()):
                break
            if not stripped and description_lines:
                break
            if stripped:
                description_lines.append(stripped)

        return " ".join(description_lines)

    def _extract_imports(self, node: Union[ast.Import, ast.ImportFrom]) -> List[str]:
        """Extract import statements."""
        imports = []

        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                imports.append(f"{module}.{alias.name}" if module else alias.name)

        return imports

    def _is_all_assignment(self, node: ast.AST) -> bool:
        """Check if node is an __all__ assignment (Issue #315 - extracted helper)."""
        if not isinstance(node, ast.Assign):
            return False
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "__all__":
                return True
        return False

    def _extract_all_values(self, value_node: ast.AST) -> List[str]:
        """Extract string values from __all__ list/tuple (Issue #315 - extracted helper)."""
        if not isinstance(value_node, _SEQUENCE_TYPES):  # Issue #380
            return []
        return [
            e.value
            for e in value_node.elts
            if isinstance(e, ast.Constant) and isinstance(e.value, str)
        ]

    def _extract_all_exports(self, tree: ast.Module) -> List[str]:
        """Extract __all__ exports from a module."""
        for node in ast.iter_child_nodes(tree):
            if not self._is_all_assignment(node):
                continue
            return self._extract_all_values(node.value)
        return []

    def _extract_dependencies(self, imports: List[str]) -> List[str]:
        """Extract third-party dependencies from imports."""
        stdlib_modules = {
            "abc", "asyncio", "collections", "contextlib", "copy", "dataclasses",
            "datetime", "enum", "functools", "hashlib", "inspect", "io", "itertools",
            "json", "logging", "math", "os", "pathlib", "random", "re", "shutil",
            "socket", "sqlite3", "string", "subprocess", "sys", "tempfile", "textwrap",
            "threading", "time", "traceback", "typing", "unittest", "urllib", "uuid",
            "warnings", "weakref",
        }

        dependencies = []
        for imp in imports:
            top_level = imp.split(".")[0]
            if top_level not in stdlib_modules and not top_level.startswith("src"):
                if top_level not in dependencies:
                    dependencies.append(top_level)

        return dependencies

    def _extract_version(self, package_path: str) -> Optional[str]:
        """Extract version from package."""
        # Check __init__.py
        init_path = os.path.join(package_path, "__init__.py")
        if os.path.exists(init_path):
            try:
                with open(init_path, "r", encoding="utf-8") as f:
                    content = f.read()
                match = _VERSION_RE.search(content)
                if match:
                    return match.group(1)
            except OSError:
                pass

        # Check setup.py
        setup_path = os.path.join(os.path.dirname(package_path), "setup.py")
        if os.path.exists(setup_path):
            try:
                with open(setup_path, "r", encoding="utf-8") as f:
                    content = f.read()
                match = _SETUP_VERSION_RE.search(content)
                if match:
                    return match.group(1)
            except OSError:
                pass

        return None

    def _extract_author(self, package_path: str) -> Optional[str]:
        """Extract author from package."""
        init_path = os.path.join(package_path, "__init__.py")
        if os.path.exists(init_path):
            try:
                with open(init_path, "r", encoding="utf-8") as f:
                    content = f.read()
                match = _AUTHOR_RE.search(content)
                if match:
                    return match.group(1)
            except OSError:
                pass
        return None

    # =========================================================================
    # Documentation Generation
    # =========================================================================

    def generate_api_docs(
        self,
        modules: List[ModuleDoc],
        title: str = "API Reference",
        format: DocFormat = DocFormat.MARKDOWN,
        include_toc: bool = True,
        include_diagrams: bool = True,
    ) -> GeneratedDoc:
        """
        Generate API documentation from analyzed modules.

        Args:
            modules: List of analyzed module documentation
            title: Documentation title
            format: Output format (Markdown, HTML, etc.)
            include_toc: Include table of contents
            include_diagrams: Include class diagrams

        Returns:
            GeneratedDoc with the generated content
        """
        if format == DocFormat.MARKDOWN:
            return self._generate_markdown_api(
                modules, title, include_toc, include_diagrams
            )
        elif format == DocFormat.HTML:
            return self._generate_html_api(modules, title, include_toc, include_diagrams)
        else:
            # Default to markdown
            return self._generate_markdown_api(
                modules, title, include_toc, include_diagrams
            )

    def _generate_markdown_api(
        self,
        modules: List[ModuleDoc],
        title: str,
        include_toc: bool,
        include_diagrams: bool,
    ) -> GeneratedDoc:
        """Generate Markdown API documentation."""
        lines = [f"# {title}", ""]

        # Table of contents
        if include_toc:
            lines.extend(self._generate_toc(modules))
            lines.append("")

        diagrams = []

        # Process each module
        for module in modules:
            lines.append(f"## Module: `{module.name}`")
            lines.append("")

            if module.file_path:
                lines.append(f"**File:** `{module.file_path}`")
                lines.append("")

            if module.description:
                lines.append(module.description)
                lines.append("")

            # Module-level constants
            if module.constants:
                lines.append("### Constants")
                lines.append("")
                for name, value in module.constants.items():
                    lines.append(f"- `{name}` = `{value}`")
                lines.append("")

            # Generate class diagram
            if include_diagrams and module.classes:
                diagram = self._generate_class_diagram(module)
                diagrams.append(diagram)
                lines.append("### Class Diagram")
                lines.append("")
                lines.append("```mermaid")
                lines.append(diagram.to_mermaid())
                lines.append("```")
                lines.append("")

            # Classes
            for class_doc in module.classes:
                lines.extend(self._generate_class_markdown(class_doc))

            # Functions
            if module.functions:
                lines.append("### Functions")
                lines.append("")
                for func_doc in module.functions:
                    lines.extend(self._generate_function_markdown(func_doc))

            lines.append("---")
            lines.append("")

        content = "\n".join(lines)
        word_count = len(content.split())

        # Calculate overall completeness
        all_completeness = [m.completeness for m in modules]
        completeness_map = {
            DocCompleteness.NONE: 0,
            DocCompleteness.MINIMAL: 25,
            DocCompleteness.PARTIAL: 50,
            DocCompleteness.COMPLETE: 75,
            DocCompleteness.COMPREHENSIVE: 100,
        }
        avg_completeness = sum(completeness_map[c] for c in all_completeness) / len(all_completeness) if all_completeness else 0

        return GeneratedDoc(
            title=title,
            content=content,
            format=DocFormat.MARKDOWN,
            sections=[DocSection.API_REFERENCE],
            source_files=[m.file_path for m in modules],
            diagrams=diagrams,
            word_count=word_count,
            completeness_score=avg_completeness,
        )

    def _generate_toc(self, modules: List[ModuleDoc]) -> List[str]:
        """Generate table of contents."""
        lines = ["## Table of Contents", ""]

        for module in modules:
            module_anchor = module.name.lower().replace(".", "-")
            lines.append(f"- [Module: `{module.name}`](#{module_anchor})")

            for class_doc in module.classes:
                class_anchor = f"{module_anchor}-{class_doc.name.lower()}"
                lines.append(f"  - [Class: `{class_doc.name}`](#{class_anchor})")

            if module.functions:
                lines.append("  - [Functions](#functions)")

        return lines

    def _generate_class_markdown(self, class_doc: ClassDoc) -> List[str]:
        """Generate Markdown documentation for a class."""
        lines = [f"### Class: `{class_doc.name}`", ""]

        # Inheritance
        if class_doc.base_classes:
            bases = ", ".join(f"`{b}`" for b in class_doc.base_classes)
            lines.append(f"**Inherits from:** {bases}")
            lines.append("")

        # Decorators
        if class_doc.decorators:
            decorators = ", ".join(f"`@{d}`" for d in class_doc.decorators)
            lines.append(f"**Decorators:** {decorators}")
            lines.append("")

        # Description
        if class_doc.description:
            lines.append(class_doc.description)
            lines.append("")

        # Class variables
        if class_doc.class_variables:
            lines.append("#### Class Variables")
            lines.append("")
            lines.append("| Name | Type |")
            lines.append("|------|------|")
            for name, type_hint in class_doc.class_variables.items():
                lines.append(f"| `{name}` | `{type_hint}` |")
            lines.append("")

        # Properties
        if class_doc.properties:
            lines.append("#### Properties")
            lines.append("")
            for prop in class_doc.properties:
                lines.extend(self._generate_function_markdown(prop, is_property=True))

        # Methods
        if class_doc.methods:
            lines.append("#### Methods")
            lines.append("")
            for method in class_doc.methods:
                lines.extend(self._generate_function_markdown(method))

        # Examples
        if class_doc.examples:
            lines.append("#### Examples")
            lines.append("")
            for example in class_doc.examples:
                if example.description:
                    lines.append(example.description)
                    lines.append("")
                lines.append(f"```{example.language}")
                lines.append(example.code)
                lines.append("```")
                lines.append("")

        return lines

    def _generate_function_markdown(
        self, func_doc: FunctionDoc, is_property: bool = False
    ) -> List[str]:
        """Generate Markdown documentation for a function/method."""
        lines = []

        # Header
        prefix = "async " if func_doc.is_async else ""
        decorator_info = ""
        if func_doc.is_static:
            decorator_info = " `@staticmethod`"
        elif func_doc.is_classmethod:
            decorator_info = " `@classmethod`"
        elif is_property or func_doc.is_property:
            decorator_info = " `@property`"

        lines.append(f"##### `{prefix}{func_doc.name}`{decorator_info}")
        lines.append("")

        # Signature
        lines.append("```python")
        lines.append(f"def {func_doc.name}{func_doc.signature}")
        lines.append("```")
        lines.append("")

        # Description
        if func_doc.description:
            lines.append(func_doc.description)
            lines.append("")

        # Parameters
        if func_doc.parameters:
            lines.append("**Parameters:**")
            lines.append("")
            for param in func_doc.parameters:
                type_info = f": `{param.type_hint}`" if param.type_hint else ""
                default_info = f" (default: `{param.default_value}`)" if param.default_value else ""
                desc = f" - {param.description}" if param.description else ""
                lines.append(f"- `{param.name}`{type_info}{default_info}{desc}")
            lines.append("")

        # Returns
        if func_doc.returns:
            type_info = f"`{func_doc.returns.type_hint}`" if func_doc.returns.type_hint else ""
            desc = f": {func_doc.returns.description}" if func_doc.returns.description else ""
            lines.append(f"**Returns:** {type_info}{desc}")
            lines.append("")

        # Exceptions
        if func_doc.exceptions:
            lines.append("**Raises:**")
            lines.append("")
            for exc in func_doc.exceptions:
                desc = f": {exc.description}" if exc.description else ""
                lines.append(f"- `{exc.exception_type}`{desc}")
            lines.append("")

        # Examples
        if func_doc.examples:
            lines.append("**Example:**")
            lines.append("")
            for example in func_doc.examples:
                lines.append("```python")
                lines.append(example.code)
                lines.append("```")
                lines.append("")

        return lines

    def _generate_class_diagram(self, module: ModuleDoc) -> DiagramSpec:
        """Generate a class diagram specification for a module."""
        diagram = DiagramSpec(
            diagram_type=DiagramType.CLASS_DIAGRAM,
            title=f"{module.name} Class Diagram",
        )

        for class_doc in module.classes:
            element = {
                "name": class_doc.name,
                "attributes": list(class_doc.class_variables.keys())[:5],  # Limit
                "methods": [m.name for m in class_doc.methods[:5]],  # Limit
            }
            diagram.elements.append(element)

            # Add inheritance relationships
            for base in class_doc.base_classes:
                if base not in _SKIP_INHERITANCE_BASES:
                    diagram.relationships.append((class_doc.name, base, "inherits"))

        return diagram

    def _generate_html_api(
        self,
        modules: List[ModuleDoc],
        title: str,
        include_toc: bool,
        include_diagrams: bool,
    ) -> GeneratedDoc:
        """Generate HTML API documentation."""
        # First generate markdown, then convert to HTML
        md_doc = self._generate_markdown_api(modules, title, include_toc, include_diagrams)

        # Simple markdown to HTML conversion
        html_content = self._markdown_to_html(md_doc.content)

        html_page = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; max-width: 900px; margin: 0 auto; padding: 20px; }}
        code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }}
        pre {{ background: #f4f4f4; padding: 15px; border-radius: 5px; overflow-x: auto; }}
        pre code {{ background: none; padding: 0; }}
        table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
        th {{ background: #f4f4f4; }}
        h1 {{ border-bottom: 2px solid #333; padding-bottom: 10px; }}
        h2 {{ border-bottom: 1px solid #ddd; padding-bottom: 5px; margin-top: 40px; }}
        h3 {{ color: #333; margin-top: 30px; }}
        hr {{ border: none; border-top: 1px solid #ddd; margin: 30px 0; }}
    </style>
</head>
<body>
{html_content}
</body>
</html>"""

        return GeneratedDoc(
            title=title,
            content=html_page,
            format=DocFormat.HTML,
            sections=[DocSection.API_REFERENCE],
            source_files=md_doc.source_files,
            diagrams=md_doc.diagrams,
            word_count=md_doc.word_count,
            completeness_score=md_doc.completeness_score,
        )

    def _markdown_to_html(self, markdown: str) -> str:
        """Simple Markdown to HTML conversion."""
        html = markdown

        # Headers (Issue #380: use pre-compiled patterns)
        html = _MD_H5_RE.sub(r"<h5>\1</h5>", html)
        html = _MD_H4_RE.sub(r"<h4>\1</h4>", html)
        html = _MD_H3_RE.sub(r"<h3>\1</h3>", html)
        html = _MD_H2_RE.sub(r"<h2>\1</h2>", html)
        html = _MD_H1_RE.sub(r"<h1>\1</h1>", html)

        # Code blocks (Issue #380: use pre-compiled pattern)
        html = _MD_CODE_BLOCK_RE.sub(r"<pre><code>\2</code></pre>", html)

        # Inline code (Issue #380: use pre-compiled pattern)
        html = _MD_INLINE_CODE_RE.sub(r"<code>\1</code>", html)

        # Bold (Issue #380: use pre-compiled pattern)
        html = _MD_BOLD_RE.sub(r"<strong>\1</strong>", html)

        # Lists (Issue #380: use pre-compiled pattern)
        html = _MD_LIST_ITEM_RE.sub(r"<li>\1</li>", html)

        # Horizontal rules (Issue #380: use pre-compiled pattern)
        html = _MD_HR_RE.sub(r"<hr>", html)

        # Paragraphs (simple approach)
        lines = html.split("\n")
        result = []
        in_list = False
        for line in lines:
            if line.startswith("<li>"):
                if not in_list:
                    result.append("<ul>")
                    in_list = True
                result.append(line)
            else:
                if in_list:
                    result.append("</ul>")
                    in_list = False
                result.append(line)
        if in_list:
            result.append("</ul>")

        return "\n".join(result)

    def generate_module_overview(
        self,
        module: ModuleDoc,
        format: DocFormat = DocFormat.MARKDOWN,
    ) -> GeneratedDoc:
        """
        Generate an overview document for a single module.

        Args:
            module: Analyzed module documentation
            format: Output format

        Returns:
            GeneratedDoc with the overview
        """
        lines = [f"# {module.name}", ""]

        if module.description:
            lines.append(module.description)
            lines.append("")

        # Quick stats
        lines.append("## Overview")
        lines.append("")
        lines.append(f"- **Classes:** {len(module.classes)}")
        lines.append(f"- **Functions:** {len(module.functions)}")
        lines.append(f"- **Constants:** {len(module.constants)}")
        lines.append(f"- **Lines of code:** {module.line_count}")
        lines.append(f"- **Documentation completeness:** {module.completeness.value}")
        lines.append("")

        # Dependencies
        if module.dependencies:
            lines.append("## Dependencies")
            lines.append("")
            for dep in module.dependencies:
                lines.append(f"- `{dep}`")
            lines.append("")

        # Exports
        if module.exports:
            lines.append("## Public API (exports)")
            lines.append("")
            for export in module.exports:
                lines.append(f"- `{export}`")
            lines.append("")

        content = "\n".join(lines)

        return GeneratedDoc(
            title=f"{module.name} Overview",
            content=content,
            format=format,
            sections=[DocSection.OVERVIEW],
            source_files=[module.file_path],
            word_count=len(content.split()),
            completeness_score=100 if module.completeness == DocCompleteness.COMPREHENSIVE else 50,
        )


# =============================================================================
# Convenience Functions
# =============================================================================


def analyze_module(file_path: str, **kwargs) -> Optional[ModuleDoc]:
    """
    Analyze a Python module and extract documentation.

    Args:
        file_path: Path to the Python file
        **kwargs: Additional options for DocGenerator

    Returns:
        ModuleDoc containing extracted documentation
    """
    generator = DocGenerator(**kwargs)
    return generator.analyze_module(file_path)


def analyze_package(package_path: str, **kwargs) -> Optional[PackageDoc]:
    """
    Analyze a Python package and all its modules.

    Args:
        package_path: Path to the package directory
        **kwargs: Additional options for DocGenerator

    Returns:
        PackageDoc containing package documentation
    """
    generator = DocGenerator(**kwargs)
    return generator.analyze_package(package_path)


def generate_docs(
    path: str,
    output_path: Optional[str] = None,
    format: DocFormat = DocFormat.MARKDOWN,
    title: str = "API Documentation",
    **kwargs,
) -> GeneratedDoc:
    """
    Generate documentation for a module or package.

    Args:
        path: Path to module file or package directory
        output_path: Optional path to write output
        format: Output format (markdown, html)
        title: Documentation title
        **kwargs: Additional options for DocGenerator

    Returns:
        GeneratedDoc with the generated content
    """
    generator = DocGenerator(**kwargs)

    if os.path.isfile(path):
        module = generator.analyze_module(path)
        modules = [module] if module else []
    else:
        package = generator.analyze_package(path)
        modules = package.modules if package else []

    doc = generator.generate_api_docs(modules, title=title, format=format)

    if output_path:
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(doc.content)
            logger.info(f"Documentation written to: {output_path}")
        except OSError as e:
            logger.error(f"Failed to write documentation: {e}")

    return doc


def get_doc_formats() -> List[str]:
    """Get available documentation formats."""
    return [f.value for f in DocFormat]


def get_doc_sections() -> List[str]:
    """Get available documentation sections."""
    return [s.value for s in DocSection]


def get_element_types() -> List[str]:
    """Get available element types."""
    return [e.value for e in ElementType]


def get_diagram_types() -> List[str]:
    """Get available diagram types."""
    return [d.value for d in DiagramType]


def get_completeness_levels() -> List[str]:
    """Get documentation completeness levels."""
    return [c.value for c in DocCompleteness]
