/**
 * Real User Monitoring (RUM) Agent for Development Mode
 * Tracks performance, errors, and user interactions for debugging
 */

interface ApiCall {
  timestamp: string
  method: string
  url: string
  duration: number
  status: string | number
  error?: string | null
  isTimeout: boolean
  isSlow: boolean
  isVerySlow: boolean
  sessionId: string
}

interface WebSocketEvent {
  timestamp: string
  event: string
  data: Record<string, any>
  sessionId: string
}

interface UserInteraction {
  timestamp: string
  action: string
  element: string
  elementId?: string | null
  elementClass?: string | null
  context: Record<string, any>
  sessionId: string
}

interface ErrorInfo {
  timestamp: string
  type: string
  message?: string
  stack?: string
  sessionId: string
  url: string
  userAgent: string
  [key: string]: any
}

interface RumMetrics {
  apiCalls: ApiCall[]
  errors: ErrorInfo[]
  userInteractions: UserInteraction[]
  webSocketEvents: WebSocketEvent[]
  pageMetrics: Record<string, any>
  resourceTimings: any[]
  sessionDuration: number
}

interface CriticalIssue {
  type: string
  severity: 'critical'
  timestamp: string
  sessionId: string
  data: Record<string, any>
}

class RumAgent {
  private isEnabled: boolean
  private sessionId: string
  private startTime: number
  private metrics: RumMetrics
  private thresholds: {
    slowApiCall: number
    verySlowApiCall: number
    timeoutThreshold: number
  }

  constructor() {
    this.isEnabled = import.meta.env.DEV || localStorage.getItem('rum_enabled') === 'true'
    this.sessionId = this.generateSessionId()
    this.startTime = performance.now()
    this.metrics = {
      apiCalls: [],
      errors: [],
      userInteractions: [],
      webSocketEvents: [],
      pageMetrics: {},
      resourceTimings: [],
      sessionDuration: 0
    }
    this.thresholds = {
      slowApiCall: 1000, // ms
      verySlowApiCall: 5000, // ms
      timeoutThreshold: 30000 // ms
    }
    
    if (this.isEnabled) {
      this.initialize()
    }
  }

  private generateSessionId(): string {
    return 'rum_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now()
  }

  private initialize(): void {
    console.log('🔍 RUM Agent initialized for session:', this.sessionId)
    
    this.monitorPagePerformance()
    this.monitorResourceTimings()
    this.monitorErrors()
    this.setupPeriodicReporting()
    
    this.logMetric('session_start', {
      sessionId: this.sessionId,
      userAgent: navigator.userAgent,
      timestamp: new Date().toISOString(),
      url: window.location.href
    })
  }

  // API Call Monitoring
  trackApiCall(method: string, url: string, startTime: number, endTime: number, status: string | number, error?: Error | null): ApiCall {
    const duration = endTime - startTime
    const isTimeout = duration > this.thresholds.timeoutThreshold
    const isSlow = duration > this.thresholds.slowApiCall
    const isVerySlow = duration > this.thresholds.verySlowApiCall
    
    const apiCall: ApiCall = {
      timestamp: new Date().toISOString(),
      method,
      url,
      duration,
      status,
      error: error?.message || null,
      isTimeout,
      isSlow,
      isVerySlow,
      sessionId: this.sessionId
    }
    
    this.metrics.apiCalls.push(apiCall)
    
    // Log performance issues immediately
    if (isTimeout) {
      console.error('🚨 API TIMEOUT:', apiCall)
      this.reportCriticalIssue('api_timeout', apiCall)
    } else if (isVerySlow) {
      console.warn('🐌 VERY SLOW API:', apiCall)
    } else if (isSlow) {
      console.warn('⚠️ SLOW API:', apiCall)
    } else {
      console.log('✅ API Call:', `${method} ${url} - ${duration}ms`)
    }
    
    return apiCall
  }

  // WebSocket Monitoring
  trackWebSocketEvent(event: string, data: Record<string, any> = {}): void {
    const wsEvent: WebSocketEvent = {
      timestamp: new Date().toISOString(),
      event,
      data,
      sessionId: this.sessionId
    }
    
    this.metrics.webSocketEvents.push(wsEvent)
    
    if (event === 'error' || event === 'close') {
      console.warn('🔌 WebSocket Issue:', wsEvent)
    } else {
      console.log('🔌 WebSocket:', event, data)
    }
  }

  // User Interaction Tracking
  trackUserInteraction(action: string, element?: Element | null, context: Record<string, any> = {}): void {
    const interaction: UserInteraction = {
      timestamp: new Date().toISOString(),
      action,
      element: element?.tagName || 'unknown',
      elementId: element?.id || null,
      elementClass: element?.className || null,
      context,
      sessionId: this.sessionId
    }
    
    this.metrics.userInteractions.push(interaction)
    console.log('👆 User Interaction:', interaction)
  }

  // Error Monitoring
  private monitorErrors(): void {
    // Global error handler
    window.addEventListener('error', (event) => {
      this.trackError('javascript_error', {
        message: event.message,
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
        stack: event.error?.stack
      })
    })

    // Promise rejection handler
    window.addEventListener('unhandledrejection', (event) => {
      this.trackError('unhandled_promise_rejection', {
        reason: event.reason?.toString(),
        stack: event.reason?.stack
      })
    })
  }

  trackError(type: string, errorData: Record<string, any>): void {
    const error: ErrorInfo = {
      timestamp: new Date().toISOString(),
      type,
      ...errorData,
      sessionId: this.sessionId,
      url: window.location.href,
      userAgent: navigator.userAgent
    }
    
    this.metrics.errors.push(error)
    console.error('💥 Error Tracked:', error)
    
    this.reportCriticalIssue('error', error)
  }

  // Page Performance Monitoring
  private monitorPagePerformance(): void {
    window.addEventListener('load', () => {
      setTimeout(() => {
        const perfData = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming
        if (perfData) {
          this.metrics.pageMetrics = {
            domContentLoaded: perfData.domContentLoadedEventEnd - perfData.domContentLoadedEventStart,
            loadComplete: perfData.loadEventEnd - perfData.loadEventStart,
            domInteractive: perfData.domInteractive - perfData.fetchStart,
            firstPaint: this.getFirstPaint(),
            timestamp: new Date().toISOString()
          }
          console.log('📊 Page Performance:', this.metrics.pageMetrics)
        }
      }, 0)
    })
  }

  private getFirstPaint(): number | null {
    const paintEntries = performance.getEntriesByType('paint')
    const firstPaint = paintEntries.find(entry => entry.name === 'first-paint')
    return firstPaint ? firstPaint.startTime : null
  }

  // Resource Timing Monitoring
  private monitorResourceTimings(): void {
    const observer = new PerformanceObserver((list) => {
      for (const entry of list.getEntries()) {
        if (entry.duration > 1000) { // Only track slow resources
          this.metrics.resourceTimings.push({
            name: entry.name,
            duration: entry.duration,
            size: (entry as PerformanceResourceTiming).transferSize,
            timestamp: new Date().toISOString()
          })
        }
      }
    })
    observer.observe({ entryTypes: ['resource'] })
  }

  // Generic metric logging
  logMetric(type: string, data: Record<string, any>): Record<string, any> {
    const metric = {
      type,
      timestamp: new Date().toISOString(),
      sessionId: this.sessionId,
      ...data
    }
    
    console.log('📈 Metric:', metric)
    return metric
  }

  // Critical issue reporting
  reportCriticalIssue(type: string, data: Record<string, any>): void {
    const issue: CriticalIssue = {
      type,
      severity: 'critical',
      timestamp: new Date().toISOString(),
      sessionId: this.sessionId,
      data
    }
    
    // Store in localStorage for persistence
    const criticalIssues = JSON.parse(localStorage.getItem('rum_critical_issues') || '[]')
    criticalIssues.push(issue)
    localStorage.setItem('rum_critical_issues', JSON.stringify(criticalIssues.slice(-50)))
    
    console.error('🚨🚨🚨 CRITICAL ISSUE:', issue)
  }

  // Periodic reporting
  private setupPeriodicReporting(): void {
    setInterval(() => {
      this.generateReport()
    }, 30000) // Every 30 seconds
  }

  generateReport(): Record<string, any> {
    const now = performance.now()
    const sessionDuration = now - this.startTime
    
    const report = {
      sessionId: this.sessionId,
      sessionDuration,
      timestamp: new Date().toISOString(),
      summary: {
        totalApiCalls: this.metrics.apiCalls.length,
        slowApiCalls: this.metrics.apiCalls.filter(call => call.isSlow).length,
        timeoutApiCalls: this.metrics.apiCalls.filter(call => call.isTimeout).length,
        totalErrors: this.metrics.errors.length,
        userInteractions: this.metrics.userInteractions.length,
        webSocketEvents: this.metrics.webSocketEvents.length
      },
      recentIssues: [
        ...this.metrics.apiCalls.filter(call => call.isTimeout || call.isVerySlow).slice(-5),
        ...this.metrics.errors.slice(-5)
      ]
    }
    
    console.log('📊 RUM Report:', report)
    
    const reports = JSON.parse(localStorage.getItem('rum_reports') || '[]')
    reports.push(report)
    localStorage.setItem('rum_reports', JSON.stringify(reports.slice(-20)))
    
    return report
  }

  // Get current metrics
  getMetrics(): RumMetrics & { sessionId: string; sessionDuration: number } {
    return {
      ...this.metrics,
      sessionId: this.sessionId,
      sessionDuration: performance.now() - this.startTime
    }
  }

  // Export data for analysis
  exportData(): void {
    const data = {
      sessionId: this.sessionId,
      metrics: this.getMetrics(),
      reports: JSON.parse(localStorage.getItem('rum_reports') || '[]'),
      criticalIssues: JSON.parse(localStorage.getItem('rum_critical_issues') || '[]'),
      timestamp: new Date().toISOString()
    }
    
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `rum-data-${this.sessionId}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  // Manual control methods
  enable(): void {
    this.isEnabled = true
    localStorage.setItem('rum_enabled', 'true')
    console.log('🔍 RUM Agent enabled')
  }

  disable(): void {
    this.isEnabled = false
    localStorage.removeItem('rum_enabled')
    console.log('🔍 RUM Agent disabled')
  }

  clear(): void {
    this.metrics = {
      apiCalls: [],
      errors: [],
      userInteractions: [],
      webSocketEvents: [],
      pageMetrics: {},
      resourceTimings: [],
      sessionDuration: 0
    }
    localStorage.removeItem('rum_reports')
    localStorage.removeItem('rum_critical_issues')
    console.log('🧹 RUM data cleared')
  }
}

// Create singleton instance
const rumAgent = new RumAgent()

// Expose to window for manual control
declare global {
  interface Window {
    rum: RumAgent
  }
}

window.rum = rumAgent

export default rumAgent
export type { ApiCall, WebSocketEvent, UserInteraction, ErrorInfo, RumMetrics, CriticalIssue }