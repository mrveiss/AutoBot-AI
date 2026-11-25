// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
'use strict';

/**
 * The one active page of a browser session (#22142).
 *
 * The worker used to keep two pages per session: `navPage` (/navigate, /back, /forward, /reload,
 * /screenshot, /status) and `mcpPage` (/automation, /state). A caller that navigated through the
 * MCP route and then went Back or Refresh acted on a different page from the one it was looking
 * at. Every route now resolves the session's page here, so history, navigate, screenshot, status
 * and automation all act on the same page.
 */

async function ensureActivePage(entry, onCreate) {
  if (!entry.page || entry.page.isClosed()) {
    entry.page = await entry.context.newPage();
    if (onCreate) await onCreate(entry.page);
  }
  return entry.page;
}

/** The session's page when it exists and is open, else null (never creates one). */
function peekActivePage(entry) {
  return entry && entry.page && !entry.page.isClosed() ? entry.page : null;
}

module.exports = { ensureActivePage, peekActivePage };
