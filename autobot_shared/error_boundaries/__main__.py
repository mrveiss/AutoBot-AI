# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``python -m autobot_shared.error_boundaries`` -- the facade's management CLI."""

import argparse
import json

from autobot_shared.error_boundaries import error_boundary, get_error_statistics
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


def _run_stats() -> None:
    """Print the error statistics as JSON."""
    logger.info("Error Statistics:")
    logger.info(json.dumps(get_error_statistics(), indent=2))


def _run_self_test() -> None:
    """Exercise one boundary-wrapped function on a normal and a failing input."""
    logger.info("Testing Error Boundary System...")

    @error_boundary(component="test", function="divide")
    def test_divide(a, b):
        """Test division function."""
        return a / b

    logger.info("Normal operation: 10 / 2 = %s", test_divide(10, 2))
    try:
        logger.info("Error handling: 10 / 0 = %s", test_divide(10, 0))
    except Exception as e:
        logger.info("Error caught: %s", e)
    logger.info("Error boundary system test completed")


def main() -> None:
    """Run the error boundary management CLI."""
    parser = argparse.ArgumentParser(description="AutoBot Error Boundary Management")
    parser.add_argument("--stats", action="store_true", help="Show error statistics")
    parser.add_argument("--test", action="store_true", help="Test error boundary system")
    args = parser.parse_args()

    if args.stats:
        _run_stats()
    elif args.test:
        _run_self_test()
    else:
        logger.info("Use --stats to show statistics or --test to test the system")


if __name__ == "__main__":
    main()
