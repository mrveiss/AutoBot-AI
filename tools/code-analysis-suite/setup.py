#!/usr/bin/env python3
"""
Setup script for AutoBot Code Analysis Suite
"""

from setuptools import setup, find_packages
import os

# Read the contents of README file
this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

# Read requirements
with open('requirements.txt') as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith('#')]

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
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    extras_require={
        'dev': [
            'pytest>=7.0.0',
            'pytest-asyncio>=0.21.0',
            'black>=22.0.0',
            'flake8>=4.0.0',
            'isort>=5.10.0',
            'mypy>=0.991',
        ],
        'npu': [
            'openvino>=2023.0.0',
            'onnxruntime>=1.12.0',
        ],
        'web': [
            'fastapi>=0.95.0',
            'uvicorn>=0.20.0',
            'jinja2>=3.1.0',
        ]
    },
    entry_points={
        'console_scripts': [
            'autobot-analyze=scripts.analyze_code_quality:main',
            'autobot-security=scripts.analyze_security:main',
            'autobot-performance=scripts.analyze_performance:main',
            'autobot-duplicates=scripts.analyze_duplicates:main',
            'autobot-patch=scripts.generate_patches:main',
        ],
    },
    include_package_data=True,
    package_data={
        'src': ['patterns/*.yaml', 'templates/*.json'],
        'docs': ['*.md'],
        'examples': ['*.py', '*.json'],
    },
    project_urls={
        "Bug Reports": "https://github.com/autobot/code-analysis-suite/issues",
        "Source": "https://github.com/autobot/code-analysis-suite",
        "Documentation": "https://autobot-code-analysis.readthedocs.io/",
    },
    keywords="code-analysis quality-assurance static-analysis security performance",
)
