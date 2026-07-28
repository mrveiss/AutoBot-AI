// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
'use strict';

/**
 * Tests for the per-session context store backing playwright-server.js
 * (#11539 — browser worker no longer shares one page/context across every
 * conversation).
 *
 * Uses Node's built-in test runner (`node --test`) so this suite has zero
 * dependency on Playwright / @playwright/test, neither of which is
 * installed in every environment this worker's logic is exercised in. The
 * store itself has no Playwright dependency either — real BrowserContext
 * objects are swapped for plain mock objects with a `cookies` Map, which is
 * enough to prove the isolation and GC contracts playwright-server.js
 * relies on.
 *
 * Run: node --test autobot-browser-worker/tests/session-store.test.js
 */

const test = require('node:test');
const assert = require('node:assert/strict');
const { SessionStore, DEFAULT_SESSION_ID } = require('../session-store');

test('resolveSessionId falls back to DEFAULT_SESSION_ID for blank/missing input', () => {
  assert.equal(SessionStore.resolveSessionId(undefined), DEFAULT_SESSION_ID);
  assert.equal(SessionStore.resolveSessionId(null), DEFAULT_SESSION_ID);
  assert.equal(SessionStore.resolveSessionId(''), DEFAULT_SESSION_ID);
  assert.equal(SessionStore.resolveSessionId('   '), DEFAULT_SESSION_ID);
  assert.equal(SessionStore.resolveSessionId('conversation-123'), 'conversation-123');
  assert.equal(SessionStore.resolveSessionId('  conversation-123  '), 'conversation-123');
});

test('getOrCreate reuses the same context for a lone/repeat session_id (backward compatible)', async () => {
  const store = new SessionStore({ idleTimeoutMs: 60000 });
  let created = 0;
  const makeContext = () => {
    created += 1;
    return { id: created, cookies: new Map() };
  };

  const first = await store.getOrCreate(DEFAULT_SESSION_ID, makeContext);
  const second = await store.getOrCreate(DEFAULT_SESSION_ID, makeContext);

  assert.equal(created, 1, 'a single default-session caller must not create a second context');
  assert.strictEqual(first, second);
});

test('getOrCreate gives distinct session_ids distinct contexts', async () => {
  const store = new SessionStore({ idleTimeoutMs: 60000 });
  let created = 0;
  const makeContext = () => {
    created += 1;
    return { id: created, cookies: new Map() };
  };

  const ctxA = await store.getOrCreate('conversation-A', makeContext);
  const ctxB = await store.getOrCreate('conversation-B', makeContext);

  assert.equal(created, 2);
  assert.notStrictEqual(ctxA, ctxB);
});

test('SECURITY (#11539): a cookie set in one conversation is absent from another', async () => {
  const store = new SessionStore({ idleTimeoutMs: 60000 });
  const makeContext = () => ({ cookies: new Map() });

  // Conversation A logs in to a site — a real BrowserContext would store this
  // in its cookie jar; here the mock's `cookies` Map stands in for that jar.
  const contextA = await store.getOrCreate('conversation-A', makeContext);
  contextA.cookies.set('session_token', 'A-secret-auth-token');

  // Conversation B (a different — possibly different-user — chat session)
  // gets its own context and must never see A's cookie jar.
  const contextB = await store.getOrCreate('conversation-B', makeContext);

  assert.equal(contextB.cookies.has('session_token'), false, "B's cookie jar must not contain A's cookie");
  assert.equal(contextA.cookies.get('session_token'), 'A-secret-auth-token');

  // A second call in conversation A (e.g. the next tool call in the same
  // chat turn) must return the SAME jar, so the login state persists within
  // the conversation.
  const contextAAgain = await store.getOrCreate('conversation-A', makeContext);
  assert.equal(contextAAgain.cookies.get('session_token'), 'A-secret-auth-token');
});

test('touch() refreshes the idle timer so an active session survives gcIdle', async () => {
  let now = 0;
  const store = new SessionStore({ idleTimeoutMs: 100, now: () => now });
  await store.getOrCreate('active', async () => ({}));

  now += 80;
  store.touch('active');
  now += 80; // 160ms since creation, but only 80ms since the touch

  const evicted = await store.gcIdle(async () => {});
  assert.deepEqual(evicted, []);
  assert.equal(store.has('active'), true);
});

test('gcIdle evicts only entries idle past the timeout, closing them via closeFn (mirrors docker_task_workspace.py idle-GC)', async () => {
  let now = 1_000_000;
  const store = new SessionStore({ idleTimeoutMs: 1000, now: () => now });
  const closed = [];
  const closeFn = async (_value, sessionId) => {
    closed.push(sessionId);
  };

  await store.getOrCreate('stale', async () => ({}));
  now += 500;
  await store.getOrCreate('fresh', async () => ({}));
  now += 600; // stale: 1100ms idle (evicted); fresh: 600ms idle (kept)

  const evicted = await store.gcIdle(closeFn);

  assert.deepEqual(evicted, ['stale']);
  assert.deepEqual(closed, ['stale']);
  assert.equal(store.has('stale'), false);
  assert.equal(store.has('fresh'), true);
});

test("gcIdle re-checks lastActivity before evicting — a session touched during an earlier entry's closeFn await survives (review fix)", async () => {
  let now = 0;
  const store = new SessionStore({ idleTimeoutMs: 100, now: () => now });

  await store.getOrCreate('first', async () => ({}));
  await store.getOrCreate('second', async () => ({}));
  now += 200; // both idle past the 100ms timeout at gcIdle-call time

  const closed = [];
  const closeFn = async (_value, sessionId) => {
    if (sessionId === 'first') {
      // Simulate a live request arriving for `second` while `first`'s close
      // is still in flight — it must not be evicted out from under it.
      now += 10;
      store.touch('second');
    }
    closed.push(sessionId);
  };

  const evicted = await store.gcIdle(closeFn);

  assert.deepEqual(evicted, ['first']);
  assert.deepEqual(closed, ['first']);
  assert.equal(store.has('first'), false);
  assert.equal(store.has('second'), true, 'second must survive — it was touched mid-GC');
});

test('gcIdle surfaces close failures via onError instead of swallowing them or aborting other evictions', async () => {
  let now = 0;
  const store = new SessionStore({ idleTimeoutMs: 10, now: () => now });
  await store.getOrCreate('bad', async () => ({}));
  await store.getOrCreate('good', async () => ({}));
  now += 100;

  const errors = [];
  const closeFn = async (_value, sessionId) => {
    if (sessionId === 'bad') throw new Error('boom');
  };
  const evicted = await store.gcIdle(closeFn, (sessionId, err) => errors.push([sessionId, err.message]));

  assert.deepEqual(evicted.sort(), ['bad', 'good']);
  assert.deepEqual(errors, [['bad', 'boom']]);
  assert.equal(store.has('bad'), false);
  assert.equal(store.has('good'), false);
});

test('gcIdle without onError rethrows on a close failure', async () => {
  let now = 0;
  const store = new SessionStore({ idleTimeoutMs: 10, now: () => now });
  await store.getOrCreate('bad', async () => ({}));
  now += 100;

  const closeFn = async () => {
    throw new Error('boom');
  };
  await assert.rejects(() => store.gcIdle(closeFn), /boom/);
});
