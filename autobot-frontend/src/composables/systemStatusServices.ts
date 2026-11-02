// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The service rows behind the System status panel (#18353): the two
 * service-monitor probes, the /api/health confirmation, and the keyed rows they
 * produce. Split from useSystemStatus.ts, which keeps the reactive state.
 *
 * A row carries i18n KEYS, never display text: useSystemStatus translates them
 * when it renders, so a language switch relabels the panel at once rather than
 * at the next poll. Text the backend sends that is not in its known vocabulary
 * (an exception message, an unknown service) passes through as `raw`.
 */

import apiEndpointMapper from '@/utils/ApiEndpointMapper.js'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'

const logger = createLogger('systemStatusServices')

// GH#12866: budget for the /api/health confirmation probe -- only has to tell
// "not answering" from "answering slowly".
const BACKEND_HEALTH_TIMEOUT_MS = 3000

// GH#12866: budget for the two service-monitor probes. 12s clears the measured
// p90 (12s on an idle, GIL-starved host) and still lands inside the 15s poll.
const STATUS_PROBE_TIMEOUT_MS = 12000

export type ServiceHealthStatus = 'healthy' | 'warning' | 'error'

/** An i18n key with its params, or backend text with no key to translate it. */
export type LocalText = { key: string; params?: Record<string, string | number> } | { raw: string }

/** One keyed row; useSystemStatus renders it into a SystemService. */
export interface ServiceRow {
  /** Stable identity: dedup key and list key, never shown. */
  id: string
  label: LocalText
  status: ServiceHealthStatus
  text: LocalText
  /** GH#12866: carried over from the last good poll, shown "(last known)". */
  lastKnown?: boolean
}

/** Response-like object from apiEndpointMapper.fetchWithFallback(). */
export interface FallbackResponse extends Response {
  fallback?: boolean
}

interface VmEntry { name: string; status: string; message?: string }
interface BackendServiceEntry { status: string; health?: string }
interface VmStatusResponse { vms?: VmEntry[] }
interface ServicesResponse { services?: Record<string, BackendServiceEntry> }

/** Service ids the panel names itself (`systemStatus.service.<id>`). */
const SERVICE_IDS = new Set(['backend', 'frontend', 'websocket', 'redis', 'ollama', 'npu_worker', 'browser', 'chromadb', 'other'])

/**
 * /service-monitor/vms/status names rows in English (autobot-backend/api/
 * service_monitor.py); map them onto the ids /service-monitor/services keys
 * by, so the two probes' rows dedupe and both translate (#10285).
 */
const VM_NAME_IDS: Record<string, string> = {
  'Backend API': 'backend',
  Redis: 'redis',
  'NPU Worker': 'npu_worker',
  'Browser Service': 'browser',
  'AI Stack (ChromaDB)': 'chromadb',
}

/**
 * The backend's status/health vocabulary (service_monitor.py) -> keys. Words
 * the shared `status.*` namespace already names go there; the rest are
 * `systemStatus.state.*`. Anything else is shown as sent.
 */
const SHARED_STATES = new Set(['online', 'offline', 'connected', 'disconnected', 'healthy', 'degraded', 'error'])
const OWN_STATES: Record<string, string> = {
  running: 'running',
  timeout: 'timeout',
  'connection refused': 'connectionRefused',
  unreachable: 'unreachable',
  unhealthy: 'unhealthy',
  warning: 'warning',
  pending: 'pending',
  up: 'online',
  down: 'offline',
  available: 'available',
  unavailable: 'unavailable',
}

/** Map any raw backend/VM status string to a display status (#2076). */
export function toHealthStatus(raw: string): ServiceHealthStatus {
  const normalized = raw.toLowerCase()
  if (['healthy', 'online', 'up', 'running', 'available', 'connected'].includes(normalized)) return 'healthy'
  if (['degraded', 'warning', 'pending'].includes(normalized)) return 'warning'
  return 'error'
}

/** The label for a service id: a key when the panel knows it, else the id itself. */
export function serviceLabel(id: string): LocalText {
  return SERVICE_IDS.has(id) ? { key: `systemStatus.service.${id}` } : { raw: id }
}

/** Translate a backend status word or message when its vocabulary is known. */
export function stateText(raw: string): LocalText {
  const normalized = raw.trim().toLowerCase()
  if (SHARED_STATES.has(normalized)) return { key: `status.${normalized}` }
  if (normalized in OWN_STATES) return { key: `systemStatus.state.${OWN_STATES[normalized]}` }
  const http = /^http (\d{3})$/.exec(normalized)
  if (http) return { key: 'systemStatus.state.http', params: { code: http[1] } }
  return { raw }
}

/** A row for a service the panel names, in a known state. */
export function row(id: string, status: ServiceHealthStatus, state: string): ServiceRow {
  return { id, label: serviceLabel(id), status, text: { key: `systemStatus.state.${state}` } }
}

/** Rows that are healthy whenever this page is running at all. */
export const CLIENT_ROWS: readonly ServiceRow[] = [row('frontend', 'healthy', 'connected'), row('websocket', 'healthy', 'connected')]

export const DEFAULT_ROWS: readonly ServiceRow[] = [
  row('backend', 'healthy', 'running'),
  ...CLIENT_ROWS,
  row('redis', 'healthy', 'connected'),
  row('ollama', 'healthy', 'connected'),
  row('npu_worker', 'healthy', 'running'),
  row('browser', 'healthy', 'running'),
]

export async function isBackendReachable(): Promise<boolean> {
  try {
    const res = (await apiEndpointMapper.fetchWithFallback(`${getApiBase()}/health`, {
      timeout: BACKEND_HEALTH_TIMEOUT_MS,
    })) as FallbackResponse
    return Boolean(res?.ok) && !res?.fallback
  } catch {
    return false
  }
}

async function probe<T>(path: string): Promise<[T, boolean]> {
  const res = (await apiEndpointMapper.fetchWithFallback(`${getApiBase()}${path}`, {
    timeout: STATUS_PROBE_TIMEOUT_MS,
  })) as FallbackResponse
  return [(await res.json()) as T, Boolean(res.fallback)]
}

export async function fetchVmStatus(): Promise<[ServiceRow[], boolean]> {
  try {
    const [data, fellBack] = await probe<VmStatusResponse>('/service-monitor/vms/status')
    const rows = (data.vms ?? []).map((vm): ServiceRow => {
      const id = VM_NAME_IDS[vm.name] ?? vm.name
      return { id, label: serviceLabel(id), status: toHealthStatus(vm.status), text: stateText(vm.message || vm.status) }
    })
    return [rows, fellBack]
  } catch (err: unknown) {
    logger.warn('Infrastructure endpoint failed:', err instanceof Error ? err.message : String(err))
    return [['backend', 'npu_worker', 'redis'].map((id) => row(id, 'warning', 'statusUnknown')), true]
  }
}

export async function fetchServiceStatus(): Promise<[ServiceRow[], boolean]> {
  try {
    const [data, fellBack] = await probe<ServicesResponse>('/service-monitor/services')
    const rows = Object.entries(data.services ?? {}).map(([id, svc]): ServiceRow => ({
      id,
      label: serviceLabel(id),
      status: toHealthStatus(svc.status),
      text: stateText(svc.health || svc.status),
    }))
    return [rows, fellBack]
  } catch (err: unknown) {
    logger.warn('Services endpoint failed:', err instanceof Error ? err.message : String(err))
    return [['ollama', 'browser'].map((id) => row(id, 'warning', 'statusUnknown')), true]
  }
}

/** `HH:MM` in the viewer's locale, for the "as of" stamp. */
function asOf(at: Date): string {
  return at.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

/**
 * GH#12866: why the backend row is amber -- the probes timed out while
 * /api/health answered (degraded), or nothing answered (unreachable) -- and
 * the time of the last good poll, if there was one.
 */
export function probeFailureRow(reachable: boolean, at: Date | null): ServiceRow {
  const kind = reachable ? 'degraded' : 'unreachable'
  const text: LocalText = at
    ? { key: `systemStatus.probe.${kind}AsOf`, params: { time: asOf(at) } }
    : { key: `systemStatus.probe.${kind}` }
  return { id: 'backend', label: serviceLabel('backend'), status: 'warning', text }
}

/** GH#12866: the last good poll's rows, amber and marked as last known. */
export function staleCopyOf(previous: ServiceRow[] | null): ServiceRow[] {
  if (!previous) return []
  return previous
    .filter((s) => !['backend', 'frontend', 'websocket'].includes(s.id))
    .map((s) => ({ ...s, status: 'warning' as const, lastKnown: true }))
}

/** One row per service id; a healthy report wins over an unhealthy duplicate. */
export function deduplicateServices(rows: ServiceRow[]): ServiceRow[] {
  return rows.reduce<ServiceRow[]>((acc, r) => {
    const existing = acc.find((s) => s.id === r.id)
    if (!existing) acc.push({ ...r })
    else if (r.status === 'healthy' && existing.status !== 'healthy') Object.assign(existing, r)
    return acc
  }, [])
}
