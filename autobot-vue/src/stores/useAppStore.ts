import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { generateChatId } from '@/utils/ChatIdGenerator.js'

export type TabType = 'dashboard' | 'chat' | 'knowledge' | 'tools' | 'monitoring' | 'secrets'

export interface BackendStatus {
  text: string
  class: 'success' | 'warning' | 'error'
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

  // Global Loading States
  const isLoading = ref(false)
  const loadingMessage = ref('')

  // Error State
  const globalError = ref<string | null>(null)

  // Computed
  const isBackendHealthy = computed(() => backendStatus.value.class === 'success')
  const hasGlobalError = computed(() => globalError.value !== null)

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

  return {
    // State
    activeTab,
    navbarOpen,
    activeChatId,
    backendStatus,
    isLoading,
    loadingMessage,
    globalError,

    // Computed
    isBackendHealthy,
    hasGlobalError,

    // Actions
    updateRoute,
    toggleNavbar,
    updateBackendStatus,
    setLoading,
    setGlobalError,
    clearGlobalError,
    generateNewChatId
  }
}, {
  persist: {
    key: 'autobot-app-store',
    storage: localStorage,
    // Only persist UI state, not sensitive data
    paths: ['activeTab', 'activeChatId'],
    // Exclude backend status, loading states, and errors (they should be fresh on reload)
  }
})
