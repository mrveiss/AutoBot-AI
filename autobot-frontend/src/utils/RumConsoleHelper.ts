/**
 * RUM Console Helper - Provides easy console commands for RUM control
 *
 * Issue #156 Fix: Import RumAgent to ensure Window.rum type is available
 */

import type { ApiCall } from './RumAgent'
// Import the module to ensure Window.rum declaration is loaded
import './RumAgent'

// Add global RUM console commands
declare global {
  interface Window {
    rumHelp: () => void
    rumStats: () => void
    rumIssues: () => void
    rumApiStats: () => void
    rumDebug: () => void
    rumTestApi: () => void
    rumTestError: () => void
  }
}

// Add global RUM console commands
window.rumHelp = () => {
  console.log(`
🔍 RUM (Real User Monitoring) Console Commands:

📊 Data & Reports:
  rum.getMetrics()           - Get current metrics
  rum.generateReport()       - Generate detailed report
  rum.exportData()           - Download complete data dump

🎛️ Control:
  rum.enable()               - Enable RUM tracking
  rum.disable()              - Disable RUM tracking
  rum.clear()                - Clear all collected data

🔧 Manual Tracking:
  rum.trackApiCall(method, url, start, end, status, error)
  rum.trackError(type, errorData)
  rum.trackUserInteraction(action, element, context)
  rum.trackWebSocketEvent(event, data)
  rum.reportCriticalIssue(type, data)

📈 Quick Stats:
  rumStats()                 - Show quick performance stats
  rumIssues()                - Show critical issues
  rumApiStats()              - Show API performance breakdown

🛠️ Debugging:
  rumDebug()                 - Enable debug mode with verbose logging
  rumTestApi()               - Test API call tracking
  rumTestError()             - Test error tracking

💾 Storage:
  View localStorage:
    localStorage.getItem('rum_reports')
    localStorage.getItem('rum_critical_issues')
  `)
}

// Issue #156 Fix: Add type annotations for call parameters
window.rumStats = () => {
  if (!window.rum) {
    return
  }

  const metrics = window.rum.getMetrics()
  const slowCalls = metrics.apiCalls.filter((call: ApiCall) => call.isSlow).length
  const timeouts = metrics.apiCalls.filter((call: ApiCall) => call.isTimeout).length
  const errors = metrics.errors.length

  console.log(`
📊 RUM Quick Stats:
   Session: ${Math.round(metrics.sessionDuration / 1000)}s
   API Calls: ${metrics.apiCalls.length} (${slowCalls} slow, ${timeouts} timeouts)
   Errors: ${errors}
   WebSocket Events: ${metrics.webSocketEvents.length}
   User Interactions: ${metrics.userInteractions.length}
  `)

  if (timeouts > 0 || errors > 0) {
    console.warn('⚠️ Performance issues detected! Use rumIssues() for details')
  }
}

window.rumIssues = () => {
  const issues = JSON.parse(localStorage.getItem('rum_critical_issues') || '[]')
  if (issues.length === 0) {
    return
  }

  issues.forEach((issue: any, index: number) => {
    console.group(`${index + 1}. ${issue.type} (${new Date(issue.timestamp).toLocaleTimeString()})`)
    console.groupEnd()
  })
}

// Issue #156 Fix: Add type annotations for call parameters
window.rumApiStats = () => {
  if (!window.rum) {
    return
  }

  const metrics = window.rum.getMetrics()
  const apiCalls = metrics.apiCalls

  // Group by endpoint
  const endpointStats: Record<string, any> = {}
  apiCalls.forEach((call: ApiCall) => {
    const endpoint = call.url
    if (!endpointStats[endpoint]) {
      endpointStats[endpoint] = {
        count: 0,
        totalDuration: 0,
        timeouts: 0,
        errors: 0,
        slowCalls: 0
      }
    }

    const stats = endpointStats[endpoint]
    stats.count++
    stats.totalDuration += call.duration
    if (call.isTimeout) stats.timeouts++
    if (call.status === 'error') stats.errors++
    if (call.isSlow) stats.slowCalls++
  })

  Object.entries(endpointStats).forEach(([endpoint, stats]: [string, any]) => {
    const avgDuration = Math.round(stats.totalDuration / stats.count)
    const hasIssues = stats.timeouts > 0 || stats.errors > 0 || stats.slowCalls > 0

    console.log(`${hasIssues ? '⚠️' : '✅'} ${endpoint}:`, {
      calls: stats.count,
      avgDuration: `${avgDuration}ms`,
      timeouts: stats.timeouts,
      errors: stats.errors,
      slowCalls: stats.slowCalls
    })
  })
}

// Issue #156 Fix: Proper typing for debug wrapper functions
window.rumDebug = () => {
  if (!window.rum) {
    return
  }

  // Enable verbose logging
  const originalTrackApiCall = window.rum.trackApiCall.bind(window.rum)
  window.rum.trackApiCall = function(
    method: string,
    url: string,
    startTime: number,
    endTime: number,
    status: string | number,
    error?: Error | null
  ) {
    return originalTrackApiCall(method, url, startTime, endTime, status, error)
  }

  const originalTrackError = window.rum.trackError.bind(window.rum)
  window.rum.trackError = function(type: string, data: any) {
    return originalTrackError(type, data)
  }

}

// Issue #156 Fix: Add non-null assertion for window.rum after check
window.rumTestApi = () => {
  if (!window.rum) {
    return
  }

  const start = performance.now()
  setTimeout(() => {
    const end = performance.now()
    window.rum?.trackApiCall('GET', '/test/endpoint', start, end, 200)
  }, 100)
}

window.rumTestError = () => {
  if (!window.rum) {
    return
  }

  window.rum.trackError('test_error', {
    message: 'This is a test error',
    source: 'RUM console helper'
  })
}

// Auto-display help on first load
if (import.meta.env.DEV) {
  setTimeout(() => {
  }, 1000)
}

export default {
  // Export functions for programmatic use
  showStats: window.rumStats,
  showIssues: window.rumIssues,
  showApiStats: window.rumApiStats,
  enableDebug: window.rumDebug,
  testApi: window.rumTestApi,
  testError: window.rumTestError
}
