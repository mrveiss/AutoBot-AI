#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Check Python syntax of modified files."""

import py_compile
import sys

import glob
import os

# Dynamically find Python files in the repository
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
files_to_check = glob.glob(os.path.join(repo_root, "**", "*.py"), recursive=True)
files_to_check.sort()

all_ok = True
for filepath in files_to_check:
    try:
        py_compile.compile(filepath, doraise=True)
        print(f"✓ {filepath}")
    except py_compile.PyCompileError as e:
        print(f"✗ {filepath}: {e}")
        all_ok = False

if all_ok:
    print("\nAll files have valid Python syntax!")
    sys.exit(0)
else:
    print("\nSome files have syntax errors!")
    sys.exit(1)
