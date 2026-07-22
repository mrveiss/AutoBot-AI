// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
'use strict';

/**
 * Tests for indexed interactive-element resolution backing playwright-server.js
 * (#11537 — click/fill by numbered index instead of an LLM-invented CSS
 * selector).
 *
 * Uses Node's built-in test runner, matching session-store.test.js. A fake
 * `page` object stands in for Playwright's Page — only `.evaluate()` is
 * exercised, and collectIndexedElements() doesn't care what produced the
 * array it receives.
 *
 * Run: node --test autobot-browser-worker/tests/element-index.test.js
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const { collectIndexedElements, resolveElementByIndex, DEFAULT_MAX_ELEMENTS } = require('../element-index');

function fakePage(rawElements) {
  return {
    evaluate: async (_script, _maxElements) => rawElements,
  };
}

test('collectIndexedElements assigns a stable sequential index to each element', async () => {
  const raw = [
    { role: 'button', name: 'Submit', tag: 'button', selector: 'xpath=/html/body/button[1]' },
    { role: 'textbox', name: 'Email', tag: 'input', selector: 'xpath=/html/body/input[1]' },
  ];
  const elements = await collectIndexedElements(fakePage(raw));

  assert.equal(elements.length, 2);
  assert.equal(elements[0].index, 0);
  assert.equal(elements[1].index, 1);
  assert.equal(elements[0].role, 'button');
  assert.equal(elements[1].name, 'Email');
});

test('collectIndexedElements passes the configured max element cap into page.evaluate', async () => {
  let receivedMax = null;
  const page = {
    evaluate: async (_script, maxElements) => {
      receivedMax = maxElements;
      return [];
    },
  };

  await collectIndexedElements(page, 7);
  assert.equal(receivedMax, 7);

  await collectIndexedElements(page);
  assert.equal(receivedMax, DEFAULT_MAX_ELEMENTS);
});

test('resolveElementByIndex returns the matching element for a valid index', () => {
  const elements = [
    { index: 0, role: 'button', name: 'Submit', selector: 'xpath=/html/body/button[1]' },
    { index: 1, role: 'link', name: 'Home', selector: 'xpath=/html/body/a[1]' },
  ];

  const result = resolveElementByIndex(elements, 1);
  assert.deepEqual(result, { element: elements[1] });
});

test('resolveElementByIndex rejects an out-of-range index with a descriptive error', () => {
  const elements = [{ index: 0, role: 'button', name: 'Submit', selector: 'xpath=/html/body/button[1]' }];

  const result = resolveElementByIndex(elements, 5);
  assert.ok(result.error);
  assert.match(result.error, /Index 5 out of range \(1 elements\)/);
});

test('resolveElementByIndex rejects a non-integer index without touching the DOM', () => {
  const elements = [{ index: 0, role: 'button', name: 'Submit', selector: 'xpath=/html/body/button[1]' }];

  assert.ok(resolveElementByIndex(elements, '1').error);
  assert.ok(resolveElementByIndex(elements, 1.5).error);
  assert.ok(resolveElementByIndex(elements, null).error);
  assert.ok(resolveElementByIndex(elements, undefined).error);
});

test('resolveElementByIndex on an empty element list always errors', () => {
  const result = resolveElementByIndex([], 0);
  assert.ok(result.error);
  assert.match(result.error, /0 elements/);
});

// --- Stale-index guard (review MINOR 3) ---
// A caller that fetched browser_state, then acted on an index against a page
// that changed shape in between (e.g. a modal opened/closed), must be told
// to re-fetch rather than silently clicking whatever now sits at that index.

test('resolveElementByIndex succeeds when expectedCount matches the live element count', () => {
  const elements = [
    { index: 0, role: 'button', name: 'Submit', selector: 'xpath=/html/body/button[1]' },
    { index: 1, role: 'link', name: 'Home', selector: 'xpath=/html/body/a[1]' },
  ];

  const result = resolveElementByIndex(elements, 1, 2);
  assert.deepEqual(result, { element: elements[1] });
});

test('resolveElementByIndex rejects a stale index when expectedCount no longer matches', () => {
  const elements = [{ index: 0, role: 'button', name: 'Submit', selector: 'xpath=/html/body/button[1]' }];

  const result = resolveElementByIndex(elements, 0, 5); // caller expected 5 elements, page now has 1
  assert.ok(result.error);
  assert.match(result.error, /Page changed since state was captured/);
  assert.match(result.error, /expected 5 elements, found 1/);
});

test('resolveElementByIndex skips the stale-index guard when expectedCount is omitted (backward compatible)', () => {
  const elements = [{ index: 0, role: 'button', name: 'Submit', selector: 'xpath=/html/body/button[1]' }];

  assert.deepEqual(resolveElementByIndex(elements, 0), { element: elements[0] });
  assert.deepEqual(resolveElementByIndex(elements, 0, undefined), { element: elements[0] });
  assert.deepEqual(resolveElementByIndex(elements, 0, null), { element: elements[0] });
});

test('resolveElementByIndex stale-index guard runs before the out-of-range check', () => {
  const elements = [{ index: 0, role: 'button', name: 'Submit', selector: 'xpath=/html/body/button[1]' }];

  // index 9 is out of range AND the count is stale — the clearer "page changed" error wins.
  const result = resolveElementByIndex(elements, 9, 5);
  assert.match(result.error, /Page changed since state was captured/);
});
