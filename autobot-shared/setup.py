# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Setup script for autobot-shared package."""

from setuptools import find_packages, setup

setup(
    name="autobot-shared",
    version="1.0.0",
    author="mrveiss",
    description="Shared utilities for AutoBot platform",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "redis>=5.0.0",
        "pydantic>=2.0.0",
        "requests>=2.31.0",
        "aiohttp>=3.9.0",
        "prometheus-client>=0.20.0",
    ],
)
