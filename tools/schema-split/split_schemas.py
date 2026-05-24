# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Split autobot-backend/api/schemas_common.py into per-domain schema files.

Usage:
    cd /path/to/AutoBot-AI
    python3 tools/schema-split/split_schemas.py

After running, also run update_imports.py to rewrite all API endpoint imports.

See README.md for the full workflow including handling new domains.
"""

import re
import os
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
API_DIR = os.path.join(REPO_ROOT, "autobot-backend", "api")
SCHEMA_FILE = os.path.join(API_DIR, "schemas_common.py")

COPYRIGHT = """# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""

PYDANTIC_IMPORT = "from typing import Any, Dict, List, Optional\n\nfrom pydantic import BaseModel\n"

# ---------------------------------------------------------------------------
# Domain → file mapping
# ---------------------------------------------------------------------------
DOMAIN_FILE = {
    "terminal": "schemas_terminal.py",
    "analytics": "schemas_analytics.py",
    "knowledge": "schemas_knowledge.py",
    "agent": "schemas_agent.py",
    "system": "schemas_system.py",
    "workflows": "schemas_workflows.py",
    "code": "schemas_code.py",
    "common": "schemas_common.py",
}

DOMAIN_HEADERS = {
    "terminal": "Terminal and AgentTerminal session, SSH, command, and health schemas.",
    "analytics": "Analytics, cost, budget, usage, and metrics schemas.",
    "knowledge": "Knowledge base collection, category, fact, grounding, and audit schemas.",
    "agent": "Agent config, memory, and LLM schemas.",
    "system": "System health, cache, NPU worker, wake-word, and feature-flag schemas.",
    "workflows": "Workflow, registry, RUM, elevation, advanced-control, state-tracking, and validation schemas.",
    "code": "Code review, git, skills, database, template, log, voice, access-control, MCP, and file-sandbox schemas.",
}

# ---------------------------------------------------------------------------
# Classification rules — longest-match prefix wins
# ---------------------------------------------------------------------------
DOMAIN_RULES = [
    # Longest prefixes first to avoid shorter-prefix false matches
    (r"^(AgentTerminal)", "terminal"),
    (r"^(AgentMessage|AgentCommand|AgentHealth|AgentConfig|AgentCommandApproval|AgentCommandExecute)", "agent"),
    (r"^(Terminal|SSH|CommandAssess|AdminExecute|PackageManagers)", "terminal"),
    (r"^(Analytics|Cost|Budget|UsageSummary|UsageBy|RecentUsage|ModelPricing|AllAgent|Metrics)", "analytics"),
    (r"^Knowledge", "knowledge"),
    (r"^(LLM|Memory)", "agent"),
    (r"^(System|NPU|WakeWord|FeatureFlag|AdminFile)", "system"),
    (
        r"^(ValidationDashboard|ValidationJudge|ValidationJudgment|Workflow|Registry|RUM|Elevation|AdvancedControl|StateTracking|StructuredThinking)",
        "workflows",
    ),
    (
        r"^(CodeReview|Git|Skills|SkillsDraft|SkillsApproval|SkillsGovernance|SkillsGap|Database|Template|Templates|Log|Voice|AccessControl|FileSandbox|MCP|HTTP)",
        "code",
    ),
    (r"^(Success|Data|UsageRecord)", "common"),
]


def classify_class(cls: str) -> str:
    for pattern, domain in DOMAIN_RULES:
        if re.match(pattern, cls):
            return domain
    return "common"  # fallback — stays in schemas_common


def _find_base_classes(content: str) -> set[str]:
    """Return all non-BaseModel base class names used in class definitions."""
    bases = set(re.findall(r"^class \w+\((\w+)\)", content, re.MULTILINE))
    bases.discard("BaseModel")
    return bases


def _build_import_line(base_classes: set[str], prefix: str = "api.") -> str | None:
    """Build 'from api.schemas_common import X, Y' for base classes from common."""
    if not base_classes:
        return None
    names = sorted(base_classes)
    if len(names) == 1:
        return f"from {prefix}schemas_common import {names[0]}"
    return f"from {prefix}schemas_common import {', '.join(names)}"


def split(dry_run: bool = False) -> None:
    with open(SCHEMA_FILE, encoding="utf-8") as f:
        content = f.read()
        lines = content.split("\n")

    # Locate class starts
    class_starts: dict[str, int] = {}
    for i, line in enumerate(lines):
        m = re.match(r"^class (\w+)\(", line)
        if m:
            class_starts[m.group(1)] = i

    ordered = list(class_starts.keys())

    # Extract class blocks (definition + body, no preceding blank lines)
    class_blocks: dict[str, str] = {}
    for j, cls in enumerate(ordered):
        start = class_starts[cls]
        end = class_starts[ordered[j + 1]] if j + 1 < len(ordered) else len(lines)
        class_blocks[cls] = "\n".join(lines[start:end])

    # Group by domain
    domain_classes: dict[str, list[str]] = defaultdict(list)
    for cls in ordered:
        domain_classes[classify_class(cls)].append(cls)

    print("Classes per domain:")
    for d, classes in sorted(domain_classes.items(), key=lambda x: -len(x[1])):
        print(f"  {d:12s}: {len(classes)}")

    if dry_run:
        print("\nDry run — no files written.")
        return

    # Write domain files
    for domain, classes in domain_classes.items():
        if domain == "common":
            continue

        fname = DOMAIN_FILE[domain]
        fpath = os.path.join(API_DIR, fname)
        body = "\n\n".join(c_block for cls in classes for c_block in [class_blocks[cls]])

        # Detect base classes used (may need import from schemas_common)
        base_import = _build_import_line(_find_base_classes(body))
        extra_import = f"\n{base_import}\n" if base_import else ""

        file_content = (
            f'{COPYRIGHT}"""\n{DOMAIN_HEADERS[domain]}\n"""\n\n'
            f"{PYDANTIC_IMPORT}{extra_import}\n"
            f"# ---------------------------------------------------------------------------\n"
            f"# {domain.capitalize()} schemas\n"
            f"# ---------------------------------------------------------------------------\n\n"
            f"{body.rstrip()}\n"
        )

        with open(fpath, "w", encoding="utf-8") as f:
            f.write(file_content)
        print(f"Wrote {fname} ({len(classes)} classes)")

    # Rewrite schemas_common.py with only the common classes
    common_classes = domain_classes["common"]
    common_body = "\n\n".join(class_blocks[cls] for cls in common_classes)

    new_common = (
        f'{COPYRIGHT}"""\n'
        "Shared cross-domain Pydantic response schemas for AutoBot API endpoints.\n\n"
        "These are truly generic types used across multiple unrelated domains.\n"
        "Domain-specific schemas live in:\n"
        + "".join(f"  {DOMAIN_FILE[d]:28s} - {DOMAIN_HEADERS[d]}\n" for d in sorted(DOMAIN_FILE) if d != "common")
        + '"""\n\n'
        f"{PYDANTIC_IMPORT}\n"
        "# ---------------------------------------------------------------------------\n"
        "# Generic / reusable (used across multiple unrelated domains)\n"
        "# ---------------------------------------------------------------------------\n\n"
        f"{common_body.rstrip()}\n"
    )

    with open(SCHEMA_FILE, "w", encoding="utf-8") as f:
        f.write(new_common)
    print(f"Updated schemas_common.py ({len(common_classes)} classes)")
    print("\nNext step: run tools/schema-split/update_imports.py")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Split schemas_common.py into domain files")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without writing files")
    args = parser.parse_args()
    split(dry_run=args.dry_run)
