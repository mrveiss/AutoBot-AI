// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * A company's CEO designation (#15945): read, set and clear through the existing
 * `/api/llc/companies/{id}/ceo` routes. The routes own the rules (company access, and a holder
 * that must belong to this company), so this only reports what they answer.
 *
 * The designation has three states the server keeps apart and so does this: none, a holder that
 * no longer exists, and a live holder. A refusal carries its reason in the response `detail`
 * (holder does not exist / has no company recorded / belongs elsewhere); it is shown as sent.
 *
 * The view is not remounted when the route moves to another company, so a response is applied
 * only while it is still for the company shown.
 */
import { computed, ref, watch } from 'vue'
import { isHttpError } from '@autobot/ui'
import type { components } from '@/types/generated/api'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useCompanyCeo')

export type CeoDesignation = components['schemas']['CEODesignationRead']
export type CeoWrite = components['schemas']['CEODesignationWrite']
export type CeoState = 'loading' | 'failed' | 'none' | 'gone' | 'live'

export interface CeoApi {
  get<T>(url: string): Promise<T>
  put<T>(url: string, body: unknown): Promise<T>
  delete<T>(url: string): Promise<T>
}

/** The server's own reason for a refusal; null when it sent none (or the call never answered). */
export function refusalDetail(err: unknown): string | null {
  if (!isHttpError(err)) return null
  return err.detail ?? (err.message || null)
}

export interface CeoCandidate {
  value: string
  label: string
}

const SHORT_ID = 8

/**
 * The choices for a new CEO, told apart by name. Two holders that share a name would look the
 * same, so only those get their id's first characters appended; a unique name stays clean.
 * The value carries the holder type the PUT needs: `agent:<id>` or `user:<id>`.
 */
export function ceoCandidates(
  agents: ReadonlyArray<{ id: string; name: string }>,
  people: ReadonlyArray<{ user_id: string; name: string }>,
  kindLabel: (kind: 'agent' | 'user') => string,
): CeoCandidate[] {
  const all = [
    ...agents.map((a) => ({ kind: 'agent' as const, id: a.id, name: a.name })),
    ...people.map((p) => ({ kind: 'user' as const, id: p.user_id, name: p.name })),
  ]
  const seen = new Map<string, number>()
  for (const c of all) seen.set(c.name, (seen.get(c.name) ?? 0) + 1)
  return all.map((c) => {
    const base = `${c.name} (${kindLabel(c.kind)})`
    const label = (seen.get(c.name) ?? 0) > 1 ? `${base} ${c.id.slice(0, SHORT_ID)}` : base
    return { value: `${c.kind}:${c.id}`, label }
  })
}

/** Splits a candidate value back into the body the PUT expects. */
export function parseCandidate(value: string): CeoWrite | null {
  const at = value.indexOf(':')
  if (at < 0) return null
  return { holder_type: value.slice(0, at), holder_id: value.slice(at + 1) }
}

export function useCompanyCeo(api: CeoApi, companyId: () => string) {
  const designation = ref<CeoDesignation | null>(null)
  const isLoading = ref(false)
  const loadFailed = ref(false)
  const isSaving = ref(false)
  /** Why the last set/clear did not happen: the server's reason, or '' when it gave none. */
  const actionError = ref<string | null>(null)
  let generation = 0

  const url = (id: string) => `/api/llc/companies/${id}/ceo`

  const state = computed<CeoState>(() => {
    if (loadFailed.value) return 'failed'
    const d = designation.value
    if (d === null) return 'loading'
    if (!d.holder_type || !d.holder_id) return 'none'
    return d.holder_exists ? 'live' : 'gone'
  })

  async function load(): Promise<void> {
    const id = companyId()
    if (!id) return
    const mine = generation
    isLoading.value = true
    loadFailed.value = false
    try {
      const result = await api.get<CeoDesignation>(url(id))
      if (mine === generation) designation.value = result
    } catch (err) {
      logger.error('Failed to load the CEO designation', err)
      if (mine === generation) loadFailed.value = true
    } finally {
      if (mine === generation) isLoading.value = false
    }
  }

  /** Runs a write; true when the server accepted it. A refusal leaves the shown designation as it was. */
  async function write(run: (id: string) => Promise<unknown>): Promise<boolean> {
    const id = companyId()
    const mine = generation
    isSaving.value = true
    actionError.value = null
    try {
      await run(id)
      if (mine !== generation) return false
      await load()
      return true
    } catch (err) {
      logger.error('CEO designation change refused', err)
      if (mine === generation) actionError.value = refusalDetail(err) ?? ''
      return false
    } finally {
      if (mine === generation) isSaving.value = false
    }
  }

  const setCeo = (holder: CeoWrite) => write((id) => api.put(url(id), holder))
  const clearCeo = () => write((id) => api.delete(url(id)))

  watch(companyId, () => {
    generation += 1
    designation.value = null
    loadFailed.value = false
    isLoading.value = false
    isSaving.value = false
    actionError.value = null
    void load()
  })

  return { designation, state, isLoading, isSaving, actionError, load, setCeo, clearCeo }
}
