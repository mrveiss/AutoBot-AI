import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { generateChatId } from '@/utils/ChatIdGenerator.js'

// Issue #156 Fix: Changed 'desktop' to 'infrastructure' to match router routes
// Issue #545: Added 'analytics' for consolidated analytics section
// Issue #591: Added 'operations' for long-running operations tracker
export type TabType = 'chat' | 'infrastructure' | 'knowledge' | 'tools' | 'monitoring' | 'operations' | 'analytics' | 'secrets' | 'settings' | 'automation' | 'vision'

export interface BackendStatus {
  text: string
  class: 'success' | 'warning' | 'error'
}

export type NotificationLevel = 'toast' | 'banner' | 'modal'
export type SystemSeverity = 'info' | 'warning' | 'error' | 'success'

export interface NotificationSettings {
  enabled: boolean
  level: NotificationLevel
  position?: string
  warningMinLevel?: NotificationLevel
  errorMinLevel?: NotificationLevel
  criticalAsModal: boolean
  autoHideSuccess: number
  autoHideInfo: number
  autoHideWarning: number
  autoHide?: {
    success?: boolean
    info?: boolean
    warning?: boolean
    error?: boolean
  }
  autoHideDelay?: {
    success?: number
    info?: number
    warning?: number
    error?: number
  }
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
  position: 'top-right',
  warningMinLevel: 'banner',
  errorMinLevel: 'banner', // Changed from modal to be less intrusive by default
  criticalAsModal: true,
  autoHideSuccess: 5,
  autoHideInfo: 8,
  autoHideWarning: 15,
  autoHide: {
    success: true,
    info: true,
    warning: false,
    error: false
  },
  autoHideDelay: {
    success: 5,
    info: 8,
    warning: 15,
    error: 0
  },
  showDetails: false,
  soundEnabled: false
}

export const useAppStore = defineStore('app', () => {
  // State
  const activeTab = ref<TabType>('chat')
  const navShown = ref(false)
  const backendStatus = ref<BackendStatus>({
    text: 'Checking...',
    class: 'warning'
  })
  const connectedUsers = ref(0)
  const systemNotifications = ref<SystemNotification[]>([])
  const notificationSettings = ref<NotificationSettings>({ ...defaultNotificationSettings })
  const lastActivityCheck = ref(Date.now())
  // Issue #820: Track auto-hide timer IDs to prevent leaks on removal/reset
  const notificationTimers = new Map<string, ReturnType<typeof setTimeout>>()

  // Loading State
  const isLoading = ref(false)
  const loadingMessage = ref('')

  // Chat State
  const sessions = ref<{
    id: string
    title: string
    messages: {
      id: string
      content: string
      sender: 'user' | 'assistant' | 'system'
      timestamp: Date
      status?: 'sending' | 'sent' | 'error'
      type?: 'message' | 'command' | 'response' | 'error' | 'system' | 'file' | 'image' | 'code'
      attachments?: {
        name: string
        size: number
        type: string
        url?: string
        data?: string
      }[]
      metadata?: {
        model?: string
        tokens?: number
        processingTime?: number
        reasoning?: string
      }
    }[]
    status: 'active' | 'archived'
    lastActivity: Date
    summary?: string
    tags?: string[]
  }[]>([])

  const currentSessionId = ref<string | null>(null)

  // System status for status indicator
  const systemStatusIndicator = computed(() => {
    const errorNotification = systemNotifications.value.find(n => n.severity === 'error' && n.visible);
    const warningNotification = systemNotifications.value.find(n => n.severity === 'warning' && n.visible);

    if (errorNotification) {
      return {
        status: 'error',
        text: 'System errors detected',
        pulse: true,
        statusDetails: errorNotification.statusDetails
      }
    }
    if (warningNotification) {
      return {
        status: 'warning',
        text: 'System warnings',
        pulse: false,
        statusDetails: warningNotification.statusDetails
      }
    }
    if (backendStatus.value.class === 'success') {
      return { status: 'success', text: backendStatus.value.text, pulse: false }  // Use actual backend status text instead of generic message
    }
    return { status: 'warning', text: backendStatus.value.text, pulse: true }
  })

  // Getters
  const currentSession = computed(() => {
    if (!currentSessionId.value) return null
    return sessions.value.find(s => s.id === currentSessionId.value) || null
  })

  const activeSessions = computed(() => {
    return sessions.value.filter(s => s.status === 'active')
  })

  const recentSessions = computed(() => {
    return [...sessions.value]
      .sort((a, b) => b.lastActivity.getTime() - a.lastActivity.getTime())
      .slice(0, 10)
  })

  // Actions
  const setActiveTab = (tab: TabType) => {
    activeTab.value = tab
  }

  // Router integration - updates active tab from navigation and handles route changes
  const updateRoute = (tab: TabType, router?: any) => {
    // Update the active tab state
    setActiveTab(tab)

    // Handle router navigation if router is provided
    if (router) {
      // Issue #156 Fix: Changed 'desktop' to 'infrastructure' to match TabType and router routes
      // Issue #591: Added 'operations' and 'analytics' routes
      const routeMap: Record<TabType, string> = {
        'chat': '/chat',
        'infrastructure': '/infrastructure',
        'knowledge': '/knowledge',
        'secrets': '/secrets',
        'tools': '/tools',
        'monitoring': '/monitoring',
        'operations': '/operations',
        'analytics': '/analytics',
        'settings': '/settings',
        'automation': '/automation',
        'vision': '/vision'
      };

      const targetRoute = routeMap[tab];
      if (targetRoute && router.currentRoute.value.path !== targetRoute) {
        router.push(targetRoute);
      }
    }
  }

  const toggleNav = () => {
    navShown.value = !navShown.value
  }

  const setBackendStatus = (status: BackendStatus) => {
    backendStatus.value = status
    lastActivityCheck.value = Date.now()
  }

  const setConnectedUsers = (count: number) => {
    connectedUsers.value = count
  }

  const setLoading = (loading: boolean, message: string = '') => {
    isLoading.value = loading
    loadingMessage.value = message
  }

  // Chat Session Management
  const createNewSession = (title?: string) => {
    const sessionId = generateChatId()
    const newSession = {
      id: sessionId,
      title: title || `Chat ${sessions.value.length + 1}`,
      messages: [],
      status: 'active' as const,
      lastActivity: new Date(),
      tags: []
    }

    sessions.value.push(newSession)
    currentSessionId.value = sessionId
    return sessionId
  }

  const switchToSession = (sessionId: string) => {
    const session = sessions.value.find(s => s.id === sessionId)
    if (session) {
      currentSessionId.value = sessionId
      session.lastActivity = new Date()
    }
  }

  const updateSessionTitle = (sessionId: string, title: string) => {
    const session = sessions.value.find(s => s.id === sessionId)
    if (session) {
      session.title = title
    }
  }

  const archiveSession = (sessionId: string) => {
    const session = sessions.value.find(s => s.id === sessionId)
    if (session) {
      session.status = 'archived'
      if (currentSessionId.value === sessionId) {
        // Switch to most recent active session or create new one
        const activeSession = activeSessions.value[0]
        if (activeSession) {
          currentSessionId.value = activeSession.id
        } else {
          createNewSession()
        }
      }
    }
  }

  const deleteSession = (sessionId: string) => {
    const index = sessions.value.findIndex(s => s.id === sessionId)
    if (index !== -1) {
      sessions.value.splice(index, 1)
      if (currentSessionId.value === sessionId) {
        // Switch to most recent session or create new one
        const remainingSession = sessions.value.find(s => s.status === 'active')
        if (remainingSession) {
          currentSessionId.value = remainingSession.id
        } else {
          createNewSession()
        }
      }
    }
  }

  const addMessageToSession = (sessionId: string, message: any) => {
    const session = sessions.value.find(s => s.id === sessionId)
    if (session) {
      session.messages.push({
        ...message,
        timestamp: message.timestamp || new Date()
      })
      session.lastActivity = new Date()
    }
  }

  const updateMessageInSession = (sessionId: string, messageId: string, updates: any) => {
    const session = sessions.value.find(s => s.id === sessionId)
    if (session) {
      const messageIndex = session.messages.findIndex(m => m.id === messageId)
      if (messageIndex !== -1) {
        session.messages[messageIndex] = {
          ...session.messages[messageIndex],
          ...updates
        }
      }
    }
  }

  // System Notifications
  const addSystemNotification = (notification: Omit<SystemNotification, 'id' | 'visible' | 'timestamp'>) => {
    const newNotification: SystemNotification = {
      ...notification,
      id: `notification-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      visible: true,
      timestamp: Date.now()
    }

    systemNotifications.value.push(newNotification)

    // Auto-hide based on settings
    if (notificationSettings.value.enabled) {
      const hideDelay = getAutoHideDelay(notification.severity)
      if (hideDelay > 0) {
        // Issue #820: Store timer ID so it can be cleared on removal
        const timerId = setTimeout(() => {
          notificationTimers.delete(newNotification.id)
          hideSystemNotification(newNotification.id)
        }, hideDelay * 1000)
        notificationTimers.set(newNotification.id, timerId)
      }
    }

    return newNotification.id
  }

  const hideSystemNotification = (id: string) => {
    const notification = systemNotifications.value.find(n => n.id === id)
    if (notification) {
      notification.visible = false
    }
  }

  const removeSystemNotification = (id: string) => {
    // Issue #820: Clear auto-hide timer to prevent leak
    const timerId = notificationTimers.get(id)
    if (timerId) {
      clearTimeout(timerId)
      notificationTimers.delete(id)
    }
    const index = systemNotifications.value.findIndex(n => n.id === id)
    if (index !== -1) {
      systemNotifications.value.splice(index, 1)
    }
  }

  const clearAllNotifications = () => {
    // Issue #820: Clear all auto-hide timers to prevent leaks
    for (const timerId of notificationTimers.values()) {
      clearTimeout(timerId)
    }
    notificationTimers.clear()
    systemNotifications.value = []
  }

  const getAutoHideDelay = (severity: SystemSeverity): number => {
    if (!notificationSettings.value.autoHide) return 0

    switch (severity) {
      case 'success':
        return notificationSettings.value.autoHide.success ? (notificationSettings.value.autoHideDelay?.success || 5) : 0
      case 'info':
        return notificationSettings.value.autoHide.info ? (notificationSettings.value.autoHideDelay?.info || 8) : 0
      case 'warning':
        return notificationSettings.value.autoHide.warning ? (notificationSettings.value.autoHideDelay?.warning || 15) : 0
      case 'error':
        return notificationSettings.value.autoHide.error ? (notificationSettings.value.autoHideDelay?.error || 0) : 0
      default:
        return 0
    }
  }

  // Notification Settings
  const updateNotificationSettings = (updates: Partial<NotificationSettings>) => {
    notificationSettings.value = {
      ...notificationSettings.value,
      ...updates
    }
  }

  const resetNotificationSettings = () => {
    notificationSettings.value = { ...defaultNotificationSettings }
  }

  // Error handling method for legacy compatibility
  const setGlobalError = (message: string) => {
    addSystemNotification({
      title: 'Error',
      message,
      severity: 'error'
    })
  }

  // Initialize with a default session if none exists
  if (sessions.value.length === 0) {
    createNewSession('Welcome Chat')
  }

  return {
    // State
    activeTab,
    navShown,
    backendStatus,
    connectedUsers,
    systemNotifications,
    notificationSettings,
    lastActivityCheck,

    // Loading State
    isLoading,
    loadingMessage,

    // Chat State
    sessions,
    currentSessionId,

    // Computed
    systemStatusIndicator,
    currentSession,
    activeSessions,
    recentSessions,

    // Actions
    setActiveTab,
    updateRoute,
    toggleNav,
    setBackendStatus,
    setConnectedUsers,
    setLoading,
    setGlobalError,

    // Chat Actions
    createNewSession,
    switchToSession,
    updateSessionTitle,
    archiveSession,
    deleteSession,
    addMessageToSession,
    updateMessageInSession,

    // Notification Actions
    addSystemNotification,
    hideSystemNotification,
    removeSystemNotification,
    clearAllNotifications,
    updateNotificationSettings,
    resetNotificationSettings
  }
}, {
  persist: {
    key: 'autobot-app',
    storage: localStorage,
    paths: [
      'sessions',
      'currentSessionId',
      'notificationSettings',
      'activeTab'
    ]
  }
})
