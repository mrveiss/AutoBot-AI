/**
 * Chunk Loading Test Utility
 * Tests and validates chunk loading fixes in development and production modes
 */

export interface ChunkTestResult {
  success: boolean
  component: string
  loadTime: number
  error?: Error
  retryCount?: number
}

export interface ChunkTestSummary {
  totalTests: number
  passed: number
  failed: number
  results: ChunkTestResult[]
  averageLoadTime: number
}

/**
 * Test chunk loading for specific Vue components
 */
export async function testComponentChunkLoading(components: string[]): Promise<ChunkTestSummary> {
  console.log('[ChunkTest] Starting component chunk loading tests...')

  const results: ChunkTestResult[] = []

  for (const component of components) {
    console.log(`[ChunkTest] Testing ${component}...`)

    try {
      const startTime = Date.now()

      // Test based on component type
      let module: any

      if (component.includes('View')) {
        // Test view components
        module = await import(`@/views/${component}.vue`)
      } else if (component.includes('Component')) {
        // Test utility components
        module = await import(`@/components/${component}.vue`)
      } else {
        // Try dynamic import
        module = await import(`@/components/${component}.vue`)
      }

      const loadTime = Date.now() - startTime

      results.push({
        success: true,
        component,
        loadTime,
      })

      console.log(`[ChunkTest] ✅ ${component} loaded in ${loadTime}ms`)

    } catch (error) {
      console.error(`[ChunkTest] ❌ ${component} failed:`, error)

      results.push({
        success: false,
        component,
        loadTime: 0,
        error: error as Error
      })
    }
  }

  const passed = results.filter(r => r.success).length
  const failed = results.filter(r => !r.success).length
  const averageLoadTime = results
    .filter(r => r.success)
    .reduce((sum, r) => sum + r.loadTime, 0) / (passed || 1)

  const summary: ChunkTestSummary = {
    totalTests: results.length,
    passed,
    failed,
    results,
    averageLoadTime
  }

  console.log('[ChunkTest] Test Summary:', summary)

  return summary
}

/**
 * Test async component error recovery
 */
export async function testAsyncComponentErrorRecovery(): Promise<boolean> {
  console.log('[ChunkTest] Testing async component error recovery...')

  try {
    // Import the async component helpers
    const { AsyncComponentErrorRecovery } = await import('./asyncComponentHelpers')

    // Test error recovery statistics
    const stats = AsyncComponentErrorRecovery.getStats()
    console.log('[ChunkTest] Error recovery stats:', stats)

    // Test marking components as failed and recovering
    AsyncComponentErrorRecovery.markAsFailed('TestComponent')
    AsyncComponentErrorRecovery.incrementRetry('TestComponent')

    const hasFailed = AsyncComponentErrorRecovery.hasFailed('TestComponent')
    const retryCount = AsyncComponentErrorRecovery.getRetryCount('TestComponent')

    console.log('[ChunkTest] Test component failure tracking:', { hasFailed, retryCount })

    // Reset test state
    AsyncComponentErrorRecovery.reset('TestComponent')

    return hasFailed && retryCount === 1
  } catch (error) {
    console.error('[ChunkTest] Error recovery test failed:', error)
    return false
  }
}

/**
 * Test cache management functionality
 */
export async function testCacheManagement(): Promise<boolean> {
  console.log('[ChunkTest] Testing cache management...')

  try {
    // Import cache management utilities
    const { showCacheUpdateNotification } = await import('./cacheManagement')

    // Test notification system (briefly)
    showCacheUpdateNotification('Testing cache management system...', 'info')

    // Auto-remove test notification after 2 seconds
    setTimeout(() => {
      const testNotifications = document.querySelectorAll('.cache-notification')
      testNotifications.forEach(notification => {
        if (notification.textContent?.includes('Testing cache management')) {
          notification.remove()
        }
      })
    }, 2000)

    console.log('[ChunkTest] ✅ Cache management system is functional')
    return true
  } catch (error) {
    console.error('[ChunkTest] ❌ Cache management test failed:', error)
    return false
  }
}

/**
 * Comprehensive chunk loading test suite
 */
export async function runComprehensiveChunkTests(): Promise<void> {
  console.log('[ChunkTest] Starting comprehensive chunk loading tests...')

  // Test common Vue view components
  const viewComponents = [
    'ChatView',
    'ToolsView',
    'MonitoringView',
    'SettingsView',
    'KnowledgeView'
  ]

  try {
    // Test component chunk loading
    const chunkResults = await testComponentChunkLoading(viewComponents)

    // Test async component error recovery
    const errorRecoveryWorks = await testAsyncComponentErrorRecovery()

    // Test cache management
    const cacheManagementWorks = await testCacheManagement()

    // Create test report
    const report = {
      timestamp: new Date().toISOString(),
      chunkLoading: chunkResults,
      errorRecovery: errorRecoveryWorks,
      cacheManagement: cacheManagementWorks,
      overallSuccess: chunkResults.failed === 0 && errorRecoveryWorks && cacheManagementWorks
    }

    console.log('[ChunkTest] Comprehensive test report:', report)

    // Show user-friendly summary
    if (report.overallSuccess) {
      console.log('[ChunkTest] 🎉 All chunk loading tests passed!')

      if (typeof window !== 'undefined' && window.confirm) {
        const shouldShowDetails = confirm('All chunk loading tests passed! Would you like to see detailed results?')
        if (shouldShowDetails) {
          console.table(chunkResults.results)
        }
      }
    } else {
      console.warn('[ChunkTest] ⚠️ Some chunk loading tests failed!')
      console.table(chunkResults.results.filter(r => !r.success))
    }

    // Store test results for debugging
    if (typeof window !== 'undefined') {
      (window as any).__chunkTestResults = report
      console.log('[ChunkTest] Test results stored in window.__chunkTestResults')
    }

  } catch (error) {
    console.error('[ChunkTest] Comprehensive test suite failed:', error)
  }
}

/**
 * Quick validation that chunk loading fixes are working
 */
export async function quickChunkValidation(): Promise<boolean> {
  console.log('[ChunkTest] Running quick chunk validation...')

  try {
    // Test importing a few key components
    const tests = [
      () => import('@/utils/asyncComponentHelpers'),
      () => import('@/utils/cacheManagement'),
      () => import('@/components/async/AsyncComponentWrapper.vue'),
      () => import('@/components/async/AsyncErrorFallback.vue')
    ]

    const results = await Promise.allSettled(tests)
    const failures = results.filter(r => r.status === 'rejected')

    if (failures.length === 0) {
      console.log('[ChunkTest] ✅ Quick validation passed - all key modules loaded successfully')
      return true
    } else {
      console.error('[ChunkTest] ❌ Quick validation failed:', failures)
      return false
    }

  } catch (error) {
    console.error('[ChunkTest] Quick validation error:', error)
    return false
  }
}

// Export for browser console testing
if (typeof window !== 'undefined') {
  (window as any).chunkTest = {
    runComprehensive: runComprehensiveChunkTests,
    quickValidation: quickChunkValidation,
    testComponents: testComponentChunkLoading,
    testErrorRecovery: testAsyncComponentErrorRecovery,
    testCacheManagement: testCacheManagement
  }

  console.log('[ChunkTest] Test utilities available in window.chunkTest')
}