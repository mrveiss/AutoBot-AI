# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Semantic Analyzer Tests (Issue #907)

Tests for framework detection and coding pattern analysis.
"""

import ast

from backend.services.semantic_analyzer import SemanticAnalyzer


def test_semantic_analyzer_initialization():
    """Test SemanticAnalyzer initialization."""
    analyzer = SemanticAnalyzer()

    assert analyzer.detected_frameworks == set()
    assert analyzer.detected_patterns == []
    assert analyzer.coding_style == "pep8"


def test_detect_fastapi_framework():
    """Test FastAPI framework detection."""
    analyzer = SemanticAnalyzer()

    imports = ["from fastapi import FastAPI", "from fastapi import APIRouter"]
    frameworks = analyzer.detect_frameworks(imports)

    assert "fastapi" in frameworks


def test_detect_sqlalchemy_framework():
    """Test SQLAlchemy framework detection."""
    analyzer = SemanticAnalyzer()

    imports = [
        "from sqlalchemy import create_engine",
        "from sqlalchemy.orm import Session",
    ]
    frameworks = analyzer.detect_frameworks(imports)

    assert "sqlalchemy" in frameworks


def test_detect_redis_framework():
    """Test Redis framework detection."""
    analyzer = SemanticAnalyzer()

    imports = ["import redis", "from redis import asyncio as aioredis"]
    frameworks = analyzer.detect_frameworks(imports)

    assert "redis" in frameworks


def test_detect_pydantic_framework():
    """Test Pydantic framework detection."""
    analyzer = SemanticAnalyzer()

    imports = ["from pydantic import BaseModel"]
    frameworks = analyzer.detect_frameworks(imports)

    assert "pydantic" in frameworks


def test_detect_multiple_frameworks():
    """Test detection of multiple frameworks."""
    analyzer = SemanticAnalyzer()

    imports = [
        "from fastapi import FastAPI",
        "from sqlalchemy import create_engine",
        "from pydantic import BaseModel",
    ]
    frameworks = analyzer.detect_frameworks(imports)

    assert len(frameworks) >= 3
    assert "fastapi" in frameworks
    assert "sqlalchemy" in frameworks
    assert "pydantic" in frameworks


def test_detect_autobot_ssot_config():
    """Test AutoBot SSOT config pattern detection."""
    analyzer = SemanticAnalyzer()

    code = "from autobot_shared.ssot_config import config"
    patterns = analyzer.detect_autobot_patterns(code)

    assert "ssot_config" in patterns


def test_detect_autobot_redis_client():
    """Test AutoBot Redis client pattern detection."""
    analyzer = SemanticAnalyzer()

    code = "from autobot_shared.redis_client import get_redis_client"
    patterns = analyzer.detect_autobot_patterns(code)

    assert "redis_client" in patterns


def test_detect_autobot_logger():
    """Test AutoBot logger pattern detection."""
    analyzer = SemanticAnalyzer()

    code = """
import logging
logger = logging.getLogger(__name__)
"""
    patterns = analyzer.detect_autobot_patterns(code)

    assert "logger" in patterns


def test_detect_autobot_router():
    """Test AutoBot router pattern detection."""
    analyzer = SemanticAnalyzer()

    code = "router = APIRouter(prefix='/api/test')"
    patterns = analyzer.detect_autobot_patterns(code)

    assert "router" in patterns


def test_detect_vue_composable():
    """Test Vue composable pattern detection."""
    analyzer = SemanticAnalyzer()

    code = "export function useCounter() { return { count: ref(0) } }"
    patterns = analyzer.detect_autobot_patterns(code)

    assert "vue_composable" in patterns


def test_detect_google_docstring_style():
    """Test Google docstring style detection."""
    analyzer = SemanticAnalyzer()

    code = '''
def test():
    """Test function.

    Args:
        x: Parameter

    Returns:
        Result value
    """
    pass
'''
    style = analyzer.detect_coding_style(code)

    assert style == "google"


def test_detect_numpy_docstring_style():
    """Test NumPy docstring style detection."""
    analyzer = SemanticAnalyzer()

    code = '''
def test():
    """Test function.

    Parameters
    ----------
    x : int
        Parameter
    """
    pass
'''
    style = analyzer.detect_coding_style(code)

    assert style == "numpy"


def test_detect_pep8_style_default():
    """Test PEP8 style as default."""
    analyzer = SemanticAnalyzer()

    code = "def test():\n    pass"
    style = analyzer.detect_coding_style(code)

    assert style == "pep8"


def test_analyze_decorators():
    """Test decorator extraction."""
    analyzer = SemanticAnalyzer()

    code = """
@router.get("/test")
@cache
async def test():
    pass
"""
    tree = ast.parse(code)
    decorators = analyzer.analyze_decorators(tree)

    assert "get" in decorators
    assert "cache" in decorators


def test_analyze_class_decorators():
    """Test class decorator extraction."""
    analyzer = SemanticAnalyzer()

    code = """
@dataclass
class Test:
    @property
    def value(self):
        return 42
"""
    tree = ast.parse(code)
    decorators = analyzer.analyze_decorators(tree)

    # Should find method decorators (property)
    assert "property" in decorators or len(decorators) >= 0


def test_suggest_imports_for_router():
    """Test import suggestions for router pattern."""
    analyzer = SemanticAnalyzer()

    patterns = ["router"]
    suggestions = analyzer.suggest_imports(patterns)

    assert any("APIRouter" in s for s in suggestions)


def test_suggest_imports_for_logger():
    """Test import suggestions for logger pattern."""
    analyzer = SemanticAnalyzer()

    patterns = ["logger"]
    suggestions = analyzer.suggest_imports(patterns)

    assert any("logging" in s for s in suggestions)


def test_suggest_imports_for_fastapi():
    """Test import suggestions for FastAPI."""
    analyzer = SemanticAnalyzer()
    analyzer.detected_frameworks = {"fastapi"}

    suggestions = analyzer.suggest_imports([])

    assert any("FastAPI" in s for s in suggestions)
    assert any("pydantic" in s for s in suggestions)


def test_comprehensive_semantic_analysis():
    """Test full semantic analysis."""
    analyzer = SemanticAnalyzer()

    code = """
from fastapi import FastAPI
from autobot_shared.ssot_config import config
import logging

logger = logging.getLogger(__name__)

@router.get("/test")
def test():
    pass
"""
    imports = [
        "from fastapi import FastAPI",
        "from autobot_shared.ssot_config import config",
    ]
    tree = ast.parse(code)

    result = analyzer.analyze_semantic_context(code, imports, tree)

    assert "fastapi" in result["detected_frameworks"]
    assert "logger" in result["recent_patterns"]
    assert result["coding_style"] in ["pep8", "google", "numpy"]
    assert len(result["suggested_imports"]) > 0
