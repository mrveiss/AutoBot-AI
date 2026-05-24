# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Rewrite all autobot-backend/api/*.py imports from schemas_common to domain-specific files.

Run AFTER split_schemas.py has created the domain files.

Usage:
    cd /path/to/AutoBot-AI
    python3 tools/schema-split/update_imports.py [--dry-run]
"""

import re
import os
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
API_DIR = os.path.join(REPO_ROOT, "autobot-backend", "api")

DOMAIN_MODULE = {
    "terminal": "schemas_terminal",
    "analytics": "schemas_analytics",
    "knowledge": "schemas_knowledge",
    "agent": "schemas_agent",
    "system": "schemas_system",
    "workflows": "schemas_workflows",
    "code": "schemas_code",
    "common": "schemas_common",
}

DOMAIN_RULES = [
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
    return "common"


def _parse_names(names_text: str) -> list[str]:
    """Extract PascalCase names from an import clause (handles parens + continuations)."""
    text = re.sub(r"[()]", "", names_text)
    text = re.sub(r"\\\s*\n", " ", text)
    text = re.sub(r"#[^\n]*", "", text)
    return [n.strip() for n in text.split(",") if n.strip() and re.match(r"^[A-Z]", n.strip())]


def update(dry_run: bool = False) -> None:
    updated = 0

    for fname in sorted(os.listdir(API_DIR)):
        if not fname.endswith(".py") or fname.startswith("schemas_") or fname.startswith("__"):
            continue

        fpath = os.path.join(API_DIR, fname)
        with open(fpath, encoding="utf-8") as f:
            content = f.read()

        pattern = re.compile(
            r"(from\s+(?:api\.)?\.?schemas_common\s+import\s+(?:\([^)]+\)|[^\n]+))",
            re.MULTILINE,
        )

        matches = list(pattern.finditer(content))
        if not matches:
            continue

        new_content = content

        for match in matches:
            orig_text = match.group(0)
            prefix_m = re.match(r"from\s+((?:api\.)?\.?)schemas_common\s+import", orig_text)
            prefix = prefix_m.group(1) if prefix_m else "api."

            names = _parse_names(re.sub(r"from\s+\S+\s+import\s+", "", orig_text, count=1))

            by_domain: dict[str, list[str]] = defaultdict(list)
            for name in names:
                by_domain[classify_class(name)].append(name)

            import_lines = []
            for domain in ["common"] + sorted(d for d in by_domain if d != "common"):
                if domain not in by_domain:
                    continue
                dom_names = sorted(by_domain[domain])
                mod = DOMAIN_MODULE[domain]
                from_part = f"{prefix}{mod}"

                if len(dom_names) <= 3:
                    import_lines.append(f"from {from_part} import {', '.join(dom_names)}")
                else:
                    inner = ",\n    ".join(dom_names)
                    import_lines.append(f"from {from_part} import (\n    {inner},\n)")

            replacement = "\n".join(import_lines)
            new_content = new_content.replace(orig_text, replacement, 1)

        if new_content != content:
            if dry_run:
                print(f"Would update: {fname}")
            else:
                with open(fpath, "w", encoding="utf-8") as f:
                    f.write(new_content)
                print(f"Updated: {fname}")
            updated += 1

    label = "Would update" if dry_run else "Updated"
    print(f"\n{label} {updated} files total")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Rewrite schemas_common imports to domain files")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without writing files")
    args = parser.parse_args()
    update(dry_run=args.dry_run)
