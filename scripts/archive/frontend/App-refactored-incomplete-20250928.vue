<template>
  <div id="app" class="min-h-screen bg-gray-100 flex flex-col">
    <!-- Header -->
    <header class="bg-gradient-to-r from-indigo-600 to-purple-600 shadow-sm relative z-30">
      <div class="max-w-full mx-auto px-4 sm:px-6 lg:px-8">
        <div class="flex items-center justify-between h-16">
          <!-- Logo/Brand with System Status -->
          <div class="flex-shrink-0 flex items-center">
            <button
              @click="toggleSystemStatus"
              class="flex items-center space-x-3 hover:bg-indigo-500 rounded-lg px-2 py-1 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-white focus:ring-opacity-50"
              :title="getSystemStatusTooltip()"
            >
              <div class="relative w-8 h-8 bg-white rounded-lg flex items-center justify-center">
                <span class="text-indigo-600 font-bold text-sm">AB</span>
                <!-- System status indicator dot -->
                <div
                  :class="{
                    'bg-green-400': systemStatus.isHealthy && !systemStatus.hasIssues,
                    'bg-yellow-400': !systemStatus.isHealthy && !systemStatus.hasIssues,
                    'bg-red-400': systemStatus.hasIssues,
                    'animate-pulse': systemStatus.hasIssues
                  }"
                  class="absolute -top-1 -right-1 w-3 h-3 rounded-full border-2 border-white"
                ></div>
              </div>
              <span class="text-white font-bold text-lg hidden sm:block">AutoBot</span>
            </button>
          </div>

          <!-- Desktop Navigation -->
          <nav class="hidden lg:block">
            <div class="hidden lg:flex items-center space-x-8">
              <div class="flex items-center space-x-4">
                <router-link
                  v-for="route in navigationRoutes"
                  :key="route.path"
                  :to="route.path"
                  :class="{
                    'bg-white text-indigo-700': $route.path.startsWith(route.path),
                    'text-white hover:bg-indigo-500': !$route.path.startsWith(route.path)
                  }"
                  class="px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200"
                >
                  <div class="flex items-center space-x-1">
                    <component :is="route.icon" class="w-4 h-4" />
                    <span>{{ route.name }}</span>
                  </div>
                </router-link>
              </div>
            </div>
          </nav>

          <!-- Right side - Mobile menu button -->
          <div class="flex items-center space-x-4">
            <button
              @click="toggleMobileNav"
              class="lg:hidden inline-flex items-center justify-center p-2 rounded-md text-white hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-indigo-600 focus:ring-white"
              aria-controls="mobile-nav"
              aria-expanded="false"
            >
              <span class="sr-only">Open main menu</span>
              <svg class="block h-6 w-6" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      <!-- Mobile Navigation Panel -->
      <MobileNavigation
        :show="showMobileNav"
        :routes="navigationRoutes"
        @close="closeMobileNav"
      />
    </header>

    <!-- System Status Modal -->
    <SystemStatusModal
      :show="showSystemStatus"
      :system-status="systemStatus"
      :system-services="systemServices"
      :get-system-status-text="getSystemStatusText"
      :get-system-status-description="getSystemStatusDescription"
      @close="showSystemStatus = false"
      @refresh="refreshSystemStatus"
    />

    <!-- System Status Notifications -->
    <SystemStatusNotification
      v-for="notif in (appStore?.systemNotifications || []).filter(n => n.visible).slice(-5)"
      :key="`notification-${notif.id}`"
      :visible="notif.visible"
      :severity="notif.severity"
      :title="notif.title"
      :message="notif.message"
      :status-details="notif.statusDetails"
      :allow-dismiss="true"
      :show-details="notif.statusDetails ? true : false"
      :auto-hide="0"
      @dismiss="() => appStore?.removeSystemNotification(notif.id)"
      @expired="() => appStore?.removeSystemNotification(notif.id)"
      @hide="() => appStore?.removeSystemNotification(notif.id)"
      @remove="() => appStore?.removeSystemNotification(notif.id)"
    />

    <!-- Main Content Area with Router -->
    <main id="main-content" class="flex-1 overflow-hidden" role="main">
      <!-- Unified Loading System -->
      <UnifiedLoadingView
        loading-key="app-main"
        :has-content="!isLoading && !hasErrors"
        :on-retry="clearAllCaches"
        :auto-timeout-ms="15000"
        @loading-complete="handleLoadingComplete"
        @loading-error="handleLoadingError"
        @loading-timeout="handleLoadingTimeout"
        class="h-full"
      >
        <!-- Use router-view for all content to enable proper sub-routing -->
        <router-view class="h-full" />
      </UnifiedLoadingView>
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useAppStore } from '@/stores/useAppStore'

// Composables
import { useSystemStatus } from '@/composables/useSystemStatus.js'
import { useNavigation } from '@/composables/useNavigation.js'
import { useGlobalErrorHandler } from '@/composables/useGlobalErrorHandler.js'
import { useHealthMonitoring } from '@/composables/useHealthMonitoring.js'

// Components
import UnifiedLoadingView from '@/components/ui/UnifiedLoadingView.vue'
import SystemStatusNotification from '@/components/SystemStatusNotification.vue'
import MobileNavigation from '@/components/app/MobileNavigation.vue'
import SystemStatusModal from '@/components/app/SystemStatusModal.vue'

// SVG Icons (simplified - could be moved to a separate composable)
const navigationRoutes = [
  { path: '/chat', name: 'Chat', icon: 'chat-icon' },
  { path: '/knowledge', name: 'Knowledge', icon: 'knowledge-icon' },
  { path: '/secrets', name: 'Secrets', icon: 'secrets-icon' },
  { path: '/tools', name: 'Tools', icon: 'tools-icon' },
  { path: '/monitoring', name: 'Monitor', icon: 'monitor-icon' },
  { path: '/settings', name: 'Settings', icon: 'settings-icon' }
]

// Store references
const appStore = useAppStore()

// Use composables
const {
  systemStatus,
  systemServices,
  showSystemStatus,
  getSystemStatusTooltip,
  getSystemStatusText,
  getSystemStatusDescription,
  toggleSystemStatus,
  refreshSystemStatus,
  updateSystemStatus
} = useSystemStatus()

const {
  showMobileNav,
  toggleMobileNav,
  closeMobileNav
} = useNavigation()

const {
  handleGlobalError,
  handleLoadingComplete,
  handleLoadingError,
  handleLoadingTimeout,
  clearAllCaches
} = useGlobalErrorHandler()

const {
  initializeHealthMonitoring,
  cleanupHealthMonitoring
} = useHealthMonitoring()

// Computed properties
const isLoading = computed(() => appStore?.isLoading || false)
const hasErrors = computed(() => appStore?.errors?.length > 0 || false)
</script>

<style scoped>
/* Minimal styles - detailed styles moved to component files */
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.5s;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}

/* Smooth transitions for navigation state changes */
.transition-transform {
  transition-property: transform;
  transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1);
  transition-duration: 300ms;
}
</style>