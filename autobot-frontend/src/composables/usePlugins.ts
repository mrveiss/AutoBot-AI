// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Plugin Manager Composable
 * Issue #929 - Plugin Manager UI
 *
 * Wraps all 10 /api/plugins/ endpoints for managing plugin lifecycle.
 */

import { ref } from 'vue'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'
import { useLoadingState } from '@/composables/useLoadingState'

const logger = createLogger('usePlugins')

// ===== Type Definitions =====

export interface PluginInfo {
  name: string
  version: string
  display_name: string
  description: string
  author: string
  status: 'unloaded' | 'loaded' | 'enabled' | 'disabled' | 'error'
  hooks: string[]
  trust_tier?: 'official' | 'verified' | 'community' | 'unverified'
}

export interface PluginManifest {
  name: string
  version: string
  display_name: string
  description: string
  author: string
  entry_point: string
  dependencies: string[]
  config_schema: Record<string, unknown>
  hooks: string[]
  trust_tier?: 'official' | 'verified' | 'community' | 'unverified'
}

export interface DiscoveredPlugin {
  manifest: PluginManifest
}

export interface CapabilityInfo {
  plugin_name: string
  trust_tier: 'official' | 'verified' | 'community' | 'unverified'
  required_capabilities: string[]
  granted_capabilities: string[]
  pending_approval: string[]
}

export interface AuditLogEntry {
  timestamp: string
  plugin_name: string
  capability: string
  granted: boolean
  operation: string
  metadata?: string
}

// ===== Composable =====

export function usePlugins() {
  const plugins = ref<PluginInfo[]>([])
  const discovered = ref<PluginManifest[]>([])
  const { isLoading: loading, wrap } = useLoadingState()
  const error = ref<string | null>(null)

  async function listPlugins(): Promise<void> {
    error.value = null
    try {
      const data = await wrap(() => ApiClient.get<any>(`${getApiBase()}/plugins`))
      // Backend returns {plugins:[...], total:N}. Guard against a bare array
      // response to handle shape divergence between PluginListResponse and actual
      // payload. (#6774)
      plugins.value = Array.isArray(data) ? data : (data?.plugins ?? [])
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to list plugins'
      error.value = msg
      logger.error('listPlugins error: %s', msg)
    }
  }

  async function discoverPlugins(): Promise<void> {
    error.value = null
    try {
      const data = await wrap(() => ApiClient.get<any>(`${getApiBase()}/plugins/discover`))
      discovered.value = data.discovered ?? []
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to discover plugins'
      error.value = msg
      logger.error('discoverPlugins error: %s', msg)
    }
  }

  async function loadPlugin(name: string, config?: Record<string, unknown>): Promise<boolean> {
    error.value = null
    try {
      await ApiClient.post<any>(`${getApiBase()}/plugins/${name}/load`, config ? { config } : {})
      await listPlugins()
      return true
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : `Failed to load plugin ${name}`
      error.value = msg
      logger.error('loadPlugin error: %s', msg)
      return false
    }
  }

  async function unloadPlugin(name: string): Promise<boolean> {
    error.value = null
    try {
      await ApiClient.post<any>(`${getApiBase()}/plugins/${name}/unload`, {})
      await listPlugins()
      return true
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : `Failed to unload plugin ${name}`
      error.value = msg
      logger.error('unloadPlugin error: %s', msg)
      return false
    }
  }

  async function reloadPlugin(name: string): Promise<boolean> {
    error.value = null
    try {
      await ApiClient.post<any>(`${getApiBase()}/plugins/${name}/reload`, {})
      await listPlugins()
      return true
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : `Failed to reload plugin ${name}`
      error.value = msg
      logger.error('reloadPlugin error: %s', msg)
      return false
    }
  }

  async function enablePlugin(name: string): Promise<boolean> {
    error.value = null
    try {
      await ApiClient.post<any>(`${getApiBase()}/plugins/${name}/enable`, {})
      await listPlugins()
      return true
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : `Failed to enable plugin ${name}`
      error.value = msg
      logger.error('enablePlugin error: %s', msg)
      return false
    }
  }

  async function disablePlugin(name: string): Promise<boolean> {
    error.value = null
    try {
      await ApiClient.post<any>(`${getApiBase()}/plugins/${name}/disable`, {})
      await listPlugins()
      return true
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : `Failed to disable plugin ${name}`
      error.value = msg
      logger.error('disablePlugin error: %s', msg)
      return false
    }
  }

  async function getPluginInfo(name: string): Promise<PluginInfo | null> {
    try {
      return await ApiClient.get<any>(`${getApiBase()}/plugins/${name}`)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : `Failed to get info for plugin ${name}`
      logger.error('getPluginInfo error: %s', msg)
      return null
    }
  }

  async function getPluginConfig(name: string): Promise<Record<string, unknown> | null> {
    try {
      return await ApiClient.get<any>(`${getApiBase()}/plugins/${name}/config`)
    } catch {
      logger.warn('getPluginConfig: no config for %s', name)
      return null
    }
  }

  async function updatePluginConfig(
    name: string,
    config: Record<string, unknown>,
  ): Promise<boolean> {
    error.value = null
    try {
      await ApiClient.put<any>(`${getApiBase()}/plugins/${name}/config`, { config })
      return true
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : `Failed to update config for plugin ${name}`
      error.value = msg
      logger.error('updatePluginConfig error: %s', msg)
      return false
    }
  }

  // Issue #6464: install 3rd-party plugins from ZIP or Git URL
  async function installFromZip(file: File): Promise<{ name: string; version: string } | null> {
    error.value = null
    const form = new FormData()
    form.append('file', file)
    try {
      const data = await wrap(() =>
        ApiClient.post(`${getApiBase()}/plugins/install/upload`, form),
      ) as { name: string; version: string }
      await discoverPlugins()
      return { name: data.name, version: data.version }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to install plugin from ZIP'
      error.value = msg
      logger.error('installFromZip error: %s', msg)
      return null
    }
  }

  async function installFromGit(
    url: string,
    ref?: string,
  ): Promise<{ name: string; version: string } | null> {
    error.value = null
    try {
      const data = await wrap(() =>
        ApiClient.post(`${getApiBase()}/plugins/install/git`, { url, ref: ref || null }),
      ) as { name: string; version: string }
      await discoverPlugins()
      return { name: data.name, version: data.version }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to install plugin from Git'
      error.value = msg
      logger.error('installFromGit error: %s', msg)
      return null
    }
  }

  async function getCapabilities(pluginName: string): Promise<CapabilityInfo | null> {
    error.value = null
    try {
      const data = await wrap(() =>
        ApiClient.get<CapabilityInfo>(`${getApiBase()}/plugins/${pluginName}/capabilities`),
      )
      return data
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : `Failed to get capabilities for ${pluginName}`
      error.value = msg
      logger.error('getCapabilities error: %s', msg)
      return null
    }
  }

  async function approveCapabilities(
    pluginName: string,
    capabilities: string[],
  ): Promise<boolean> {
    error.value = null
    try {
      await ApiClient.post(`${getApiBase()}/plugins/${pluginName}/approve-capabilities`, {
        capabilities,
      })
      return true
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : `Failed to approve capabilities for ${pluginName}`
      error.value = msg
      logger.error('approveCapabilities error: %s', msg)
      return false
    }
  }

  async function getAuditLog(limit = 50): Promise<AuditLogEntry[]> {
    error.value = null
    try {
      const data = await wrap(() =>
        ApiClient.get<{ entries: AuditLogEntry[] }>(`${getApiBase()}/plugins/audit?limit=${limit}`),
      )
      return data.entries ?? []
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch audit log'
      error.value = msg
      logger.error('getAuditLog error: %s', msg)
      return []
    }
  }

  return {
    plugins,
    discovered,
    loading,
    error,
    listPlugins,
    discoverPlugins,
    loadPlugin,
    unloadPlugin,
    reloadPlugin,
    enablePlugin,
    disablePlugin,
    getPluginInfo,
    getPluginConfig,
    updatePluginConfig,
    installFromZip,
    installFromGit,
    getCapabilities,
    approveCapabilities,
    getAuditLog,
  }
}
