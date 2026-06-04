// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
//
// useHostInventory — SLM node/host management composable (GH#7513)
// Calls the SLM backend /api/nodes endpoints.
//
// ⚠️ DISTINCT FROM useHostSelection (GH#9063 audit):
// - useHostInventory: Ansible-managed fleet (SLM nodes with provisioning, roles, health metrics)
//   → Admin dashboard for managing infrastructure nodes
//   → Data source: SLM backend /api/nodes (node inventory, Ansible state)
//
// - useHostSelection: User-configured SSH targets (secrets.env infrastructure hosts)
//   → Agent SSH actions + terminal selector
//   → Data source: main backend /api/infrastructure/hosts (user secrets)
//
// These serve DIFFERENT purposes and MUST remain separate composables.

import { ref } from 'vue'
import { getSLMUrl } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'
import { useLoadingState } from '@/composables/useLoadingState'

const logger = createLogger('useHostInventory')

// ---------------------------------------------------------------------------
// Types (mirror SLM NodeResponse / NodeListResponse schemas)
// ---------------------------------------------------------------------------

export interface HostRole {
  role_name: string
  assignment_type: 'auto' | 'manual'
  status: 'active' | 'inactive' | 'not_installed'
  current_version: string | null
  last_error: string | null
}

export interface Host {
  id: number
  node_id: string
  hostname: string
  ansible_name: string | null
  ip_address: string
  status: string
  roles: string[]
  detected_roles: string[]
  ssh_user: string | null
  ssh_port: number | null
  auth_method: string | null
  cpu_percent: number
  memory_percent: number
  disk_percent: number
  last_heartbeat: string | null
  agent_version: string | null
  os_info: string | null
  created_at: string
  updated_at: string
}

export interface HostListResponse {
  nodes: Host[]
  total: number
  page: number
  per_page: number
}

export interface HostCreate {
  hostname: string
  ip_address: string
  ansible_name?: string
  roles?: string[]
  ssh_user?: string
  ssh_port?: number
  auth_method?: 'key' | 'password'
}

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

export function useHostInventory() {
  const hosts = ref<Host[]>([])
  const total = ref(0)
  const { isLoading: loading, wrap } = useLoadingState()
  const error = ref<string | null>(null)

  function slmBase(): string {
    return `${getSLMUrl()}/api/nodes`
  }

  async function _slmFetch<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(path, {
      headers: { 'Content-Type': 'application/json', ...init?.headers },
      ...init,
    })
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText)
      throw new Error(`SLM ${res.status}: ${text}`)
    }
    return res.json() as Promise<T>
  }

  async function fetchHosts(page = 1, perPage = 50): Promise<void> {
    error.value = null
    await wrap(async () => {
      try {
        const data = await _slmFetch<HostListResponse>(
          `${slmBase()}?page=${page}&per_page=${perPage}`,
        )
        hosts.value = data.nodes
        total.value = data.total
      } catch (err: unknown) {
        error.value = err instanceof Error ? err.message : 'Failed to load hosts'
        logger.error('fetchHosts error:', err)
      }
    })
  }

  async function addHost(payload: HostCreate): Promise<Host | null> {
    error.value = null
    return wrap(async () => {
      try {
        const host = await _slmFetch<Host>(slmBase(), {
          method: 'POST',
          body: JSON.stringify(payload),
        })
        await fetchHosts()
        return host
      } catch (err: unknown) {
        error.value = err instanceof Error ? err.message : 'Failed to add host'
        logger.error('addHost error:', err)
        return null
      }
    })
  }

  async function provisionRole(nodeId: string, roleName: string): Promise<string | null> {
    error.value = null
    return wrap(async () => {
      try {
        const result = await _slmFetch<{ job_id?: string; message?: string }>(
          `${slmBase()}/${nodeId}/provision`,
          {
            method: 'POST',
            body: JSON.stringify({ roles: [roleName] }),
          },
        )
        return result.job_id ?? null
      } catch (err: unknown) {
        error.value = err instanceof Error ? err.message : 'Failed to provision role'
        logger.error('provisionRole error:', err)
        return null
      }
    })
  }

  function clearError(): void {
    error.value = null
  }

  return {
    hosts,
    total,
    loading,
    error,
    fetchHosts,
    addHost,
    provisionRole,
    clearError,
  }
}
