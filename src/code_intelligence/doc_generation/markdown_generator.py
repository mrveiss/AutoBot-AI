# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Markdown Documentation Generator Module

Generates Markdown and HTML documentation from analyzed code structures.
Extracted from DocGenerator as part of Issue #394.

Part of god class refactoring initiative.
"""

import re
from typing import List, Pattern

from src.code_intelligence.doc_generation.helpers import SKIP_INHERITANCE_BASES
from src.code_intelligence.doc_generation.models import (
    ClassDoc,
    DiagramSpec,
    FunctionDoc,
    GeneratedDoc,
    ModuleDoc,
)
from src.code_intelligence.doc_generation.types import (
    DiagramType,
    DocCompleteness,
    DocFormat,
    DocSection,
)

# Pre-compiled regex patterns for markdown-to-HTML conversion
_MD_H5_RE: Pattern[str] = re.compile(r"^##### (.+)$", re.MULTILINE)
_MD_H4_RE: Pattern[str] = re.compile(r"^#### (.+)$", re.MULTILINE)
_MD_H3_RE: Pattern[str] = re.compile(r"^### (.+)$", re.MULTILINE)
_MD_H2_RE: Pattern[str] = re.compile(r"^## (.+)$", re.MULTILINE)
_MD_H1_RE: Pattern[str] = re.compile(r"^# (.+)$", re.MULTILINE)
_MD_CODE_BLOCK_RE: Pattern[str] = re.compile(r"```(\w+)?\n(.*?)```", re.DOTALL)
_MD_INLINE_CODE_RE: Pattern[str] = re.compile(r"`([^`]+)`")
_MD_BOLD_RE: Pattern[str] = re.compile(r"\*\*([^*]+)\*\*")
_MD_LIST_ITEM_RE: Pattern[str] = re.compile(r"^- (.+)$", re.MULTILINE)
_MD_HR_RE: Pattern[str] = re.compile(r"^---$", re.MULTILINE)

# Completeness score mapping (Issue #665: extracted for reuse)
_COMPLETENESS_SCORES = {
    DocCompleteness.NONE: 0,
    DocCompleteness.MINIMAL: 25,
    DocCompleteness.PARTIAL: 50,
    DocCompleteness.COMPLETE: 75,
    DocCompleteness.COMPREHENSIVE: 100,
}


def _calculate_avg_completeness(modules: List[ModuleDoc]) -> float:
    """Calculate average completeness score from modules.

    Issue #665: Extracted from _generate_markdown_api to reduce function length.

    Args:
        modules: List of module documentation objects

    Returns:
        Average completeness percentage (0-100)
    """
    if not modules:
        return 0
    all_completeness = [m.completeness for m in modules]
    return sum(_COMPLETENESS_SCORES[c] for c in all_completeness) / len(
        all_completeness
    )


def _generate_module_header_lines(module: ModuleDoc) -> List[str]:
    """Generate header lines for a module section.

    Issue #665: Extracted from _generate_markdown_api to reduce function length.

    Args:
        module: Module documentation object

    Returns:
        List of markdown lines for module header
    """
    lines = [f"## Module: `{module.name}`", ""]
    if module.file_path:
        lines.extend([f"**File:** `{module.file_path}`", ""])
    if module.description:
        lines.extend([module.description, ""])
    return lines


def _generate_constants_section(constants: dict) -> List[str]:
    """Generate constants section for a module.

    Issue #665: Extracted from _generate_markdown_api to reduce function length.

    Args:
        constants: Dictionary of constant names to values

    Returns:
        List of markdown lines for constants section
    """
    if not constants:
        return []
    lines = ["### Constants", ""]
    for name, value in constants.items():
        lines.append(f"- `{name}` = `{value}`")
    lines.append("")
    return lines


class MarkdownGenerator:
    """
    Generator for Markdown and HTML documentation.

    Produces formatted documentation from analyzed code structures.

    Example:
        >>> generator = MarkdownGenerator()
        >>> doc = generator.generate_api_docs(modules, "API Reference")
    """

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
            return self._generate_html_api(
                modules, title, include_toc, include_diagrams
            )
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
        """Generate Markdown API documentation.

        Issue #665: Refactored to use extracted helper functions.
        Issue #620: Further refactored to extract module processing.
        """
        lines = [f"# {title}", ""]

        if include_toc:
            lines.extend(self._generate_toc(modules))
            lines.append("")

        diagrams = []

        # Process each module using helpers (Issue #665, #620)
        for module in modules:
            module_lines, module_diagrams = self._process_module_content(
                module, include_diagrams
            )
            lines.extend(module_lines)
            diagrams.extend(module_diagrams)

        content = "\n".join(lines)

        return GeneratedDoc(
            title=title,
            content=content,
            format=DocFormat.MARKDOWN,
            sections=[DocSection.API_REFERENCE],
            source_files=[m.file_path for m in modules],
            diagrams=diagrams,
            word_count=len(content.split()),
            completeness_score=_calculate_avg_completeness(modules),
        )

    def _process_module_content(
        self, module: ModuleDoc, include_diagrams: bool
    ) -> tuple:
        """
        Process a single module and generate its markdown content.

        Issue #620: Extracted from _generate_markdown_api. Issue #620.

        Args:
            module: Module documentation to process
            include_diagrams: Whether to include class diagrams

        Returns:
            Tuple of (lines list, diagrams list)
        """
        lines = []
        diagrams = []

        lines.extend(_generate_module_header_lines(module))
        lines.extend(_generate_constants_section(module.constants))

        # Generate class diagram if requested
        if include_diagrams and module.classes:
            diagram = self._generate_class_diagram(module)
            diagrams.append(diagram)
            lines.extend(self._format_diagram_section(diagram))

        # Classes and functions
        for class_doc in module.classes:
            lines.extend(self._generate_class_markdown(class_doc))

        if module.functions:
            lines.extend(["### Functions", ""])
            for func_doc in module.functions:
                lines.extend(self._generate_function_markdown(func_doc))

        lines.extend(["---", ""])
        return lines, diagrams

    def _format_diagram_section(self, diagram: DiagramSpec) -> List[str]:
        """
        Format a class diagram as a mermaid code block.

        Issue #620: Extracted from _generate_markdown_api. Issue #620.

        Args:
            diagram: DiagramSpec containing the class diagram

        Returns:
            List of markdown lines for the diagram section
        """
        return [
            "### Class Diagram",
            "",
            "```mermaid",
            diagram.to_mermaid(),
            "```",
            "",
        ]

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

    def _generate_class_header(self, class_doc: ClassDoc) -> List[str]:
        """
        Generate class header with inheritance and decorators.

        Issue #620.
        """
        lines = [f"### Class: `{class_doc.name}`", ""]

        if class_doc.base_classes:
            bases = ", ".join(f"`{b}`" for b in class_doc.base_classes)
            lines.append(f"**Inherits from:** {bases}")
            lines.append("")

        if class_doc.decorators:
            decorators = ", ".join(f"`@{d}`" for d in class_doc.decorators)
            lines.append(f"**Decorators:** {decorators}")
            lines.append("")

        if class_doc.description:
            lines.append(class_doc.description)
            lines.append("")

        return lines

    def _generate_class_variables_table(self, class_doc: ClassDoc) -> List[str]:
        """
        Generate markdown table for class variables.

        Issue #620.
        """
        if not class_doc.class_variables:
            return []

        lines = ["#### Class Variables", ""]
        lines.append("| Name | Type |")
        lines.append("|------|------|")
        for name, type_hint in class_doc.class_variables.items():
            lines.append(f"| `{name}` | `{type_hint}` |")
        lines.append("")
        return lines

    def _generate_class_members(self, class_doc: ClassDoc) -> List[str]:
        """
        Generate documentation for class properties and methods.

        Issue #620.
        """
        lines = []

        if class_doc.properties:
            lines.append("#### Properties")
            lines.append("")
            for prop in class_doc.properties:
                lines.extend(self._generate_function_markdown(prop, is_property=True))

        if class_doc.methods:
            lines.append("#### Methods")
            lines.append("")
            for method in class_doc.methods:
                lines.extend(self._generate_function_markdown(method))

        return lines

    def _generate_class_examples(self, class_doc: ClassDoc) -> List[str]:
        """
        Generate examples section for class documentation.

        Issue #620.
        """
        if not class_doc.examples:
            return []

        lines = ["#### Examples", ""]
        for example in class_doc.examples:
            if example.description:
                lines.append(example.description)
                lines.append("")
            lines.append(f"```{example.language}")
            lines.append(example.code)
            lines.append("```")
            lines.append("")
        return lines

    def _generate_class_markdown(self, class_doc: ClassDoc) -> List[str]:
        """Generate Markdown documentation for a class."""
        lines = self._generate_class_header(class_doc)
        lines.extend(self._generate_class_variables_table(class_doc))
        lines.extend(self._generate_class_members(class_doc))
        lines.extend(self._generate_class_examples(class_doc))
        return lines

    def _generate_function_header(
        self, func_doc: FunctionDoc, is_property: bool
    ) -> List[str]:
        """
        Generate function header with async/decorator info.

        Issue #620: Extracted from _generate_function_markdown.
        """
        lines = []
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
        lines.append("```python")
        lines.append(f"def {func_doc.name}{func_doc.signature}")
        lines.append("```")
        lines.append("")

        if func_doc.description:
            lines.append(func_doc.description)
            lines.append("")
        return lines

    def _generate_parameters_section(self, func_doc: FunctionDoc) -> List[str]:
        """
        Generate parameters documentation section.

        Issue #620: Extracted from _generate_function_markdown.
        """
        if not func_doc.parameters:
            return []

        lines = ["**Parameters:**", ""]
        for param in func_doc.parameters:
            type_info = f": `{param.type_hint}`" if param.type_hint else ""
            default_info = (
                f" (default: `{param.default_value}`)" if param.default_value else ""
            )
            desc = f" - {param.description}" if param.description else ""
            lines.append(f"- `{param.name}`{type_info}{default_info}{desc}")
        lines.append("")
        return lines

    def _generate_returns_and_exceptions(self, func_doc: FunctionDoc) -> List[str]:
        """
        Generate returns and exceptions documentation sections.

        Issue #620: Extracted from _generate_function_markdown.
        """
        lines = []

        if func_doc.returns:
            type_info = (
                f"`{func_doc.returns.type_hint}`" if func_doc.returns.type_hint else ""
            )
            desc = (
                f": {func_doc.returns.description}"
                if func_doc.returns.description
                else ""
            )
            lines.append(f"**Returns:** {type_info}{desc}")
            lines.append("")

        if func_doc.exceptions:
            lines.append("**Raises:**")
            lines.append("")
            for exc in func_doc.exceptions:
                desc = f": {exc.description}" if exc.description else ""
                lines.append(f"- `{exc.exception_type}`{desc}")
            lines.append("")

        return lines

    def _generate_function_markdown(
        self, func_doc: FunctionDoc, is_property: bool = False
    ) -> List[str]:
        """
        Generate Markdown documentation for a function/method.

        Issue #620: Refactored to use helper methods.
        """
        lines = []

        # Issue #620: Use helpers for each section
        lines.extend(self._generate_function_header(func_doc, is_property))
        lines.extend(self._generate_parameters_section(func_doc))
        lines.extend(self._generate_returns_and_exceptions(func_doc))

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
                if base not in SKIP_INHERITANCE_BASES:
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
        md_doc = self._generate_markdown_api(
            modules, title, include_toc, include_diagrams
        )

        # Simple markdown to HTML conversion
        html_content = self._markdown_to_html(md_doc.content)

        html_page = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6; max-width: 900px; margin: 0 auto; padding: 20px;
        }}
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

    def _apply_markdown_substitutions(self, html: str) -> str:
        """
        Apply regex-based markdown substitutions for headers, code, bold, etc.

        Issue #665: Extracted from _markdown_to_html to improve maintainability.

        Args:
            html: HTML string with markdown formatting

        Returns:
            HTML string with markdown converted to HTML tags
        """
        # Headers (use pre-compiled patterns)
        html = _MD_H5_RE.sub(r"<h5>\1</h5>", html)
        html = _MD_H4_RE.sub(r"<h4>\1</h4>", html)
        html = _MD_H3_RE.sub(r"<h3>\1</h3>", html)
        html = _MD_H2_RE.sub(r"<h2>\1</h2>", html)
        html = _MD_H1_RE.sub(r"<h1>\1</h1>", html)

        # Code blocks
        html = _MD_CODE_BLOCK_RE.sub(r"<pre><code>\2</code></pre>", html)

        # Inline code
        html = _MD_INLINE_CODE_RE.sub(r"<code>\1</code>", html)

        # Bold
        html = _MD_BOLD_RE.sub(r"<strong>\1</strong>", html)

        # Lists
        html = _MD_LIST_ITEM_RE.sub(r"<li>\1</li>", html)

        # Horizontal rules
        html = _MD_HR_RE.sub(r"<hr>", html)

        return html

    def _wrap_list_items(self, html: str) -> str:
        """
        Wrap consecutive <li> elements in <ul> tags.

        Issue #665: Extracted from _markdown_to_html to improve maintainability.

        Args:
            html: HTML string with <li> elements

        Returns:
            HTML string with <li> elements wrapped in <ul> tags
        """
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

    def _markdown_to_html(self, markdown: str) -> str:
        """
        Simple Markdown to HTML conversion.

        Issue #665: Refactored to use extracted helpers.

        Args:
            markdown: Markdown formatted string

        Returns:
            HTML formatted string
        """
        html = self._apply_markdown_substitutions(markdown)
        return self._wrap_list_items(html)

    def _build_overview_stats_section(self, module: ModuleDoc) -> List[str]:
        """Build the overview statistics section for a module.

        Issue #620.

        Args:
            module: Module documentation object

        Returns:
            List of markdown lines for the stats section
        """
        return [
            "## Overview",
            "",
            f"- **Classes:** {len(module.classes)}",
            f"- **Functions:** {len(module.functions)}",
            f"- **Constants:** {len(module.constants)}",
            f"- **Lines of code:** {module.line_count}",
            f"- **Documentation completeness:** {module.completeness.value}",
            "",
        ]

    def _build_list_section(
        self, title: str, items: List[str], code_format: bool = True
    ) -> List[str]:
        """Build a markdown list section with optional code formatting.

        Issue #620.

        Args:
            title: Section heading
            items: List of items to include
            code_format: Whether to wrap items in backticks

        Returns:
            List of markdown lines, empty if no items
        """
        if not items:
            return []
        lines = [f"## {title}", ""]
        for item in items:
            lines.append(f"- `{item}`" if code_format else f"- {item}")
        lines.append("")
        return lines

    def generate_module_overview(
        self,
        module: ModuleDoc,
        format: DocFormat = DocFormat.MARKDOWN,
    ) -> GeneratedDoc:
        """Generate an overview document for a single module.

        Issue #620: Refactored to use extracted helpers.

        Args:
            module: Analyzed module documentation
            format: Output format

        Returns:
            GeneratedDoc with the overview
        """
        lines = [f"# {module.name}", ""]
        if module.description:
            lines.extend([module.description, ""])

        lines.extend(self._build_overview_stats_section(module))
        lines.extend(self._build_list_section("Dependencies", module.dependencies))
        lines.extend(self._build_list_section("Public API (exports)", module.exports))

        content = "\n".join(lines)
        completeness_score = (
            100 if module.completeness == DocCompleteness.COMPREHENSIVE else 50
        )

        return GeneratedDoc(
            title=f"{module.name} Overview",
            content=content,
            format=format,
            sections=[DocSection.OVERVIEW],
            source_files=[module.file_path],
            word_count=len(content.split()),
            completeness_score=completeness_score,
        )


# Module-level instance for convenience
_generator = MarkdownGenerator()


def generate_api_docs(
    modules: List[ModuleDoc],
    title: str = "API Reference",
    format: DocFormat = DocFormat.MARKDOWN,
    include_toc: bool = True,
    include_diagrams: bool = True,
) -> GeneratedDoc:
    """
    Convenience function to generate API documentation.

    Args:
        modules: List of analyzed module documentation
        title: Documentation title
        format: Output format
        include_toc: Include table of contents
        include_diagrams: Include class diagrams

    Returns:
        GeneratedDoc with the generated content
    """
    return _generator.generate_api_docs(
        modules, title, format, include_toc, include_diagrams
    )


def generate_module_overview(
    module: ModuleDoc,
    format: DocFormat = DocFormat.MARKDOWN,
) -> GeneratedDoc:
    """
    Convenience function to generate module overview.

    Args:
        module: Analyzed module documentation
        format: Output format

    Returns:
        GeneratedDoc with the overview
    """
    return _generator.generate_module_overview(module, format)


__all__ = [
    "MarkdownGenerator",
    "generate_api_docs",
    "generate_module_overview",
]
