// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
'use strict';

/**
 * One active page per session (#22142): history, navigate, screenshot, status and automation
 * resolve the same page. Run: node --test autobot-browser-worker/tests/session-page.test.js
 */

const test = require('node:test');
const assert = require('node:assert');
const { ensureActivePage, peekActivePage } = require('../session-page');

function fakeEntry() {
  let created = 0;
  const entry = {
    page: null,
    context: {
      newPage: async () => {
        created += 1;
        const page = { id: created, closed: false, isClosed() { return this.closed; } };
        return page;
      },
    },
  };
  return { entry, created: () => created };
}

test('every caller of one session gets the same page', async () => {
  const { entry, created } = fakeEntry();
  const history = await ensureActivePage(entry);
  const automation = await ensureActivePage(entry);
  const screenshot = await ensureActivePage(entry);
  assert.strictEqual(history, automation);
  assert.strictEqual(automation, screenshot);
  assert.strictEqual(created(), 1);
  assert.strictEqual(peekActivePage(entry), history);
});

test('a closed page is replaced once and the replacement is shared', async () => {
  const { entry, created } = fakeEntry();
  const first = await ensureActivePage(entry);
  first.closed = true;
  assert.strictEqual(peekActivePage(entry), null);
  const second = await ensureActivePage(entry);
  assert.notStrictEqual(second, first);
  assert.strictEqual(await ensureActivePage(entry), second);
  assert.strictEqual(created(), 2);
});

test('onCreate runs only for a newly created page', async () => {
  const { entry } = fakeEntry();
  const seen = [];
  await ensureActivePage(entry, async (p) => seen.push(p.id));
  await ensureActivePage(entry, async (p) => seen.push(p.id));
  assert.deepStrictEqual(seen, [1]);
});

test('peek never creates a page', () => {
  const { entry, created } = fakeEntry();
  assert.strictEqual(peekActivePage(entry), null);
  assert.strictEqual(peekActivePage(undefined), null);
  assert.strictEqual(created(), 0);
});
