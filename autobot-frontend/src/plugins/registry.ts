// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Plugin Mount Registry
 *
 * Replaces ad-hoc symlink-based frontend plugin mounting with a typed,
 * explicit registry that maps plugin IDs to their Vue component entry points.
 *
 * Issue #6972 - Standardized frontend-module mounting.
 *
 * Usage:
 *   import { mountPlugin, getPluginComponent } from '@/plugins/registry'
 *
 *   // Mount a registered plugin into the Vue app
 *   mountPlugin(app, 'my-plugin-id')
 *
 *   // Resolve the async component for dynamic rendering
 *   const Comp = getPluginComponent('my-plugin-id')
 */

import type { App, AsyncComponentLoader, Component } from 'vue'
import { defineAsyncComponent } from 'vue'

export interface PluginMountEntry {
  /** Canonical plugin identifier matching the backend PluginManifest.name */
  id: string
  /** Human-readable label used for debugging and dev tools */
  label: string
  /**
   * Async factory that resolves the plugin's root Vue component.
   * Use `() => import('./path/to/Component.vue')` — this is tree-shaken at
   * build time and loaded on demand at runtime.
   */
  loader: AsyncComponentLoader
}

/**
 * Registry of all known frontend plugin entry points.
 *
 * Add an entry here when shipping a new plugin that has a Vue UI.
 * The backend PluginManifest.name must match `id`.
 *
 * Convention: plugins live under `src/components/plugins/<plugin-id>/`.
 */
export const PLUGIN_MOUNT_REGISTRY: readonly PluginMountEntry[] = [
  // Built-in plugins bundled with AutoBot.
  // Third-party / marketplace plugins are discovered at runtime via the
  // backend API and resolved through getPluginComponent() below.
  {
    id: 'terminal',
    label: 'SSH Terminal',
    loader: () => import('@/components/plugins/TerminalPlugin.vue'),
  },
  {
    id: 'vnc',
    label: 'VNC Viewer',
    loader: () => import('@/components/plugins/VncPlugin.vue'),
  },
] as const

const _indexById = new Map<string, PluginMountEntry>(
  PLUGIN_MOUNT_REGISTRY.map((entry) => [entry.id, entry])
)

/**
 * Return the PluginMountEntry for a given plugin ID, or undefined if not
 * registered.
 */
export function getPluginEntry(pluginId: string): PluginMountEntry | undefined {
  return _indexById.get(pluginId)
}

/**
 * Resolve a plugin's async Vue component wrapper.
 *
 * Returns `null` when the plugin is unknown — callers should fall back to a
 * generic "plugin not found" placeholder rather than throwing.
 */
export function getPluginComponent(pluginId: string): Component | null {
  const entry = _indexById.get(pluginId)
  if (!entry) return null
  return defineAsyncComponent(entry.loader)
}

/**
 * Mount a registered plugin as a global async component on the Vue app.
 *
 * The component is registered under the name `Plugin_<camelCased-id>` so it
 * is available without explicit imports in templates.
 *
 * Throws if the plugin ID is not in PLUGIN_MOUNT_REGISTRY — this is a
 * developer error, not a runtime error.
 */
export function mountPlugin(app: App, pluginId: string): void {
  const entry = _indexById.get(pluginId)
  if (!entry) {
    throw new Error(
      `Plugin '${pluginId}' is not registered in PLUGIN_MOUNT_REGISTRY. ` +
        'Add an entry to src/plugins/registry.ts before calling mountPlugin().'
    )
  }
  const componentName = `Plugin_${pluginId.replace(/-/g, '_')}`
  app.component(componentName, defineAsyncComponent(entry.loader))
}

/**
 * Mount all registered plugins as global async components.
 * Typically called once during app initialization in main.ts.
 */
export function mountAllPlugins(app: App): void {
  for (const entry of PLUGIN_MOUNT_REGISTRY) {
    mountPlugin(app, entry.id)
  }
}
