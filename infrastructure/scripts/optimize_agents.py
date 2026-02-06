#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Optimize agent configuration files by removing redundant sections.
Reduces token consumption while preserving critical policies.
"""

import re
from pathlib import Path


def optimize_agent_file(file_path: Path) -> tuple[bool, int, int]:
    """
    Optimize a single agent file.

    Returns:
        (modified, lines_before, lines_after)
    """
    content = file_path.read_text()
    original_lines = content.count("\n")

    # Pattern to match the entire "MANDATORY LOCAL-ONLY EDITING ENFORCEMENT" section
    pattern = r"\n## 🚨 MANDATORY LOCAL-ONLY EDITING ENFORCEMENT\n.*?(?=\n---|$)"

    # Check if section exists
    if not re.search(pattern, content, re.DOTALL):
        print(f"  ℹ️  {file_path.name}: No optimization needed (section not found)")
        return False, original_lines, original_lines

    # Replace with concise reference
    replacement = (
        "\n\n## 📋 AUTOBOT POLICIES\n\n"
        + "**See CLAUDE.md for:**\n"
        + "- No temporary fixes policy (MANDATORY)\n"
        + "- Local-only development workflow\n"
        + "- Repository cleanliness standards\n"
        + "- VM sync procedures and SSH requirements\n"
    )

    # Perform replacement
    optimized_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

    # Write back
    file_path.write_text(optimized_content)

    optimized_lines = optimized_content.count("\n")
    original_lines - optimized_lines

    return True, original_lines, optimized_lines


def main():
    """Main optimization routine."""
    agents_dir = Path("/home/kali/Desktop/AutoBot/.claude/agents")

    if not agents_dir.exists():
        print(f"❌ Error: Agents directory not found: {agents_dir}")
        return 1

    # Get all .md files except MANDATORY_LOCAL_EDIT_POLICY.md
    agent_files = [
        f for f in agents_dir.glob("*.md") if f.name != "MANDATORY_LOCAL_EDIT_POLICY.md"
    ]

    if not agent_files:
        print(f"❌ Error: No agent files found in {agents_dir}")
        return 1

    print(f"\n🔧 Optimizing {len(agent_files)} agent configuration files...\n")

    total_modified = 0
    total_lines_before = 0
    total_lines_after = 0

    for agent_file in sorted(agent_files):
        modified, lines_before, lines_after = optimize_agent_file(agent_file)

        if modified:
            lines_saved = lines_before - lines_after
            percentage = (lines_saved / lines_before * 100) if lines_before > 0 else 0
            print(
                f"  ✅ {agent_file.name}: {lines_before} → {lines_after} lines "
                f"(saved {lines_saved} lines, {percentage:.1f}%)"
            )
            total_modified += 1

        total_lines_before += lines_before
        total_lines_after += lines_after

    print("\n📊 Optimization Summary:")
    print(f"  • Files processed: {len(agent_files)}")
    print(f"  • Files modified: {total_modified}")
    print(f"  • Files unchanged: {len(agent_files) - total_modified}")
    print(f"  • Total lines before: {total_lines_before}")
    print(f"  • Total lines after: {total_lines_after}")

    if total_lines_before > 0:
        total_saved = total_lines_before - total_lines_after
        percentage = total_saved / total_lines_before * 100
        print(f"  • Total lines saved: {total_saved} ({percentage:.1f}%)")

    print("\n✅ Agent optimization complete!")
    return 0


if __name__ == "__main__":
    exit(main())
