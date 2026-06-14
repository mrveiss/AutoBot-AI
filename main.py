# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
DEPRECATED ENTRY POINT - Issue #725, #781

This file exists only to redirect users to the correct entry point.
The production backend is now at: autobot-user-backend/main.py

To start the backend:
    cd autobot-user-backend && uvicorn main:app --host 0.0.0.0 --port 8001

Or use SLM orchestration:
    SLM GUI: https://10.0.0.9/orchestration
    CLI: scripts/start-services.sh start
"""

import sys
import warnings

warnings.warn(
    "\n"
    "=" * 70 + "\n"
    "DEPRECATED: This entry point (main.py) is deprecated.\n"
    "Use 'cd autobot-user-backend && uvicorn main:app' instead.\n"
    "Or use SLM orchestration (scripts/start-services.sh) to start.\n"
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
    print("  SLM GUI: https://10.0.0.9/orchestration")
    print("  CLI: scripts/start-services.sh start")
    print()
    print("See Issue #781 for the new folder structure.")
    print("=" * 70)
    sys.exit(1)
