// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Named request timeouts for endpoints whose budget differs from the client
 * default (#13140 for the SLM backend, #13079 for the autobot backend).
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

/**
 * `GET /skills/governance/approvals` when issued from `useSkillGovernance`'s
 * approval poll (#951), which runs on a **30-second** `setInterval`.
 *
 * `useAutobotApi`'s default budget is also 30s, so a tick that ran to its
 * timeout would still be in flight as the next tick fired. The polled read gets
 * a sub-interval budget instead, so a tick is always resolved before its
 * successor starts and the next tick is the retry.
 *
 * This is NOT a preservation of the 15s that the private `axios.create` in
 * `useSkills.ts` applied to every skills call. That 15s predates the poll
 * (introduced in #731, the poll added later in #951), carries no comment, and
 * was demonstrably wrong for at least one endpoint it covered —
 * `POST /skills/repos/{id}/sync` awaits a git clone inline. Only the poll has a
 * reason for a shorter budget, so only the poll gets one.
 */
export const SKILL_APPROVAL_POLL_TIMEOUT_MS = timeoutFromEnv(
  'VITE_SKILL_APPROVAL_POLL_TIMEOUT_MS',
  10_000
)
