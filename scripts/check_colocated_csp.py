#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Static CSP-conformance check for the user frontend under the strict
co-located Content-Security-Policy (#10023, catches the #9966 class).

On co-located deployments the user frontend is served behind the SLM nginx
strict header set (autobot-security-headers-strict.conf.j2, #7737/#9933).
This script parses the CSP from that template (single source of truth) and
scans a BUILT frontend dist directory for content the policy would block:

  * inline <script> without src      -> blocked by script-src 'self'
  * external script/stylesheet URLs  -> blocked by script-src / style-src
  * @import / url(http...) in CSS    -> blocked by style-src / font-src
  * data: fonts in CSS               -> blocked when font-src lacks data:

Exit code 0 = conformant, 1 = violations found, 2 = usage/parse error.
Stdlib-only so it runs on a bare CI runner.
"""

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

CSP_RE = re.compile(r'Content-Security-Policy\s+"([^"]+)"')
EXTERNAL_URL_RE = re.compile(r"""url\(\s*['"]?(https?:)?//""", re.IGNORECASE)
CSS_IMPORT_RE = re.compile(r"""@import\s+(?:url\(\s*)?['"]?(https?:)?//""", re.IGNORECASE)
DATA_FONT_RE = re.compile(r"""url\(\s*['"]?data:(?:font|application/(?:x-)?font)""", re.IGNORECASE)


def parse_csp(template_path: Path) -> dict[str, list[str]]:
    """Extract the CSP directive map from the nginx header template."""
    match = CSP_RE.search(template_path.read_text(encoding="utf-8"))
    if not match:
        sys.exit(f"ERROR: no Content-Security-Policy header found in {template_path}")
    directives: dict[str, list[str]] = {}
    for chunk in match.group(1).split(";"):
        tokens = chunk.strip().split()
        if tokens:
            directives[tokens[0]] = tokens[1:]
    return directives


def _is_external(url: str) -> bool:
    url = url.strip().lower()
    return url.startswith(("http://", "https://", "//"))


class _IndexHtmlScanner(HTMLParser):
    """Collect CSP-relevant facts from index.html."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.inline_scripts: list[int] = []  # line numbers of inline <script>
        self.external_scripts: list[str] = []
        self.external_styles: list[str] = []
        self._in_script_without_src = False
        self._script_line = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        attr_map = dict(attrs)
        if tag == "script":
            src = attr_map.get("src")
            if src is None:
                self._in_script_without_src = True
                self._script_line = self.getpos()[0]
            elif _is_external(src):
                self.external_scripts.append(src)
        elif tag == "link":
            rel = (attr_map.get("rel") or "").lower()
            href = attr_map.get("href") or ""
            if rel in ("stylesheet", "preload") and _is_external(href):
                self.external_styles.append(href)

    def handle_data(self, data: str) -> None:
        if self._in_script_without_src and data.strip():
            self.inline_scripts.append(self._script_line)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_script_without_src = False


def check_index_html(path: Path, csp: dict[str, list[str]]) -> list[str]:
    """Return violations the strict CSP would raise for index.html."""
    scanner = _IndexHtmlScanner()
    scanner.feed(path.read_text(encoding="utf-8"))
    violations = []
    script_src = csp.get("script-src", csp.get("default-src", []))
    if "'unsafe-inline'" not in script_src:
        for line in scanner.inline_scripts:
            violations.append(f"{path}:{line}: inline <script> blocked by script-src {' '.join(script_src)}")
    for src in scanner.external_scripts:
        violations.append(f"{path}: external script '{src}' blocked by script-src 'self'")
    for href in scanner.external_styles:
        violations.append(f"{path}: external stylesheet '{href}' blocked by style-src 'self'")
    return violations


def check_css_file(path: Path, csp: dict[str, list[str]]) -> list[str]:
    """Return violations the strict CSP would raise for one built CSS file."""
    text = path.read_text(encoding="utf-8", errors="replace")
    violations = []
    if CSS_IMPORT_RE.search(text):
        violations.append(f"{path}: external @import blocked by style-src 'self'")
    elif EXTERNAL_URL_RE.search(text):
        violations.append(f"{path}: external url(...) blocked by style-src/font-src 'self'")
    font_src = csp.get("font-src", csp.get("default-src", []))
    if "data:" not in font_src and DATA_FONT_RE.search(text):
        violations.append(f"{path}: data: font blocked by font-src {' '.join(font_src)}")
    return violations


def scan_dist(dist: Path, csp: dict[str, list[str]]) -> list[str]:
    """Scan the built user-frontend dist (excluding the /slm SLM-UI subtree)."""
    slm_subtree = dist / "slm"
    violations = []
    index_html = dist / "index.html"
    if not index_html.is_file():
        sys.exit(f"ERROR: {index_html} not found — is --dist a built frontend?")
    violations += check_index_html(index_html, csp)
    for css in sorted(dist.rglob("*.css")):
        if slm_subtree in css.parents:
            continue
        violations += check_css_file(css, csp)
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csp-template", required=True, type=Path, help="nginx strict-headers template containing the CSP"
    )
    parser.add_argument("--dist", required=True, type=Path, help="built user-frontend dist directory")
    args = parser.parse_args()

    csp = parse_csp(args.csp_template)
    print(f"Strict co-located CSP: {'; '.join(k + ' ' + ' '.join(v) for k, v in csp.items())}")
    violations = scan_dist(args.dist, csp)
    if violations:
        print(
            f"\nFAIL: {len(violations)} CSP violation(s) — user frontend would break "
            "under the strict co-located CSP (#9966 class):"
        )
        for v in violations:
            print(f"  - {v}")
        return 1
    print("OK: user frontend conforms to the strict co-located CSP")
    return 0


if __name__ == "__main__":
    sys.exit(main())
