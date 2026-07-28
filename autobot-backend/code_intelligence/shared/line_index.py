# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Re-export of :class:`utils.line_index.LineIndex` (#12884).

The implementation lives in ``utils/`` because modules outside this package
(api/, code_analysis/, services/) need it too, and importing
``code_intelligence.shared.line_index`` from them fails at startup: the
``code_intelligence`` package is heavy/stubbed in the import-smoke environment,
so traversing it raises ModuleNotFoundError for the submodule.

This shim keeps the in-package import path working for
``code_intelligence/security/analyzer.py`` (#12866).
"""

from utils.line_index import LineIndex

__all__ = ["LineIndex"]
