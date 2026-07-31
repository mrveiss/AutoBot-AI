// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Request timeouts for SLM endpoints that outlive the client default (#13140).
 *
 * `slmApiClient` applies `VITE_SLM_API_TIMEOUT_MS` (30s default) to every
 * request. That budget is right for a CRUD read, but the raw `fetch` sites this
 * issue migrates had NO timeout at all, so a handful of them were relying on
 * being able to run longer than 30s. Handing those the default would abort a
 * workflow that works today — a regression dressed up as a refactor. They get
 * an explicit, named, env-sourced budget instead of a magic number at the call
 * site.
 */

/** Parse an env var as a positive integer, falling back when unset/invalid. */
function timeoutFromEnv(name: string, fallbackMs: number): number {
  const raw = import.meta.env[name]
  const parsed = raw != null && raw !== '' ? parseInt(String(raw), 10) : NaN
  return Number.isNaN(parsed) || parsed <= 0 ? fallbackMs : parsed
}

/**
 * `POST /nodes/{id}/exec` and the node connection/health probes run SSH or an
 * ansible ad-hoc command against a fleet node and block until it finishes.
 * Five minutes matches the ansible-runner ceiling these endpoints sit behind.
 */
export const REMOTE_EXEC_TIMEOUT_MS = timeoutFromEnv('VITE_SLM_REMOTE_EXEC_TIMEOUT_MS', 300_000)

/**
 * `POST /infrastructure/execute` kicks off a playbook run. The call returns as
 * soon as the execution is registered (status is then polled), but registration
 * itself involves inventory resolution on a cold cache.
 */
export const PLAYBOOK_EXECUTE_TIMEOUT_MS = timeoutFromEnv(
  'VITE_SLM_PLAYBOOK_EXEC_TIMEOUT_MS',
  120_000
)

/**
 * The WebSocket reconnect loop's liveness pre-flight (`useSlmWebSocket`). It
 * gates an exponential backoff, so it must fail FAST rather than hold the
 * reconnect timer open for the full default budget.
 */
export const HEALTH_PROBE_TIMEOUT_MS = timeoutFromEnv('VITE_SLM_HEALTH_PROBE_TIMEOUT_MS', 3_000)

/**
 * Reads issued from a polling loop must not retry: `slmApiClient.get()` retries
 * a 5xx three times with exponential backoff (~3s), which for a 1s status poll
 * means overlapping in-flight requests and a status stream that lags behind the
 * run it is reporting on. Polled reads pass this so a tick is single-shot and
 * the next tick is the retry.
 */
export const POLLED_READ_MAX_RETRIES = 1
