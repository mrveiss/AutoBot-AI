#!/usr/bin/env python3
"""
Feature Envy Detector - Finds functions that access too many attributes from external objects.

Detects code smell pattern: functions that access another object's data more than their own.
This indicates the method likely belongs on the external object.

GitHub Issue: #372 - Code Smell: Refactor 2,596 feature envy patterns

Author: mrveiss
Copyright (c) 2025 mrveiss
"""

import ast
import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set


@dataclass
class FeatureEnvyCandidate:
    """Represents a potential feature envy pattern."""

    file_path: str
    function_name: str
    line_number: int
    envied_object: str
    access_count: int
    unique_attributes: Set[str] = field(default_factory=set)


class FeatureEnvyVisitor(ast.NodeVisitor):
    """AST visitor that detects feature envy patterns."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.candidates: List[FeatureEnvyCandidate] = []
        self.current_function: str = None
        self.current_function_line: int = 0
        self.attribute_accesses: Dict[str, Dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self.unique_attrs: Dict[str, Set[str]] = defaultdict(set)

    def visit_FunctionDef(self, node: ast.FunctionDef):
        self._process_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self._process_function(node)

    def _process_function(self, node):
        """Process a function definition."""
        old_function = self.current_function
        old_line = self.current_function_line
        old_accesses = self.attribute_accesses
        old_unique = self.unique_attrs

        self.current_function = node.name
        self.current_function_line = node.lineno
        self.attribute_accesses = defaultdict(lambda: defaultdict(int))
        self.unique_attrs = defaultdict(set)

        # Visit function body
        for child in ast.walk(node):
            if isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name):
                obj_name = child.value.id
                attr_name = child.attr
                # Skip self/cls references
                if obj_name not in ("sel", "cls"):
                    self.attribute_accesses[obj_name][attr_name] += 1
                    self.unique_attrs[obj_name].add(attr_name)

        # Analyze results for this function
        for obj_name, attrs in self.attribute_accesses.items():
            total_accesses = sum(attrs.values())
            unique_count = len(self.unique_attrs[obj_name])

            # Thresholds: 8+ unique attributes OR 15+ total accesses
            if unique_count >= 8 or total_accesses >= 15:
                self.candidates.append(
                    FeatureEnvyCandidate(
                        file_path=self.file_path,
                        function_name=self.current_function,
                        line_number=self.current_function_line,
                        envied_object=obj_name,
                        access_count=total_accesses,
                        unique_attributes=self.unique_attrs[obj_name].copy(),
                    )
                )

        # Restore state
        self.current_function = old_function
        self.current_function_line = old_line
        self.attribute_accesses = old_accesses
        self.unique_attrs = old_unique

        # Continue visiting nested functions
        self.generic_visit(node)


def scan_file(file_path: str) -> List[FeatureEnvyCandidate]:
    """Scan a Python file for feature envy patterns."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        tree = ast.parse(content, filename=file_path)
        visitor = FeatureEnvyVisitor(file_path)
        visitor.visit(tree)
        return visitor.candidates
    except (SyntaxError, UnicodeDecodeError):
        return []


def scan_directory(
    root_dir: str, exclude_dirs: Set[str] = None
) -> List[FeatureEnvyCandidate]:
    """Scan all Python files in directory."""
    if exclude_dirs is None:
        exclude_dirs = {
            "venv",
            ".venv",
            "__pycache__",
            ".git",
            "node_modules",
            "archive",
        }

    candidates = []
    root_path = Path(root_dir)

    for py_file in root_path.rglob("*.py"):
        # Skip excluded directories
        if any(excl in py_file.parts for excl in exclude_dirs):
            continue
        candidates.extend(scan_file(str(py_file)))

    return candidates


def aggregate_by_object(
    candidates: List[FeatureEnvyCandidate],
) -> Dict[str, List[FeatureEnvyCandidate]]:
    """Group candidates by the envied object name."""
    by_object = defaultdict(list)
    for c in candidates:
        by_object[c.envied_object].append(c)
    return dict(by_object)


def main():
    """Main entry point."""
    root_dir = Path(__file__).parent.parent

    print("Scanning for Feature Envy patterns...")
    print("=" * 80)

    candidates = scan_directory(str(root_dir))

    # Aggregate and sort by total accesses
    by_object = aggregate_by_object(candidates)
    sorted_objects = sorted(
        by_object.items(), key=lambda x: sum(c.access_count for c in x[1]), reverse=True
    )

    print(f"\nFound {len(candidates)} potential feature envy patterns\n")
    print("Top candidates by object (total accesses across all functions):\n")

    for obj_name, obj_candidates in sorted_objects[:30]:
        total = sum(c.access_count for c in obj_candidates)
        locations = len(obj_candidates)
        print(f"  {obj_name}: {total}x accesses in {locations} location(s)")

        # Show top 3 locations for each object
        sorted_locs = sorted(obj_candidates, key=lambda c: c.access_count, reverse=True)
        for c in sorted_locs[:3]:
            rel_path = os.path.relpath(c.file_path, root_dir)
            attrs_str = ", ".join(sorted(c.unique_attributes)[:5])
            if len(c.unique_attributes) > 5:
                attrs_str += f"... (+{len(c.unique_attributes) - 5} more)"
            print(
                f"    - {rel_path}:{c.line_number} {c.function_name}() [{c.access_count}x]"
            )
            print(f"      Attrs: {attrs_str}")

    print("\n" + "=" * 80)
    print(
        "To refactor: Add methods to the envied object that encapsulate attribute access"
    )
    print("Pattern: obj.attr1, obj.attr2 -> obj.to_dict(), obj.get_computed_value()")


if __name__ == "__main__":
    main()
