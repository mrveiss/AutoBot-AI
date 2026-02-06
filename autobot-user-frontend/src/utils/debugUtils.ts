// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Frontend Debugging Utilities
 * Reusable debugging, logging, and diagnostic functions for Vue.js applications
 */

// ============================================================================
// Types and Interfaces
// ============================================================================

/**
 * Log levels for console output
 */
export type LogLevel = 'debug' | 'info' | 'warn' | 'error'

/**
 * Storage type for browser storage operations
 */
export type StorageType = 'localStorage' | 'sessionStorage'

/**
 * Console log entry structure
 */
export interface ConsoleLogEntry {
  level: LogLevel
  message: string
  timestamp: number
  data?: any
}

/**
 * Storage validation result
 */
export interface StorageValidationResult {
  isValid: boolean
  key: string
  error?: string
  value?: any
}

/**
 * Vue.js framework detection result
 */
export interface VueFrameworkCheck {
  vue_available: boolean
  vue3_app: boolean
  vite_client: boolean
  app_instance: boolean
  vue_devtools: boolean
}

/**
 * Performance metrics
 */
export interface PerformanceMetrics {
  timestamp: number
  memory?: {
    usedJSHeapSize: number
    totalJSHeapSize: number
    jsHeapSizeLimit: number
  }
  timing?: {
    navigationStart: number
    loadEventEnd: number
    domContentLoadedEventEnd: number
  }
}

// ============================================================================
// Console Logging Utilities
// ============================================================================

/**
 * Enhanced console logging with timestamps and formatting
 *
 * @param level - Log level (debug, info, warn, error)
 * @param message - Log message
 * @param data - Optional data to log
 *
 * @example
 * ```ts
 * log('info', 'Component mounted')
 * log('error', 'Failed to load data', { error: e })
 * ```
 */
export function log(level: LogLevel, message: string, data?: any): void {
  const timestamp = new Date().toISOString()
  const prefix = `[${timestamp}] [${level.toUpperCase()}]`

  switch (level) {
    case 'debug':
      if (data) {
        console.debug(prefix, message, data)
      } else {
        console.debug(prefix, message)
      }
      break
    case 'info':
      if (data) {
        console.info(prefix, message, data)
      } else {
        console.info(prefix, message)
      }
      break
    case 'warn':
      if (data) {
        console.warn(prefix, message, data)
      } else {
        console.warn(prefix, message)
      }
      break
    case 'error':
      if (data) {
        console.error(prefix, message, data)
      } else {
        console.error(prefix, message)
      }
      break
  }
}

/**
 * Create a scoped logger with automatic prefix
 *
 * @param scope - Scope name (e.g., 'WorkflowComponent', 'API')
 * @returns Scoped logging functions
 *
 * @example
 * ```ts
 * const logger = createLogger('ChatComponent')
 * logger.info('User sent message')
 * logger.error('Failed to connect', error)
 * ```
 */
export function createLogger(scope: string) {
  return {
    debug: (message: string, data?: any) => log('debug', `[${scope}] ${message}`, data),
    info: (message: string, data?: any) => log('info', `[${scope}] ${message}`, data),
    warn: (message: string, data?: any) => log('warn', `[${scope}] ${message}`, data),
    error: (message: string, data?: any) => log('error', `[${scope}] ${message}`, data)
  }
}

// ============================================================================
// Storage Utilities
// ============================================================================

/**
 * Get storage object by type
 *
 * @param type - Storage type (localStorage or sessionStorage)
 * @returns Storage object
 */
function getStorage(type: StorageType): Storage {
  return type === 'localStorage' ? localStorage : sessionStorage
}

/**
 * Safely get item from browser storage
 *
 * @param key - Storage key
 * @param type - Storage type (default: 'localStorage')
 * @returns Stored value or null if not found/error
 *
 * @example
 * ```ts
 * const settings = getStorageItem('chat_settings')
 * const tempData = getStorageItem('temp_data', 'sessionStorage')
 * ```
 */
export function getStorageItem(
  key: string,
  type: StorageType = 'localStorage'
): string | null {
  try {
    const storage = getStorage(type)
    return storage.getItem(key)
  } catch (e) {
    log('error', `Failed to get ${type} item: ${key}`, e)
    return null
  }
}

/**
 * Safely set item in browser storage
 *
 * @param key - Storage key
 * @param value - Value to store
 * @param type - Storage type (default: 'localStorage')
 * @returns Success status
 *
 * @example
 * ```ts
 * setStorageItem('chat_settings', JSON.stringify(settings))
 * setStorageItem('session_id', id, 'sessionStorage')
 * ```
 */
export function setStorageItem(
  key: string,
  value: string,
  type: StorageType = 'localStorage'
): boolean {
  try {
    const storage = getStorage(type)
    storage.setItem(key, value)
    return true
  } catch (e) {
    log('error', `Failed to set ${type} item: ${key}`, e)
    return false
  }
}

/**
 * Safely remove item from browser storage
 *
 * @param key - Storage key
 * @param type - Storage type (default: 'localStorage')
 * @returns Success status
 *
 * @example
 * ```ts
 * removeStorageItem('temp_data')
 * removeStorageItem('session_id', 'sessionStorage')
 * ```
 */
export function removeStorageItem(
  key: string,
  type: StorageType = 'localStorage'
): boolean {
  try {
    const storage = getStorage(type)
    storage.removeItem(key)
    return true
  } catch (e) {
    log('error', `Failed to remove ${type} item: ${key}`, e)
    return false
  }
}

/**
 * Clear all items from browser storage
 *
 * @param type - Storage type (default: 'localStorage')
 * @returns Success status
 *
 * @example
 * ```ts
 * clearStorage() // Clear localStorage
 * clearStorage('sessionStorage') // Clear sessionStorage
 * ```
 */
export function clearStorage(type: StorageType = 'localStorage'): boolean {
  try {
    const storage = getStorage(type)
    storage.clear()
    log('info', `${type} cleared successfully`)
    return true
  } catch (e) {
    log('error', `Failed to clear ${type}`, e)
    return false
  }
}

// ============================================================================
// JSON Utilities
// ============================================================================

/**
 * Safely parse JSON string
 *
 * @param jsonString - JSON string to parse
 * @param fallback - Fallback value if parsing fails
 * @returns Parsed object or fallback
 *
 * @example
 * ```ts
 * const settings = safeJsonParse(localStorage.getItem('settings'), {})
 * const config = safeJsonParse(response.data, null)
 * ```
 */
export function safeJsonParse<T = any>(
  jsonString: string | null,
  fallback: T
): T {
  if (!jsonString) {
    return fallback
  }

  try {
    return JSON.parse(jsonString) as T
  } catch (e) {
    log('error', 'JSON parse error', { jsonString, error: e })
    return fallback
  }
}

/**
 * Safely stringify object to JSON
 *
 * @param obj - Object to stringify
 * @param fallback - Fallback value if stringification fails
 * @returns JSON string or fallback
 *
 * @example
 * ```ts
 * const json = safeJsonStringify({ key: 'value' }, '{}')
 * localStorage.setItem('data', safeJsonStringify(data, '{}'))
 * ```
 */
export function safeJsonStringify(obj: any, fallback: string = '{}'): string {
  try {
    return JSON.stringify(obj)
  } catch (e) {
    log('error', 'JSON stringify error', { obj, error: e })
    return fallback
  }
}

/**
 * Get and parse JSON from storage
 *
 * @param key - Storage key
 * @param fallback - Fallback value if not found or invalid
 * @param type - Storage type (default: 'localStorage')
 * @returns Parsed object or fallback
 *
 * @example
 * ```ts
 * const settings = getStorageJson('chat_settings', {})
 * const session = getStorageJson('session', null, 'sessionStorage')
 * ```
 */
export function getStorageJson<T = any>(
  key: string,
  fallback: T,
  type: StorageType = 'localStorage'
): T {
  const item = getStorageItem(key, type)
  return safeJsonParse(item, fallback)
}

/**
 * Stringify and set JSON to storage
 *
 * @param key - Storage key
 * @param value - Value to store
 * @param type - Storage type (default: 'localStorage')
 * @returns Success status
 *
 * @example
 * ```ts
 * setStorageJson('chat_settings', { theme: 'dark' })
 * setStorageJson('session', sessionData, 'sessionStorage')
 * ```
 */
export function setStorageJson(
  key: string,
  value: any,
  type: StorageType = 'localStorage'
): boolean {
  const json = safeJsonStringify(value)
  if (json === null) {
    return false
  }
  return setStorageItem(key, json, type)
}

/**
 * Validate JSON structure in storage
 *
 * @param key - Storage key
 * @param type - Storage type (default: 'localStorage')
 * @returns Validation result
 *
 * @example
 * ```ts
 * const result = validateStorageJson('chat_settings')
 * if (!result.isValid) {
 *   console.error(result.error)
 * }
 * ```
 */
export function validateStorageJson(
  key: string,
  type: StorageType = 'localStorage'
): StorageValidationResult {
  const item = getStorageItem(key, type)

  if (!item) {
    return {
      isValid: false,
      key,
      error: 'Item not found in storage'
    }
  }

  try {
    const parsed = JSON.parse(item)
    return {
      isValid: true,
      key,
      value: parsed
    }
  } catch (e) {
    return {
      isValid: false,
      key,
      error: `Invalid JSON: ${(e as Error).message}`
    }
  }
}

// ============================================================================
// Vue.js Framework Detection
// ============================================================================

/**
 * Check for Vue.js framework presence and configuration
 *
 * @returns Framework detection results
 *
 * @example
 * ```ts
 * const vueCheck = checkVueFramework()
 * if (!vueCheck.vue3_app) {
 *   console.error('Vue 3 app not detected')
 * }
 * ```
 */
export function checkVueFramework(): VueFrameworkCheck {
  const w = window as any

  return {
    vue_available: typeof w.Vue !== 'undefined',
    vue3_app: typeof w.__VUE__ !== 'undefined',
    vite_client: typeof w.__vite_plugin_vue_export_helper !== 'undefined',
    app_instance: typeof w.app !== 'undefined',
    vue_devtools: typeof w.__VUE_DEVTOOLS_GLOBAL_HOOK__ !== 'undefined'
  }
}

/**
 * Log Vue.js framework status to console
 *
 * @example
 * ```ts
 * logVueFrameworkStatus() // Prints framework detection results
 * ```
 */
export function logVueFrameworkStatus(): void {
  const checks = checkVueFramework()

  console.log('🔍 Vue.js Framework Status:')
  console.log('  Vue available:', checks.vue_available)
  console.log('  Vue 3 app:', checks.vue3_app)
  console.log('  Vite client:', checks.vite_client)
  console.log('  App instance:', checks.app_instance)
  console.log('  Vue DevTools:', checks.vue_devtools)
}

// ============================================================================
// Performance Monitoring
// ============================================================================

/**
 * Get current performance metrics
 *
 * @returns Performance metrics object
 *
 * @example
 * ```ts
 * const metrics = getPerformanceMetrics()
 * console.log('Memory used:', metrics.memory?.usedJSHeapSize)
 * ```
 */
export function getPerformanceMetrics(): PerformanceMetrics {
  const metrics: PerformanceMetrics = {
    timestamp: Date.now()
  }

  // Memory metrics (if available)
  const perf = performance as any
  if (perf.memory) {
    metrics.memory = {
      usedJSHeapSize: perf.memory.usedJSHeapSize,
      totalJSHeapSize: perf.memory.totalJSHeapSize,
      jsHeapSizeLimit: perf.memory.jsHeapSizeLimit
    }
  }

  // Timing metrics
  if (performance.timing) {
    metrics.timing = {
      navigationStart: performance.timing.navigationStart,
      loadEventEnd: performance.timing.loadEventEnd,
      domContentLoadedEventEnd: performance.timing.domContentLoadedEventEnd
    }
  }

  return metrics
}

/**
 * Log performance metrics to console
 *
 * @example
 * ```ts
 * logPerformanceMetrics() // Prints current performance data
 * ```
 */
export function logPerformanceMetrics(): void {
  const metrics = getPerformanceMetrics()

  console.log('📊 Performance Metrics:')

  if (metrics.memory) {
    const usedMB = (metrics.memory.usedJSHeapSize / 1024 / 1024).toFixed(2)
    const totalMB = (metrics.memory.totalJSHeapSize / 1024 / 1024).toFixed(2)
    const limitMB = (metrics.memory.jsHeapSizeLimit / 1024 / 1024).toFixed(2)
    console.log(`  Memory: ${usedMB}MB / ${totalMB}MB (limit: ${limitMB}MB)`)
  }

  if (metrics.timing) {
    const loadTime = metrics.timing.loadEventEnd - metrics.timing.navigationStart
    const domTime = metrics.timing.domContentLoadedEventEnd - metrics.timing.navigationStart
    console.log(`  Page load time: ${loadTime}ms`)
    console.log(`  DOM load time: ${domTime}ms`)
  }
}

// ============================================================================
// Error Collection
// ============================================================================

/**
 * Global error collection array
 */
const collectedErrors: Array<{
  message: string
  stack?: string
  timestamp: number
}> = []

/**
 * Start collecting global errors
 *
 * @example
 * ```ts
 * startErrorCollection()
 * // Errors will be collected in background
 * const errors = getCollectedErrors()
 * ```
 */
export function startErrorCollection(): void {
  window.addEventListener('error', (event) => {
    collectedErrors.push({
      message: event.message,
      stack: event.error?.stack,
      timestamp: Date.now()
    })
  })

  window.addEventListener('unhandledrejection', (event) => {
    collectedErrors.push({
      message: `Unhandled Promise Rejection: ${event.reason}`,
      timestamp: Date.now()
    })
  })

  log('info', 'Error collection started')
}

/**
 * Get collected errors
 *
 * @returns Array of collected errors
 *
 * @example
 * ```ts
 * const errors = getCollectedErrors()
 * console.log(`Collected ${errors.length} errors`)
 * ```
 */
export function getCollectedErrors() {
  return [...collectedErrors]
}

/**
 * Clear collected errors
 *
 * @example
 * ```ts
 * clearCollectedErrors()
 * ```
 */
export function clearCollectedErrors(): void {
  collectedErrors.length = 0
  log('info', 'Collected errors cleared')
}

// ============================================================================
// Diagnostic Commands
// ============================================================================

/**
 * Run comprehensive diagnostics and log results
 *
 * @example
 * ```ts
 * runDiagnostics() // Prints full diagnostic report
 * ```
 */
export function runDiagnostics(): void {
  console.log('🔧 AutoBot Frontend Diagnostics')
  console.log('=' .repeat(60))

  // Vue.js framework
  logVueFrameworkStatus()
  console.log('')

  // Performance
  logPerformanceMetrics()
  console.log('')

  // Storage
  console.log('💾 Storage Status:')
  const settingsValid = validateStorageJson('chat_settings')
  console.log('  chat_settings:', settingsValid.isValid ? '✅ Valid' : '❌ Invalid')
  console.log('')

  // Collected errors
  const errors = getCollectedErrors()
  console.log(`⚠️ Collected Errors: ${errors.length}`)
  if (errors.length > 0) {
    errors.forEach((error, i) => {
      console.log(`  ${i + 1}. ${error.message}`)
    })
  }

  console.log('=' .repeat(60))
}

// ============================================================================
// Export All
// ============================================================================

export default {
  // Logging
  log,
  createLogger,

  // Storage
  getStorageItem,
  setStorageItem,
  removeStorageItem,
  clearStorage,

  // JSON
  safeJsonParse,
  safeJsonStringify,
  getStorageJson,
  setStorageJson,
  validateStorageJson,

  // Vue.js
  checkVueFramework,
  logVueFrameworkStatus,

  // Performance
  getPerformanceMetrics,
  logPerformanceMetrics,

  // Errors
  startErrorCollection,
  getCollectedErrors,
  clearCollectedErrors,

  // Diagnostics
  runDiagnostics
}
