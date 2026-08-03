# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical browser interface shared across AutoBot (#12651, ADR-009).

Callers state the capabilities they need; the registry picks a backend that
declares them and is currently reachable, and validates every URL with the
DNS-resolving public-address guard before any backend sees it.

    from autobot_shared.browser import Capability, NavigateRequest, get_browser

    browser = await get_browser(requires={Capability.NAVIGATE, Capability.EXTRACT_TEXT})
    page = await browser.navigate(NavigateRequest(url=url))

Ask for the content shape you need — `EXTRACT_HTML` for markup,
`EXTRACT_STRUCTURED` for parsed structure. A backend that cannot produce the
requested format is not selected, and naming a mismatched format on the
request raises rather than returning the wrong shape (#13236).

Backends are registered by the app that owns their transport — see
``registry.register_backend`` — so this package never imports an app-local
module.

Re-exports are lazy (PEP 562), matching ``autobot_shared/user_management``:
importing the package must not drag SQLAlchemy, aiohttp or Playwright into a
caller that only wanted the ``Capability`` enum. Eager imports here were what
pulled ``email_validator`` into the migration gate in #13129.
"""

_LAZY_IMPORTS = {
    "ActionRequest": (".base", "ActionRequest"),
    "BrowserBackend": (".base", "BrowserBackend"),
    "BrowserError": (".base", "BrowserError"),
    "BrowserResult": (".base", "BrowserResult"),
    "Capability": (".base", "Capability"),
    "ContentFormat": (".base", "ContentFormat"),
    "FORMAT_CAPABILITY": (".base", "FORMAT_CAPABILITY"),
    "ExtractRequest": (".base", "ExtractRequest"),
    "NavigateRequest": (".base", "NavigateRequest"),
    "NoCapableBackendError": (".base", "NoCapableBackendError"),
    "ScreenshotRequest": (".base", "ScreenshotRequest"),
    "SessionHandle": (".base", "SessionHandle"),
    "UnsafeUrlError": (".base", "UnsafeUrlError"),
    "UnsupportedFormatError": (".base", "UnsupportedFormatError"),
    "Browser": (".registry", "Browser"),
    "clear_backends": (".registry", "clear_backends"),
    "get_browser": (".registry", "get_browser"),
    "register_backend": (".registry", "register_backend"),
    "registered_backends": (".registry", "registered_backends"),
    "resolve_backend": (".registry", "resolve_backend"),
}

__all__ = list(_LAZY_IMPORTS)


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        import importlib

        module_path, attr_name = _LAZY_IMPORTS[name]
        mod = importlib.import_module(module_path, __name__)
        val = getattr(mod, attr_name)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(_LAZY_IMPORTS))
