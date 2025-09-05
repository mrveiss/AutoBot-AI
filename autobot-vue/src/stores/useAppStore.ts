import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { generateChatId } from '@/utils/ChatIdGenerator.js'

export type TabType = 'dashboard' | 'chat' | 'knowledge' | 'tools' | 'monitoring' | 'settings'

export interface BackendStatus {
  text: string
  class: 'success' | 'warning' | 'error'
}

export type NotificationLevel = 'toast' | 'banner' | 'modal'
export type SystemSeverity = 'info' | 'warning' | 'error' | 'success'

export interface NotificationSettings {
  enabled: boolean
  level: NotificationLevel
  warningMinLevel?: NotificationLevel
  errorMinLevel?: NotificationLevel
  criticalAsModal: boolean
  autoHideSuccess: number
  autoHideInfo: number
  autoHideWarning: number
  showDetails: boolean
  soundEnabled: boolean
}

export interface SystemStatusDetails {
  status: string
  lastCheck: number
  consecutiveFailures?: number
  error?: string
  timestamp: number
}

export interface SystemNotification {
  id: string
  severity: SystemSeverity
  title: string
  message: string
  visible: boolean
  statusDetails?: SystemStatusDetails
  timestamp: number
}

const defaultNotificationSettings: NotificationSettings = {
  enabled: true,
  level: 'banner',
  warningMinLevel: 'banner',
  errorMinLevel: 'banner', // Changed from modal to be less intrusive by default
  criticalAsModal: false, // Changed to false to respect user preference
  autoHideSuccess: 5000,
  autoHideInfo: 8000,
  autoHideWarning: 0, // Don't auto-hide warnings
  showDetails: true,
  soundEnabled: false
}

export const useAppStore = defineStore('app', () => {
  // Navigation and UI State
  const activeTab = ref<TabType>('dashboard')
  const navbarOpen = ref(false)
  const activeChatId = ref(generateChatId())

  // Backend Status and Health
  const backendStatus = ref<BackendStatus>({
    text: 'Checking...',
    class: 'warning'
  })

  // System Status and Notifications
  const isSystemDown = ref(false)
  const systemDownMessage = ref('')
  const lastSuccessfulCheck = ref(Date.now())
  const systemNotifications = ref<SystemNotification[]>([])
  const notificationSettings = ref<NotificationSettings>({ ...defaultNotificationSettings })

  // Global Loading States
  const isLoading = ref(false)
  const loadingMessage = ref('')

  // Error State
  const globalError = ref<string | null>(null)

  // Computed
  const isBackendHealthy = computed(() => backendStatus.value.class === 'success')
  const hasGlobalError = computed(() => globalError.value !== null)
  const hasActiveNotifications = computed(() => systemNotifications.value.some(n => n.visible))
  const currentSystemNotification = computed(() => 
    systemNotifications.value.find(n => n.visible && n.severity !== 'success')
  )
  const systemStatusIndicator = computed(() => {
    if (isSystemDown.value) return { status: 'error', text: 'System Down', pulse: true }
    if (!isBackendHealthy.value) return { status: 'warning', text: 'Checking...', pulse: false }
    if (hasActiveNotifications.value) return { status: 'warning', text: 'Issues', pulse: false }
    return { status: 'success', text: 'Healthy', pulse: false }
  })

  // Actions
  function updateRoute(tab: TabType) {
    activeTab.value = tab
    navbarOpen.value = false
  }

  function toggleNavbar() {
    navbarOpen.value = !navbarOpen.value
  }

  function updateBackendStatus(status: BackendStatus) {
    backendStatus.value = status
  }

  function setLoading(loading: boolean, message = '') {
    isLoading.value = loading
    loadingMessage.value = message
  }

  function setGlobalError(error: string | null) {
    globalError.value = error
  }

  function clearGlobalError() {
    globalError.value = null
  }

  function generateNewChatId() {
    activeChatId.value = generateChatId()
    return activeChatId.value
  }

  // System Status and Notification Methods
  function updateSystemStatus(isDown: boolean, message = '', details?: SystemStatusDetails) {
    isSystemDown.value = isDown
    systemDownMessage.value = message
    
    if (isDown) {
      addSystemNotification({
        severity: 'error',
        title: 'System Status Alert',
        message: message || 'AutoBot system is experiencing issues',
        statusDetails: details
      })
    } else {
      // Clear system down notifications when system recovers
      systemNotifications.value = systemNotifications.value.filter(n => 
        !(n.severity === 'error' && n.title.includes('System Status'))
      )
      
      // Add recovery notification
      if (systemNotifications.value.length > 0) {
        addSystemNotification({
          severity: 'success',
          title: 'System Recovered',
          message: 'AutoBot system is back online and functioning normally',
          statusDetails: {
            status: 'Online',
            lastCheck: Date.now(),
            timestamp: Date.now()
          }
        })
      }
    }
    
    if (details) {
      lastSuccessfulCheck.value = details.lastCheck
    }
  }

  function addSystemNotification(notification: Omit<SystemNotification, 'id' | 'visible' | 'timestamp'>) {
    const id = `notification_${Date.now()}_${Math.random().toString(36).substring(2, 11)}`
    const newNotification: SystemNotification = {
      ...notification,
      id,
      visible: true,
      timestamp: Date.now()
    }
    
    // Remove duplicate notifications (same title and severity)
    systemNotifications.value = systemNotifications.value.filter(n => 
      !(n.title === notification.title && n.severity === notification.severity)
    )
    
    // Add new notification
    systemNotifications.value.push(newNotification)
    
    // Auto-hide success notifications
    if (notification.severity === 'success' && notificationSettings.value.autoHideSuccess > 0) {
      setTimeout(() => {
        dismissNotification(id)
      }, notificationSettings.value.autoHideSuccess)
    }
    
    // Auto-hide info notifications
    if (notification.severity === 'info' && notificationSettings.value.autoHideInfo > 0) {
      setTimeout(() => {
        dismissNotification(id)
      }, notificationSettings.value.autoHideInfo)
    }
    
    // Auto-hide warning notifications if configured
    if (notification.severity === 'warning' && notificationSettings.value.autoHideWarning > 0) {
      setTimeout(() => {
        dismissNotification(id)
      }, notificationSettings.value.autoHideWarning)
    }
  }

  function dismissNotification(id: string) {
    const notification = systemNotifications.value.find(n => n.id === id)
    if (notification) {
      notification.visible = false
    }
    
    // Clean up old notifications after 5 minutes
    setTimeout(() => {
      systemNotifications.value = systemNotifications.value.filter(n => n.id !== id)
    }, 5 * 60 * 1000)
  }

  function clearAllNotifications() {
    systemNotifications.value.forEach(n => n.visible = false)
    setTimeout(() => {
      systemNotifications.value = []
    }, 1000) // Allow animations to complete
  }

  function updateNotificationSettings(settings: Partial<NotificationSettings>) {
    notificationSettings.value = { ...notificationSettings.value, ...settings }
  }

  function resetNotificationSettings() {
    notificationSettings.value = { ...defaultNotificationSettings }
  }

  return {
    // State
    activeTab,
    navbarOpen,
    activeChatId,
    backendStatus,
    isLoading,
    loadingMessage,
    globalError,
    isSystemDown,
    systemDownMessage,
    lastSuccessfulCheck,
    systemNotifications,
    notificationSettings,

    // Computed
    isBackendHealthy,
    hasGlobalError,
    hasActiveNotifications,
    currentSystemNotification,
    systemStatusIndicator,

    // Actions
    updateRoute,
    toggleNavbar,
    updateBackendStatus,
    setLoading,
    setGlobalError,
    clearGlobalError,
    generateNewChatId,
    updateSystemStatus,
    addSystemNotification,
    dismissNotification,
    clearAllNotifications,
    updateNotificationSettings,
    resetNotificationSettings
  }
}, {
  persist: {
    key: 'autobot-app-store',
    storage: localStorage,
    // Persist UI state and user preferences
    paths: ['activeTab', 'activeChatId', 'notificationSettings'],
    // Exclude dynamic state like notifications, status, loading states
  }
})