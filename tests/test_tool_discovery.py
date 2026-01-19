import pytest
import shutil
import subprocess
from unittest.mock import patch
from src.tool_discovery import discover_tools, ESSENTIAL_TOOLS

# Mock shutil.which to control tool discovery results
@pytest.fixture
def mock_shutil_which():
    with patch('shutil.which') as mock_which:
        yield mock_which

# Mock subprocess.getoutput to control version output
@pytest.fixture
def mock_subprocess_getoutput():
    with patch('subprocess.getoutput') as mock_getoutput:
        yield mock_getoutput

def test_discover_tools_all_found(mock_shutil_which, mock_subprocess_getoutput):
    """
    Test case where all essential tools are found and return a version.
    """
    mock_shutil_which.side_effect = lambda x: f"/usr/bin/{x}"
    mock_subprocess_getoutput.side_effect = lambda x: f"{x.split(' ')[0]} version 1.0"

    found_tools = discover_tools()

    assert len(found_tools) == len(ESSENTIAL_TOOLS)
    for tool in ESSENTIAL_TOOLS:
        assert tool in found_tools
        assert found_tools[tool]["path"] == f"/usr/bin/{tool}"
        assert found_tools[tool]["version"] == f"{tool} version 1.0"

def test_discover_tools_some_missing(mock_shutil_which, mock_subprocess_getoutput):
    """
    Test case where some essential tools are missing.
    """
    def which_side_effect(tool):
        if tool in ["bash", "python3", "git"]:
            return f"/usr/bin/{tool}"
        return None

    mock_shutil_which.side_effect = which_side_effect
    mock_subprocess_getoutput.side_effect = lambda x: f"{x.split(' ')[0]} version 1.0"

    found_tools = discover_tools()

    assert len(found_tools) == 3
    assert "bash" in found_tools
    assert "python3" in found_tools
    assert "git" in found_tools
    assert "curl" not in found_tools # Example of a missing tool

def test_discover_tools_version_unavailable(mock_shutil_which, mock_subprocess_getoutput):
    """
    Test case where a tool is found but its version cannot be retrieved.
    """
    mock_shutil_which.side_effect = lambda x: f"/usr/bin/{x}"
    mock_subprocess_getoutput.side_effect = lambda x: "" # Simulate no version output

    found_tools = discover_tools()

    assert len(found_tools) == len(ESSENTIAL_TOOLS)
    for tool in ESSENTIAL_TOOLS:
        assert tool in found_tools
        assert found_tools[tool]["path"] == f"/usr/bin/{tool}"
        assert found_tools[tool]["version"] == "available"

def test_discover_tools_subprocess_error(mock_shutil_which, mock_subprocess_getoutput):
    """
    Test case where subprocess.getoutput raises an exception.
    """
    mock_shutil_which.side_effect = lambda x: f"/usr/bin/{x}"
    mock_subprocess_getoutput.side_effect = Exception("Command failed")

    found_tools = discover_tools()

    assert len(found_tools) == len(ESSENTIAL_TOOLS)
    for tool in ESSENTIAL_TOOLS:
        assert tool in found_tools
        assert found_tools[tool]["path"] == f"/usr/bin/{tool}"
        assert found_tools[tool]["version"] == "available"

def test_discover_tools_empty_essential_tools(mock_shutil_which, mock_subprocess_getoutput):
    """
    Test case with an empty ESSENTIAL_TOOLS list.
    """
    with patch('src.tool_discovery.ESSENTIAL_TOOLS', []):
        found_tools = discover_tools()
        assert len(found_tools) == 0
        assert found_tools == {}
