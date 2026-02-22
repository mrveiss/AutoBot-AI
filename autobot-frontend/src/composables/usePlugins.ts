// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
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
}

export interface DiscoveredPlugin {
  manifest: PluginManifest
}

// ===== Composable =====

export function usePlugins() {
  const plugins = ref<PluginInfo[]>([])
  const discovered = ref<PluginManifest[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function listPlugins(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const data = await ApiClient.get('/api/plugins')
      plugins.value = data.plugins ?? []
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to list plugins'
      error.value = msg
      logger.error('listPlugins error: %s', msg)
    } finally {
      loading.value = false
    }
  }

  async function discoverPlugins(): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const data = await ApiClient.get('/api/plugins/discover')
      discovered.value = data.discovered ?? []
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to discover plugins'
      error.value = msg
      logger.error('discoverPlugins error: %s', msg)
    } finally {
      loading.value = false
    }
  }

  async function loadPlugin(name: string, config?: Record<string, unknown>): Promise<boolean> {
    error.value = null
    try {
      await ApiClient.post(`/api/plugins/${name}/load`, config ? { config } : {})
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
      await ApiClient.post(`/api/plugins/${name}/unload`, {})
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
      await ApiClient.post(`/api/plugins/${name}/reload`, {})
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
      await ApiClient.post(`/api/plugins/${name}/enable`, {})
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
      await ApiClient.post(`/api/plugins/${name}/disable`, {})
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
      return await ApiClient.get(`/api/plugins/${name}`)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : `Failed to get info for plugin ${name}`
      logger.error('getPluginInfo error: %s', msg)
      return null
    }
  }

  async function getPluginConfig(name: string): Promise<Record<string, unknown> | null> {
    try {
      return await ApiClient.get(`/api/plugins/${name}/config`)
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
      await ApiClient.put(`/api/plugins/${name}/config`, { config })
      return true
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : `Failed to update config for plugin ${name}`
      error.value = msg
      logger.error('updatePluginConfig error: %s', msg)
      return false
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
  }
}
