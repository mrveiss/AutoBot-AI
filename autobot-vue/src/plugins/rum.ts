/**
 * Vue RUM Plugin - Integrates RUM agent with Vue application
 */

import type { App } from 'vue'
import type { Router } from 'vue-router'
import rumAgent from '../utils/RumAgent'

interface RumPluginOptions {
  router?: Router
}

export default {
  install(app: App, options: RumPluginOptions = {}) {
    // Configure Vue error handler
    app.config.errorHandler = (error, instance, info) => {
      // Track Vue errors with RUM
      const err = error as Error
      rumAgent.trackError('vue_error', {
        message: err.message,
        stack: err.stack,
        componentInfo: info,
        component: (instance as any)?.$options?.name || 'unknown'
      })

      // Also log to console for development
      console.error('Vue Error:', error, info)
    }

    // Add RUM agent to global properties
    app.config.globalProperties.$rum = rumAgent

    // Provide RUM agent for composition API
    app.provide('rum', rumAgent)

    // Add performance tracking mixin
    app.mixin({
      beforeMount() {
        if ((this as any).$options.name) {
          (this as any)._rumMountStart = performance.now()
        }
      },
      mounted() {
        if ((this as any).$options.name && (this as any)._rumMountStart) {
          const mountTime = performance.now() - (this as any)._rumMountStart
          if (mountTime > 100) { // Only track slow mounts
            rumAgent.logMetric('component_mount', {
              component: (this as any).$options.name,
              duration: mountTime
            })
          }
        }
      },
      beforeUpdate() {
        if ((this as any).$options.name) {
          (this as any)._rumUpdateStart = performance.now()
        }
      },
      updated() {
        if ((this as any).$options.name && (this as any)._rumUpdateStart) {
          const updateTime = performance.now() - (this as any)._rumUpdateStart
          if (updateTime > 50) { // Only track slow updates
            rumAgent.logMetric('component_update', {
              component: (this as any).$options.name,
              duration: updateTime
            })
          }
        }
      }
    })

    // Track route changes
    if (options.router) {
      options.router.beforeEach((to, from, next) => {
        rumAgent.trackUserInteraction('route_change', null, {
          from: from.path,
          to: to.path
        })
        next()
      })
    }

    // RUM Plugin installed successfully
  }
}
