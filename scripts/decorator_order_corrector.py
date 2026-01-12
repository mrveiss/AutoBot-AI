#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Fix @with_error_handling decorator order

This script fixes endpoints where @with_error_handling appears AFTER @router
instead of BEFORE it. The correct order is:

@with_error_handling(...)
@router.get("/...")
async def ...

Wrong order:
@router.get("/...")
@with_error_handling(...)
async def ...
"""

import re
from pathlib import Path


def decorator_order_corrector_in_file(file_path: Path) -> tuple[int, list[str]]:
    """
    Fix decorator order in a single file.

    Returns:
        Tuple of (number_of_fixes, list_of_fixed_endpoints)
    """
    content = file_path.read_text()
    lines = content.split('\n')
    fixes = []
    fixed_count = 0

    i = 0
    while i < len(lines):
        line = lines[i]

        # Look for @router decorator
        if re.match(r'\s*@router\.(get|post|put|delete|patch)', line):
            router_line_idx = i
            router_indent = len(line) - len(line.lstrip())

            # Look ahead for @with_error_handling (wrong order)
            j = i + 1
            error_handler_start = None
            error_handler_end = None

            while j < len(lines) and j < i + 15:
                next_line = lines[j].strip()

                # Found @with_error_handling after @router - wrong order!
                if '@with_error_handling' in next_line:
                    error_handler_start = j

                    # Find end of decorator (might span multiple lines)
                    paren_count = next_line.count('(') - next_line.count(')')
                    error_handler_end = j

                    while paren_count > 0 and error_handler_end < len(lines) - 1:
                        error_handler_end += 1
                        paren_count += lines[error_handler_end].count('(')
                        paren_count -= lines[error_handler_end].count(')')

                    break

                # Stop if we hit the function definition
                if next_line.startswith('async def') or next_line.startswith('def'):
                    break

                j += 1

            # If we found wrong order, fix it
            if error_handler_start is not None:
                # Extract the @with_error_handling decorator block
                error_handler_lines = lines[error_handler_start:error_handler_end + 1]

                # Extract the @router decorator (might also span multiple lines)
                router_end = router_line_idx
                paren_count = line.count('(') - line.count(')')

                while paren_count > 0 and router_end < len(lines) - 1:
                    router_end += 1
                    paren_count += lines[router_end].count('(')
                    paren_count -= lines[router_end].count(')')

                router_lines = lines[router_line_idx:router_end + 1]

                # Remove the @with_error_handling decorator from its current position
                del lines[error_handler_start:error_handler_end + 1]

                # Insert @with_error_handling BEFORE @router (correct order)
                for idx, handler_line in enumerate(error_handler_lines):
                    lines.insert(router_line_idx + idx, handler_line)

                endpoint_name = lines[router_line_idx + len(error_handler_lines)].strip()
                fixes.append(f"{file_path.name}:{router_line_idx + 1} - {endpoint_name}")
                fixed_count += 1

                # Skip ahead to avoid re-processing
                i = router_line_idx + len(error_handler_lines) + len(router_lines) + 1
                continue

        i += 1

    # Write back if any fixes were made
    if fixed_count > 0:
        file_path.write_text('\n'.join(lines))

    return fixed_count, fixes


def main():
    """Entry point for fixing decorator order in backend API files."""
    backend_api = Path("backend/api")
    total_fixes = 0
    all_fixes = []

    print("🔧 Fixing decorator order in backend/api/*.py files...\n")

    for py_file in sorted(backend_api.glob("*.py")):
        fixed_count, fixes = decorator_order_corrector_in_file(py_file)

        if fixed_count > 0:
            total_fixes += fixed_count
            all_fixes.extend(fixes)
            print(f"✅ {py_file.name}: Fixed {fixed_count} endpoint(s)")

    print(f"\n🎉 Total fixes: {total_fixes} endpoints")

    if all_fixes:
        print("\nFixed endpoints:")
        for fix in all_fixes[:20]:
            print(f"  {fix}")
        if len(all_fixes) > 20:
            print(f"  ... and {len(all_fixes) - 20} more")


if __name__ == "__main__":
    main()
