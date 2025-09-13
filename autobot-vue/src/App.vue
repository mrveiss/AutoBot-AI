<template>
  <div id="app" class="min-h-screen bg-gray-100 flex flex-col">
    <!-- Header -->
    <header class="bg-gradient-to-r from-indigo-600 to-purple-600 shadow-sm relative z-30">
      <div class="max-w-full mx-auto px-4 sm:px-6 lg:px-8">
        <div class="flex items-center justify-between h-16">
          <!-- Logo/Brand -->
          <div class="flex-shrink-0 flex items-center">
            <div class="flex items-center space-x-3">
              <div class="w-8 h-8 bg-white rounded-lg flex items-center justify-center">
                <span class="text-indigo-600 font-bold text-sm">AB</span>
              </div>
              <span class="text-white font-bold text-lg hidden sm:block">AutoBot</span>
            </div>
          </div>

          <!-- Desktop Navigation -->
          <nav class="hidden lg:block">
            <div class="hidden lg:flex items-center space-x-8">
              <div class="flex items-center space-x-4">
                <router-link
                  to="/chat"
                  :class="{ 
                    'bg-white text-indigo-700': $route.path.startsWith('/chat'),
                    'text-white hover:bg-indigo-500': !$route.path.startsWith('/chat')
                  }"
                  class="px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200"
                >
                  <div class="flex items-center space-x-1">
                    <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                      <path fill-rule="evenodd" d="M18 10c0 3.866-3.582 7-8 7a8.841 8.841 0 01-4.083-.98L2 17l1.338-3.123C2.493 12.767 2 11.434 2 10c0-3.866 3.582-7 8-7s8 3.134 8 7zM7 9H5v2h2V9zm8 0h-2v2h2V9zM9 9h2v2H9V9z" clip-rule="evenodd"></path>
                    </svg>
                    <span>Chat</span>
                  </div>
                </router-link>
                
                <router-link
                  to="/knowledge"
                  :class="{
                    'bg-white text-indigo-700': $route.path.startsWith('/knowledge'),
                    'text-white hover:bg-indigo-500': !$route.path.startsWith('/knowledge')
                  }"
                  class="px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200"
                >
                  <div class="flex items-center space-x-1">
                    <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                      <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                    <span>Knowledge</span>
                  </div>
                </router-link>
                
                <router-link
                  to="/secrets"
                  :class="{
                    'bg-white text-indigo-700': $route.path.startsWith('/secrets'),
                    'text-white hover:bg-indigo-500': !$route.path.startsWith('/secrets')
                  }"
                  class="px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200"
                >
                  <div class="flex items-center space-x-1">
                    <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                      <path fill-rule="evenodd" d="M18 8a6 6 0 01-7.743 5.743L10 14l-1 1-1 1H6v2H2v-4l4.257-4.257A6 6 0 1118 8zm-6-4a1 1 0 100 2 2 2 0 012 2 1 1 0 102 0 4 4 0 00-4-4z" clip-rule="evenodd"></path>
                    </svg>
                    <span>Secrets</span>
                  </div>
                </router-link>
                
                <router-link
                  to="/tools"
                  :class="{
                    'bg-white text-indigo-700': $route.path.startsWith('/tools'),
                    'text-white hover:bg-indigo-500': !$route.path.startsWith('/tools')
                  }"
                  class="px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200"
                >
                  <div class="flex items-center space-x-1">
                    <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                      <path fill-rule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd"></path>
                    </svg>
                    <span>Tools</span>
                  </div>
                </router-link>
                
                <router-link
                  to="/monitoring"
                  :class="{
                    'bg-white text-indigo-700': $route.path.startsWith('/monitoring'),
                    'text-white hover:bg-indigo-500': !$route.path.startsWith('/monitoring')
                  }"
                  class="px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200"
                >
                  <div class="flex items-center space-x-1">
                    <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                      <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                    </svg>
                    <span>Monitor</span>
                  </div>
                </router-link>

                <router-link
                  to="/settings"
                  :class="{
                    'bg-white text-indigo-700': $route.path.startsWith('/settings'),
                    'text-white hover:bg-indigo-500': !$route.path.startsWith('/settings')
                  }"
                  class="px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200"
                >
                  <div class="flex items-center space-x-1">
                    <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                      <path fill-rule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd"></path>
                    </svg>
                    <span>Settings</span>
                  </div>
                </router-link>
              </div>
            </div>
          </nav>

          <!-- Right side - Status and controls -->
          <div class="flex items-center space-x-4">
            <SystemStatusIndicator />
            <RumDashboard />
            
            <!-- Mobile menu button -->
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
      <Transition
        enter-active-class="transition duration-300 ease-out"
        enter-from-class="transform -translate-y-full opacity-0"
        enter-to-class="transform translate-y-0 opacity-100"
        leave-active-class="transition duration-200 ease-in"
        leave-from-class="transform translate-y-0 opacity-100"
        leave-to-class="transform -translate-y-full opacity-0"
      >
        <div 
          v-show="showMobileNav"
          id="mobile-nav"
          class="lg:hidden absolute top-full left-0 right-0 bg-gradient-to-r from-indigo-600 to-purple-600 shadow-lg z-20"
        >
          <div class="px-4 py-3 space-y-2">
            <router-link
              to="/chat"
              @click="closeMobileNav"
              :class="{ 
                'bg-white text-indigo-700': $route.path.startsWith('/chat'),
                'text-white hover:bg-indigo-600': !$route.path.startsWith('/chat')
              }"
              class="w-full text-left px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200 block"
            >
              <div class="flex items-center space-x-2">
                <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                  <path fill-rule="evenodd" d="M18 10c0 3.866-3.582 7-8 7a8.841 8.841 0 01-4.083-.98L2 17l1.338-3.123C2.493 12.767 2 11.434 2 10c0-3.866 3.582-7 8-7s8 3.134 8 7zM7 9H5v2h2V9zm8 0h-2v2h2V9zM9 9h2v2H9V9z" clip-rule="evenodd"></path>
                </svg>
                <span>Chat</span>
              </div>
            </router-link>
            
            <router-link
              to="/knowledge"
              @click="closeMobileNav"
              :class="{
                'bg-white text-indigo-700': $route.path.startsWith('/knowledge'),
                'text-white hover:bg-indigo-600': !$route.path.startsWith('/knowledge')
              }"
              class="w-full text-left px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200 block"
            >
              <div class="flex items-center space-x-2">
                <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                  <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                </svg>
                <span>Knowledge</span>
              </div>
            </router-link>
            
            <router-link
              to="/secrets"
              @click="closeMobileNav"
              :class="{
                'bg-white text-indigo-700': $route.path.startsWith('/secrets'),
                'text-white hover:bg-indigo-600': !$route.path.startsWith('/secrets')
              }"
              class="w-full text-left px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200 block"
            >
              <div class="flex items-center space-x-2">
                <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                  <path fill-rule="evenodd" d="M18 8a6 6 0 01-7.743 5.743L10 14l-1 1-1 1H6v2H2v-4l4.257-4.257A6 6 0 1118 8zm-6-4a1 1 0 100 2 2 2 0 012 2 1 1 0 102 0 4 4 0 00-4-4z" clip-rule="evenodd"></path>
                </svg>
                <span>Secrets</span>
              </div>
            </router-link>
            
            <router-link
              to="/tools"
              @click="closeMobileNav"
              :class="{
                'bg-white text-indigo-700': $route.path.startsWith('/tools'),
                'text-white hover:bg-indigo-600': !$route.path.startsWith('/tools')
              }"
              class="w-full text-left px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200 block"
            >
              <div class="flex items-center space-x-2">
                <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                  <path fill-rule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd"></path>
                </svg>
                <span>Tools</span>
              </div>
            </router-link>
            
            <router-link
              to="/monitoring"
              @click="closeMobileNav"
              :class="{
                'bg-white text-indigo-700': $route.path.startsWith('/monitoring'),
                'text-white hover:bg-indigo-600': !$route.path.startsWith('/monitoring')
              }"
              class="w-full text-left px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200 block"
            >
              <div class="flex items-center space-x-2">
                <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                  <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                </svg>
                <span>Monitor</span>
              </div>
            </router-link>

            <router-link
              to="/settings"
              @click="closeMobileNav"
              :class="{
                'bg-white text-indigo-700': $route.path.startsWith('/settings'),
                'text-white hover:bg-indigo-600': !$route.path.startsWith('/settings')
              }"
              class="w-full text-left px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200 block"
            >
              <div class="flex items-center space-x-2">
                <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                  <path fill-rule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd"></path>
                </svg>
                <span>Settings</span>
              </div>
            </router-link>
          </div>
        </div>
      </Transition>

      <!-- Click overlay to close mobile nav -->
      <div 
        v-if="showMobileNav"
        @click="showMobileNav = false"
        class="lg:hidden fixed inset-0 bg-black bg-opacity-25 z-10"
      ></div>
    </header>

    <!-- System Status Notifications (limit to last 5 to prevent teleport accumulation) -->
    <SystemStatusNotification
      v-for="notification in (appStore?.systemNotifications || []).filter(n => n.visible).slice(-5)"
      :key="notification.id"
      :visible="notification.visible || true"
      :severity="notification.severity || 'info'"
      :title="notification.title || 'Notification'"
      :message="notification.message || ''"
      :status-details="notification.statusDetails"
      :allow-dismiss="notification.allowDismiss !== false"
      :show-details="notification.showDetails || false"
      :auto-hide="notification.autoHide || 0"
      @dismiss="() => appStore?.hideSystemNotification(notification.id)"
      @expired="() => appStore?.removeSystemNotification(notification.id)"
    />

    <!-- Main Content Area with Router -->
    <main id="main-content" class="flex-1 overflow-hidden" role="main">
      <!-- Loading Screen -->
      <div v-if="isLoading" class="flex items-center justify-center h-full">
        <div class="text-center">
          <div class="animate-spin rounded-full h-32 w-32 border-b-2 border-indigo-600 mx-auto mb-4"></div>
          <p class="text-gray-600">Loading AutoBot...</p>
        </div>
      </div>

      <!-- Error Screen -->
      <div v-else-if="hasErrors" class="flex items-center justify-center h-full">
        <div class="text-center">
          <div class="text-red-500 mb-4">
            <svg class="w-16 h-16 mx-auto" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
              <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd"></path>
            </svg>
          </div>
          <h2 class="text-xl font-semibold text-gray-900 mb-2">System Error</h2>
          <p class="text-gray-600 mb-4">An error occurred while loading AutoBot.</p>
          <button 
            @click="clearAllCaches"
            class="bg-indigo-600 text-white px-4 py-2 rounded-md hover:bg-indigo-700 transition-colors duration-200"
          >
            Refresh System
          </button>
        </div>
      </div>

      <!-- Use router-view for all content to enable proper sub-routing -->
      <router-view v-else class="h-full" />
    </main>
  </div>
</template>

<script>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import { useAppStore } from '@/stores/useAppStore'
import { useChatStore } from '@/stores/useChatStore'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import SystemStatusNotification from '@/components/SystemStatusNotification.vue';
import SystemStatusIndicator from '@/components/SystemStatusIndicator.vue';
import RumDashboard from '@/components/RumDashboard.vue';
import { cacheBuster } from '@/utils/CacheBuster.js';
import { routerHealthMonitor } from '@/utils/RouterHealthMonitor.js';
import { frontendHealthMonitor } from '@/utils/FrontendHealthMonitor.js';

export default {
  name: 'App',
  
  components: {
    SystemStatusNotification,
    SystemStatusIndicator,
    RumDashboard,
  },
  
  setup() {
    // Store references
    const appStore = useAppStore();
    const chatStore = useChatStore();
    const knowledgeStore = useKnowledgeStore();
    const router = useRouter();
    
    // Reactive data
    const showMobileNav = ref(false);

    let systemHealthCheck = null;
    let notificationCleanup = null;

    // Computed properties
    const isLoading = computed(() => appStore?.isLoading || false);
    const hasErrors = computed(() => appStore?.errors?.length > 0 || false);
    
    // Methods
    const toggleMobileNav = () => {
      showMobileNav.value = !showMobileNav.value;
    };

    const closeMobileNav = () => {
      showMobileNav.value = false;
    };

    const closeNavbarOnClickOutside = (event) => {
      // Close mobile nav when clicking outside
      if (showMobileNav.value && !event.target.closest('#mobile-nav') && !event.target.closest('[aria-controls="mobile-nav"]')) {
        showMobileNav.value = false;
      }
    };

    const clearAllCaches = async () => {
      try {
        // Clear all stores
        if (appStore && typeof appStore.clearAllNotifications === 'function') {
          appStore.clearAllNotifications();
        }
        if (chatStore && typeof chatStore.clearAllSessions === 'function') {
          chatStore.clearAllSessions();
        }
        if (knowledgeStore && typeof knowledgeStore.clearCache === 'function') {
          knowledgeStore.clearCache();
        }
        
        // Reload the page
        window.location.reload();
      } catch (error) {
        console.error('Error clearing caches:', error);
      }
    };

    const handleGlobalError = (error) => {
      console.error('Global error:', error);
      if (appStore && typeof appStore.addSystemNotification === 'function') {
        appStore.addSystemNotification({
          severity: 'error',
          title: 'Application Error',
          message: error.message || 'An unexpected error occurred'
        });
      }
    };

    // System health monitoring
    const startSystemHealthCheck = () => {
      if (systemHealthCheck) {
        clearInterval(systemHealthCheck);
      }
      
      systemHealthCheck = setInterval(async () => {
        try {
          const response = await fetch('/api/health');
          if (response.ok) {
            if (appStore && typeof appStore.setBackendStatus === 'function') {
              appStore.setBackendStatus({
                text: 'Connected',
                class: 'success'
              });
            }
          } else {
            throw new Error(`Health check failed: ${response.status}`);
          }
        } catch (error) {
          if (appStore && typeof appStore.setBackendStatus === 'function') {
            appStore.setBackendStatus({
              text: 'Disconnected',
              class: 'error'
            });
          }
        }
      }, 30000); // Check every 30 seconds
    };

    const stopSystemHealthCheck = () => {
      if (systemHealthCheck) {
        clearInterval(systemHealthCheck);
        systemHealthCheck = null;
      }
    };

    // Start notification cleanup to prevent accumulation
    const startNotificationCleanup = () => {
      if (notificationCleanup) {
        clearInterval(notificationCleanup);
      }

      notificationCleanup = setInterval(() => {
        if (appStore && appStore.systemNotifications && appStore.systemNotifications.length > 10) {
          console.log('[App] Cleaning up excessive notifications:', appStore.systemNotifications.length);
          // Keep only the last 5 notifications
          const recentNotifications = appStore.systemNotifications.slice(-5);
          appStore.systemNotifications.splice(0, appStore.systemNotifications.length, ...recentNotifications);
        }
      }, 10000); // Check every 10 seconds
    };

    const stopNotificationCleanup = () => {
      if (notificationCleanup) {
        clearInterval(notificationCleanup);
        notificationCleanup = null;
      }
    };

    // Lifecycle hooks
    onMounted(() => {
      // Add global click listener for mobile nav
      document.addEventListener('click', closeNavbarOnClickOutside);

      // Set up global error handler
      window.addEventListener('error', (event) => {
        handleGlobalError(event.error || event);
      });

      window.addEventListener('unhandledrejection', (event) => {
        handleGlobalError(event.reason);
      });

      // Initialize bulletproof systems
      try {
        // Initialize cache buster
        if (cacheBuster && typeof cacheBuster.initialize === 'function') {
          cacheBuster.initialize();
        }

        // Initialize router health monitor
        if (routerHealthMonitor && typeof routerHealthMonitor.initialize === 'function') {
          routerHealthMonitor.initialize(router);

          // Set up router health listeners
          routerHealthMonitor.on('failure', (data) => {
            console.error('[App] Router failure detected:', data);
            if (appStore && typeof appStore.addSystemNotification === 'function') {
              appStore.addSystemNotification({
                severity: 'warning',
                title: 'Navigation Issue',
                message: `Router failure detected. Attempting recovery... (${data.failureCount})`
              });
            }
          });

          routerHealthMonitor.on('recovery', (data) => {
            console.log('[App] Router recovery successful:', data);
            if (appStore && typeof appStore.addSystemNotification === 'function') {
              appStore.addSystemNotification({
                severity: 'success',
                title: 'Recovery Complete',
                message: 'Router has been successfully recovered.'
              });
            }
          });
        }

        // Initialize frontend health monitor
        if (frontendHealthMonitor && typeof frontendHealthMonitor.initialize === 'function') {
          frontendHealthMonitor.initialize();

          // Set up health status listeners
          frontendHealthMonitor.onHealthChange((healthData) => {
            if (healthData.status.overall !== 'healthy') {
              console.warn('[App] Frontend health degraded:', healthData);

              if (appStore && typeof appStore.addSystemNotification === 'function') {
                let severity = 'info';
                let title = 'System Status';
                let message = '';

                switch (healthData.status.overall) {
                  case 'degraded':
                    severity = 'warning';
                    title = 'Performance Degraded';
                    message = 'System performance is degraded. Monitoring for recovery...';
                    break;
                  case 'unhealthy':
                    severity = 'error';
                    title = 'System Issues Detected';
                    message = 'System health issues detected. Auto-recovery in progress...';
                    break;
                }

                if (message) {
                  appStore.addSystemNotification({ severity, title, message });
                }
              }
            }
          });
        }
      } catch (error) {
        console.error('[App] Error initializing bulletproof systems:', error);
      }

      // Start health monitoring
      startSystemHealthCheck();

      // Start notification cleanup to prevent teleport accumulation
      startNotificationCleanup();

      // Initial health check
      setTimeout(() => {
        startSystemHealthCheck();
      }, 1000);
    });

    onUnmounted(() => {
      // Clean up listeners
      document.removeEventListener('click', closeNavbarOnClickOutside);
      stopSystemHealthCheck();
      stopNotificationCleanup();
    });

    return {
      // Store references
      appStore,
      chatStore,
      knowledgeStore,
      
      // Reactive data
      showMobileNav,
      
      // Computed
      isLoading,
      hasErrors,
      
      // Methods
      toggleMobileNav,
      closeMobileNav,
      clearAllCaches,
      handleGlobalError,
    };
  }
};
</script>

<style scoped>
/* Add any component-specific styles here */
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.5s;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}

/* Ensure proper z-index for mobile navigation */
#mobile-nav {
  z-index: 50;
}

/* Smooth transitions for navigation state changes */
.transition-transform {
  transition-property: transform;
  transition-timing-function: cubic-bezier(0.4, 0, 0.2, 1);
  transition-duration: 300ms;
}
</style>