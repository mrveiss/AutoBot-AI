/**
 * Global Error Handler Composable
 * Extracted from App.vue for better maintainability
 */

import { onMounted, onUnmounted } from 'vue'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for useGlobalErrorHandler
const logger = createLogger('useGlobalErrorHandler')
import { useAppStore } from '@/stores/useAppStore'
import { useChatStore } from '@/stores/useChatStore'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import { showSubtleErrorNotification } from '@/utils/cacheManagement'

export function useGlobalErrorHandler() {
  const appStore = useAppStore()
  const chatStore = useChatStore()
  const knowledgeStore = useKnowledgeStore()

  const handleGlobalError = (error) => {
    logger.error('Global error:', error)

    // Extract error message
    const errorMessage = error.message || 'An unexpected error occurred'

    // Determine if this is a chat-related error
    const isChatError = errorMessage.includes('Failed to save chat') ||
                       errorMessage.includes('chat') ||
                       errorMessage.includes('Chat')

    // Determine if this is a network error
    const isNetworkError = errorMessage.includes('HTTP 500') ||
                          errorMessage.includes('Internal Server Error') ||
                          errorMessage.includes('Failed to fetch') ||
                          errorMessage.includes('Network Error')

    // Determine if this is a critical system error
    const isCriticalError = errorMessage.includes('Fatal') ||
                           errorMessage.includes('System failure') ||
                           errorMessage.includes('Cannot recover') ||
                           errorMessage.includes('Application crash')

    // Use appropriate title based on error type
    let title = 'Application Error'
    let severity = 'error'

    if (isChatError) {
      title = isNetworkError ? 'Chat Save Failed' : 'Chat Error'
      // Don't show network errors as critical - they're temporary
      severity = isNetworkError ? 'warning' : 'error'
    } else if (isNetworkError) {
      title = 'Connection Issue'
      severity = 'warning'
    }

    // ALWAYS use subtle notification for ALL errors (non-intrusive)
    showSubtleErrorNotification(title, errorMessage, severity)

    // ONLY add to system notifications (intrusive) for CRITICAL SYSTEM ERRORS
    // Do NOT add chat errors, network errors, or routine errors to systemNotifications
    if (isCriticalError && appStore && typeof appStore.addSystemNotification === 'function') {
      appStore.addSystemNotification({
        severity: 'error',
        title: title,
        message: errorMessage
      })
    }
  }

  // Unified loading event handlers
  const handleLoadingComplete = () => {
    if (appStore && typeof appStore.setLoading === 'function') {
      appStore.setLoading(false)
    }
  }

  const handleLoadingError = (error) => {
    logger.error('[App] Loading error:', error)
    handleGlobalError(new Error(error))
  }

  const handleLoadingTimeout = () => {
    logger.warn('[App] Loading timed out - continuing with available content')

    // Use subtle notification for timeout warnings (non-intrusive)
    showSubtleErrorNotification(
      'Loading Timeout',
      'Some components took longer than expected to load, but the application is ready to use.',
      'warning'
    )

    // Do NOT add loading timeouts to systemNotifications - they're not critical
    // The subtle notification is sufficient
  }

  const clearAllCaches = async () => {
    try {
      // Clear all stores
      if (appStore && typeof appStore.clearAllNotifications === 'function') {
        appStore.clearAllNotifications()
      }
      if (chatStore && typeof chatStore.clearAllSessions === 'function') {
        chatStore.clearAllSessions()
      }
      if (knowledgeStore && typeof knowledgeStore.clearCache === 'function') {
        knowledgeStore.clearCache()
      }

      // Reload the page
      window.location.reload()
    } catch (error) {
      logger.error('Error clearing caches:', error)
    }
  }

  // Set up global error handling
  const setupErrorHandlers = () => {
    // Set up global error handling
    window.addEventListener('error', (event) => {
      handleGlobalError(event.error || event)
    })

    window.addEventListener('unhandledrejection', (event) => {
      handleGlobalError(event.reason)
    })
  }

  const cleanupErrorHandlers = () => {
    // Note: In practice, we might want to store references to the actual handlers
    // for proper cleanup, but for App.vue this isn't critical since it's the root component
  }

  onMounted(() => {
    setupErrorHandlers()
  })

  onUnmounted(() => {
    cleanupErrorHandlers()
  })

  return {
    // Error handlers
    handleGlobalError,
    handleLoadingComplete,
    handleLoadingError,
    handleLoadingTimeout,
    clearAllCaches
  }
}