# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``python -m autobot_shared.error_boundaries`` -- the facade's management CLI."""

import json
import logging

from autobot_shared.error_boundaries import error_boundary, get_error_statistics

logger = logging.getLogger(__name__)


def main() -> None:
    """Run the error boundary management CLI."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    import argparse

    parser = argparse.ArgumentParser(description="AutoBot Error Boundary Management")
    parser.add_argument("--stats", action="store_true", help="Show error statistics")
    parser.add_argument("--test", action="store_true", help="Test error boundary system")

    args = parser.parse_args()

    if args.stats:
        stats = get_error_statistics()
        logger.info("Error Statistics:")
        logger.info(json.dumps(stats, indent=2))

    elif args.test:
        logger.info("Testing Error Boundary System...")

        @error_boundary(component="test", function="divide")
        def test_divide(a, b):
            """Test division function."""
            return a / b

        # Test normal operation
        result = test_divide(10, 2)
        logger.info(f"Normal operation: 10 / 2 = {result}")

        # Test error handling
        try:
            result = test_divide(10, 0)
            logger.info(f"Error handling: 10 / 0 = {result}")
        except Exception as e:
            logger.info(f"Error caught: {e}")

        logger.info("Error boundary system test completed")

    else:
        logger.info("Use --stats to show statistics or --test to test the system")


if __name__ == "__main__":
    main()
