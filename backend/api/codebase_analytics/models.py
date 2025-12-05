# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Pydantic models for codebase analytics API
"""

from typing import List, Optional

from pydantic import BaseModel


class CodebaseStats(BaseModel):
    """Statistics about the codebase"""
    total_files: int
    total_lines: int
    python_files: int
    javascript_files: int
    vue_files: int
    other_files: int
    total_functions: int
    total_classes: int
    average_file_size: float
    last_indexed: str


class ProblemItem(BaseModel):
    """Represents a code problem or issue"""
    type: str
    severity: str
    file_path: str
    line_number: Optional[int]
    description: str
    suggestion: str


class HardcodeItem(BaseModel):
    """Represents a hardcoded value in the codebase"""
    file_path: str
    line_number: int
    type: str  # 'url', 'path', 'ip', 'port', 'api_key', 'string'
    value: str
    context: str


class DeclarationItem(BaseModel):
    """Represents a code declaration (function, class, variable)"""
    name: str
    type: str  # 'function', 'class', 'variable'
    file_path: str
    line_number: int
    usage_count: int
    is_exported: bool
    parameters: Optional[List[str]]
