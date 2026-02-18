#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Integrate System Knowledge into Knowledge Base V2
Populates man pages and AutoBot documentation into the searchable knowledge base
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def _build_man_content_parts(man_data: dict, command: str, section: int) -> list:
    """Build content parts for man page.

    Helper for integrate_cached_man_pages (Issue #825).
    """
    description = man_data.get("description", f"Manual page for {command}")
    content_parts = [
        f"# {command}({section}) - {description}",
        "",
        f"**Synopsis:** {man_data.get('synopsis', 'N/A')}",
        "",
        "## Options:",
    ]

    for opt in man_data.get("options", [])[:20]:  # Top 20 options
        if isinstance(opt, dict):
            content_parts.append(
                f"- `{opt.get('flag', '')}`: {opt.get('description', '')}"
            )
        else:
            content_parts.append(f"- {opt}")

    if man_data.get("examples"):
        content_parts.append("")
        content_parts.append("## Examples:")
        for ex in man_data.get("examples", [])[:5]:  # Top 5 examples
            if isinstance(ex, dict):
                content_parts.append(
                    f"- `{ex.get('command', '')}`: {ex.get('description', '')}"
                )
            else:
                content_parts.append(f"- {ex}")

    if man_data.get("see_also"):
        content_parts.append("")
        content_parts.append(f"**See Also:** {', '.join(man_data.get('see_also', []))}")

    return content_parts


async def integrate_cached_man_pages(kb_v2):
    """Integrate cached man pages from data/system_knowledge/man_pages/"""
    logger.info("Starting cached man pages integration...")

    cache_dir = Path("data/system_knowledge/man_pages")
    if not cache_dir.exists():
        logger.warning("Man pages cache directory not found: %s", cache_dir)
        return 0

    man_files = list(cache_dir.glob("*.json"))
    logger.info("Found %s cached man pages", len(man_files))

    integrated_count = 0

    for man_file in man_files:
        try:
            with open(man_file, "r") as f:
                man_data = json.load(f)

            command = man_data.get("command", man_file.stem.split("_")[0])
            section = man_data.get("section", 1)

            # Build comprehensive content
            content_parts = _build_man_content_parts(man_data, command, section)
            content = "\n".join(content_parts)

            # Store in Knowledge Base V2
            result = await kb_v2.store_fact(
                content=content,
                metadata={
                    "type": "man_page",
                    "command": command,
                    "section": section,
                    "category": "system_commands",
                    "source": "man_pages_cache",
                    "title": f"man {command}({section})",
                },
            )

            if result.get("status") == "success":
                integrated_count += 1
                if integrated_count % 10 == 0:
                    logger.info(
                        "Integrated %s/%s man pages...",
                        integrated_count,
                        len(man_files),
                    )

        except Exception as e:
            logger.error("Error integrating %s: %s", man_file, e)
            continue

    logger.info("✓ Integrated %s man pages into Knowledge Base V2", integrated_count)
    return integrated_count


def _extract_doc_title(content: str, doc_path: Path) -> str:
    """Extract title from content or filename (Issue #315: extracted helper)."""
    lines = content.split("\n")
    title = doc_path.stem.replace("_", " ").title()
    for line in lines[:10]:
        if line.startswith("# "):
            return line.lstrip("# ").strip()
    return title


def _determine_doc_category(doc_path: Path) -> str:
    """Determine category based on document path (Issue #315: extracted helper)."""
    category_map = [
        ("/api/", "api_reference"),
        ("/architecture/", "architecture"),
        ("/developer/", "developer_guide"),
        ("/troubleshooting/", "troubleshooting"),
    ]
    doc_path_str = str(doc_path)
    for path_pattern, cat in category_map:
        if path_pattern in doc_path_str:
            return cat
    if doc_path.name == "CLAUDE.md":
        return "project_rules"
    return "documentation"


async def _integrate_single_doc(doc_path: Path, kb_v2) -> bool:
    """Integrate a single documentation file (Issue #315: extracted helper)."""
    with open(doc_path, "r", encoding="utf-8") as f:
        content = f.read()

    title = _extract_doc_title(content, doc_path)
    category = _determine_doc_category(doc_path)

    result = await kb_v2.store_fact(
        content=content,
        metadata={
            "type": "autobot_documentation",
            "title": title,
            "category": category,
            "source": "autobot_docs",
            "file_path": str(doc_path),
        },
    )

    if result.get("status") == "success":
        logger.info("✓ Integrated documentation: %s", title)
        return True
    return False


async def integrate_autobot_documentation(kb_v2):
    """Integrate AutoBot documentation from docs/ directory (Issue #315: refactored)."""
    logger.info("Starting AutoBot documentation integration...")

    docs_dir = Path("docs")
    if not docs_dir.exists():
        logger.warning("Documentation directory not found: %s", docs_dir)
        return 0

    priority_docs = [
        "CLAUDE.md",
        "docs/system-state.md",
        "docs/api/COMPREHENSIVE_API_DOCUMENTATION.md",
        "docs/architecture/PHASE_5_DISTRIBUTED_ARCHITECTURE.md",
        "docs/developer/PHASE_5_DEVELOPER_SETUP.md",
        "docs/troubleshooting/COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md",
    ]

    integrated_count = 0

    for doc_path_str in priority_docs:
        doc_path = Path(doc_path_str)
        if not doc_path.exists():
            logger.warning("Documentation file not found: %s", doc_path)
            continue

        try:
            if await _integrate_single_doc(doc_path, kb_v2):
                integrated_count += 1
        except Exception as e:
            logger.error("Error integrating %s: %s", doc_path, e)
            continue

    logger.info(
        "✓ Integrated %s documentation files into Knowledge Base V2", integrated_count
    )
    return integrated_count


async def main():
    """Main integration function"""
    logger.info("=" * 80)
    logger.info("SYSTEM KNOWLEDGE INTEGRATION - Knowledge Base V2")
    logger.info("=" * 80)

    try:
        # Import and initialize Knowledge Base V2
        from knowledge_base import KnowledgeBase

        logger.info("\n1. Initializing Knowledge Base V2...")
        kb_v2 = KnowledgeBase()
        await kb_v2.initialize()

        if not kb_v2.initialized:
            logger.error("✗ Knowledge Base V2 initialization failed")
            return 1

        logger.info("✓ Knowledge Base V2 initialized successfully")

        # Get current stats
        stats = await kb_v2.get_stats()
        logger.info("\nCurrent Knowledge Base Stats:")
        logger.info("  - Total facts: %s", stats.get("total_facts", 0))
        logger.info("  - Total vectors: %s", stats.get("total_vectors", 0))

        # Integrate man pages
        logger.info("\n2. Integrating Man Pages...")
        man_pages_count = await integrate_cached_man_pages(kb_v2)

        # Integrate AutoBot documentation
        logger.info("\n3. Integrating AutoBot Documentation...")
        docs_count = await integrate_autobot_documentation(kb_v2)

        # Get updated stats
        updated_stats = await kb_v2.get_stats()
        logger.info("\nUpdated Knowledge Base Stats:")
        logger.info("  - Total facts: %s", updated_stats.get("total_facts", 0))
        logger.info("  - Total vectors: %s", updated_stats.get("total_vectors", 0))

        logger.info("\n" + "=" * 80)
        logger.info("INTEGRATION COMPLETE")
        logger.info("=" * 80)
        logger.info("✓ Man pages integrated: %s", man_pages_count)
        logger.info("✓ Documentation files integrated: %s", docs_count)
        logger.info("✓ Total system knowledge added: %s", man_pages_count + docs_count)
        logger.info("=" * 80)

        return 0

    except Exception as e:
        logger.error("✗ Integration failed: %s", e)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
