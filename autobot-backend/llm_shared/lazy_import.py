# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One thread-safe lazy-import primitive for heavy optional dependencies (#13049 C4).

#12714 extracted this pattern once for torch, after it had been reimplemented
across 9 modules with only one of them using double-checked locking. The
accelerate loader was missed by that round and had itself been forked twice --
``optimization/meta_eviction.py`` and ``optimization/model_inspector.py`` each
defined ``_import_accelerate()``, already drifted: one caught
``(ImportError, RuntimeError)`` and re-raised both as ``ImportError``, the other
caught ``ImportError`` alone.

Rather than add a third copy of the caching-and-locking machinery alongside
``torch_loader``, that machinery lives here once and both loaders are thin
wrappers over it. ``lazy_torch``'s public signature and behaviour are unchanged;
its 18 call sites are untouched.

THE RUNTIMEERROR RULE IS INHERITED, NOT INVENTED
-------------------------------------------------
``torch_loader`` already ruled on it: a custom ``error_message`` applies only
when the dependency is genuinely ABSENT (``ImportError``). A ``RuntimeError`` --
the library is installed but failed to initialise -- is always re-raised
unchanged, because rewording it as "install with: pip install X" would send a
reader to fix a dependency that is already there.

This changes one behaviour, deliberately and narrowly: ``meta_eviction`` used to
convert such a ``RuntimeError`` into ``ImportError``. Its public entry point
``evict_layer_to_meta`` documents ``ImportError: If quantizer is provided but
accelerate is not installed`` -- the not-installed case, which still raises
``ImportError``. Nothing catches the converted error (the only call site,
``_evict_quantized_layer``, is unguarded), so no handler changes meaning.
"""

from __future__ import annotations

import importlib
import threading
from typing import Any, Optional, Tuple, Type


class LazyModule:
    """A heavy optional dependency, imported once on first use.

    The outcome -- module or failure -- is cached for the process after the
    first attempt, so repeated calls are cheap regardless of which caller made
    the first one, and a missing dependency is not re-attempted on every call.
    """

    def __init__(
        self,
        module_name: str,
        *,
        catch: Tuple[Type[BaseException], ...] = (ImportError, RuntimeError),
    ) -> None:
        self._module_name = module_name
        self._catch = catch
        self._module: Any = None
        self._error: Optional[BaseException] = None
        self._lock = threading.Lock()

    def load(self, required: bool = True, error_message: Optional[str] = None) -> Any:
        """Return the module, importing it on first call (thread-safe).

        Args:
            required: when True (default), an unavailable dependency raises.
                When False, returns ``None`` instead.
            error_message: replaces the message when the dependency is ABSENT
                (``ImportError``). Ignored when the module loaded, and ignored
                when the failure was anything else -- see the module docstring.

        Returns:
            The imported module, or ``None`` when ``required=False`` and it
            could not be imported.
        """
        if self._module is None and self._error is None:
            with self._lock:
                # Re-checked under the lock: two threads can pass the test above
                # concurrently, which is the race #12714 found in 8 of 9 copies.
                if self._module is None and self._error is None:
                    try:
                        self._module = importlib.import_module(self._module_name)
                    except self._catch as exc:
                        self._error = exc
        if self._module is None and required:
            if error_message and isinstance(self._error, ImportError):
                raise ImportError(error_message) from self._error
            raise self._error  # noqa: B904 - re-raising the cached original
        return self._module
