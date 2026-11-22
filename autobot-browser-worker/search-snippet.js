// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
'use strict';

/**
 * The snippet of one search result block (#21877).
 *
 * The result loop used to hardcode the snippet to '', so the model got a title and a URL and nothing
 * to answer from. The selectors cover DuckDuckGo's two result layouts, most specific first.
 */
const SNIPPET_SELECTORS = [
  '[data-result="snippet"]',
  '[data-testid="result-snippet"]',
  '.result__snippet',
];

const DEFAULT_SNIPPET_MAX_CHARS = 500;

/** Cap on a snippet's length: AUTOBOT_BROWSER_SEARCH_SNIPPET_MAX_CHARS (registered once, in the env registry). */
function snippetCap(env = process.env) {
  const parsed = parseInt(env.AUTOBOT_BROWSER_SEARCH_SNIPPET_MAX_CHARS || '', 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_SNIPPET_MAX_CHARS;
}

/**
 * Text of the first snippet element inside a result block, whitespace-collapsed and capped.
 * A block with no snippet element, or one that cannot be read, gives '' and never throws.
 */
async function extractSnippet(resultElement, maxChars = snippetCap()) {
  for (const selector of SNIPPET_SELECTORS) {
    try {
      const node = await resultElement.$(selector);
      const text = node ? await node.textContent() : '';
      const collapsed = (text || '').replace(/\s+/g, ' ').trim();
      if (collapsed) return collapsed.slice(0, maxChars);
    } catch (e) {
      continue;
    }
  }
  return '';
}

module.exports = { SNIPPET_SELECTORS, DEFAULT_SNIPPET_MAX_CHARS, snippetCap, extractSnippet };
