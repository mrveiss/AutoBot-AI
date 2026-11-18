# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Documentation category taxonomy (#18129).

Promoted verbatim from the standalone ``scripts/utilities/index_documentation.py``
indexer, which was retired in favour of ``DocIndexerService``. The documentation
browser (``GET /api/knowledge_base/docs/categories``) and the indexer's
``category`` filter both read it, so it lives next to the canonical indexer
instead of inside a duplicate pipeline.
"""

from pathlib import Path

CATEGORY_TAXONOMY = {
    # Order matters - more specific categories first
    "architecture": {
        "name": "Architecture",
        "description": "System architecture and design",
        "patterns": [
            "/architecture/",
            "DISTRIBUTED_ARCHITECTURE",
            "VISUAL_ARCHITECTURE",
        ],
    },
    "developer": {
        "name": "Developer Guide",
        "description": "Setup, architecture, and development documentation",
        "patterns": ["/developer/", "DEVELOPER_SETUP"],
    },
    "api": {
        "name": "API Reference",
        "description": "Complete API endpoint documentation",
        "patterns": ["/api/", "COMPREHENSIVE_API_DOCUMENTATION"],
    },
    "troubleshooting": {
        "name": "Troubleshooting",
        "description": "Problem resolution and debugging guides",
        "patterns": ["/troubleshooting/", "COMPREHENSIVE_TROUBLESHOOTING"],
    },
    "deployment": {
        "name": "Deployment",
        "description": "Deployment strategies and guides",
        "patterns": ["/deployment/", "DOCKER", "CI_PIPELINE"],
    },
    "security": {
        "name": "Security",
        "description": "Security implementation and guidelines",
        "patterns": ["/security/", "SECURITY_"],
    },
    "features": {
        "name": "Features",
        "description": "Feature documentation and guides",
        "patterns": ["/features/", "SYSTEM_STATUS", "OPTIMIZATION"],
    },
    "testing": {
        "name": "Testing",
        "description": "Testing frameworks and guides",
        "patterns": ["/testing/", "TEST_", "_TEST"],
    },
    "workflow": {
        "name": "Workflow",
        "description": "Workflow orchestration and automation",
        "patterns": ["/workflow/", "WORKFLOW_"],
    },
    "guides": {
        "name": "User Guides",
        "description": "User guides and tutorials",
        "patterns": ["/guides/", "/user_guide/", "GUIDE"],
    },
    "implementation": {
        "name": "Implementation",
        "description": "Implementation summaries and reports",
        "patterns": ["/implementation/", "IMPLEMENTATION_"],
    },
    "agents": {
        "name": "Agent System",
        "description": "Agent architecture and guides",
        "patterns": ["/agents/", "AGENT_", "multi-agent"],
    },
    "general": {
        "name": "General Documentation",
        "description": "Miscellaneous documentation",
        "patterns": ["README", "CLAUDE.md", "decisions.md"],
    },
}


def detect_category(file_path: Path) -> str:
    """Detect category based on file path and name patterns - prioritizes directory paths"""
    file_path_str = str(file_path)
    file_name = file_path.name

    # Check each category in order (more specific first)
    for category, config in CATEGORY_TAXONOMY.items():
        for pattern in config["patterns"]:
            # Check directory path first (more reliable)
            if pattern.startswith("/") and pattern in file_path_str:
                return category
            # Then check filename patterns
            elif not pattern.startswith("/") and pattern in file_name:
                return category

    return "general"


def category_of(file_path, root_dir: Path) -> str:
    """Category of *file_path* judged by its path under *root_dir*, so a checkout that itself lives under
    ``/api/`` or ``/testing/`` cannot skew the match (#17530)."""
    try:
        return detect_category(Path(file_path).relative_to(root_dir))
    except ValueError:
        return detect_category(Path(file_path))
