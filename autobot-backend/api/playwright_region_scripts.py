# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Browser-side script for the Playwright router's region snapshot (moved verbatim from ``playwright.py``).

Split out (#17576) so ``playwright.py`` stays under its recorded size ceiling while its Browser VM calls
gain the egress guard; the script is data, not router logic.
"""

# JavaScript used by snapshot_with_regions to walk the DOM and collect regions.
JS_COLLECT_REGIONS = """
() => {
  const results = [];
  const seen = new Set();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
  while (walker.nextNode()) {
    const el = walker.currentNode;
    const rect = el.getBoundingClientRect();
    const area = rect.width * rect.height;
    if (area < 20) continue;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;
    if (rect.width === 0 || rect.height === 0) continue;
    const key = `${Math.round(rect.x)},${Math.round(rect.y)},${Math.round(rect.width)},${Math.round(rect.height)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const role = el.getAttribute('role') || el.tagName.toLowerCase();
    const textPreview = (el.textContent || '').trim().slice(0, 80);
    if (!textPreview && !el.getAttribute('aria-label') && !el.getAttribute('alt')) continue;
    let selector = el.tagName.toLowerCase();
    if (el.id) selector = `#${el.id}`;
    else if (el.className && typeof el.className === 'string') {
      const cls = el.className.trim().split(/\\s+/)[0];
      if (cls) selector = `.${cls}`;
    }
    let xpath = '';
    let node = el;
    while (node && node !== document.body) {
      const tag = node.tagName.toLowerCase();
      const idx = Array.from(node.parentElement?.children || [])
        .filter(c => c.tagName === node.tagName).indexOf(node) + 1;
      xpath = `/${tag}[${idx}]${xpath}`;
      node = node.parentElement;
    }
    xpath = `/html/body${xpath}`;
    results.push({
      selector,
      xpath,
      rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height },
      textPreview: textPreview || el.getAttribute('aria-label') || el.getAttribute('alt') || '',
      role
    });
  }
  return results.slice(0, 200);
}
"""
