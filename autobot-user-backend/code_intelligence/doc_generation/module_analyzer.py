# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Module Analyzer for Documentation Generation

Analyzes Python modules, classes, and functions to extract documentation.
Extracted from DocGenerator as part of Issue #394.

Part of god class refactoring initiative.
"""

import ast
import os
from typing import List, Optional, Set, Union

from code_intelligence.doc_generation.types import (
    ElementType,
    ParameterDoc,
    ReturnDoc,
)
from code_intelligence.doc_generation.models import (
    ClassDoc,
    FunctionDoc,
    ModuleDoc,
    PackageDoc,
)
from code_intelligence.doc_generation import helpers
from code_intelligence.doc_generation.docstring_parser import DocstringParser

# Re-export constants for internal use
_FUNCTION_DEF_TYPES = helpers.FUNCTION_DEF_TYPES
_IMPORT_TYPES = helpers.IMPORT_TYPES
_SELF_CLS_ARGS = helpers.SELF_CLS_ARGS


class ModuleAnalyzer:
    """
    Analyzer for Python modules, classes, and functions.

    Extracts structured documentation from Python AST.

    Example:
        >>> analyzer = ModuleAnalyzer()
        >>> module_doc = analyzer.analyze_module('path/to/module.py')
    """

    # Decorator attribute mappings for functions
    _DECORATOR_ATTR_MAP = {
        "staticmethod": ("is_static", True),
        "classmethod": ("is_classmethod", True),
        "abstractmethod": ("is_abstract", True),
    }

    def __init__(
        self,
        include_private: bool = False,
        include_dunder: bool = False,
        max_depth: int = 10,
    ):
        """
        Initialize the module analyzer.

        Args:
            include_private: Include private members (_prefix)
            include_dunder: Include dunder methods (__name__)
            max_depth: Maximum recursion depth for package traversal
        """
        self.include_private = include_private
        self.include_dunder = include_dunder
        self.max_depth = max_depth
        self._analyzed_files: Set[str] = set()
        self._docstring_parser = DocstringParser()

    def analyze_module(self, file_path: str) -> Optional[ModuleDoc]:
        """
        Analyze a Python module and extract documentation.

        Args:
            file_path: Path to the Python file

        Returns:
            ModuleDoc containing extracted documentation, or None if parse fails
        """
        validated_path = helpers.validate_module_path(file_path)
        if validated_path is None:
            return None

        parsed = helpers.read_and_parse_module(validated_path)
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
            module_doc.description = helpers.extract_description(
                module_doc.docstring, self._docstring_parser.SECTION_PATTERNS
            )

        for node in ast.iter_child_nodes(tree):
            self._process_module_node(node, source, module_doc)

        module_doc.exports = helpers.extract_all_exports(tree)
        module_doc.dependencies = helpers.extract_dependencies(module_doc.imports)
        module_doc.completeness = module_doc.calculate_completeness()

        self._analyzed_files.add(validated_path)
        return module_doc

    def _process_module_node(
        self, node: ast.AST, source: str, module_doc: ModuleDoc
    ) -> None:
        """Process a single top-level module node."""
        if isinstance(node, ast.ClassDef):
            class_doc = self.analyze_class(node, source)
            if class_doc and self._should_include(class_doc.name):
                module_doc.classes.append(class_doc)
            return

        if isinstance(node, _FUNCTION_DEF_TYPES):
            func_doc = self.analyze_function(node, source)
            if func_doc and self._should_include(func_doc.name):
                module_doc.functions.append(func_doc)
            return

        if isinstance(node, ast.Assign):
            self._process_module_constants(node, module_doc)
            return

        if isinstance(node, _IMPORT_TYPES):
            for import_stmt in helpers.extract_imports(node):
                module_doc.add_import(import_stmt)

    def _process_module_constants(self, node: ast.Assign, module_doc: ModuleDoc) -> None:
        """Extract constants from assignment node."""
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if not target.id.isupper():
                continue
            value = helpers.get_node_value(node.value)
            module_doc.add_constant(target.id, value)

    def analyze_package(
        self, package_path: str, depth: int = 0
    ) -> Optional[PackageDoc]:
        """Analyze a Python package and all its modules."""
        import logging
        logger = logging.getLogger(__name__)

        if depth > self.max_depth:
            logger.warning("Max depth reached for package: %s", package_path)
            return None

        package_path = os.path.abspath(package_path)

        if not os.path.isdir(package_path):
            logger.error("Not a directory: %s", package_path)
            return None

        init_file = os.path.join(package_path, "__init__.py")
        if not os.path.exists(init_file):
            logger.warning("Not a Python package (no __init__.py): %s", package_path)
            return None

        package_name = os.path.basename(package_path)
        package_doc = PackageDoc(name=package_name, path=package_path)

        # Read __init__.py docstring
        init_module = self.analyze_module(init_file)
        if init_module:
            package_doc.init_docstring = init_module.docstring

        # Issue #623: Use PackageContentCache for efficient file loading
        # Files are read once, then all metadata extracted from pre-loaded content
        pkg_cache = helpers.PackageContentCache(package_path)
        package_doc.readme_content = pkg_cache.readme_content
        package_doc.version = pkg_cache.extract_version()
        package_doc.author = pkg_cache.extract_author()

        # Process all items in package
        for item in os.listdir(package_path):
            self._process_package_item(item, package_path, package_doc, depth)

        return package_doc

    def _process_package_item(
        self, item: str, package_path: str, package_doc: PackageDoc, depth: int
    ) -> None:
        """Process a single item in package directory."""
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

    def analyze_class(self, node: ast.ClassDef, source: str) -> ClassDoc:
        """Analyze a class definition and extract documentation."""
        class_doc = ClassDoc(
            name=node.name,
            docstring=ast.get_docstring(node),
            line_number=node.lineno,
        )

        for base in node.bases:
            class_doc.add_base_class(helpers.get_node_name(base))

        for decorator in node.decorator_list:
            dec_name = helpers.get_node_name(decorator)
            class_doc.add_decorator(dec_name)

        class_doc.check_enum_inheritance()

        if class_doc.docstring:
            class_doc.description = helpers.extract_description(
                class_doc.docstring, self._docstring_parser.SECTION_PATTERNS
            )

        for item in node.body:
            self._process_class_body_item(item, source, class_doc)

        class_doc.completeness = class_doc.calculate_completeness()
        return class_doc

    def _process_class_body_item(
        self, item: ast.AST, source: str, class_doc: ClassDoc
    ) -> None:
        """Process a single class body item."""
        if isinstance(item, _FUNCTION_DEF_TYPES):
            if not self._should_include(item.name):
                return
            func_doc = self.analyze_function(item, source)
            if func_doc:
                class_doc.add_method(func_doc)
            return

        if isinstance(item, ast.AnnAssign):
            self._process_annotated_class_var(item, class_doc)
            return

        if isinstance(item, ast.Assign):
            self._process_unannotated_class_var(item, class_doc)

    def _process_annotated_class_var(
        self, item: ast.AnnAssign, class_doc: ClassDoc
    ) -> None:
        """Process annotated class variable."""
        if not isinstance(item.target, ast.Name):
            return
        var_name = item.target.id
        var_type = helpers.get_node_name(item.annotation) if item.annotation else "Any"
        class_doc.add_class_variable(var_name, var_type)

    def _process_unannotated_class_var(
        self, item: ast.Assign, class_doc: ClassDoc
    ) -> None:
        """Process unannotated class variable."""
        for target in item.targets:
            if isinstance(target, ast.Name):
                class_doc.add_class_variable(target.id)

    def analyze_function(
        self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef], source: str
    ) -> FunctionDoc:
        """Analyze a function/method definition and extract documentation."""
        is_async = isinstance(node, ast.AsyncFunctionDef)
        element_type = ElementType.METHOD if helpers.is_method(node) else ElementType.FUNCTION

        func_doc = FunctionDoc(
            name=node.name,
            element_type=element_type,
            signature=helpers.build_signature(node),
            docstring=ast.get_docstring(node),
            is_async=is_async,
            line_number=node.lineno,
        )

        for decorator in node.decorator_list:
            dec_name = helpers.get_node_name(decorator)
            self._process_function_decorator(dec_name, func_doc)

        func_doc.parameters = self._extract_parameters(node)

        if node.returns:
            func_doc.returns = ReturnDoc(type_hint=helpers.get_node_name(node.returns))

        if func_doc.docstring:
            func_doc.description = helpers.extract_description(
                func_doc.docstring, self._docstring_parser.SECTION_PATTERNS
            )
            self._docstring_parser.enhance_function_doc(func_doc)

        func_doc.completeness = func_doc.calculate_completeness()
        return func_doc

    def _process_function_decorator(self, dec_name: str, func_doc: FunctionDoc) -> None:
        """Process a single function decorator."""
        func_doc.decorators.append(dec_name)

        # Handle property decorator specially
        if dec_name == "property":
            func_doc.is_property = True
            func_doc.element_type = ElementType.PROPERTY
            return

        # Use lookup for simple attribute decorators
        if dec_name in self._DECORATOR_ATTR_MAP:
            attr_name, attr_value = self._DECORATOR_ATTR_MAP[dec_name]
            setattr(func_doc, attr_name, attr_value)

    def _create_parameter(
        self,
        arg: ast.arg,
        is_positional_only: bool = False,
        is_keyword_only: bool = False,
    ) -> ParameterDoc:
        """
        Create a ParameterDoc from an ast.arg node.

        Issue #665: Extracted from _extract_parameters to reduce duplication.

        Args:
            arg: AST argument node
            is_positional_only: Whether this is a positional-only parameter
            is_keyword_only: Whether this is a keyword-only parameter

        Returns:
            ParameterDoc instance
        """
        return ParameterDoc(
            name=arg.arg,
            type_hint=helpers.get_node_name(arg.annotation) if arg.annotation else None,
            is_positional_only=is_positional_only,
            is_keyword_only=is_keyword_only,
        )

    def _extract_regular_args(
        self, args: ast.arguments
    ) -> List[ParameterDoc]:
        """
        Extract regular (non-keyword-only, non-positional-only) arguments.

        Issue #665: Extracted from _extract_parameters to improve maintainability.

        Args:
            args: AST arguments node

        Returns:
            List of ParameterDoc for regular arguments
        """
        params = []
        defaults_offset = len(args.args) - len(args.defaults)

        for i, arg in enumerate(args.args):
            if arg.arg in _SELF_CLS_ARGS:
                continue

            param = self._create_parameter(arg)

            # Check for default value
            default_idx = i - defaults_offset
            if 0 <= default_idx < len(args.defaults):
                param.default_value = helpers.get_node_value(args.defaults[default_idx])
                param.is_optional = True

            params.append(param)

        return params

    def _extract_keyword_only_args(
        self, args: ast.arguments
    ) -> List[ParameterDoc]:
        """
        Extract keyword-only arguments.

        Issue #665: Extracted from _extract_parameters to improve maintainability.

        Args:
            args: AST arguments node

        Returns:
            List of ParameterDoc for keyword-only arguments
        """
        params = []
        kw_defaults_map = {i: d for i, d in enumerate(args.kw_defaults) if d is not None}

        for i, arg in enumerate(args.kwonlyargs):
            param = self._create_parameter(arg, is_keyword_only=True)
            if i in kw_defaults_map:
                param.default_value = helpers.get_node_value(kw_defaults_map[i])
                param.is_optional = True
            params.append(param)

        return params

    def _extract_parameters(
        self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef]
    ) -> List[ParameterDoc]:
        """
        Extract parameter documentation from function definition.

        Issue #665: Refactored to use extracted helpers for each parameter type.

        Args:
            node: Function AST node

        Returns:
            List of ParameterDoc for all parameters
        """
        args = node.args
        params = []

        # Regular arguments (Issue #665: use helper)
        params.extend(self._extract_regular_args(args))

        # Positional-only arguments (Python 3.8+)
        for arg in args.posonlyargs:
            params.append(self._create_parameter(arg, is_positional_only=True))

        # Keyword-only arguments (Issue #665: use helper)
        params.extend(self._extract_keyword_only_args(args))

        return params

    def _should_include(self, name: str) -> bool:
        """Check if a name should be included based on settings."""
        if name.startswith("__") and name.endswith("__"):
            return self.include_dunder
        if name.startswith("_"):
            return self.include_private
        return True


# Module-level instance for convenience
_analyzer = ModuleAnalyzer()


def analyze_module(file_path: str, **kwargs) -> Optional[ModuleDoc]:
    """
    Convenience function to analyze a module.

    Args:
        file_path: Path to the Python file
        **kwargs: Additional options for ModuleAnalyzer

    Returns:
        ModuleDoc containing extracted documentation
    """
    if kwargs:
        analyzer = ModuleAnalyzer(**kwargs)
        return analyzer.analyze_module(file_path)
    return _analyzer.analyze_module(file_path)


def analyze_package(package_path: str, **kwargs) -> Optional[PackageDoc]:
    """
    Convenience function to analyze a package.

    Args:
        package_path: Path to the package directory
        **kwargs: Additional options for ModuleAnalyzer

    Returns:
        PackageDoc containing package documentation
    """
    if kwargs:
        analyzer = ModuleAnalyzer(**kwargs)
        return analyzer.analyze_package(package_path)
    return _analyzer.analyze_package(package_path)


__all__ = [
    "ModuleAnalyzer",
    "analyze_module",
    "analyze_package",
]
