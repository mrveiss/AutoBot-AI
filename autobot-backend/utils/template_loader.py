# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Template Loading Utility

Provides helper functions to load CSS, HTML, and other template files
from the templates/ directory. Extracted from Issue #515 to organize
data templates and embedded content.

Created: 2025-12-21
"""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml

logger = logging.getLogger(__name__)

# Project root directory (parent of src/)
_PROJECT_ROOT = Path(__file__).parent.parent.parent

# Template directories
TEMPLATES_DIR = _PROJECT_ROOT / "templates"
DATA_DIR = _PROJECT_ROOT / "data"


@lru_cache(maxsize=64)
def load_template(template_path: str, strip_whitespace: bool = False) -> str:
    """
    Load a template file from the templates/ directory.

    Issue #515: Centralized template loading with caching.

    Args:
        template_path: Relative path from templates/ directory
                      (e.g., "dashboards/styles/performance_dashboard.css")
        strip_whitespace: If True, strip leading/trailing whitespace

    Returns:
        Template content as string

    Raises:
        FileNotFoundError: If template file doesn't exist
        IOError: If template cannot be read
    """
    full_path = TEMPLATES_DIR / template_path

    if not full_path.exists():
        logger.error("Template not found: %s", full_path)
        raise FileNotFoundError(f"Template not found: {template_path}")

    try:
        content = full_path.read_text(encoding="utf-8")
        if strip_whitespace:
            content = content.strip()
        logger.debug("Loaded template: %s", template_path)
        return content
    except Exception as e:
        logger.error("Failed to load template %s: %s", template_path, e)
        raise IOError(f"Failed to load template {template_path}: {e}") from e


def load_css(css_name: str, subdirectory: str = "dashboards/styles") -> str:
    """
    Load a CSS template file.

    Issue #515: Convenience wrapper for CSS templates.

    Args:
        css_name: CSS filename (with or without .css extension)
        subdirectory: Subdirectory within templates/ (default: dashboards/styles)

    Returns:
        CSS content as string
    """
    if not css_name.endswith(".css"):
        css_name = f"{css_name}.css"

    template_path = f"{subdirectory}/{css_name}"
    return load_template(template_path)


def load_html(html_name: str, subdirectory: str = "dashboards") -> str:
    """
    Load an HTML template file.

    Issue #515: Convenience wrapper for HTML templates.

    Args:
        html_name: HTML filename (with or without .html extension)
        subdirectory: Subdirectory within templates/ (default: dashboards)

    Returns:
        HTML content as string
    """
    if not html_name.endswith(".html"):
        html_name = f"{html_name}.html"

    template_path = f"{subdirectory}/{html_name}"
    return load_template(template_path)


def load_widget(widget_name: str) -> str:
    """
    Load a widget template from templates/widgets/.

    Issue #515: Convenience wrapper for widget templates.

    Args:
        widget_name: Widget filename (with or without .html extension)

    Returns:
        Widget HTML content as string
    """
    return load_html(widget_name, subdirectory="widgets")


@lru_cache(maxsize=32)
def load_data_file(data_path: str) -> str:
    """
    Load a data file from the data/ directory.

    Issue #515: Load YAML/JSON data files.

    Args:
        data_path: Relative path from data/ directory
                  (e.g., "mcp_tools/http_client_tools.yaml")

    Returns:
        File content as string

    Raises:
        FileNotFoundError: If data file doesn't exist
    """
    full_path = DATA_DIR / data_path

    if not full_path.exists():
        logger.error("Data file not found: %s", full_path)
        raise FileNotFoundError(f"Data file not found: {data_path}")

    try:
        content = full_path.read_text(encoding="utf-8")
        logger.debug("Loaded data file: %s", data_path)
        return content
    except Exception as e:
        logger.error("Failed to load data file %s: %s", data_path, e)
        raise IOError(f"Failed to load data file {data_path}: {e}") from e


def template_exists(template_path: str) -> bool:
    """
    Check if a template file exists.

    Args:
        template_path: Relative path from templates/ directory

    Returns:
        True if template exists, False otherwise
    """
    full_path = TEMPLATES_DIR / template_path
    return full_path.exists()


def data_file_exists(data_path: str) -> bool:
    """
    Check if a data file exists.

    Args:
        data_path: Relative path from data/ directory

    Returns:
        True if data file exists, False otherwise
    """
    full_path = DATA_DIR / data_path
    return full_path.exists()


def clear_template_cache() -> None:
    """
    Clear the template loading cache.

    Useful during development or when templates are updated dynamically.
    """
    load_template.cache_clear()
    load_data_file.cache_clear()
    logger.debug("Template cache cleared")


def get_template_path(template_path: str) -> Path:
    """
    Get the full filesystem path for a template.

    Args:
        template_path: Relative path from templates/ directory

    Returns:
        Full Path object to the template
    """
    return TEMPLATES_DIR / template_path


def get_data_path(data_path: str) -> Path:
    """
    Get the full filesystem path for a data file.

    Args:
        data_path: Relative path from data/ directory

    Returns:
        Full Path object to the data file
    """
    return DATA_DIR / data_path


def load_yaml_data(
    data_path: str, substitutions: Optional[Dict[str, Any]] = None
) -> Union[Dict[str, Any], List[Any]]:
    """
    Load and parse a YAML data file with optional placeholder substitution.

    Issue #515: Load YAML data files for MCP tools, knowledge data, etc.

    Args:
        data_path: Relative path from data/ directory
                  (e.g., "mcp_tools/http_client_tools.yaml")
        substitutions: Optional dict of placeholder values to substitute
                      e.g., {"DEFAULT_TIMEOUT": 30, "MAX_TIMEOUT": 120}

    Returns:
        Parsed YAML content (dict or list)

    Raises:
        FileNotFoundError: If data file doesn't exist
        yaml.YAMLError: If YAML parsing fails
    """
    content = load_data_file(data_path)

    # Apply placeholder substitutions if provided
    if substitutions:
        for key, value in substitutions.items():
            placeholder = f"${{{key}}}"
            content = content.replace(placeholder, str(value))

    try:
        return yaml.safe_load(content)
    except yaml.YAMLError as e:
        logger.error("Failed to parse YAML %s: %s", data_path, e)
        raise


def load_mcp_tools(
    tool_file: str, config: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Load MCP tool definitions from a YAML file.

    Issue #515: Externalize MCP tool definitions to YAML files.

    Args:
        tool_file: Filename in data/mcp_tools/ (with or without .yaml extension)
        config: Configuration values to substitute in tool definitions
               e.g., {"DEFAULT_TIMEOUT": 30, "MAX_TIMEOUT": 120}

    Returns:
        List of MCP tool definition dicts

    Example YAML structure:
        tools:
          - name: http_get
            description: "Perform HTTP GET request..."
            input_schema:
              type: object
              properties:
                url:
                  type: string
                  description: "Target URL"
              required: ["url"]
    """
    if not tool_file.endswith(".yaml"):
        tool_file = f"{tool_file}.yaml"

    data_path = f"mcp_tools/{tool_file}"
    data = load_yaml_data(data_path, substitutions=config)

    if isinstance(data, dict) and "tools" in data:
        return data["tools"]
    elif isinstance(data, list):
        return data
    else:
        logger.warning("Unexpected MCP tools YAML structure in %s", data_path)
        return []


def mcp_tools_exist(tool_file: str) -> bool:
    """
    Check if an MCP tools YAML file exists.

    Args:
        tool_file: Filename in data/mcp_tools/ (with or without .yaml extension)

    Returns:
        True if file exists, False otherwise
    """
    if not tool_file.endswith(".yaml"):
        tool_file = f"{tool_file}.yaml"

    return data_file_exists(f"mcp_tools/{tool_file}")


def load_knowledge_data(
    data_file: str, key: Optional[str] = None
) -> Union[Dict[str, Any], List[Any]]:
    """
    Load knowledge data from a YAML file in data/knowledge/.

    Issue #515: Externalize knowledge base data to YAML files.

    Args:
        data_file: Filename in data/knowledge/ (with or without .yaml extension)
        key: Optional key to extract from the YAML (e.g., "commands")

    Returns:
        Parsed YAML content (dict or list)

    Example:
        commands = load_knowledge_data("system_commands", key="commands")
    """
    if not data_file.endswith(".yaml"):
        data_file = f"{data_file}.yaml"

    data_path = f"knowledge/{data_file}"
    data = load_yaml_data(data_path)

    if key and isinstance(data, dict) and key in data:
        return data[key]

    return data


def knowledge_data_exists(data_file: str) -> bool:
    """
    Check if a knowledge data YAML file exists.

    Args:
        data_file: Filename in data/knowledge/ (with or without .yaml extension)

    Returns:
        True if file exists, False otherwise
    """
    if not data_file.endswith(".yaml"):
        data_file = f"{data_file}.yaml"

    return data_file_exists(f"knowledge/{data_file}")
