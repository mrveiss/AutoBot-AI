// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
'use strict';

const test = require('node:test');
const assert = require('node:assert');
const {
  DEFAULT_EXCERPT_MAX_CHARS,
  DEFAULT_EXCERPT_TIMEOUT_MS,
  excerptCap,
  excerptTimeoutMs,
  pageExcerpt,
} = require('../element-index');

const VAR = 'AUTOBOT_BROWSER_NAVIGATE_EXCERPT_MAX_CHARS';

test('the cap is the registered env var', () => {
  assert.strictEqual(excerptCap({ [VAR]: '200' }), 200);
});

test('a missing, non-numeric or non-positive cap falls back to the default', () => {
  for (const bad of [undefined, '', 'abc', '0', '-5']) {
    assert.strictEqual(excerptCap({ [VAR]: bad }), DEFAULT_EXCERPT_MAX_CHARS);
  }
});

test('the excerpt is whitespace-collapsed and capped', async () => {
  const page = { evaluate: async () => 'Hello \n\n  world\t again' };
  assert.strictEqual(await pageExcerpt(page, 11), 'Hello world');
});

test('a page that cannot be read gives an empty excerpt, never a thrown error', async () => {
  const page = { evaluate: async () => { throw new Error('Execution context was destroyed'); } };
  assert.strictEqual(await pageExcerpt(page, 100), '');
});

test('a read that never settles gives an empty excerpt once the deadline passes', async () => {
  const page = { evaluate: () => new Promise(() => {}) };
  assert.strictEqual(await pageExcerpt(page, 100, 20), '');
});

test('the deadline is the registered env var, with a default for a bad value', () => {
  const name = 'AUTOBOT_BROWSER_NAVIGATE_EXCERPT_TIMEOUT_MS';
  assert.strictEqual(excerptTimeoutMs({ [name]: '50' }), 50);
  assert.strictEqual(excerptTimeoutMs({ [name]: 'x' }), DEFAULT_EXCERPT_TIMEOUT_MS);
});
