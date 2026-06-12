"""Fixture: no print() — should produce zero diagnostics."""

import logging

logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("hi")
