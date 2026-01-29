# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
DEPRECATED ENTRY POINT - Issue #725

This file exists only to redirect users to the correct entry point.
The production backend is now at: backend/main.py

To start the backend:
    python -m backend.main
    OR
    uvicorn backend.main:app --host 0.0.0.0 --port 8001

For the legacy code, see: main.py.deprecated
"""

import sys
import warnings

warnings.warn(
    "\n"
    "=" * 70 + "\n"
    "DEPRECATED: This entry point (main.py) is deprecated.\n"
    "Use 'python -m backend.main' or 'uvicorn backend.main:app' instead.\n"
    "See Issue #725 for details.\n"
    "=" * 70,
    DeprecationWarning,
    stacklevel=2
)

if __name__ == "__main__":
    print("=" * 70)
    print("ERROR: This entry point is deprecated.")
    print()
    print("The production backend has moved to: backend/main.py")
    print()
    print("To start the backend, use one of:")
    print("  python -m backend.main")
    print("  uvicorn backend.main:app --host 0.0.0.0 --port 8001")
    print()
    print("For the legacy code, see: main.py.deprecated")
    print("=" * 70)
    sys.exit(1)
