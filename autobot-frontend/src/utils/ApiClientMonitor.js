// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * API Client Monitor - Wraps API calls with RUM monitoring
 */

import rumAgent from './RumAgent.js'
import { getApiBase } from '@/config/ssot-config'

export function createMonitoredApiClient(originalApiClient) {
  return new Proxy(originalApiClient, {
    get(target, prop) {
      const original = target[prop]

      // If it's not a function, return as-is
      if (typeof original !== 'function') {
        return original
      }

      // Wrap API methods with monitoring
      return function(...args) {
        const startTime = performance.now()
        const method = prop.toUpperCase()
        const url = getUrlFromArgs(prop, args)

        rumAgent.trackUserInteraction('api_call_initiated', null, { method, url })

        const result = original.apply(this, args)

        // Handle promises (most API calls)
        if (result && typeof result.then === 'function') {
          return result
            .then(response => {
              const endTime = performance.now()
              rumAgent.trackApiCall(method, url, startTime, endTime, 'success')
              return response
            })
            .catch(error => {
              const endTime = performance.now()
              rumAgent.trackApiCall(method, url, startTime, endTime, 'error', error)

              // Track specific error types
              if (error.message?.includes('timeout')) {
                rumAgent.reportCriticalIssue('api_timeout', {
                  method,
                  url,
                  duration: endTime - startTime,
                  error: error.message
                })
              } else if (error.message?.includes('network')) {
                rumAgent.reportCriticalIssue('network_error', {
                  method,
                  url,
                  error: error.message
                })
              }

              throw error
            })
        }

        // Handle synchronous calls
        const endTime = performance.now()
        rumAgent.trackApiCall(method, url, startTime, endTime, 'success')
        return result
      }
    }
  })
}

// Helper to extract URL from different API method signatures
function getUrlFromArgs(method, args) {
  // Common patterns for API methods
  if (method === 'request' && args[0]?.url) {
    return args[0].url
  }
  if (method === 'get' || method === 'delete') {
    return args[0] || 'unknown'
  }
  if (method === 'post' || method === 'put' || method === 'patch') {
    return args[0] || 'unknown'
  }

  // Method-specific patterns
  // Issue #552: Fixed paths to match backend endpoints
  const base = getApiBase()
  const methodUrlMap = {
    getChatList: `${base}/chat/sessions`,
    createNewChat: `${base}/chat/sessions`,
    sendMessage: `${base}/chat/message`,
    getSystemHealth: `${base}/system/health`,
    getSettings: `${base}/settings/`,
    executeWorkflow: `${base}/workflow/execute`
  }

  return methodUrlMap[method] || `/${method}`
}
