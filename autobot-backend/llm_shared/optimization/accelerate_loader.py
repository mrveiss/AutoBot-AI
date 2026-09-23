# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One thread-safe lazy accelerate loader for this package (#13049 C4).

``_import_accelerate()`` was defined twice in this directory --
``meta_eviction.py`` and ``model_inspector.py`` -- same package, same optional
dependency. #13049 calls them "character-for-character in intent"; they had in
fact already drifted on the part that matters. ``meta_eviction`` caught
``(ImportError, RuntimeError)`` and re-raised BOTH as ``ImportError``;
``model_inspector`` caught ``ImportError`` alone and let ``RuntimeError``
through. This is the same class of fork #12714 closed for the nine
``_get_torch()`` copies; the accelerate loader was missed by that round.

THE RAISE POLICY IS INHERITED FROM ``torch_loader``, NOT INVENTED
------------------------------------------------------------------
``llm_shared/torch_loader.py`` already ruled on the question the two copies
disagreed about: a custom ``error_message`` applies only when the dependency is
genuinely ABSENT (``ImportError``), while a ``RuntimeError`` -- installed but
failed to initialise -- is re-raised unchanged, because rewording it as
"Install with: pip install X" sends a reader to fix something already present.

That changes one behaviour, narrowly and deliberately: ``meta_eviction``'s
``RuntimeError``-to-``ImportError`` conversion is gone. Its public entry point
``evict_layer_to_meta`` documents *"ImportError: If quantizer is provided but
accelerate is not installed"* -- the not-installed case, which still raises
``ImportError``. The only call site, ``_evict_quantized_layer``, is unguarded
and nothing upstream catches it, so no handler changes meaning.

WHY IT LIVES HERE RATHER THAN BESIDE ``torch_loader``
-------------------------------------------------------
#13049 suggests "alongside the existing shared ``llm_shared.torch_loader``",
i.e. at the package root. It is here instead, next to both of its callers,
because a module at the ``llm_shared`` root is invisible to the test harness
until it is named in ``autobot-backend/conftest.py`` -- and that file sits at
EXACTLY its recorded 1505-line size ceiling on ``origin/main``, so it cannot
take another entry without raising a ceiling, which is not allowed.
``llm_shared.optimization`` is given a real ``__path__`` by that same conftest,
so a module here resolves with no registration at all.

The consequence is that the locking-and-caching machinery now exists twice --
once here and once in ``torch_loader`` -- which is a smaller duplication than
the one this closes, but a real one. Extracting it into a shared primitive
needs a conftest entry, so it is blocked on that ceiling and filed separately
rather than worked around by hiding a generic class inside ``torch_loader``.
"""

from __future__ import annotations

import threading
from typing import Any, Optional

_accelerate: Any = None
_accelerate_error: Optional[BaseException] = None
_accelerate_lock = threading.Lock()


def lazy_accelerate(required: bool = True, error_message: Optional[str] = None) -> Any:
    """Return the accelerate module, importing it on first call (thread-safe).

    The result -- module or failure -- is cached process-wide after the first
    attempt, so a missing optional dependency is not re-attempted on every call.

    Args:
        required: if True (default), an unavailable accelerate raises
            ``ImportError`` (or the original exception, re-raised). If False,
            returns ``None`` instead.
        error_message: replaces the message when accelerate is genuinely
            ABSENT, so each call site can say what it needed accelerate for.
            Ignored when accelerate imported, and ignored when the failure was
            a ``RuntimeError`` -- see the module docstring.

    Returns:
        The imported ``accelerate`` module, or ``None`` when ``required=False``
        and it could not be imported.
    """
    global _accelerate, _accelerate_error  # noqa: PLW0603
    if _accelerate is None and _accelerate_error is None:
        with _accelerate_lock:
            # Re-checked under the lock: two threads can pass the test above
            # concurrently, which is the race #12714 found in 8 of its 9 copies.
            if _accelerate is None and _accelerate_error is None:
                try:
                    import accelerate as _a  # noqa: PLC0415
                except (ImportError, RuntimeError) as exc:
                    _accelerate_error = exc
                else:
                    _accelerate = _a
    if _accelerate is None and required:
        if error_message and isinstance(_accelerate_error, ImportError):
            raise ImportError(error_message) from _accelerate_error
        raise _accelerate_error  # noqa: B904 - re-raising the cached original
    return _accelerate
