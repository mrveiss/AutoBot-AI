# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Standalone demo runners for intelligence/ modules (#7127).

The demos used to live as `__main__` blocks inside the production modules,
but the sys.path bootstrap they depended on ran AFTER the modules' top-level
imports — so `python intelligence/intelligent_agent.py` always failed with
`ModuleNotFoundError: No module named 'intelligence'` (and then `autobot_shared`)
before ever reaching the demo. The runners in this directory bootstrap
sys.path FIRST, then import the production surfaces, then run the demo.
"""
