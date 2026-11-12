#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Setup script for AutoBot Code Analysis Suite
"""

import os
import re

from setuptools import find_packages, setup

_SSOT_CONSTRAINTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "constraints", "shared.txt")


def _ssot_floor(package: str, constraints: str = _SSOT_CONSTRAINTS) -> str:
    """The ``>=`` floor *package* has in constraints/shared.txt, the one place it is stated (#18047).

    Raises rather than falling back to a literal: a restated floor is what drifted on every bump.
    """
    with open(constraints, encoding="utf-8") as f:
        for line in f:
            match = re.match(rf"^{re.escape(package)}\s*(>=\s*[0-9][0-9.]*)", line.split("#", 1)[0].strip())
            if match:
                return match.group(1).replace(" ", "")
    raise RuntimeError(f"{package} has no >= floor in {constraints}")


# Read the contents of README file
this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

# Read requirements
with open("requirements.txt", encoding="utf-8") as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]

setup(
    name="autobot-code-analysis-suite",
    version="1.0.0",
    author="AutoBot Development Team",
    author_email="dev@autobot.ai",
    description="Comprehensive code quality analysis system with Redis caching and NPU acceleration",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/autobot/code-analysis-suite",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Quality Assurance",
        "Topic :: Software Development :: Testing",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.14",
    install_requires=requirements,
    extras_require={
        "dev": [
            f"pytest{_ssot_floor('pytest')}",  # #18060: floors for constrained packages come from the SSOT
            f"pytest-asyncio{_ssot_floor('pytest-asyncio')}",
            "black>=22.0.0",
            "flake8>=4.0.0",
            "isort>=5.10.0",
            "mypy>=0.991",
        ],
        "npu": [
            f"openvino{_ssot_floor('openvino')}",  # #18047: the floor is read from the SSOT, never restated
            "onnxruntime>=1.12.0",
        ],
        "web": [
            f"fastapi{_ssot_floor('fastapi')}",
            f"uvicorn{_ssot_floor('uvicorn')}",
            f"jinja2{_ssot_floor('jinja2')}",
        ],
    },
    entry_points={
        "console_scripts": [
            "autobot-analyze=scripts.analyze_code_quality:main",
            "autobot-security=scripts.analyze_security:main",
            "autobot-performance=scripts.analyze_performance:main",
            "autobot-duplicates=scripts.analyze_duplicates:main",
            "autobot-patch=scripts.generate_patches:main",
        ],
    },
    include_package_data=True,
    package_data={
        "src": ["patterns/*.yaml", "templates/*.json"],
        "docs": ["*.md"],
        "examples": ["*.py", "*.json"],
    },
    project_urls={
        "Bug Reports": "https://github.com/autobot/code-analysis-suite/issues",
        "Source": "https://github.com/autobot/code-analysis-suite",
        "Documentation": "https://autobot-code-analysis.readthedocs.io/",
    },
    keywords="code-analysis quality-assurance static-analysis security performance",
)
