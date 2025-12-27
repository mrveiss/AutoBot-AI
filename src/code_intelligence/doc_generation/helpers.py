# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AST Helper Utilities for Documentation Generation.

Provides utility functions for working with Python AST nodes,
extracting values, names, and types from parsed code.

Part of Issue #381 god class refactoring - extracted from DocGenerator.
"""

import ast
import os
import re
from typing import FrozenSet, List, Optional, Tuple, Union

# Issue #380: Module-level frozenset for enum base class checking
ENUM_BASE_CLASSES: FrozenSet[str] = frozenset({"Enum", "IntEnum", "StrEnum"})
ABSTRACT_DECORATORS: FrozenSet[str] = frozenset({"ABC", "abstractmethod"})
SELF_CLS_ARGS: FrozenSet[str] = frozenset({"self", "cls"})
SKIP_INHERITANCE_BASES: FrozenSet[str] = frozenset({"object", "ABC", "Enum"})

# Issue #380: Module-level tuple for function definition AST nodes
FUNCTION_DEF_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)
IMPORT_TYPES = (ast.Import, ast.ImportFrom)
SEQUENCE_TYPES = (ast.List, ast.Tuple)

# Issue #380: Pre-compiled regex patterns for version/author extraction
VERSION_RE = re.compile(r'__version__\s*=\s*["\']([^"\']+)["\']')
SETUP_VERSION_RE = re.compile(r'version\s*=\s*["\']([^"\']+)["\']')
AUTHOR_RE = re.compile(r'__author__\s*=\s*["\']([^"\']+)["\']')

# Standard library modules for dependency detection
STDLIB_MODULES = frozenset({
    "abc", "asyncio", "collections", "contextlib", "copy", "dataclasses",
    "datetime", "enum", "functools", "hashlib", "inspect", "io", "itertools",
    "json", "logging", "math", "os", "pathlib", "random", "re", "shutil",
    "socket", "sqlite3", "string", "subprocess", "sys", "tempfile", "textwrap",
    "threading", "time", "traceback", "typing", "unittest", "urllib", "uuid",
    "warnings", "weakref",
})

# Standard README file names
README_NAMES = ["README.md", "README.rst", "README.txt", "README"]


def get_node_name(node: Optional[ast.AST]) -> str:
    """Get the name representation of an AST node.

    Args:
        node: AST node to get name from

    Returns:
        String representation of the node name
    """
    if node is None:
        return "None"
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{get_node_name(node.value)}.{node.attr}"
    if isinstance(node, ast.Subscript):
        return f"{get_node_name(node.value)}[{get_node_name(node.slice)}]"
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.Tuple):
        return f"({', '.join(get_node_name(e) for e in node.elts)})"
    if isinstance(node, ast.List):
        return f"[{', '.join(get_node_name(e) for e in node.elts)}]"
    if isinstance(node, ast.Call):
        return get_node_name(node.func)
    if isinstance(node, ast.BinOp):
        return f"{get_node_name(node.left)} | {get_node_name(node.right)}"
    return str(type(node).__name__)


def get_node_value(node: Optional[ast.AST]) -> str:
    """Get the value representation of an AST node.

    Args:
        node: AST node to get value from

    Returns:
        String representation of the node value
    """
    if node is None:
        return "None"
    if isinstance(node, ast.Constant):
        return repr(node.value)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.List):
        return f"[{', '.join(get_node_value(e) for e in node.elts)}]"
    if isinstance(node, ast.Dict):
        items = [
            f"{get_node_value(k)}: {get_node_value(v)}"
            for k, v in zip(node.keys, node.values)
        ]
        return "{" + ", ".join(items) + "}"
    if isinstance(node, ast.Tuple):
        return f"({', '.join(get_node_value(e) for e in node.elts)})"
    if isinstance(node, ast.Call):
        return f"{get_node_name(node.func)}(...)"
    return "..."


def extract_imports(node: Union[ast.Import, ast.ImportFrom]) -> List[str]:
    """Extract import statements from AST node.

    Args:
        node: Import or ImportFrom AST node

    Returns:
        List of imported module names
    """
    imports = []

    if isinstance(node, ast.Import):
        for alias in node.names:
            imports.append(alias.name)
    elif isinstance(node, ast.ImportFrom):
        module = node.module or ""
        for alias in node.names:
            imports.append(f"{module}.{alias.name}" if module else alias.name)

    return imports


def extract_dependencies(imports: List[str]) -> List[str]:
    """Extract third-party dependencies from imports.

    Args:
        imports: List of import statements

    Returns:
        List of third-party dependency names
    """
    dependencies = []
    for imp in imports:
        top_level = imp.split(".")[0]
        if top_level not in STDLIB_MODULES and not top_level.startswith("src"):
            if top_level not in dependencies:
                dependencies.append(top_level)
    return dependencies


def extract_description(docstring: str, section_patterns: dict) -> str:
    """Extract the description (first paragraph) from a docstring.

    Args:
        docstring: Full docstring text
        section_patterns: Dict of section header regex patterns

    Returns:
        First paragraph of docstring as description
    """
    if not docstring:
        return ""

    lines = docstring.strip().split("\n")
    description_lines = []

    for line in lines:
        stripped = line.strip()
        # Stop at section headers or empty lines after content
        if any(p.match(stripped) for p in section_patterns.values()):
            break
        if not stripped and description_lines:
            break
        if stripped:
            description_lines.append(stripped)

    return " ".join(description_lines)


def is_all_assignment(node: ast.AST) -> bool:
    """Check if node is an __all__ assignment.

    Args:
        node: AST node to check

    Returns:
        True if this is an __all__ assignment
    """
    if not isinstance(node, ast.Assign):
        return False
    for target in node.targets:
        if isinstance(target, ast.Name) and target.id == "__all__":
            return True
    return False


def extract_all_values(value_node: ast.AST) -> List[str]:
    """Extract string values from __all__ list/tuple.

    Args:
        value_node: AST node containing __all__ value

    Returns:
        List of exported names
    """
    if not isinstance(value_node, SEQUENCE_TYPES):
        return []
    return [
        e.value
        for e in value_node.elts
        if isinstance(e, ast.Constant) and isinstance(e.value, str)
    ]


def extract_all_exports(tree: ast.Module) -> List[str]:
    """Extract __all__ exports from a module.

    Args:
        tree: Parsed module AST

    Returns:
        List of exported names
    """
    for node in ast.iter_child_nodes(tree):
        if not is_all_assignment(node):
            continue
        return extract_all_values(node.value)
    return []


class PackageContentCache:
    """Cache for pre-loaded package file contents.

    Issue #623: Provides a pattern where files are read once at a higher level,
    then passed to multiple analyzers that work with the pre-loaded content.

    Usage:
        cache = PackageContentCache(package_path)
        version = cache.extract_version()
        author = cache.extract_author()
        readme = cache.readme_content
    """

    def __init__(self, package_path: str):
        """Initialize cache by pre-loading relevant package files.

        Args:
            package_path: Path to package directory
        """
        self.package_path = package_path
        self._init_content: Optional[str] = None
        self._setup_content: Optional[str] = None
        self._readme_content: Optional[str] = None
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Lazy-load all relevant package files once."""
        if self._loaded:
            return

        # Read __init__.py
        init_path = os.path.join(self.package_path, "__init__.py")
        if os.path.exists(init_path):
            try:
                with open(init_path, "r", encoding="utf-8") as f:
                    self._init_content = f.read()
            except OSError:
                pass

        # Read setup.py (in parent dir)
        setup_path = os.path.join(os.path.dirname(self.package_path), "setup.py")
        if os.path.exists(setup_path):
            try:
                with open(setup_path, "r", encoding="utf-8") as f:
                    self._setup_content = f.read()
            except OSError:
                pass

        # Read README
        for readme_name in README_NAMES:
            readme_path = os.path.join(self.package_path, readme_name)
            if os.path.exists(readme_path):
                try:
                    with open(readme_path, "r", encoding="utf-8") as f:
                        self._readme_content = f.read()
                    break
                except OSError:
                    pass

        self._loaded = True

    def extract_version(self) -> Optional[str]:
        """Extract version from pre-loaded content."""
        self._ensure_loaded()

        # Check __init__.py first
        if self._init_content:
            match = VERSION_RE.search(self._init_content)
            if match:
                return match.group(1)

        # Fallback to setup.py
        if self._setup_content:
            match = SETUP_VERSION_RE.search(self._setup_content)
            if match:
                return match.group(1)

        return None

    def extract_author(self) -> Optional[str]:
        """Extract author from pre-loaded content."""
        self._ensure_loaded()

        if self._init_content:
            match = AUTHOR_RE.search(self._init_content)
            if match:
                return match.group(1)

        return None

    @property
    def readme_content(self) -> Optional[str]:
        """Get pre-loaded README content."""
        self._ensure_loaded()
        return self._readme_content

    def get_all_metadata(self) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Get all metadata in one call.

        Returns:
            Tuple of (version, author, readme_content)
        """
        self._ensure_loaded()
        return self.extract_version(), self.extract_author(), self._readme_content


def extract_package_metadata(package_path: str) -> Tuple[Optional[str], Optional[str]]:
    """Extract version and author from package in single file read.

    Issue #623: Consolidates extract_version and extract_author to avoid
    repeated file opens on __init__.py.

    Args:
        package_path: Path to package directory

    Returns:
        Tuple of (version, author), either may be None
    """
    cache = PackageContentCache(package_path)
    return cache.extract_version(), cache.extract_author()


def extract_version(package_path: str) -> Optional[str]:
    """Extract version from package.

    Args:
        package_path: Path to package directory

    Returns:
        Version string if found
    """
    cache = PackageContentCache(package_path)
    return cache.extract_version()


def extract_author(package_path: str) -> Optional[str]:
    """Extract author from package.

    Args:
        package_path: Path to package directory

    Returns:
        Author string if found
    """
    cache = PackageContentCache(package_path)
    return cache.extract_author()


def load_readme_content(package_path: str) -> Optional[str]:
    """Load README content if available.

    Args:
        package_path: Path to package directory

    Returns:
        README content if found
    """
    cache = PackageContentCache(package_path)
    return cache.readme_content


def validate_module_path(file_path: str) -> Optional[str]:
    """Validate module path exists and is a Python file.

    Args:
        file_path: Path to validate

    Returns:
        Absolute path if valid, None otherwise
    """
    import logging
    logger = logging.getLogger(__name__)

    abs_path = os.path.abspath(file_path)

    if not os.path.exists(abs_path):
        logger.error("File not found: %s", abs_path)
        return None

    if not abs_path.endswith(".py"):
        logger.warning("Not a Python file: %s", abs_path)
        return None

    return abs_path


def read_and_parse_module(file_path: str) -> Optional[Tuple[str, ast.Module]]:
    """Read and parse a Python module.

    Args:
        file_path: Path to the Python file

    Returns:
        Tuple of (source, ast) or None on error
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
    except OSError as e:
        logger.error("Failed to read file %s: %s", file_path, e)
        return None

    try:
        tree = ast.parse(source, filename=file_path)
        return (source, tree)
    except SyntaxError as e:
        logger.error("Syntax error in %s: %s", file_path, e)
        return None


def build_signature(node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> str:
    """Build function signature string.

    Args:
        node: Function definition AST node

    Returns:
        Signature string like "(arg1: Type, arg2) -> ReturnType"
    """
    params = []

    for arg in node.args.args:
        if arg.arg in SELF_CLS_ARGS:
            continue
        param_str = arg.arg
        if arg.annotation:
            param_str += f": {get_node_name(arg.annotation)}"
        params.append(param_str)

    for arg in node.args.kwonlyargs:
        param_str = arg.arg
        if arg.annotation:
            param_str += f": {get_node_name(arg.annotation)}"
        params.append(param_str)

    signature = f"({', '.join(params)})"

    if node.returns:
        signature += f" -> {get_node_name(node.returns)}"

    return signature


def is_method(node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> bool:
    """Check if a function is a method (has self/cls parameter).

    Args:
        node: Function definition AST node

    Returns:
        True if this is a method
    """
    if node.args.args:
        first_arg = node.args.args[0].arg
        return first_arg in SELF_CLS_ARGS
    return False


__all__ = [
    # Constants
    "ENUM_BASE_CLASSES",
    "ABSTRACT_DECORATORS",
    "SELF_CLS_ARGS",
    "SKIP_INHERITANCE_BASES",
    "FUNCTION_DEF_TYPES",
    "IMPORT_TYPES",
    "SEQUENCE_TYPES",
    "STDLIB_MODULES",
    "README_NAMES",
    "VERSION_RE",
    "SETUP_VERSION_RE",
    "AUTHOR_RE",
    # Functions
    "get_node_name",
    "get_node_value",
    "extract_imports",
    "extract_dependencies",
    "extract_description",
    "is_all_assignment",
    "extract_all_values",
    "extract_all_exports",
    "PackageContentCache",
    "extract_package_metadata",
    "extract_version",
    "extract_author",
    "load_readme_content",
    "validate_module_path",
    "read_and_parse_module",
    "build_signature",
    "is_method",
]
