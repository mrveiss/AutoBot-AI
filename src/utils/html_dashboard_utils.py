# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
HTML Dashboard Utilities
Centralized HTML/CSS/Chart utilities for dashboard generation

This module provides reusable components for creating consistent dashboards
across the AutoBot platform. Supports both dark (GitHub-style) and light themes.
"""

from typing import Any, Dict, List, Optional


def _get_dark_base_styles() -> str:
    """
    Generate base reset and body styles for dark theme.

    Issue #665: Extracted from get_dark_theme_css

    Returns:
        str: CSS for base styles including reset and body
    """
    return """
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0d1117;
            color: #c9d1d9;
            line-height: 1.6;
        }"""


def _get_dark_header_styles() -> str:
    """
    Generate header and status indicator styles for dark theme.

    Issue #665: Extracted from get_dark_theme_css

    Returns:
        str: CSS for header, title, and status indicators
    """
    return """
        .header {
            background: #161b22;
            border-bottom: 1px solid #30363d;
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .title { color: #58a6ff; font-size: 1.5rem; font-weight: 600; }
        .status-indicator {
            padding: 0.25rem 0.75rem;
            border-radius: 1rem;
            font-size: 0.875rem;
            font-weight: 500;
        }
        .status-healthy { background: #238636; color: #fff; }
        .status-warning { background: #d29922; color: #fff; }
        .status-error { background: #da3633; color: #fff; }"""


def _get_dark_component_styles() -> str:
    """
    Generate component styles for dark theme (cards, metrics, charts).

    Issue #665: Extracted from get_dark_theme_css

    Returns:
        str: CSS for containers, metric cards, and chart containers
    """
    return """
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }
        .metric-card {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 0.5rem;
            padding: 1.5rem;
            transition: border-color 0.2s;
        }
        .metric-card:hover { border-color: #58a6ff; }
        .metric-title {
            font-size: 0.875rem;
            font-weight: 600;
            color: #8b949e;
            text-transform: uppercase;
            margin-bottom: 0.5rem;
            letter-spacing: 0.05em;
        }
        .metric-value {
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 0.25rem;
        }
        .metric-change {
            font-size: 0.875rem;
            opacity: 0.8;
        }
        .chart-container {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 0.5rem;
            padding: 1.5rem;
            margin-bottom: 1.5rem;
        }
        .loading {
            text-align: center;
            padding: 2rem;
            color: #8b949e;
        }"""


def get_dark_theme_css() -> str:
    """
    Return GitHub-style dark theme CSS for dashboards.

    This theme uses GitHub's color palette:
    - Background: #0d1117
    - Cards/containers: #161b22
    - Borders: #30363d
    - Primary accent: #58a6ff
    - Success: #238636
    - Warning: #d29922
    - Error: #da3633

    Returns:
        str: Complete CSS stylesheet for dark theme
    """
    base_styles = _get_dark_base_styles()
    header_styles = _get_dark_header_styles()
    component_styles = _get_dark_component_styles()

    return f"{base_styles}\n{header_styles}\n{component_styles}\n    """


def _get_light_base_styles() -> str:
    """
    Generate base reset and body styles for light theme.

    Issue #665: Extracted from get_light_theme_css

    Returns:
        str: CSS for base styles including reset and body
    """
    return """
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background-color: #f5f5f5;
            color: #333;
            line-height: 1.6;
        }"""


def _get_light_header_styles() -> str:
    """
    Generate header and status indicator styles for light theme.

    Issue #665: Extracted from get_light_theme_css

    Returns:
        str: CSS for header with purple gradient and status indicators
    """
    return """
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 2rem;
            text-align: center;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .header h1 {
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
        }
        .header p {
            font-size: 1.1rem;
            opacity: 0.9;
        }
        .status-healthy { color: #38a169; }
        .status-warning { color: #d69e2e; }
        .status-critical { color: #e53e3e; }"""


def _get_light_component_styles() -> str:
    """
    Generate component styles for light theme (cards, metrics, charts).

    Issue #665: Extracted from get_light_theme_css

    Returns:
        str: CSS for containers, metric cards, and chart containers
    """
    return """
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 2rem;
        }
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }
        .metric-card {
            background: white;
            border-radius: 10px;
            padding: 1.5rem;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }
        .metric-card:hover {
            transform: translateY(-2px);
        }
        .metric-title {
            color: #4a5568;
            font-size: 0.875rem;
            font-weight: 600;
            text-transform: uppercase;
            margin-bottom: 0.5rem;
        }
        .metric-value {
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 0.25rem;
            color: #2d3748;
        }
        .metric-change {
            font-size: 0.875rem;
            color: #666;
        }
        .chart-container {
            background: white;
            border-radius: 10px;
            padding: 1.5rem;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            margin-bottom: 1.5rem;
        }"""


def get_light_theme_css() -> str:
    """
    Return light theme CSS with purple gradient header.

    Issue #665: Refactored to use helper functions for maintainability.

    This theme uses a modern light color scheme:
    - Background: #f5f5f5
    - Cards/containers: white
    - Primary gradient: purple (667eea -> 764ba2)
    - Success: #38a169
    - Warning: #d69e2e
    - Error: #e53e3e

    Returns:
        str: Complete CSS stylesheet for light theme
    """
    base_styles = _get_light_base_styles()
    header_styles = _get_light_header_styles()
    component_styles = _get_light_component_styles()

    return f"{base_styles}\n{header_styles}\n{component_styles}\n    "


def create_metric_card(
    title: str, value: str, change: Optional[str] = None, card_id: Optional[str] = None
) -> str:
    """
    Generate a metric card HTML component.

    Args:
        title: Title/label for the metric (e.g., "CPU Usage")
        value: Main metric value (e.g., "45%" or "12.5 GB")
        change: Optional change description (e.g., "+5% from yesterday")
        card_id: Optional ID for the metric value element (for dynamic updates)

    Returns:
        str: HTML for a metric card

    Example:
        >>> create_metric_card("CPU Usage", "45%", "22-core Intel Ultra 9")
        '<div class="metric-card">...</div>'
    """
    value_id = f'id="{card_id}"' if card_id else ""
    change_html = f'<div class="metric-change">{change}</div>' if change else ""

    return f"""
                <div class="metric-card">
                    <div class="metric-title">{title}</div>
                    <div {value_id} class="metric-value">{value}</div>
                    {change_html}
                </div>"""


def create_chart_container(
    chart_id: str, title: Optional[str] = None, description: Optional[str] = None
) -> str:
    """
    Generate a chart container HTML component.

    Args:
        chart_id: ID for the chart element (used by Plotly/Chart.js)
        title: Optional title displayed above the chart
        description: Optional description text below title

    Returns:
        str: HTML for a chart container

    Example:
        >>> create_chart_container("cpu-chart", "CPU Usage Over Time")
        '<div class="chart-container">...</div>'
    """
    title_html = f"<h3>{title}</h3>" if title else ""
    desc_html = f"<p>{description}</p>" if description else ""

    return f"""
            <div class="chart-container">
                {title_html}
                {desc_html}
                <div id="{chart_id}"></div>
            </div>"""


def get_plotly_dark_config() -> Dict[str, Any]:
    """
    Return Plotly dark theme configuration.

    Returns configuration object for Plotly charts that matches
    the GitHub dark theme.

    Returns:
        dict: Plotly layout configuration for dark theme

    Example:
        >>> import plotly.graph_objects as go
        >>> fig = go.Figure(data=[...])
        >>> fig.update_layout(**get_plotly_dark_config())
    """
    return {
        "template": "plotly_dark",
        "paper_bgcolor": "#161b22",
        "plot_bgcolor": "#161b22",
        "font": {
            "color": "#c9d1d9",
            "family": (
                "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
            ),
        },
        "xaxis": {"gridcolor": "#30363d", "linecolor": "#30363d"},
        "yaxis": {"gridcolor": "#30363d", "linecolor": "#30363d"},
        "margin": {"l": 40, "r": 40, "t": 40, "b": 40},
    }


def get_plotly_light_config() -> Dict[str, Any]:
    """
    Return Plotly light theme configuration.

    Returns configuration object for Plotly charts that matches
    the light purple-gradient theme.

    Returns:
        dict: Plotly layout configuration for light theme

    Example:
        >>> import plotly.graph_objects as go
        >>> fig = go.Figure(data=[...])
        >>> fig.update_layout(**get_plotly_light_config())
    """
    return {
        "template": "plotly_white",
        "paper_bgcolor": "white",
        "plot_bgcolor": "white",
        "font": {
            "color": "#333",
            "family": (
                "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
            ),
        },
        "xaxis": {"gridcolor": "#e2e8f0", "linecolor": "#cbd5e0"},
        "yaxis": {"gridcolor": "#e2e8f0", "linecolor": "#cbd5e0"},
        "margin": {"l": 40, "r": 40, "t": 40, "b": 40},
    }


def create_dashboard_header(
    title: str,
    subtitle: Optional[str] = None,
    status: Optional[str] = "healthy",
    theme: str = "dark",
) -> str:
    """
    Generate dashboard header HTML.

    Args:
        title: Main dashboard title
        subtitle: Optional subtitle text
        status: System status ("healthy", "warning", "error")
        theme: Theme to use ("dark" or "light")

    Returns:
        str: HTML for dashboard header

    Example:
        >>> create_dashboard_header("AutoBot Dashboard", "Live Monitoring", "healthy", "dark")
    """
    if theme == "dark":
        # Dark theme: horizontal header with status indicator
        status_class = f"status-{status}"
        status_text = status.capitalize()
        return f"""
    <div class="header">
        <div class="title">{title}</div>
        <div id="system-status" class="status-indicator {status_class}">{status_text}</div>
    </div>"""
    else:
        # Light theme: centered header with subtitle
        subtitle_html = f'<p class="subtitle">{subtitle}</p>' if subtitle else ""
        return f"""
    <div class="header">
        <h1>{title}</h1>
        {subtitle_html}
    </div>"""


def create_metrics_grid(metrics: List[Dict[str, str]]) -> str:
    """
    Generate a grid of metric cards.

    Args:
        metrics: List of metric dictionaries with keys:
            - title: Metric title
            - value: Metric value
            - change: Optional change description
            - card_id: Optional element ID

    Returns:
        str: HTML for metrics grid

    Example:
        >>> metrics = [
        ...     {"title": "CPU", "value": "45%", "change": "Normal"},
        ...     {"title": "Memory", "value": "8GB", "change": "Available"}
        ... ]
        >>> create_metrics_grid(metrics)
    """
    cards = "\n".join(
        [
            create_metric_card(
                m["title"], m["value"], m.get("change"), m.get("card_id")
            )
            for m in metrics
        ]
    )

    return f"""
            <div class="metrics-grid">
{cards}
            </div>"""


# Export all public functions
__all__ = [
    "get_dark_theme_css",
    "get_light_theme_css",
    "create_metric_card",
    "create_chart_container",
    "get_plotly_dark_config",
    "get_plotly_light_config",
    "create_dashboard_header",
    "create_metrics_grid",
]
