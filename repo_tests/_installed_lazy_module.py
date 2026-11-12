# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tell a package's own spec-less module from a stub a test built (#15169).

``kombu`` ends its ``__init__`` with ``sys.modules[__name__] = module(__name__)`` where
``module`` is a ``types.ModuleType`` subclass it defines, so the entry has no ``__spec__``
although nothing in this repository made it.  A hand-built stub is a plain ``ModuleType``
(or a mock), and copying a real package's ``__file__`` onto one is the usual way to shadow it,
so a file on disk alone proves nothing.  What a stub cannot fake cheaply is its CLASS: it must
be a ``ModuleType`` subclass whose defining module is itself a real installed file.

The caller passes its own third-party and real-file predicates, so there is one definition of
each.  The third-party test is path based (a file outside the repository root): a virtualenv
inside the root makes the package look first-party, and then it is reported as before.
"""

from __future__ import annotations

import sys
import types
from typing import Callable


def is_installed_subclass_module(
    module: object,
    is_third_party: Callable[[object], bool],
    has_real_file: Callable[[object], bool],
) -> bool:
    """True when *module* is a ``ModuleType`` subclass instance defined by installed code, on an installed file."""
    cls = type(module)
    if cls is types.ModuleType or not issubclass(cls, types.ModuleType):
        return False
    owner = sys.modules.get(cls.__module__)
    return all(is_third_party(m) and has_real_file(m) for m in (module, owner))
