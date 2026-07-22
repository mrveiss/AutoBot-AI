// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
'use strict';

/**
 * Indexed interactive-element helpers (#11537).
 *
 * The chat LLM used to invent CSS selectors from imagination
 * (`click({"selector": "button#submit"})` against a page it cannot see).
 * OpenManus's fix — numbering every interactive element so the model picks
 * a target from a menu it can see (`click_element index=12`) — is mirrored
 * here.
 *
 * Only the browser-worker process holds the real Playwright `Page`, so
 * indexing (and resolving an index back to an actionable locator) happens
 * here rather than in `services/web_pipeline/snapshot.py` (which captures
 * the accessibility tree of a *different* Playwright subsystem —
 * `research_browser_manager`, an in-process Python page used by the
 * research/scraping-template tools, not the chat tool_handler path). The
 * two stay conceptually aligned (interactive-role filtering, stable index)
 * without literally sharing code across the Python/Node boundary.
 *
 * Kept free of any Playwright import — like session-store.js — so the
 * resolution logic can be unit tested with `node --test` and a fake `page`.
 */

const DEFAULT_MAX_ELEMENTS = parseInt(process.env.BROWSER_STATE_MAX_ELEMENTS || '50', 10);

// Executed in-page via page.evaluate(INDEX_ELEMENTS_SCRIPT, maxElements).
// Walks interactive elements in document order and builds a unique xpath
// locator per element (Playwright's `xpath=` selector prefix), so each
// returned entry is directly clickable/fillable server-side. Playwright's
// Node evaluate() accepts a function source string, matching the pattern
// already used for `_JS_COLLECT_REGIONS` in api/playwright.py.
const INDEX_ELEMENTS_SCRIPT = `(maxElements) => {
  const INTERACTIVE_SELECTOR = [
    'a[href]', 'button', 'input', 'select', 'textarea',
    '[role="button"]', '[role="link"]', '[role="checkbox"]', '[role="radio"]',
    '[role="tab"]', '[role="menuitem"]', '[role="switch"]', '[role="combobox"]',
    '[role="searchbox"]', '[role="textbox"]', '[onclick]', '[contenteditable="true"]',
  ].join(',');
  const candidates = Array.from(document.querySelectorAll(INTERACTIVE_SELECTOR));
  const results = [];
  for (const el of candidates) {
    const rect = el.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) continue;
    const style = window.getComputedStyle(el);
    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue;
    if (el.disabled) continue;
    let xpath = '';
    let node = el;
    while (node && node !== document.body) {
      const tag = node.tagName.toLowerCase();
      const siblingIndex = Array.from(node.parentElement ? node.parentElement.children : [])
        .filter((c) => c.tagName === node.tagName).indexOf(node) + 1;
      xpath = '/' + tag + '[' + siblingIndex + ']' + xpath;
      node = node.parentElement;
    }
    xpath = '/html/body' + xpath;
    const role = el.getAttribute('role') || el.tagName.toLowerCase();
    const name = (el.textContent || '').trim().slice(0, 120)
      || el.getAttribute('aria-label') || el.getAttribute('placeholder')
      || el.getAttribute('value') || el.getAttribute('alt') || '';
    results.push({ role, name, tag: el.tagName.toLowerCase(), selector: 'xpath=' + xpath });
    if (results.length >= maxElements) break;
  }
  return results;
}`;

/**
 * Capture the numbered interactive-element menu for `page`.
 * @param {object} page - Playwright Page (or a test double exposing `.evaluate`).
 * @param {number} [maxElements]
 * @returns {Promise<Array<{index:number, role:string, name:string, tag:string, selector:string}>>}
 */
async function collectIndexedElements(page, maxElements = DEFAULT_MAX_ELEMENTS) {
  const elements = await page.evaluate(INDEX_ELEMENTS_SCRIPT, maxElements);
  return elements.map((el, index) => ({ index, ...el }));
}

/**
 * Resolve an `index` param against a previously-collected element list.
 * Pure/no I/O — this is what "resolved server-side" means for click_index /
 * fill_index / select_index / hover_index: the index never reaches the DOM
 * directly, it is translated to a concrete locator here first.
 *
 * @param {Array<object>} elements - Result of collectIndexedElements().
 * @param {*} index - The raw `index` param from the tool call.
 * @returns {{element:object}|{error:string}}
 */
function resolveElementByIndex(elements, index) {
  if (typeof index !== 'number' || !Number.isInteger(index)) {
    return { error: 'index must be an integer' };
  }
  const target = elements[index];
  if (!target) {
    return { error: `Index ${index} out of range (${elements.length} elements)` };
  }
  return { element: target };
}

module.exports = {
  DEFAULT_MAX_ELEMENTS,
  INDEX_ELEMENTS_SCRIPT,
  collectIndexedElements,
  resolveElementByIndex,
};
