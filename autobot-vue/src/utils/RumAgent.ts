/**
 * Real User Monitoring (RUM) Agent for Development Mode
 * Tracks performance, errors, and user interactions for debugging
 *
 * Issue #476: Added Prometheus metrics export via /api/rum/metrics endpoint.
 */

// Issue #476: Prometheus metrics payload interfaces
interface PrometheusPageMetrics {
  page: string
  load_time_seconds?: number
  fcp_seconds?: number
  lcp_seconds?: number
  tti_seconds?: number
  dom_loaded_seconds?: number
}

interface PrometheusApiCallMetric {
  endpoint: string
  method: string
  status: string
  latency_seconds: number
  is_slow: boolean
  is_timeout: boolean
  error_type?: string
}

interface PrometheusJsErrorMetric {
  error_type: string
  page: string
  is_rejection: boolean
  component?: string
}

interface PrometheusSessionMetric {
  event: string
  duration_seconds?: number
}

interface PrometheusWebSocketMetric {
  event: string
  direction?: string
  event_type?: string
}

interface PrometheusResourceMetric {
  resource_type: string
  load_time_seconds: number
  is_slow: boolean
}

interface PrometheusCriticalIssueMetric {
  issue_type: string
}

interface PrometheusRumMetrics {
  session_id: string
  timestamp: string
  page_metrics?: PrometheusPageMetrics
  api_calls?: PrometheusApiCallMetric[]
  js_errors?: PrometheusJsErrorMetric[]
  session?: PrometheusSessionMetric
  websocket_events?: PrometheusWebSocketMetric[]
  resources?: PrometheusResourceMetric[]
  critical_issues?: PrometheusCriticalIssueMetric[]
}

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
  // Issue #476: Prometheus metrics export configuration
  private prometheusEnabled: boolean
  private prometheusEndpoint: string
  private prometheusReportInterval: number
  private lastPrometheusReport: number
  private pendingApiCalls: PrometheusApiCallMetric[]
  private pendingJsErrors: PrometheusJsErrorMetric[]
  private pendingWsEvents: PrometheusWebSocketMetric[]
  private pendingResources: PrometheusResourceMetric[]
  private pendingCriticalIssues: PrometheusCriticalIssueMetric[]

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

    // Issue #476: Initialize Prometheus metrics export
    this.prometheusEnabled = localStorage.getItem('rum_prometheus_enabled') !== 'false'
    this.prometheusEndpoint = '/api/rum/metrics'
    this.prometheusReportInterval = 30000 // 30 seconds
    this.lastPrometheusReport = 0
    this.pendingApiCalls = []
    this.pendingJsErrors = []
    this.pendingWsEvents = []
    this.pendingResources = []
    this.pendingCriticalIssues = []

    if (this.isEnabled) {
      this.initialize()
    }
  }

  private generateSessionId(): string {
    return 'rum_' + Math.random().toString(36).substr(2, 9) + '_' + Date.now()
  }

  private initialize(): void {

    this.monitorPagePerformance()
    this.monitorResourceTimings()
    this.monitorErrors()
    this.setupPeriodicReporting()

    // Issue #476: Setup Prometheus metrics reporting
    if (this.prometheusEnabled) {
      this.setupPrometheusReporting()
      // Report session start
      this.sendPrometheusMetrics({
        session_id: this.sessionId,
        timestamp: new Date().toISOString(),
        session: { event: 'start' }
      })
    }

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

    // Issue #476: Queue for Prometheus reporting
    if (this.prometheusEnabled) {
      const statusStr = typeof status === 'number'
        ? (status >= 200 && status < 400 ? 'success' : 'error')
        : String(status)
      const errorType = error ? 'network' : (isTimeout ? 'timeout' : undefined)

      this.pendingApiCalls.push({
        endpoint: this.normalizeEndpoint(url),
        method,
        status: isTimeout ? 'timeout' : statusStr,
        latency_seconds: duration / 1000,
        is_slow: isSlow || isVerySlow,
        is_timeout: isTimeout,
        error_type: errorType
      })
    }

    // Log performance issues immediately
    if (isTimeout) {
      console.error('🚨 API TIMEOUT:', apiCall)
      this.reportCriticalIssue('api_timeout', apiCall)
    } else if (isVerySlow) {
      console.warn('🐌 VERY SLOW API:', apiCall)
    } else if (isSlow) {
      console.warn('⚠️ SLOW API:', apiCall)
    } else {
    }

    return apiCall
  }

  // Issue #476: Normalize endpoint to prevent high cardinality
  private normalizeEndpoint(url: string): string {
    try {
      const urlObj = new URL(url, window.location.origin)
      let path = urlObj.pathname
      // Remove query parameters
      path = path.split('?')[0]
      // Replace numeric IDs with placeholder
      path = path.replace(/\/\d+/g, '/{id}')
      // Replace UUIDs with placeholder
      path = path.replace(/\/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi, '/{uuid}')
      return path
    } catch {
      return url
    }
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

    // Issue #476: Queue for Prometheus reporting
    if (this.prometheusEnabled) {
      this.pendingWsEvents.push({
        event,
        direction: data.direction,
        event_type: data.type || data.event_type
      })
    }

    if (event === 'error' || event === 'close') {
      console.warn('🔌 WebSocket Issue:', wsEvent)
    } else {
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

    // Issue #476: Queue for Prometheus reporting
    if (this.prometheusEnabled) {
      const isRejection = type === 'unhandled_promise_rejection'
      const page = this.getCurrentPage()
      this.pendingJsErrors.push({
        error_type: type,
        page,
        is_rejection: isRejection,
        component: errorData.component
      })
    }

    // Reduce noise from expected network errors during backend connection attempts
    if (type !== 'network_error' && type !== 'http_error') {
      console.error('💥 Error Tracked:', error)
    }

    this.reportCriticalIssue('error', error)
  }

  // Issue #476: Get current page name for metrics
  private getCurrentPage(): string {
    const path = window.location.pathname
    // Extract meaningful page name from path
    const parts = path.split('/').filter(p => p)
    return parts.length > 0 ? parts.join('/') : 'home'
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

          // Issue #476: Send page metrics to Prometheus immediately
          if (this.prometheusEnabled) {
            const page = this.getCurrentPage()
            const loadTime = perfData.loadEventEnd - perfData.fetchStart
            const fcpTime = this.getFirstContentfulPaint()
            const lcpTime = this.getLargestContentfulPaint()

            this.sendPrometheusMetrics({
              session_id: this.sessionId,
              timestamp: new Date().toISOString(),
              page_metrics: {
                page,
                load_time_seconds: loadTime / 1000,
                fcp_seconds: fcpTime ? fcpTime / 1000 : undefined,
                lcp_seconds: lcpTime ? lcpTime / 1000 : undefined,
                tti_seconds: perfData.domInteractive ? (perfData.domInteractive - perfData.fetchStart) / 1000 : undefined,
                dom_loaded_seconds: (perfData.domContentLoadedEventEnd - perfData.domContentLoadedEventStart) / 1000
              }
            })
          }
        }
      }, 0)
    })
  }

  // Issue #476: Get First Contentful Paint
  private getFirstContentfulPaint(): number | null {
    const paintEntries = performance.getEntriesByType('paint')
    const fcp = paintEntries.find(entry => entry.name === 'first-contentful-paint')
    return fcp ? fcp.startTime : null
  }

  // Issue #476: Get Largest Contentful Paint
  private getLargestContentfulPaint(): number | null {
    // LCP requires PerformanceObserver, use cached value if available
    try {
      const lcpEntries = performance.getEntriesByType('largest-contentful-paint')
      if (lcpEntries.length > 0) {
        return (lcpEntries[lcpEntries.length - 1] as PerformanceEntry).startTime
      }
    } catch {
      // LCP not available
    }
    return null
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

          // Issue #476: Queue for Prometheus reporting
          if (this.prometheusEnabled) {
            const resourceType = this.getResourceType(entry.name)
            this.pendingResources.push({
              resource_type: resourceType,
              load_time_seconds: entry.duration / 1000,
              is_slow: true
            })
          }
        }
      }
    })
    observer.observe({ entryTypes: ['resource'] })
  }

  // Issue #476: Determine resource type from URL
  private getResourceType(url: string): string {
    const lowerUrl = url.toLowerCase()
    if (lowerUrl.match(/\.(js|mjs|cjs)(\?|$)/)) return 'script'
    if (lowerUrl.match(/\.(css)(\?|$)/)) return 'stylesheet'
    if (lowerUrl.match(/\.(png|jpg|jpeg|gif|webp|svg|ico)(\?|$)/)) return 'image'
    if (lowerUrl.match(/\.(woff|woff2|ttf|otf|eot)(\?|$)/)) return 'font'
    if (lowerUrl.match(/\.(mp4|webm|ogg|mp3|wav)(\?|$)/)) return 'media'
    return 'other'
  }

  // Generic metric logging
  logMetric(type: string, data: Record<string, any>): Record<string, any> {
    const metric = {
      type,
      timestamp: new Date().toISOString(),
      sessionId: this.sessionId,
      ...data
    }
    
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

    // Issue #476: Queue for Prometheus reporting
    if (this.prometheusEnabled) {
      this.pendingCriticalIssues.push({
        issue_type: type
      })
    }

    // Reduce excessive logging for known network issues
    if (issue.type !== 'network_error' && issue.type !== 'http_error') {
      console.error('🚨🚨🚨 CRITICAL ISSUE:', issue)
    }
  }

  // Periodic reporting
  private setupPeriodicReporting(): void {
    setInterval(() => {
      this.generateReport()
    }, 30000) // Every 30 seconds
  }

  // Issue #476: Setup Prometheus metrics reporting
  private setupPrometheusReporting(): void {
    // Send metrics periodically
    setInterval(() => {
      this.flushPrometheusMetrics()
    }, this.prometheusReportInterval)

    // Send session end metrics on page unload
    window.addEventListener('beforeunload', () => {
      const sessionDuration = (performance.now() - this.startTime) / 1000
      this.sendPrometheusMetrics({
        session_id: this.sessionId,
        timestamp: new Date().toISOString(),
        session: {
          event: 'end',
          duration_seconds: sessionDuration
        }
      })
    })
  }

  // Issue #476: Flush pending metrics to backend
  private flushPrometheusMetrics(): void {
    // Only send if there are pending metrics
    const hasPending =
      this.pendingApiCalls.length > 0 ||
      this.pendingJsErrors.length > 0 ||
      this.pendingWsEvents.length > 0 ||
      this.pendingResources.length > 0 ||
      this.pendingCriticalIssues.length > 0

    if (!hasPending) return

    const metrics: PrometheusRumMetrics = {
      session_id: this.sessionId,
      timestamp: new Date().toISOString()
    }

    // Move pending metrics to payload and clear
    if (this.pendingApiCalls.length > 0) {
      metrics.api_calls = [...this.pendingApiCalls]
      this.pendingApiCalls = []
    }

    if (this.pendingJsErrors.length > 0) {
      metrics.js_errors = [...this.pendingJsErrors]
      this.pendingJsErrors = []
    }

    if (this.pendingWsEvents.length > 0) {
      metrics.websocket_events = [...this.pendingWsEvents]
      this.pendingWsEvents = []
    }

    if (this.pendingResources.length > 0) {
      metrics.resources = [...this.pendingResources]
      this.pendingResources = []
    }

    if (this.pendingCriticalIssues.length > 0) {
      metrics.critical_issues = [...this.pendingCriticalIssues]
      this.pendingCriticalIssues = []
    }

    this.sendPrometheusMetrics(metrics)
  }

  // Issue #476: Send metrics to backend
  private sendPrometheusMetrics(metrics: PrometheusRumMetrics): void {
    // Use sendBeacon for reliability (works during page unload)
    const useBeacon = typeof navigator.sendBeacon === 'function' && document.visibilityState === 'hidden'

    if (useBeacon) {
      const blob = new Blob([JSON.stringify(metrics)], { type: 'application/json' })
      navigator.sendBeacon(this.prometheusEndpoint, blob)
    } else {
      // Use fetch with keepalive for better reliability
      fetch(this.prometheusEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(metrics),
        keepalive: true
      }).catch(() => {
        // Silently ignore errors to not disrupt user experience
        // Metrics will be collected in next batch
      })
    }
  }

  // Issue #476: Enable/disable Prometheus reporting
  enablePrometheusReporting(): void {
    this.prometheusEnabled = true
    localStorage.setItem('rum_prometheus_enabled', 'true')
  }

  disablePrometheusReporting(): void {
    this.prometheusEnabled = false
    localStorage.setItem('rum_prometheus_enabled', 'false')
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
  }

  disable(): void {
    this.isEnabled = false
    localStorage.removeItem('rum_enabled')
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