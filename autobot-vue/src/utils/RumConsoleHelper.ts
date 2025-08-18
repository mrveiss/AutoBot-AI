/**
 * RUM Console Helper - Provides easy console commands for RUM control
 */

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

window.rumStats = () => {
  if (!window.rum) {
    console.log('❌ RUM not available')
    return
  }
  
  const metrics = window.rum.getMetrics()
  const slowCalls = metrics.apiCalls.filter(call => call.isSlow).length
  const timeouts = metrics.apiCalls.filter(call => call.isTimeout).length
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
    console.log('✅ No critical issues found')
    return
  }
  
  console.log('🚨 Critical Issues:')
  issues.forEach((issue: any, index: number) => {
    console.group(`${index + 1}. ${issue.type} (${new Date(issue.timestamp).toLocaleTimeString()})`)
    console.log(issue.data)
    console.groupEnd()
  })
}

window.rumApiStats = () => {
  if (!window.rum) {
    console.log('❌ RUM not available')
    return
  }
  
  const metrics = window.rum.getMetrics()
  const apiCalls = metrics.apiCalls
  
  // Group by endpoint
  const endpointStats: Record<string, any> = {}
  apiCalls.forEach(call => {
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
  
  console.log('📡 API Endpoint Performance:')
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

window.rumDebug = () => {
  if (!window.rum) {
    console.log('❌ RUM not available')
    return
  }
  
  // Enable verbose logging
  const originalTrackApiCall = window.rum.trackApiCall
  window.rum.trackApiCall = function(this: any, ...args: any[]) {
    console.log('🌐 API Call Tracked:', args)
    return originalTrackApiCall.apply(this, args)
  }
  
  const originalTrackError = window.rum.trackError
  window.rum.trackError = function(this: any, ...args: any[]) {
    console.log('💥 Error Tracked:', args)
    return originalTrackError.apply(this, args)
  }
  
  console.log('🛠️ RUM Debug mode enabled - verbose logging activated')
}

window.rumTestApi = () => {
  if (!window.rum) {
    console.log('❌ RUM not available')
    return
  }
  
  console.log('🧪 Testing API call tracking...')
  const start = performance.now()
  setTimeout(() => {
    const end = performance.now()
    window.rum.trackApiCall('GET', '/test/endpoint', start, end, 200)
    console.log('✅ Test API call tracked')
  }, 100)
}

window.rumTestError = () => {
  if (!window.rum) {
    console.log('❌ RUM not available')
    return
  }
  
  console.log('🧪 Testing error tracking...')
  window.rum.trackError('test_error', {
    message: 'This is a test error',
    source: 'RUM console helper'
  })
  console.log('✅ Test error tracked')
}

// Auto-display help on first load
if (import.meta.env.DEV) {
  setTimeout(() => {
    console.log('🔍 RUM Console Helper loaded! Type rumHelp() for available commands')
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