// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Vue RUM Plugin - Integrates RUM agent with Vue application
 */

import type { App, ComponentPublicInstance } from 'vue'
import type { Router } from 'vue-router'
import rumAgent from '../utils/RumAgent'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('RumPlugin')

interface RumPluginOptions {
  router?: Router
}

// Minimal structural view of a component instance as this plugin uses it:
// the merged options carry an optional `name`, and the performance-tracking
// mixin stashes mount/update start timestamps directly on the instance.
type RumComponentInstance = ComponentPublicInstance & {
  $options: { name?: string }
  _rumMountStart?: number
  _rumUpdateStart?: number
}

export default {
  install(app: App, options: RumPluginOptions = {}) {
    // Configure Vue error handler
    app.config.errorHandler = (error, instance, info) => {
      // Track Vue errors with RUM
      const err = error as Error
      const vm = instance as RumComponentInstance | null
      rumAgent.trackError('vue_error', {
        message: err.message,
        stack: err.stack,
        componentInfo: info,
        component: vm?.$options?.name || 'unknown'
      })

      // Also log for development
      logger.error('Vue Error', { error, info })
    }

    // Add RUM agent to global properties
    app.config.globalProperties.$rum = rumAgent

    // Provide RUM agent for composition API
    app.provide('rum', rumAgent)

    // Add performance tracking mixin
    app.mixin({
      beforeMount(this: RumComponentInstance) {
        if (this.$options.name) {
          this._rumMountStart = performance.now()
        }
      },
      mounted(this: RumComponentInstance) {
        if (this.$options.name && this._rumMountStart) {
          const mountTime = performance.now() - this._rumMountStart
          if (mountTime > 100) { // Only track slow mounts
            rumAgent.logMetric('component_mount', {
              component: this.$options.name,
              duration: mountTime
            })
          }
        }
      },
      beforeUpdate(this: RumComponentInstance) {
        if (this.$options.name) {
          this._rumUpdateStart = performance.now()
        }
      },
      updated(this: RumComponentInstance) {
        if (this.$options.name && this._rumUpdateStart) {
          const updateTime = performance.now() - this._rumUpdateStart
          if (updateTime > 50) { // Only track slow updates
            rumAgent.logMetric('component_update', {
              component: this.$options.name,
              duration: updateTime
            })
          }
        }
      }
    })

    // Track route changes
    // Issue #2676: Migrated from next() callback to return-value pattern (vue-router v5)
    if (options.router) {
      options.router.beforeEach((to, from) => {
        rumAgent.trackUserInteraction('route_change', null, {
          from: from.path,
          to: to.path
        })
      })
    }

    // RUM Plugin installed successfully
  }
}
