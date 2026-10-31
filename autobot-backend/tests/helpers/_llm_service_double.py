# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An ``LLMService`` double that only accepts what the real class defines (#19649).

The backend conftest stubs ``services.llm_service`` with a ``MagicMock`` module, so
``create_autospec(LLMService)`` against the stub fails ("Cannot autospec a Mock
object"). The genuine file is loaded here once, under a private name, leaving the
stub other tests rely on in place.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import create_autospec

_BACKEND = Path(__file__).resolve().parents[2]
_PRIVATE_NAME = "_real_llm_service_19649"


def real_llm_service_class() -> type:
    """The genuine ``LLMService`` class."""
    if _PRIVATE_NAME not in sys.modules:
        spec = importlib.util.spec_from_file_location(_PRIVATE_NAME, _BACKEND / "services" / "llm_service.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[_PRIVATE_NAME] = module
        spec.loader.exec_module(module)
    return sys.modules[_PRIVATE_NAME].LLMService


def make_llm_service_double():
    """An instance double: calling a method ``LLMService`` lacks raises ``AttributeError``."""
    return create_autospec(real_llm_service_class(), instance=True)
