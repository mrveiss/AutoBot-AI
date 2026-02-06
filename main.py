# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
DEPRECATED ENTRY POINT - Issue #725, #781

This file exists only to redirect users to the correct entry point.
The production backend is now at: autobot-user-backend/main.py

To start the backend:
    cd autobot-user-backend && uvicorn main:app --host 0.0.0.0 --port 8001

Or use the provided scripts:
    ./run_autobot.sh --dev
"""

import sys
import warnings

warnings.warn(
    "\n"
    "=" * 70 + "\n"
    "DEPRECATED: This entry point (main.py) is deprecated.\n"
    "Use 'cd autobot-user-backend && uvicorn main:app' instead.\n"
    "Or use './run_autobot.sh --dev' to start the application.\n"
    "See Issue #781 for the new folder structure.\n"
    "=" * 70,
    DeprecationWarning,
    stacklevel=2,
)

if __name__ == "__main__":
    print("=" * 70)
    print("ERROR: This entry point is deprecated.")
    print()
    print("The production backend has moved to: autobot-user-backend/main.py")
    print()
    print("To start the backend, use one of:")
    print("  cd autobot-user-backend && uvicorn main:app --host 0.0.0.0 --port 8001")
    print("  ./run_autobot.sh --dev")
    print()
    print("See Issue #781 for the new folder structure.")
    print("=" * 70)
    sys.exit(1)
