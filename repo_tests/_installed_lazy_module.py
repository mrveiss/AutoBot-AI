# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tell a package's own spec-less module from a stub a test built (#15169).

``kombu`` ends its ``__init__`` with ``sys.modules[__name__] = module(__name__)`` where
``module`` is a ``types.ModuleType`` subclass it defines, so the entry has no ``__spec__``
although nothing in this repository made it.  A hand-built stub is a plain ``ModuleType``
(or a mock), and copying a real package's ``__file__`` onto one is the usual way to shadow it,
so a file on disk alone proves nothing.  Three things hold for the kombu shape and cost a stub
more than assigning a string:

* the class is a ``ModuleType`` subclass whose functions all have code in a real installed
  file (``__code__.co_filename``, which a class cannot reassign the way it can ``__module__``);
* the lazy instance is its own defining module: ``type(m).__module__ == m.__name__ == key``;
* the instance's own ``__file__`` is a real installed file.

Residual, accepted as out of reach of a static rule: a test that makes the REAL installed
package import itself and then registers a copy of its genuine class under the SAME name is
indistinguishable from the package.  Instantiating that class for another name is rejected by
the identity above.  The third-party test is path based (a file outside the repository root):
a virtualenv inside the root makes the package look first-party, and it is reported as before.
"""

from __future__ import annotations

import types
from typing import Callable, Iterator

Predicate = Callable[[object], bool]


class _At:
    """Adapts a path string to the ``__file__``-reading predicates the guard already has."""

    def __init__(self, path: str) -> None:
        self.__file__ = path


def _functions_of(cls: type) -> Iterator[object]:
    """The functions *cls* defines itself, with static/class methods and properties unwrapped."""
    for value in vars(cls).values():
        inner = getattr(value, "__func__", None) or getattr(value, "fget", None) or value
        if isinstance(inner, types.FunctionType):
            yield inner


def _code_is_installed(cls: type, is_third_party: Predicate, has_real_file: Predicate) -> bool:
    """True when *cls* defines at least one function and every one of them lives in an installed file."""
    files = [_At(fn.__code__.co_filename) for fn in _functions_of(cls)]
    return bool(files) and all(is_third_party(f) and has_real_file(f) for f in files)


def is_installed_lazy_module(name: str, module: object, is_third_party: Predicate, has_real_file: Predicate) -> bool:
    """True when *module*, registered as *name*, is an installed package's own ``ModuleType`` subclass instance."""
    cls = type(module)
    if cls is types.ModuleType or not issubclass(cls, types.ModuleType):
        return False
    if not (cls.__module__ == getattr(module, "__name__", None) == name):
        return False
    return is_third_party(module) and has_real_file(module) and _code_is_installed(cls, is_third_party, has_real_file)
