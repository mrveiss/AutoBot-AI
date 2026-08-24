#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Backend startup: the workflow router must import and register its routes.

#14920 named this module's ``test_imports`` as the clearest case in the repo of
a test that cannot fail. It was a script: it wrapped every import in
``try/except Exception``, printed a tick or a cross, and ended each branch with
``return True`` or ``return False``. pytest discards a test's return value, so
*both* branches passed — the function reported an import failure by returning a
value nobody read, and the suite went green on the failure path exactly as
loudly as on the success path.

The verdict is now an assertion, which is the only thing pytest reads. The
progress printing and the developer instructions that made it look like a
script have moved into ``main()``, where they belong, and ``main()`` still
returns the exit code the command line expects — the module is usable both ways
without either use pretending to be the other.
"""

from tests.test_helpers import get_test_backend_url


def test_imports() -> None:
    """The workflow router imports and exposes routes.

    No ``try``/``except``: an ImportError here IS the failure this test exists
    to report, and swallowing it was the bug. Nothing is caught, nothing is
    returned — the exception is the verdict.
    """
    from api.workflow import router

    routes = [route.path for route in router.routes]
    assert routes, (
        "api.workflow.router imported but registered no routes — the workflow "
        "endpoints would 404 at runtime while every import looked healthy"
    )


def main() -> int:
    """Run the check as a script and report it for a human."""
    print("🧪 Testing Backend Imports")  # noqa: print
    print("-" * 40)  # noqa: print
    try:
        test_imports()
    except Exception as error:  # noqa: BLE001 - a script reports, it does not raise
        print(f"❌ Import error: {error}")  # noqa: print
        print("\n❌ Fix import errors before starting AutoBot backend.")  # noqa: print
        return 1

    from api.workflow import router

    routes = [route.path for route in router.routes]
    print(f"✅ Workflow router import successful: {len(routes)} routes")  # noqa: print
    for route in routes[:5]:
        print(f"   - {route}")  # noqa: print

    print("\n🎉 All imports successful! Backend should start properly now.")  # noqa: print
    print("\n📋 Next steps:")  # noqa: print
    print("1. Start the backend: python main.py")  # noqa: print
    print(f"2. Test workflow endpoint: {get_test_backend_url()}/api/workflow/workflows")  # noqa: print
    print("3. Open frontend and navigate to Workflows tab")  # noqa: print
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
