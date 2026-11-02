// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The Handbook's generated reference pages (#18431). One page per role, workflow, process and
 * meta skill, read from the company model's own routes -- there is no copy of any of it, so a
 * new role, workflow or process has a page the next time the screen loads.
 *
 * Each source carries its own state: a source that could not be read is `error`, which is not the
 * same answer as "the company has none". A page's detail is read when the page is opened, and
 * each part of it that fails is named so the page never shows a gap as an empty list.
 */
import { computed, ref, type Ref } from 'vue'
import { useApiClient } from '@/plugins/api'
import { describeApiError } from '@/composables/llc/apiErrorMessage'
import type { components } from '@/types/generated/api'

type Schemas = components['schemas']
export type HandbookRole = Schemas['CompanyRoleResponse']
export type HandbookWorkflow = Schemas['CompanyWorkflowResponse']
export type HandbookProcess = Schemas['ProcessResponse']
export type HandbookGraph = Schemas['GraphResponse']
export type HandbookSkills = Schemas['RoleSkillsResponse']
export type HandbookHolder = Schemas['HolderResponse']

export type PageKind = 'role' | 'workflow' | 'process' | 'metaSkill'
export type SourceState = 'loading' | 'ready' | 'error'

export interface HandbookPage {
  id: string
  kind: PageKind
  title: string
  ownerRoleId: string | null
  /** The description the company model records, or null when it records none. */
  description: string | null
}

/** What was read for the open page; `failed` names every part that could not be. */
export interface PageDetail {
  state: SourceState
  holders: HandbookHolder[]
  workflowIds: string[]
  tools: string[]
  skills: HandbookSkills | null
  graph: HandbookGraph | null
  failed: string[]
}

const ROOT = '/api/llc/company-os'

function emptyDetail(state: SourceState): PageDetail {
  return { state, holders: [], workflowIds: [], tools: [], skills: null, graph: null, failed: [] }
}

function toPages(roles: HandbookRole[], workflows: HandbookWorkflow[], processes: HandbookProcess[]): HandbookPage[] {
  return [
    ...roles.map((r) => ({ id: r.id, kind: 'role' as const, title: r.name, ownerRoleId: null, description: r.description?.trim() || null })),
    ...workflows.map((w) => ({
      id: w.workflow_id,
      kind: w.kind === 'meta_skill' ? ('metaSkill' as const) : ('workflow' as const),
      title: w.name || w.workflow_id,
      ownerRoleId: w.owner_role_id,
      description: null,
    })),
    ...processes.map((p) => ({
      id: p.process_key,
      kind: 'process' as const,
      title: p.name,
      ownerRoleId: p.owner_role_id,
      description: p.description?.trim() || null,
    })),
  ]
}

export function useHandbook(companyId: () => string) {
  const api = useApiClient()
  const roles: Ref<HandbookRole[]> = ref([])
  const workflows: Ref<HandbookWorkflow[]> = ref([])
  const processes: Ref<HandbookProcess[]> = ref([])
  const sources: Ref<Record<'roles' | 'workflows' | 'processes', SourceState>> = ref({ roles: 'loading', workflows: 'loading', processes: 'loading' })
  const errors: Ref<string[]> = ref([])
  const detail: Ref<PageDetail> = ref(emptyDetail('loading'))
  /** Opening another page while one is still being read drops the older answer. */
  let opened = 0

  const pages = computed(() => toPages(roles.value, workflows.value, processes.value))
  const roleName = (id: string | null): string => roles.value.find((r) => r.id === id)?.name ?? ''
  const workflowName = (id: string): string => workflows.value.find((w) => w.workflow_id === id)?.name || id
  const processName = (key: string): string => processes.value.find((p) => p.process_key === key)?.name || key

  async function pull(name: 'roles' | 'workflows' | 'processes', url: string, into: Ref<unknown[]>): Promise<void> {
    sources.value[name] = 'loading'
    try {
      const rows: unknown[] = await api.get(url)
      into.value = rows ?? []
      sources.value[name] = 'ready'
    } catch (err: unknown) {
      into.value = []
      sources.value[name] = 'error'
      errors.value.push(describeApiError(err, name))
    }
  }

  async function load(): Promise<void> {
    errors.value = []
    if (!companyId()) return
    await Promise.all([
      pull('roles', `/api/llc/roles/${companyId()}`, roles),
      pull('workflows', `${ROOT}/workflows`, workflows),
      pull('processes', `${ROOT}/processes`, processes),
    ])
  }

  async function part<T>(failed: string[], name: string, read: () => Promise<T>, fallback: T): Promise<T> {
    try {
      return await read()
    } catch {
      failed.push(name)
      return fallback
    }
  }

  async function loadRole(id: string): Promise<PageDetail> {
    const base = `/api/llc/roles/${companyId()}/${encodeURIComponent(id)}`
    const failed: string[] = []
    const holders: HandbookHolder[] = await part(failed, 'holders', () => api.get(`${base}/holders?include_past=false`), [])
    const workflowIds: string[] = await part(failed, 'workflows', () => api.get(`${base}/workflows`), [])
    const tools: string[] = await part(failed, 'tools', () => api.get(`${base}/tools`), [])
    const skills: HandbookSkills | null = await part(failed, 'skills', () => api.get(`${ROOT}/roles/${encodeURIComponent(id)}/skills`), null)
    return { ...emptyDetail('ready'), holders, workflowIds, tools, skills, failed }
  }

  async function loadGraph(id: string): Promise<PageDetail> {
    const failed: string[] = []
    const graph: HandbookGraph | null = await part(failed, 'graph', () => api.get(`${ROOT}/workflows/${encodeURIComponent(id)}/graph`), null)
    return { ...emptyDetail('ready'), graph, failed }
  }

  /** Reads what the open page shows beyond the listings; processes need nothing more. */
  async function open(page: HandbookPage | null): Promise<void> {
    const mine = ++opened
    detail.value = emptyDetail('loading')
    if (!page) return
    let read: PageDetail = emptyDetail('ready')
    if (page.kind === 'role') read = await loadRole(page.id)
    if (page.kind === 'workflow' || page.kind === 'metaSkill') read = await loadGraph(page.id)
    if (mine === opened) detail.value = read
  }

  return { roles, workflows, processes, pages, sources, errors, detail, roleName, workflowName, processName, load, open }
}
