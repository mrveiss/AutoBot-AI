// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
'use strict';

const test = require('node:test');
const assert = require('node:assert');
const { DEFAULT_SNIPPET_MAX_CHARS, snippetCap, extractSnippet } = require('../search-snippet');

// A result block as the worker sees it: a selector lookup that yields a node with textContent().
// The fixtures mirror the markup of the two DuckDuckGo result layouts the worker scrapes.
const block = (bySelector) => ({
  $: async (selector) =>
    selector in bySelector ? { textContent: async () => bySelector[selector] } : null,
});

const LAYOUTS = {
  script: { '[data-result="snippet"]': 'Riga: 4 C, cloudy.\n  Wind 5 m/s.' },
  testid: { '[data-testid="result-snippet"]': 'Riga: 4 C, cloudy.   Wind 5 m/s.' },
  html: { '.result__snippet': ' Riga: 4 C, cloudy. Wind 5 m/s. ' },
};

for (const [name, markup] of Object.entries(LAYOUTS)) {
  test(`the snippet is read from the ${name} result layout`, async () => {
    assert.strictEqual(await extractSnippet(block(markup)), 'Riga: 4 C, cloudy. Wind 5 m/s.');
  });
}

test('a result with no snippet element gives an empty snippet, not an exception', async () => {
  assert.strictEqual(await extractSnippet(block({})), '');
});

test('a snippet element that cannot be read gives an empty snippet', async () => {
  const broken = { $: async () => { throw new Error('detached'); } };
  assert.strictEqual(await extractSnippet(broken), '');
});

test('an empty snippet element falls through to the next selector', async () => {
  const markup = { '[data-result="snippet"]': '   ', '.result__snippet': 'real text' };
  assert.strictEqual(await extractSnippet(block(markup)), 'real text');
});

test('the snippet is capped', async () => {
  assert.strictEqual(await extractSnippet(block(LAYOUTS.html), 8), 'Riga: 4 ');
});

test('the cap is the registered env var and falls back to the default', () => {
  assert.strictEqual(snippetCap({ AUTOBOT_BROWSER_SEARCH_SNIPPET_MAX_CHARS: '120' }), 120);
  for (const bad of [undefined, '', 'abc', '0', '-1']) {
    assert.strictEqual(snippetCap({ AUTOBOT_BROWSER_SEARCH_SNIPPET_MAX_CHARS: bad }), DEFAULT_SNIPPET_MAX_CHARS);
  }
});
