# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
XHR Interceptor — captures fetch() and XMLHttpRequest network calls made by a page.

Inject the interception script before navigation, then call collect_results() after
the page interaction is complete to retrieve every captured request/response pair.

Issue #1967 — Web Pipeline Engine Phase 1.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class InterceptedRequest:
    """A single captured network request and its response.

    Ref: Issue #1967.
    """

    url: str
    method: str
    request_headers: Dict[str, str] = field(default_factory=dict)
    request_body: str | None = None
    response_status: int | None = None
    response_headers: Dict[str, str] = field(default_factory=dict)
    response_body: str | None = None
    error: str | None = None

    # Convenience helpers ------------------------------------------------

    @property
    def succeeded(self) -> bool:
        """True when a response was received without a network error."""
        return self.error is None and self.response_status is not None

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict for JSON transport."""
        return {
            "url": self.url,
            "method": self.method,
            "request_headers": self.request_headers,
            "request_body": self.request_body,
            "response_status": self.response_status,
            "response_headers": self.response_headers,
            "response_body": self.response_body,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Injected JavaScript
# ---------------------------------------------------------------------------

_INTERCEPT_JS = r"""
(() => {
  if (window.__autobotXHRCapture) return;   // idempotent — do not double-install

  window.__autobotXHRCapture = [];

  // --- fetch() interception ---
  const _origFetch = window.fetch.bind(window);
  window.fetch = async function(input, init) {
    const url    = (input instanceof Request) ? input.url : String(input);
    const method = ((init && init.method) ||
                    (input instanceof Request && input.method) ||
                    'GET').toUpperCase();
    const reqHeaders = {};
    if (init && init.headers) {
      const h = new Headers(init.headers);
      h.forEach((v, k) => { reqHeaders[k] = v; });
    }
    const reqBody = (init && init.body != null) ? String(init.body) : null;

    const entry = { url, method, request_headers: reqHeaders, request_body: reqBody,
                    response_status: null, response_headers: {}, response_body: null,
                    error: null };

    try {
      const resp = await _origFetch(input, init);
      const cloned = resp.clone();
      entry.response_status = resp.status;
      cloned.headers.forEach((v, k) => { entry.response_headers[k] = v; });
      try { entry.response_body = await cloned.text(); } catch (_) {}
      window.__autobotXHRCapture.push(entry);
      return resp;
    } catch (err) {
      entry.error = String(err);
      window.__autobotXHRCapture.push(entry);
      throw err;
    }
  };

  // --- XMLHttpRequest interception ---
  const _OrigXHR = window.XMLHttpRequest;
  function PatchedXHR() {
    const xhr  = new _OrigXHR();
    const meta = { url: '', method: 'GET', request_headers: {}, request_body: null,
                   response_status: null, response_headers: {}, response_body: null,
                   error: null };

    const _origOpen = xhr.open.bind(xhr);
    xhr.open = function(method, url, ...rest) {
      meta.method = String(method).toUpperCase();
      meta.url    = String(url);
      return _origOpen(method, url, ...rest);
    };

    const _origSetHeader = xhr.setRequestHeader.bind(xhr);
    xhr.setRequestHeader = function(name, value) {
      meta.request_headers[name] = value;
      return _origSetHeader(name, value);
    };

    const _origSend = xhr.send.bind(xhr);
    xhr.send = function(body) {
      if (body != null) meta.request_body = String(body);

      xhr.addEventListener('load', function() {
        meta.response_status = xhr.status;
        const raw = xhr.getAllResponseHeaders();
        raw.trim().split(/[\r\n]+/).forEach(line => {
          const idx = line.indexOf(':');
          if (idx > -1) {
            meta.response_headers[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
          }
        });
        try { meta.response_body = xhr.responseText; } catch (_) {}
        window.__autobotXHRCapture.push(Object.assign({}, meta));
      });

      xhr.addEventListener('error', function() {
        meta.error = 'XHR network error';
        window.__autobotXHRCapture.push(Object.assign({}, meta));
      });

      return _origSend(body);
    };

    return xhr;
  }

  // Preserve static members
  Object.setPrototypeOf(PatchedXHR, _OrigXHR);
  PatchedXHR.prototype = _OrigXHR.prototype;
  window.XMLHttpRequest = PatchedXHR;
})();
"""

# ---------------------------------------------------------------------------
# Interceptor class
# ---------------------------------------------------------------------------


class XHRInterceptor:
    """Injects a JavaScript shim into a Playwright page to capture network requests.

    Usage::

        interceptor = XHRInterceptor()
        await page.add_init_script(interceptor.generate_intercept_script())
        await page.goto(url)
        # … interact with the page …
        requests = await interceptor.collect_results(page)

    Issue #1967 — Web Pipeline Engine Phase 1.
    """

    def generate_intercept_script(self) -> str:
        """Return the JavaScript source to inject via ``page.add_init_script()``.

        The script is idempotent — safe to inject multiple times on the same page.
        It patches ``window.fetch`` and ``window.XMLHttpRequest`` to record every
        request/response pair into ``window.__autobotXHRCapture``.

        Returns:
            JS source string ready to pass to ``page.add_init_script()``.
        """
        logger.debug("Generating XHR intercept script")
        return _INTERCEPT_JS

    async def collect_results(self, page: Any) -> List[InterceptedRequest]:
        """Read captured requests from the page and return them as dataclass instances.

        This must be called *after* page interactions have completed.  The in-page
        buffer is left intact so callers can re-read it if needed.

        Args:
            page: A Playwright ``Page`` object (typed as ``Any`` to avoid a hard
                  dependency on playwright at import time).

        Returns:
            List of :class:`InterceptedRequest` objects, one per captured call.
            Returns an empty list if none were captured or on evaluation error.
        """
        try:
            raw_list = await page.evaluate("window.__autobotXHRCapture || []")
        except Exception as exc:
            logger.error("XHRInterceptor.collect_results evaluate failed: %s", exc)
            return []

        results: List[InterceptedRequest] = []
        for item in raw_list:
            if not isinstance(item, dict):
                logger.warning("XHRInterceptor: skipping non-dict capture entry: %r", item)
                continue
            req = InterceptedRequest(
                url=item.get("url", ""),
                method=item.get("method", "GET"),
                request_headers=item.get("request_headers") or {},
                request_body=item.get("request_body"),
                response_status=item.get("response_status"),
                response_headers=item.get("response_headers") or {},
                response_body=item.get("response_body"),
                error=item.get("error"),
            )
            results.append(req)

        logger.info("XHRInterceptor collected %d request(s)", len(results))
        return results
