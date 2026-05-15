# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Documentation Models Module

Contains larger data classes for documentation entities:
- FunctionDoc, ClassDoc, ModuleDoc, PackageDoc
- DiagramSpec, GeneratedDoc

Extracted from doc_generator.py as part of Issue #381 refactoring.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from code_intelligence.doc_generation.types import (
    DiagramType,
    DocCompleteness,
    DocFormat,
    DocSection,
    ElementType,
    ExampleDoc,
    ExceptionDoc,
    ParameterDoc,
    ReturnDoc,
)

# Issue #380: Module-level frozenset for enum base class checking
_ENUM_BASE_CLASSES: FrozenSet[str] = frozenset({"Enum", "IntEnum", "StrEnum"})
_ABSTRACT_DECORATORS: FrozenSet[str] = frozenset({"ABC", "abstractmethod"})


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
                {
                    "none": 0,
                    "minimal": 1,
                    "partial": 2,
                    "complete": 3,
                    "comprehensive": 4,
                }[s]
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
                {
                    "none": 0,
                    "minimal": 1,
                    "partial": 2,
                    "complete": 3,
                    "comprehensive": 4,
                }[s]
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
