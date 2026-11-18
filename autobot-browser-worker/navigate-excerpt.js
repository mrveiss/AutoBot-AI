// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
'use strict';

/**
 * The visible-text excerpt a `navigate` result carries (#21772).
 *
 * One cap, shared with the backend: AUTOBOT_BROWSER_NAVIGATE_EXCERPT_MAX_CHARS is registered once
 * (autobot_shared/env_registry_agent_tools.py) and read here and in
 * chat_workflow/browser_tool_handler.py. A missing or unusable value falls back to the same default.
 */

const DEFAULT_EXCERPT_MAX_CHARS = 1500;

/** The cap from the environment; a non-numeric or non-positive value yields the default. */
function excerptCap(env = process.env) {
  const parsed = parseInt(env.AUTOBOT_BROWSER_NAVIGATE_EXCERPT_MAX_CHARS || '', 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_EXCERPT_MAX_CHARS;
}

/** Whitespace-collapsed visible text of the page, capped; '' when the page cannot be read. */
async function pageExcerpt(page, cap = excerptCap()) {
  try {
    const text = await page.evaluate(() => (document.body ? document.body.innerText : ''));
    return String(text || '').replace(/\s+/g, ' ').trim().slice(0, cap);
  } catch (err) {
    // The excerpt is a convenience: a page that cannot be read must never fail the navigation itself.
    return '';
  }
}

module.exports = { DEFAULT_EXCERPT_MAX_CHARS, excerptCap, pageExcerpt };
