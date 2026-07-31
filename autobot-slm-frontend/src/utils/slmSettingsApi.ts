// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * SLM settings/setup endpoints, expressed once against the canonical
 * `slmApiClient` (#13140, ADR-008 rule 3: "endpoint paths and payload types for
 * a backend live with that backend's client, not inline in the component that
 * happens to call them first").
 *
 * Before this module, five view/composable files each hand-rolled the same
 * settings transport on top of `authStore.getApiUrl()` + `getAuthHeaders()`:
 *
 *   * the base URL came from `stores/auth.ts:getApiUrl()`, which hard-returns
 *     `''` under `import.meta.env.DEV` and therefore ignores `VITE_API_URL`,
 *     while every other SLM call site resolves `getSlmApiBase()`
 *     (`VITE_API_URL + '/api'`). The two agree only while the SLM `dev` script
 *     leaves `VITE_API_URL` unset — a co-located (`/slm`) dev server silently
 *     addressed the wrong origin.
 *   * the bearer token came from the reactive `authStore.token` ref alone, with
 *     no `sessionStorage`/`localStorage` fallback, and `getAuthHeaders()`
 *     returns `{}` when that ref is null — so the request went out
 *     unauthenticated instead of failing.
 *   * a 401 was swallowed (`if (response.ok)` with no else), leaving the panel
 *     rendered with its hard-coded defaults; a subsequent "Save" then wrote
 *     those defaults over the real stored settings.
 *   * no timeout, so a hung SLM backend left the panel spinning forever.
 *
 * Routing through `slmApiClient` fixes all four in one place. `rawRequest` is
 * used wherever the caller's contract is status-code shaped (the PUT-then-POST
 * settings upsert, the "return null when absent" reads) — it is the seam that
 * applies base URL + token + timeout + the 401 session handler while still
 * handing back the `Response`, so those callers keep their existing semantics.
 */

import { slmApiClient, type RequestOptions } from '@/utils/ApiClient'
import type { components } from '@/types/generated/api'

/** `GET /api/settings` item and `GET /api/settings/{key}` body. */
export type Setting = components['schemas']['SettingResponse']
/** Body of `PUT`/`POST /api/settings/{key}`. */
export type SettingUpdate = components['schemas']['SettingUpdate']
/** `GET`/`PUT /api/settings/time/config`. */
export type TimeConfig = components['schemas']['TimeConfig']
/** `POST /api/settings/time/sync` response. */
export type TimeSyncResult = components['schemas']['TimeSyncResult']
/** `GET /api/setup/status` response. */
export type WizardStatus = components['schemas']['WizardStatus']

/** Endpoints, relative to `getSlmApiBase()` (i.e. `/api` or `/slm/api`). */
const SETTINGS = '/settings'
const TIME_CONFIG = '/settings/time/config'
const TIME_SYNC = '/settings/time/sync'
const SETUP_STATUS = '/setup/status'
const SETUP_RESET = '/setup/reset'

function settingPath(key: string): string {
  return `${SETTINGS}/${encodeURIComponent(key)}`
}

/**
 * List every stored setting. Throws on a non-OK response (the client's
 * `HTTP <status>: <detail>` error) rather than silently yielding defaults.
 */
export function listSettings(options: RequestOptions = {}): Promise<Setting[]> {
  return slmApiClient.get<Setting[]>(SETTINGS, options)
}

/**
 * Read one setting, or `null` when it does not exist / is not readable.
 * Keeps the "absent key is not an error" contract of the JSON-settings panels.
 */
export async function getSetting(key: string): Promise<Setting | null> {
  const res = await slmApiClient.rawRequest(settingPath(key))
  if (!res.ok) return null
  return (await res.json()) as Setting
}

/**
 * Upsert a setting: `PUT`, falling back to `POST` when the key does not exist
 * yet (the SLM settings API has no single upsert route). Returns whether the
 * write succeeded — the five copies this replaces all had exactly this shape.
 */
export async function upsertSetting(key: string, update: SettingUpdate): Promise<boolean> {
  const endpoint = settingPath(key)
  let res = await slmApiClient.rawRequest(endpoint, { method: 'PUT', body: update })
  if (res.status === 404) {
    res = await slmApiClient.rawRequest(endpoint, { method: 'POST', body: update })
  }
  return res.ok
}

/** Read the fleet time configuration, or `null` when it is unavailable. */
export async function getTimeConfig(): Promise<TimeConfig | null> {
  const res = await slmApiClient.rawRequest(TIME_CONFIG)
  if (!res.ok) return null
  return (await res.json()) as TimeConfig
}

/** Write the fleet time configuration. Throws on a non-OK response. */
export function putTimeConfig(config: TimeConfig): Promise<TimeConfig> {
  return slmApiClient.put<TimeConfig>(TIME_CONFIG, config)
}

/**
 * Trigger the Ansible time_sync role across fleet nodes.
 * `nodeIds === null` means "every node" (the backend's `TimeSyncRequest`).
 */
export function syncTimeToNodes(nodeIds: string[] | null = null): Promise<TimeSyncResult> {
  return slmApiClient.post<TimeSyncResult>(TIME_SYNC, { node_ids: nodeIds })
}

/** Read setup-wizard progress, or `null` when it is unavailable (non-critical). */
export async function getWizardStatus(): Promise<WizardStatus | null> {
  const res = await slmApiClient.rawRequest(SETUP_STATUS)
  if (!res.ok) return null
  return (await res.json()) as WizardStatus
}

/** Reset the setup wizard. Returns whether the reset succeeded. */
export async function resetWizard(): Promise<boolean> {
  const res = await slmApiClient.rawRequest(SETUP_RESET, { method: 'POST' })
  return res.ok
}
