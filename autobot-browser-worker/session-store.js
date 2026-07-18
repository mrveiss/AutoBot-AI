// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
'use strict';

/**
 * Per-session resource store with idle-based garbage collection.
 *
 * GH#11539: the browser worker previously held a single global page shared by
 * every conversation/user, so cookies and login state bled across
 * conversations. This store keys one resource (a Playwright BrowserContext,
 * in playwright-server.js) per session_id so each conversation gets its own
 * isolated cookie jar / localStorage / auth state.
 *
 * Mirrors the idle-GC pattern in
 * autobot-backend/services/docker_task_workspace.py: an env-var-driven idle
 * timeout constant plus a gc pass that destroys resources idle longer than
 * that timeout. Kept free of any Playwright dependency so the
 * creation/reuse/eviction semantics can be unit tested without a browser.
 */

const DEFAULT_SESSION_ID = 'default';

// Env-configurable idle timeout — never hardcode the TTL (repo convention).
const DEFAULT_IDLE_TIMEOUT_MS = parseInt(process.env.BROWSER_SESSION_IDLE_TIMEOUT_MS || String(30 * 60 * 1000), 10);

class SessionStore {
  /**
   * @param {object} [opts]
   * @param {number} [opts.idleTimeoutMs] - evict entries idle longer than this (ms)
   * @param {() => number} [opts.now] - clock injection point for tests
   */
  constructor(opts = {}) {
    this._idleTimeoutMs = opts.idleTimeoutMs ?? DEFAULT_IDLE_TIMEOUT_MS;
    this._now = opts.now || (() => Date.now());
    this._entries = new Map(); // sessionId -> { value, lastActivity }
  }

  /** Normalize an incoming session id — falsy/blank input maps to DEFAULT_SESSION_ID
   * so a lone caller with no session_id keeps today's single-session behavior. */
  static resolveSessionId(rawId) {
    return rawId && String(rawId).trim() ? String(rawId).trim() : DEFAULT_SESSION_ID;
  }

  /** Return the current value for sessionId without touching its idle timer, or null. */
  peek(sessionId) {
    const entry = this._entries.get(sessionId);
    return entry ? entry.value : null;
  }

  has(sessionId) {
    return this._entries.has(sessionId);
  }

  /**
   * Get the value for sessionId, creating it via `await createFn()` if absent.
   * Always refreshes the idle timer (touch-on-access), matching the
   * "active session never GC'd mid-conversation" requirement.
   */
  async getOrCreate(sessionId, createFn) {
    let entry = this._entries.get(sessionId);
    if (!entry) {
      const value = await createFn();
      entry = { value, lastActivity: this._now() };
      this._entries.set(sessionId, entry);
    } else {
      entry.lastActivity = this._now();
    }
    return entry.value;
  }

  /** Refresh the idle timer for an existing session without creating one. */
  touch(sessionId) {
    const entry = this._entries.get(sessionId);
    if (entry) entry.lastActivity = this._now();
  }

  delete(sessionId) {
    this._entries.delete(sessionId);
  }

  ids() {
    return Array.from(this._entries.keys());
  }

  size() {
    return this._entries.size;
  }

  /**
   * Evict entries idle longer than idleTimeoutMs, awaiting
   * `closeFn(value, sessionId)` for each eviction. A `closeFn` rejection is
   * reported via `onError(sessionId, error)` (if provided) rather than being
   * swallowed or aborting the remaining evictions; without `onError` it
   * rethrows on the first failure.
   *
   * Returns the list of evicted session ids.
   */
  async gcIdle(closeFn, onError) {
    const cutoff = this._now() - this._idleTimeoutMs;
    const candidateIds = [];
    for (const [sessionId, entry] of this._entries.entries()) {
      if (entry.lastActivity < cutoff) {
        candidateIds.push(sessionId);
      }
    }
    const evicted = [];
    for (const sessionId of candidateIds) {
      // Re-check right before evicting: a live request may have touched (or
      // recreated) this session between the scan above and here, or while
      // this loop was awaiting an earlier entry's closeFn — don't close a
      // session out from under it.
      const entry = this._entries.get(sessionId);
      if (!entry || !(entry.lastActivity < cutoff)) {
        continue;
      }
      this._entries.delete(sessionId);
      evicted.push(sessionId);
      try {
        await closeFn(entry.value, sessionId);
      } catch (err) {
        if (onError) {
          onError(sessionId, err);
        } else {
          throw err;
        }
      }
    }
    return evicted;
  }
}

module.exports = { SessionStore, DEFAULT_SESSION_ID, DEFAULT_IDLE_TIMEOUT_MS };
