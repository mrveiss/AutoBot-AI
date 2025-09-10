<template>
  <ErrorBoundary :on-error="handleGlobalError">

    <!-- Skip Navigation Link for Accessibility -->
    <a href="#main-content" class="sr-only focus:not-sr-only focus:absolute focus:top-0 focus:left-0 bg-indigo-600 text-white px-4 py-2 rounded-br-lg z-[100000] focus:outline-none focus:ring-2 focus:ring-white">
      Skip to main content
    </a>

    <div class="min-h-screen bg-blueGray-50">
      <!-- Main content -->
      <div class="relative bg-blueGray-50" :class="appStore?.activeTab === 'chat' ? 'h-screen flex flex-col' : 'min-h-screen'">

      <!-- Header gradient with navigation - Always visible sticky header -->
      <div class="sticky top-0 bg-gradient-to-br from-indigo-600 to-indigo-800 z-50 shadow-lg">
        <div class="px-4 md:px-6 mx-auto w-full">
          <div class="flex flex-row items-center justify-between py-3">
            <!-- Brand (Left side) -->
            <div class="flex items-center flex-shrink-0 ml-2">
              <div class="w-10 h-10 bg-white rounded-full flex items-center justify-center shadow-lg">
                <span class="text-indigo-700 text-lg font-bold">A</span>
              </div>
              <span class="ml-3 text-lg font-semibold text-white">AutoBot Pro</span>
            </div>

            <!-- Navigation (Center) -->
            <div class="hidden lg:flex items-center space-x-8">
              <div class="flex items-center space-x-4">
                <button 
                  @click="setActiveTab('chat')"
                  :class="{ 
                    'bg-white text-indigo-700': appStore?.activeTab === 'chat',
                    'text-white hover:bg-indigo-500': appStore?.activeTab !== 'chat'
                  }"
                  class="px-4 py-2 rounded-lg font-medium transition-colors duration-200 flex items-center"
                  title="Chat Interface"
                  role="tab"
                  :aria-selected="appStore?.activeTab === 'chat'"
                >
                  💬 Chat
                </button>
                
                
                <button 
                  @click="setActiveTab('knowledge')"
                  :class="{
                    'bg-white text-indigo-700': appStore?.activeTab === 'knowledge',
                    'text-white hover:bg-indigo-500': appStore?.activeTab !== 'knowledge'
                  }"
                  class="px-4 py-2 rounded-lg font-medium transition-colors duration-200 flex items-center"
                  title="Knowledge Base"
                  role="tab"
                  :aria-selected="appStore?.activeTab === 'knowledge'"
                >
                  📚 Knowledge
                </button>
                
                <button 
                  @click="setActiveTab('secrets')"
                  :class="{
                    'bg-white text-indigo-700': appStore?.activeTab === 'secrets',
                    'text-white hover:bg-indigo-500': appStore?.activeTab !== 'secrets'
                  }"
                  class="px-4 py-2 rounded-lg font-medium transition-colors duration-200 flex items-center"
                  title="Secrets Manager"
                  role="tab"
                  :aria-selected="appStore?.activeTab === 'secrets'"
                >
                  🔐 Secrets
                </button>
                
                <button 
                  @click="setActiveTab('tools')"
                  :class="{
                    'bg-white text-indigo-700': appStore?.activeTab === 'tools',
                    'text-white hover:bg-indigo-500': appStore?.activeTab !== 'tools'
                  }"
                  class="px-4 py-2 rounded-lg font-medium transition-colors duration-200 flex items-center"
                  title="Tools Browser"
                  role="tab"
                  :aria-selected="appStore?.activeTab === 'tools'"
                >
                  🛠️ Tools
                </button>
                
                <button 
                  @click="setActiveTab('monitoring')"
                  :class="{
                    'bg-white text-indigo-700': appStore?.activeTab === 'monitoring',
                    'text-white hover:bg-indigo-500': appStore?.activeTab !== 'monitoring'
                  }"
                  class="px-4 py-2 rounded-lg font-medium transition-colors duration-200 flex items-center"
                  title="System Monitoring"
                  role="tab"
                  :aria-selected="appStore?.activeTab === 'monitoring'"
                >
                  📊 Monitoring
                </button>

                <button 
                  @click="setActiveTab('settings')"
                  :class="{
                    'bg-white text-indigo-700': appStore?.activeTab === 'settings',
                    'text-white hover:bg-indigo-500': appStore?.activeTab !== 'settings'
                  }"
                  class="px-4 py-2 rounded-lg font-medium transition-colors duration-200 flex items-center"
                  title="Settings & Configuration"
                  role="tab"
                  :aria-selected="appStore?.activeTab === 'settings'"
                >
                  ⚙️ Settings
                </button>
              </div>
            </div>

            <!-- System Status and Mobile Menu (Right side) -->
            <div class="flex items-center space-x-3">
              <!-- System Status Indicator -->
              <SystemStatusIndicator />
              
              <!-- Cache Clear Button -->
              <button 
                @click="clearAllCaches"
                :disabled="clearingCaches"
                class="hidden md:flex items-center px-3 py-1 rounded-lg bg-indigo-500 hover:bg-indigo-400 text-white text-sm transition-colors duration-200 disabled:opacity-50"
                title="Clear all caches to prevent configuration issues"
              >
                <span v-if="clearingCaches" class="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></span>
                🧹 Clear Cache
              </button>

              <!-- Mobile Menu Toggle -->
              <button 
                @click="toggleMobileNav"
                class="lg:hidden relative z-[70] flex items-center justify-center w-10 h-10 rounded-lg bg-indigo-500 hover:bg-indigo-600 transition-colors duration-200"
                :aria-expanded="showMobileNav"
                aria-controls="mobile-nav"
                aria-label="Toggle mobile navigation"
              >
                <!-- Hamburger Icon with Animation -->
                <div class="relative w-6 h-6 flex flex-col justify-center">
                  <div 
                    class="absolute h-0.5 w-6 bg-white transform transition-all duration-200"
                    :class="showMobileNav ? 'rotate-45' : '-translate-y-1'"
                  ></div>
                  <div 
                    class="absolute h-0.5 w-6 bg-white transform transition-all duration-200"
                    :class="showMobileNav ? 'opacity-0' : ''"
                  ></div>
                  <div 
                    class="absolute h-0.5 w-6 bg-white transform transition-all duration-200"
                    :class="showMobileNav ? '-rotate-45' : 'translate-y-1'"
                  ></div>
                </div>
              </button>
            </div>
          </div>
        </div>

        <!-- Mobile Navigation Menu -->
        <div 
          v-show="showMobileNav"
          id="mobile-nav"
          class="lg:hidden relative z-[60] bg-indigo-700"
          role="menu"
        >
          <div class="px-4 py-3 space-y-2">
            <button 
              @click="setActiveTab('chat')"
              :class="{ 
                'bg-white text-indigo-700': appStore?.activeTab === 'chat',
                'text-white hover:bg-indigo-600': appStore?.activeTab !== 'chat'
              }"
              class="w-full text-left px-4 py-3 rounded-lg font-medium transition-colors duration-200 flex items-center"
              role="menuitem"
            >
              💬 Chat Interface
            </button>
            
            
            <button 
              @click="setActiveTab('knowledge')"
              :class="{
                'bg-white text-indigo-700': appStore?.activeTab === 'knowledge',
                'text-white hover:bg-indigo-600': appStore?.activeTab !== 'knowledge'
              }"
              class="w-full text-left px-4 py-3 rounded-lg font-medium transition-colors duration-200 flex items-center"
              role="menuitem"
            >
              📚 Knowledge Base
            </button>
            
            <button 
              @click="setActiveTab('secrets')"
              :class="{
                'bg-white text-indigo-700': appStore?.activeTab === 'secrets',
                'text-white hover:bg-indigo-600': appStore?.activeTab !== 'secrets'
              }"
              class="w-full text-left px-4 py-3 rounded-lg font-medium transition-colors duration-200 flex items-center"
              role="menuitem"
            >
              🔐 Secrets Manager
            </button>
            
            <button 
              @click="setActiveTab('tools')"
              :class="{
                'bg-white text-indigo-700': appStore?.activeTab === 'tools',
                'text-white hover:bg-indigo-600': appStore?.activeTab !== 'tools'
              }"
              class="w-full text-left px-4 py-3 rounded-lg font-medium transition-colors duration-200 flex items-center"
              role="menuitem"
            >
              🛠️ Tools Browser
            </button>
            
            <button 
              @click="setActiveTab('monitoring')"
              :class="{
                'bg-white text-indigo-700': appStore?.activeTab === 'monitoring',
                'text-white hover:bg-indigo-600': appStore?.activeTab !== 'monitoring'
              }"
              class="w-full text-left px-4 py-3 rounded-lg font-medium transition-colors duration-200 flex items-center"
              role="menuitem"
            >
              📊 System Monitoring
            </button>

            <button 
              @click="setActiveTab('settings')"
              :class="{
                'bg-white text-indigo-700': appStore?.activeTab === 'settings',
                'text-white hover:bg-indigo-600': appStore?.activeTab !== 'settings'
              }"
              class="w-full text-left px-4 py-3 rounded-lg font-medium transition-colors duration-200 flex items-center"
              role="menuitem"
            >
              ⚙️ Settings & Configuration
            </button>
            
            <!-- Mobile Cache Clear Button -->
            <button 
              @click="clearAllCaches"
              :disabled="clearingCaches"
              class="w-full text-left px-4 py-3 rounded-lg bg-indigo-500 hover:bg-indigo-400 text-white transition-colors duration-200 flex items-center disabled:opacity-50"
              role="menuitem"
            >
              <span v-if="clearingCaches" class="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2"></span>
              🧹 Clear All Caches
            </button>
          </div>
        </div>
      </div>

        <!-- Main Content Area with id for skip link -->
        <main id="main-content" :class="appStore?.activeTab === 'chat' ? 'flex-1 overflow-hidden' : 'flex-1'" role="main">
          <!-- Use router-view for all content to enable proper sub-routing -->
          <router-view />
        </main>
      </div>

      <!-- Elevation Dialog -->
      <ElevationDialog 
        :show="showElevationDialog"
        :service="elevationRequest.service"
        :reason="elevationRequest.reason"
        :request-id="elevationRequest.requestId || 'default-request-id'"
        :details="elevationRequest.details"
        @approved="onElevationApproved"
        @denied="onElevationDenied"
        @cancel="onElevationCancelled"
      />


      <!-- RUM Dashboard (only if enabled) -->
      <div v-if="appStore?.rumEnabled" class="fixed bottom-4 right-4 z-[60]">
        <div class="bg-white rounded-lg shadow-lg p-4 max-w-sm">
          <Suspense>
            <template #default>
              <RumDashboard />
            </template>
            <template #fallback>
              <div class="flex items-center justify-center p-4">
                <div class="animate-spin rounded-full h-6 w-6 border-b-2 border-indigo-600"></div>
                <span class="ml-2 text-sm">Loading RUM...</span>
              </div>
            </template>
          </Suspense>
        </div>
      </div>
    </div>

    <!-- Global notifications -->
    <SystemStatusNotification 
      :visible="false"
      severity="info"
      title=""
      message=""
    />
    <ErrorNotifications />
  </ErrorBoundary>
</template>

<script>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import { useAppStore } from '@/stores/useAppStore'
import { useChatStore } from '@/stores/useChatStore'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
// Core components loaded immediately (small and always needed)
import ElevationDialog from './components/ElevationDialog.vue';
import ErrorNotifications from './components/ErrorNotifications.vue';
import ErrorBoundary from './components/ErrorBoundary.vue';
import SystemStatusNotification from './components/SystemStatusNotification.vue';
import SystemStatusIndicator from './components/SystemStatusIndicator.vue';

// Import cache manager
import { cacheManager } from '@/utils/CacheManager.ts';
import { invalidateApiCache } from '@/config/environment.js';

// Import async RUM Dashboard component
import { defineAsyncComponent } from 'vue';

const RumDashboard = defineAsyncComponent({
  loader: () => import('./components/RumDashboard.vue'),
  loadingComponent: { template: '<div class="flex items-center justify-center p-8"><div class="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600"></div><span class="ml-3">Loading RUM Dashboard...</span></div>' },
  errorComponent: { template: '<div class="text-red-600 p-4">Failed to load RUM Dashboard component</div>' },
  delay: 100,
  timeout: 10000
});


export default {
  name: 'App',
  components: {
    ElevationDialog,
    ErrorNotifications,
    ErrorBoundary,
    SystemStatusNotification,
    SystemStatusIndicator,
    RumDashboard,
    // Async components loaded on-demand
    ChatInterface: defineAsyncComponent(() => import('./components/chat/ChatInterface.vue')),
    KnowledgeInterface: defineAsyncComponent(() => import('./components/knowledge/KnowledgeInterface.vue')),
    SecretsManager: defineAsyncComponent(() => import('./components/SecretsManager.vue')),
    ToolsBrowser: defineAsyncComponent(() => import('./components/ToolsBrowser.vue')),
    SystemMonitor: defineAsyncComponent(() => import('./components/SystemMonitor.vue')),
    SettingsInterface: defineAsyncComponent(() => import('./components/settings/SettingsInterface.vue')),
  },
  
  setup() {
    // Store references
    const appStore = useAppStore();
    const chatStore = useChatStore();
    const knowledgeStore = useKnowledgeStore();
    const router = useRouter();
    
    // Reactive data
    const showMobileNav = ref(false);
    const showElevationDialog = ref(false);
    const clearingCaches = ref(false);
    
    const elevationRequest = ref({
      service: '',
      reason: '',
      requestId: '',
      details: ''
    });

    let systemHealthCheck = null;

    // Computed properties
    const isLoading = computed(() => appStore?.isLoading || false);
    const hasErrors = computed(() => appStore?.errors?.length > 0 || false);
    
    // Methods
    const setActiveTab = (tab) => {
      // Update app store state
      appStore?.updateRoute(tab);
      
      // Navigate using Vue Router for proper sub-routing
      const routeMap = {
        'chat': '/chat',
        'desktop': '/desktop',
        'knowledge': '/knowledge',
        'secrets': '/secrets',
        'tools': '/tools',
        'monitoring': '/monitoring',
        'settings': '/settings'
      };
      
      const targetRoute = routeMap[tab];
      if (targetRoute && router.currentRoute.value.path !== targetRoute) {
        router.push(targetRoute);
      }
      
      // Close mobile nav when tab is selected
      showMobileNav.value = false;
    };

    const toggleMobileNav = () => {
      showMobileNav.value = !showMobileNav.value;
    };

    const closeNavbarOnClickOutside = (event) => {
      // Close mobile nav when clicking outside
      if (showMobileNav.value && !event.target.closest('#mobile-nav') && !event.target.closest('[aria-controls="mobile-nav"]')) {
        showMobileNav.value = false;
      }
    };

    // Cache management methods
    const clearAllCaches = async () => {
      if (clearingCaches.value) return;
      
      clearingCaches.value = true;
      console.log('[AutoBot] Starting comprehensive cache clearing...');
      
      try {
        // Show user notification
        appStore?.addSystemNotification({
          severity: 'info',
          title: 'Cache Management',
          message: 'Clearing all caches to prevent configuration issues...'
        });
        
        // Clear API configuration cache
        invalidateApiCache();
        
        // Clear browser caches via cache manager
        await cacheManager.clearAllCaches();
        
        // Clear service worker cache
        if ('serviceWorker' in navigator) {
          const registration = await navigator.serviceWorker.ready;
          if (registration.active) {
            const messageChannel = new MessageChannel();
            const clearPromise = new Promise((resolve) => {
              messageChannel.port1.onmessage = () => resolve();
            });
            
            registration.active.postMessage(
              { type: 'CLEAR_CACHE' },
              [messageChannel.port2]
            );
            
            await clearPromise;
          }
        }
        
        // Update build version to prevent future cache issues
        cacheManager.updateBuildVersion();
        
        console.log('[AutoBot] Cache clearing completed successfully');
        
        // Show success notification
        appStore?.addSystemNotification({
          severity: 'success',
          title: 'Cache Cleared',
          message: 'All caches cleared successfully! API configurations refreshed.'
        });
        
        // Optional: Reload page to ensure clean state
        const shouldReload = await new Promise((resolve) => {
          const confirmed = window.confirm(
            'Caches have been cleared successfully.\n\nWould you like to reload the page to ensure a completely clean state?\n\n(This is recommended for full cache invalidation)'
          );
          resolve(confirmed);
        });
        
        if (shouldReload) {
          window.location.reload();
        }
        
      } catch (error) {
        console.error('[AutoBot] Cache clearing failed:', error);
        
        appStore?.addSystemNotification({
          severity: 'error',
          title: 'Cache Clear Failed',
          message: `Cache clearing failed: ${error.message}. Try refreshing the page manually.`
        });
      } finally {
        clearingCaches.value = false;
      }
    };

    const checkSystemHealth = async () => {
      try {
        // Use the new notification system for health status
        const response = await fetch('/api/system/health', {
          headers: {
            'Cache-Control': 'no-cache',
            'X-Cache-Bust': Date.now().toString()
          }
        });
        
        if (!response.ok) {
          throw new Error(`Health check failed: ${response.status}`);
        }
        
        const healthData = await response.json();
        
        // Update system health status
        if (healthData.status !== 'healthy') {
          appStore?.addSystemNotification({
            severity: 'warning',
            title: 'System Health',
            message: `System health check: ${healthData.status}. Some services may be degraded.`
          });
        }
      } catch (error) {
        // Only show notification for persistent failures (not single timeouts)
        if (error.message.includes('Failed to fetch') || error.message.includes('Network error')) {
          appStore?.addSystemNotification({
            severity: 'error',
            title: 'Backend Connection Lost',
            message: 'Backend connection lost. Check if services are running and clear cache if issues persist.'
          });
        }
      }
    };

    const handleGlobalError = (error, instance, info) => {
      console.error('Global error caught:', error, info);
      
      // Check if error is related to cache or configuration
      const cacheRelatedErrors = [
        'Failed to fetch',
        'NetworkError',
        'ERR_INTERNET_DISCONNECTED',
        'ERR_NETWORK_CHANGED',
        'Configuration error',
        'API endpoint not found'
      ];
      
      const isCacheRelated = cacheRelatedErrors.some(errorType => 
        error.message?.includes(errorType) || error.toString().includes(errorType)
      );
      
      if (isCacheRelated) {
        appStore?.addSystemNotification({
          severity: 'error',
          title: 'Network/Configuration Error',
          message: `Network/Configuration error detected: ${error.message}. This might be resolved by clearing caches.`
        });
      } else {
        appStore?.addSystemNotification({
          severity: 'error',
          title: 'Application Error',
          message: `Application error: ${error.message}`
        });
      }
    };


    const onElevationApproved = (password) => {
      console.log('Elevation approved');
      
      // Send approval event with the password
      window.dispatchEvent(new CustomEvent('elevation-approved', {
        detail: {
          service: elevationRequest.value.service,
          password: password
        }
      }));
      
      showElevationDialog.value = false;
      elevationRequest.value = { service: '', reason: '', requestId: '', details: '' };
    };

    const onElevationDenied = () => {
      console.log('Elevation denied');
      
      // Send denial event
      window.dispatchEvent(new CustomEvent('elevation-denied', {
        detail: {
          service: elevationRequest.value.service,
        }
      }));
      
      showElevationDialog.value = false;
      elevationRequest.value = { service: '', reason: '', requestId: '', details: '' };
    };

    const onElevationCancelled = () => {
      console.log('Elevation cancelled');
      showElevationDialog.value = false;
      elevationRequest.value = { service: '', reason: '', requestId: '', details: '' };
    };

    const handleElevationRequest = (event) => {
      const { service, reason, details } = event.detail;
      
      elevationRequest.value = {
        service: service || 'Unknown Service',
        reason: reason || 'No reason provided',
        requestId: Date.now().toString() + '-' + Math.random().toString(36).substr(2, 9),
        details: details || ''
      };
      
      showElevationDialog.value = true;
    };

    // Lifecycle hooks
    onMounted(async () => {
      console.log('App mounted, initializing application...')
      document.addEventListener('click', closeNavbarOnClickOutside)
      
      // Listen for global elevation requests
      window.addEventListener('elevation-request', handleElevationRequest);
      
      // Initialize cache manager
      try {
        await cacheManager.initialize();
        console.log('[AutoBot] Cache manager initialized successfully');
      } catch (error) {
        console.error('[AutoBot] Cache manager initialization failed:', error);
      }
      
      // Start system health monitoring using new notification system
      systemHealthCheck = setInterval(checkSystemHealth, 10000) // Check every 10 seconds
      
      // Initial health check
      setTimeout(checkSystemHealth, 1000);
      
      console.log('App initialization completed');
    });

    onUnmounted(() => {
      document.removeEventListener('click', closeNavbarOnClickOutside)
      window.removeEventListener('elevation-request', handleElevationRequest);
      
      if (systemHealthCheck) {
        clearInterval(systemHealthCheck);
      }
    });

    return {
      // Stores
      appStore,
      chatStore,
      knowledgeStore,
      
      // Reactive data
      showMobileNav,
      showElevationDialog,
      clearingCaches,
      elevationRequest,
      
      // Computed
      isLoading,
      hasErrors,
      
      // Methods
      setActiveTab,
      toggleMobileNav,
      clearAllCaches,
      handleGlobalError,
      onElevationApproved,
      onElevationDenied,
      onElevationCancelled,
    }
  },
}
</script>

<style scoped>
/* Add any component-specific styles here */
.router-link-active {
  @apply bg-white text-indigo-700;
}

/* Animation for mobile menu */
#mobile-nav {
  animation: slideDown 0.2s ease-out;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* Focus styles for accessibility */
button:focus-visible {
  @apply ring-2 ring-white ring-offset-2 ring-offset-indigo-600;
}

/* Mobile navigation z-index fix */
.lg\:hidden {
  position: relative;
}
</style>