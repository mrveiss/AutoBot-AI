/**
 * Global Error Handler Composable
 * Extracted from App.vue for better maintainability
 */

import { onMounted, onUnmounted } from 'vue'
import { useAppStore } from '@/stores/useAppStore'
import { useChatStore } from '@/stores/useChatStore'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'

export function useGlobalErrorHandler() {
  const appStore = useAppStore()
  const chatStore = useChatStore()
  const knowledgeStore = useKnowledgeStore()

  const handleGlobalError = (error) => {
    console.error('Global error:', error)
    if (appStore && typeof appStore.addSystemNotification === 'function') {
      appStore.addSystemNotification({
        severity: 'error',
        title: 'Application Error',
        message: error.message || 'An unexpected error occurred'
      })
    }
  }

  // Unified loading event handlers
  const handleLoadingComplete = () => {
    console.log('[App] Loading completed successfully')
    if (appStore && typeof appStore.setLoading === 'function') {
      appStore.setLoading(false)
    }
  }

  const handleLoadingError = (error) => {
    console.error('[App] Loading error:', error)
    handleGlobalError(new Error(error))
  }

  const handleLoadingTimeout = () => {
    console.warn('[App] Loading timed out - continuing with available content')
    if (appStore && typeof appStore.addSystemNotification === 'function') {
      appStore.addSystemNotification({
        severity: 'warning',
        title: 'Loading Timeout',
        message: 'Some components took longer than expected to load, but the application is ready to use.'
      })
    }
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
      console.error('Error clearing caches:', error)
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