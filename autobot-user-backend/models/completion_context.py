# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Completion Context Model (Issue #907)

Data model for multi-level code context analysis.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class CompletionContext:
    """
    Multi-level context for code completion.

    Captures file, function, block, and line-level context
    to enable intelligent, context-aware completions.
    """

    # Metadata
    context_id: str
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # File-level context
    file_path: str = ""
    language: str = ""
    imports: List[str] = field(default_factory=list)
    defined_classes: List[str] = field(default_factory=list)
    defined_functions: List[str] = field(default_factory=list)
    module_docstring: Optional[str] = None

    # Function-level context
    current_function: Optional[str] = None
    function_params: List[Tuple[str, str]] = field(default_factory=list)  # (name, type)
    function_return_type: Optional[str] = None
    decorators: List[str] = field(default_factory=list)

    # Block-level context
    variables_in_scope: Dict[str, str] = field(
        default_factory=dict
    )  # name -> inferred type
    control_flow_type: Optional[str] = None  # if/for/while/try/with
    indent_level: int = 0

    # Line-level context
    cursor_line: str = ""
    cursor_position: int = 0
    preceding_lines: List[str] = field(default_factory=list)
    following_lines: List[str] = field(default_factory=list)
    partial_statement: str = ""
    expected_type: Optional[str] = None

    # Semantic context
    detected_frameworks: Set[str] = field(default_factory=set)
    coding_style: str = ""  # pep8, google, numpy
    recent_patterns: List[str] = field(default_factory=list)
    suggested_imports: List[str] = field(default_factory=list)

    # Dependency context
    import_aliases: Dict[str, str] = field(default_factory=dict)  # alias -> full_name
    used_imports: Set[str] = field(default_factory=set)
    missing_imports: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Serialize to dictionary for API responses."""
        return {
            "context_id": self.context_id,
            "timestamp": self.timestamp.isoformat(),
            "file_context": {
                "file_path": self.file_path,
                "language": self.language,
                "imports": self.imports,
                "defined_classes": self.defined_classes,
                "defined_functions": self.defined_functions,
                "module_docstring": self.module_docstring,
            },
            "function_context": {
                "current_function": self.current_function,
                "function_params": [
                    {"name": name, "type": type_}
                    for name, type_ in self.function_params
                ],
                "function_return_type": self.function_return_type,
                "decorators": self.decorators,
            },
            "block_context": {
                "variables_in_scope": self.variables_in_scope,
                "control_flow_type": self.control_flow_type,
                "indent_level": self.indent_level,
            },
            "line_context": {
                "cursor_line": self.cursor_line,
                "cursor_position": self.cursor_position,
                "preceding_lines": self.preceding_lines[-5:],  # Last 5 lines
                "following_lines": self.following_lines[:5],  # Next 5 lines
                "partial_statement": self.partial_statement,
                "expected_type": self.expected_type,
            },
            "semantic_context": {
                "detected_frameworks": list(self.detected_frameworks),
                "coding_style": self.coding_style,
                "recent_patterns": self.recent_patterns,
                "suggested_imports": self.suggested_imports,
            },
            "dependency_context": {
                "import_aliases": self.import_aliases,
                "used_imports": list(self.used_imports),
                "missing_imports": self.missing_imports,
            },
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "CompletionContext":
        """Deserialize from dictionary."""
        return cls(
            context_id=data["context_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            file_path=data["file_context"]["file_path"],
            language=data["file_context"]["language"],
            imports=data["file_context"]["imports"],
            defined_classes=data["file_context"]["defined_classes"],
            defined_functions=data["file_context"]["defined_functions"],
            module_docstring=data["file_context"]["module_docstring"],
            current_function=data["function_context"]["current_function"],
            function_params=[
                (p["name"], p["type"])
                for p in data["function_context"]["function_params"]
            ],
            function_return_type=data["function_context"]["function_return_type"],
            decorators=data["function_context"]["decorators"],
            variables_in_scope=data["block_context"]["variables_in_scope"],
            control_flow_type=data["block_context"]["control_flow_type"],
            indent_level=data["block_context"]["indent_level"],
            cursor_line=data["line_context"]["cursor_line"],
            cursor_position=data["line_context"]["cursor_position"],
            preceding_lines=data["line_context"]["preceding_lines"],
            following_lines=data["line_context"]["following_lines"],
            partial_statement=data["line_context"]["partial_statement"],
            expected_type=data["line_context"]["expected_type"],
            detected_frameworks=set(data["semantic_context"]["detected_frameworks"]),
            coding_style=data["semantic_context"]["coding_style"],
            recent_patterns=data["semantic_context"]["recent_patterns"],
            suggested_imports=data["semantic_context"]["suggested_imports"],
            import_aliases=data["dependency_context"]["import_aliases"],
            used_imports=set(data["dependency_context"]["used_imports"]),
            missing_imports=data["dependency_context"]["missing_imports"],
        )
