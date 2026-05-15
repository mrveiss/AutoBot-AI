# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Type Inference Tests (Issue #907)

Tests for static type analysis.
"""

import ast

from services.type_inference import TypeInferencer


def test_type_inferencer_initialization():
    """Test TypeInferencer initialization."""
    inferencer = TypeInferencer()

    assert inferencer.type_map == {}
    assert "int" in inferencer.builtins
    assert "str" in inferencer.builtins


def test_infer_from_constant():
    """Test type inference from constant values."""
    inferencer = TypeInferencer()

    # Integer
    node = ast.parse("x = 42").body[0].value
    assert inferencer.infer_from_assignment("x", node) == "int"

    # String
    node = ast.parse("x = 'hello'").body[0].value
    assert inferencer.infer_from_assignment("x", node) == "str"

    # Float
    node = ast.parse("x = 3.14").body[0].value
    assert inferencer.infer_from_assignment("x", node) == "float"

    # Boolean
    node = ast.parse("x = True").body[0].value
    assert inferencer.infer_from_assignment("x", node) == "bool"


def test_infer_from_collection():
    """Test type inference from collection literals."""
    inferencer = TypeInferencer()

    # List
    node = ast.parse("x = [1, 2, 3]").body[0].value
    assert inferencer.infer_from_assignment("x", node) == "list"

    # Dict
    node = ast.parse("x = {'a': 1}").body[0].value
    assert inferencer.infer_from_assignment("x", node) == "dict"

    # Set
    node = ast.parse("x = {1, 2, 3}").body[0].value
    assert inferencer.infer_from_assignment("x", node) == "set"

    # Tuple
    node = ast.parse("x = (1, 2)").body[0].value
    assert inferencer.infer_from_assignment("x", node) == "tuple"


def test_infer_from_builtin_call():
    """Test type inference from builtin constructor calls."""
    inferencer = TypeInferencer()

    # int()
    node = ast.parse("x = int('5')").body[0].value
    assert inferencer.infer_from_assignment("x", node) == "int"

    # str()
    node = ast.parse("x = str(10)").body[0].value
    assert inferencer.infer_from_assignment("x", node) == "str"


def test_infer_from_comparison():
    """Test type inference from comparison operations."""
    inferencer = TypeInferencer()

    node = ast.parse("x = a > b").body[0].value
    assert inferencer.infer_from_assignment("x", node) == "bool"


def test_infer_from_arithmetic():
    """Test type inference from arithmetic operations."""
    inferencer = TypeInferencer()

    # Integer arithmetic
    inferencer.type_map = {"a": "int", "b": "int"}
    node = ast.parse("x = a + b").body[0].value
    assert inferencer.infer_from_assignment("x", node) == "int"

    # Float arithmetic
    inferencer.type_map = {"a": "float", "b": "int"}
    node = ast.parse("x = a + b").body[0].value
    assert inferencer.infer_from_assignment("x", node) == "float"


def test_infer_from_string_concat():
    """Test type inference from string concatenation."""
    inferencer = TypeInferencer()

    inferencer.type_map = {"a": "str", "b": "str"}
    node = ast.parse("x = a + b").body[0].value
    assert inferencer.infer_from_assignment("x", node) == "str"


def test_infer_from_annotation():
    """Test type extraction from annotations."""
    inferencer = TypeInferencer()

    # Simple annotation
    node = ast.parse("x: int").body[0].annotation
    assert inferencer.infer_from_annotation(node) == "int"

    # Generic annotation
    node = ast.parse("x: List[int]").body[0].annotation
    inferred = inferencer.infer_from_annotation(node)
    assert "List" in inferred or "list" in inferred


def test_infer_function_return_type():
    """Test function return type inference."""
    inferencer = TypeInferencer()

    # With annotation
    code = "def test() -> int:\n    return 42"
    tree = ast.parse(code)
    func = tree.body[0]
    assert inferencer.infer_function_return_type(func) == "int"

    # Without annotation, single return
    code = "def test():\n    return 42"
    tree = ast.parse(code)
    func = tree.body[0]
    assert inferencer.infer_function_return_type(func) == "int"

    # No return
    code = "def test():\n    print('hello')"  # noqa: print
    tree = ast.parse(code)
    func = tree.body[0]
    assert inferencer.infer_function_return_type(func) == "None"


def test_extract_function_params():
    """Test function parameter extraction."""
    inferencer = TypeInferencer()

    code = "def test(a: int, b: str, c):\n    pass"
    tree = ast.parse(code)
    func = tree.body[0]
    params = inferencer.extract_function_params(func)

    assert len(params) == 3
    assert params[0] == ("a", "int")
    assert params[1] == ("b", "str")
    assert params[2] == ("c", "Any")


def test_analyze_scope():
    """Test variable scope analysis."""
    inferencer = TypeInferencer()

    code = """
def test():
    x = 42
    y: str = "hello"
    z = x + 10
"""
    tree = ast.parse(code)
    variables = inferencer.analyze_scope(tree)

    assert "x" in variables
    assert variables["x"] == "int"
    assert "y" in variables
    assert variables["y"] == "str"


def test_analyze_scope_with_for_loop():
    """Test scope analysis with for loop."""
    inferencer = TypeInferencer()

    code = """
for i in range(10):
    x = i * 2
"""
    tree = ast.parse(code)
    variables = inferencer.analyze_scope(tree)

    assert "i" in variables
    assert "x" in variables


def test_infer_from_variable():
    """Test type inference from variable assignment."""
    inferencer = TypeInferencer()

    inferencer.type_map = {"a": "int"}
    node = ast.parse("x = a").body[0].value
    assert inferencer.infer_from_assignment("x", node) == "int"


def test_unknown_type_defaults_to_any():
    """Test unknown types default to Any."""
    inferencer = TypeInferencer()

    # Unknown function call
    node = ast.parse("x = unknown_func()").body[0].value
    assert inferencer.infer_from_assignment("x", node) == "Any"

    # Complex expression
    node = ast.parse("x = (a if b else c)").body[0].value
    assert inferencer.infer_from_assignment("x", node) == "Any"
