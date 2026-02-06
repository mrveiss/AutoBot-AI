#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test Documentation API Endpoints (Local Testing)
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, "/home/kali/Desktop/AutoBot")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_documentation_browser_logic():
    """Test the documentation browser logic locally without the backend"""

    print("=== Testing Documentation Browser Logic ===")

    try:
        import hashlib
        import mimetypes

        project_root = Path("/home/kali/Desktop/AutoBot")

        documentation_files = []
        total_size = 0
        total_docs = 0

        def _extract_title_and_preview(content: str, filename: str) -> tuple:
            """Extract title and preview from content (Issue #315: extracted helper)."""
            title = filename
            preview = ""
            if not content:
                return title, preview
            lines = content.split("\n")
            for line in lines:
                if line.strip():
                    if line.startswith("# "):
                        title = line[2:].strip()
                    preview = line.strip()
                    break
            return title, preview

        def _determine_category(rel_path: str, category_prefix: str) -> str:
            """Determine document category from path (Issue #315: extracted helper)."""
            if "/docs/" not in rel_path:
                return category_prefix
            parts = rel_path.split("/")
            if len(parts) > 2:  # docs/subfolder/file.md
                return f"docs/{parts[1]}"
            return "docs/root"

        def _build_file_info(
            item: Path, content: str, project_root: Path, category_prefix: str
        ) -> dict:
            """Build file info dict for a single file (Issue #315: extracted helper)."""
            stat = item.stat()
            content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()[:8]
            title, preview = _extract_title_and_preview(content, item.name)
            rel_path = str(item.relative_to(project_root))
            category = _determine_category(rel_path, category_prefix)

            return {
                "id": f"doc_{content_hash}_{stat.st_ino}",
                "path": rel_path,
                "filename": item.name,
                "title": title,
                "category": category,
                "type": item.suffix.lower()[1:],  # Remove the dot
                "size_bytes": stat.st_size,
                "size_chars": len(content),
                "modified": stat.st_mtime,
                "created": stat.st_ctime,
                "mime_type": mimetypes.guess_type(str(item))[0] or "text/plain",
                "preview": preview[:200] + "..." if len(preview) > 200 else preview,
                "content_hash": content_hash,
                "exists": True,
                "readable": True,
                "line_count": len(content.split("\n")) if content else 0,
                "word_count": len(content.split()) if content else 0,
            }

        def _process_doc_file(
            item: Path, project_root: Path, category_prefix: str
        ) -> dict:
            """Process a single documentation file (Issue #315: extracted helper)."""
            with open(item, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            return _build_file_info(item, content, project_root, category_prefix)

        def scan_directory(dir_path: Path, category_prefix: str = ""):
            """Recursively scan directory for documentation files (Issue #315: refactored)."""
            nonlocal total_size, total_docs
            files = []

            if not dir_path.exists() or not dir_path.is_dir():
                return files

            doc_extensions = [".md", ".txt", ".yaml", ".yml", ".json"]

            try:
                for item in dir_path.iterdir():
                    if item.is_file() and item.suffix.lower() in doc_extensions:
                        try:
                            file_info = _process_doc_file(
                                item, project_root, category_prefix
                            )
                            files.append(file_info)
                            total_size += file_info["size_bytes"]
                            total_docs += 1
                        except Exception as e:
                            logger.warning(f"Error processing file {item}: {e}")

                    elif (
                        item.is_dir()
                        and not item.name.startswith(".")
                        and item.name != "__pycache__"
                    ):
                        # Recursively scan subdirectories
                        subdir_category = (
                            f"{category_prefix}/{item.name}"
                            if category_prefix
                            else item.name
                        )
                        subdir_files = scan_directory(item, subdir_category)
                        files.extend(subdir_files)

            except PermissionError as e:
                logger.warning(f"Permission denied accessing {dir_path}: {e}")
            except Exception as e:
                logger.error(f"Error scanning directory {dir_path}: {e}")

            return files

        # Add root documentation files
        root_files = [
            ("CLAUDE.md", "Claude Development Instructions", "project-root"),
            ("README.md", "Project README", "project-root"),
            ("IMPLEMENTATION_PLAN.md", "Implementation Plan", "project-root"),
            ("CHAT_HANG_ANALYSIS.md", "Chat Hang Analysis", "project-root"),
            ("DESKTOP_ACCESS.md", "Desktop Access Guide", "project-root"),
        ]

        all_files = []

        for file_path, title, category in root_files:
            full_path = project_root / file_path
            if full_path.exists() and full_path.is_file():
                try:
                    stat = full_path.stat()
                    with open(full_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()[:8]

                    file_info = {
                        "id": f"root_{content_hash}_{stat.st_ino}",
                        "path": file_path,
                        "filename": full_path.name,
                        "title": title,
                        "category": category,
                        "type": full_path.suffix.lower()[1:],
                        "size_bytes": stat.st_size,
                        "size_chars": len(content),
                        "modified": stat.st_mtime,
                        "line_count": len(content.split("\n")),
                        "word_count": len(content.split()),
                    }

                    all_files.append(file_info)
                    total_size += stat.st_size
                    total_docs += 1

                    print(f"✅ {file_path} - {title}")
                    print(
                        f"   Size: {file_info['size_chars']} chars, {file_info['line_count']} lines"
                    )

                except Exception as e:
                    print(f"❌ Error processing {file_path}: {e}")

        # Scan docs directory
        print("\n📁 Scanning docs directory...")
        docs_path = project_root / "docs"
        if docs_path.exists():
            docs_files = scan_directory(docs_path, "docs")
            all_files.extend(docs_files)
            print(f"   Found {len(docs_files)} documentation files in docs/")

        # Group by category
        categories = {}
        for file_info in all_files:
            category = file_info.get("category", "uncategorized")
            if category not in categories:
                categories[category] = {
                    "name": category,
                    "files": [],
                    "total_files": 0,
                    "total_size": 0,
                }
            categories[category]["files"].append(file_info)
            categories[category]["total_files"] += 1
            categories[category]["total_size"] += file_info.get("size_bytes", 0)

        print("\n📊 Documentation Statistics:")
        print(f"   Total files: {total_docs}")
        print(f"   Total size: {round(total_size / (1024 * 1024), 2)} MB")
        print(f"   Categories: {len(categories)}")

        print("\n📁 Categories found:")
        for category, info in categories.items():
            size_mb = round(info["total_size"] / (1024 * 1024), 2)
            print(f"   {category}: {info['total_files']} files ({size_mb} MB)")

        # Test reading a specific file
        print("\n📖 Testing file reading:")
        test_file = "CLAUDE.md"
        full_path = project_root / test_file
        if full_path.exists():
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Check if AutoBot identity is in the content
            if "AutoBot" in content:
                print(f"✅ {test_file} contains AutoBot information")
                # Find lines with AutoBot
                lines_with_autobot = [
                    i + 1
                    for i, line in enumerate(content.split("\n"))
                    if "AutoBot" in line
                ]
                print(f"   AutoBot mentioned on lines: {lines_with_autobot[:10]}...")
            else:
                print(f"❌ {test_file} does not contain AutoBot information")

        return {
            "success": True,
            "total_files": total_docs,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "categories": list(categories.keys()),
            "files": all_files[:5],  # Sample
        }

    except Exception as e:
        print(f"❌ Error in documentation browser test: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    result = asyncio.run(test_documentation_browser_logic())
    print(f"\n🏁 Test Result: {result['success']}")
    if result["success"]:
        print(f"   Documentation system is ready with {result['total_files']} files")
    else:
        print(f"   Error: {result.get('error', 'Unknown error')}")
