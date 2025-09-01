<template>
  <ErrorBoundary :on-error="handleGlobalError">
    <!-- Startup Loader -->
    <StartupLoader 
      v-if="showStartupLoader"
      :auto-hide="true"
      :min-display-time="2000"
      @ready="onStartupReady"
      @skip="onStartupSkip"
    />

    <!-- Skip Navigation Link for Accessibility -->
    <a href="#main-content" class="sr-only focus:not-sr-only focus:absolute focus:top-0 focus:left-0 bg-indigo-600 text-white px-4 py-2 rounded-br-lg z-[100000] focus:outline-none focus:ring-2 focus:ring-white">
      Skip to main content
    </a>

    <!-- System Down Banner -->
    <div v-if="isSystemDown && !showStartupLoader" class="fixed top-0 left-0 right-0 bg-red-600 text-white text-center py-2 px-4 z-[99998] shadow-lg">
      <div class="flex items-center justify-center gap-2">
        <i class="fas fa-exclamation-triangle animate-pulse"></i>
        <span class="font-medium">{{ systemDownMessage }}</span>
        <div class="animate-spin">🔄</div>
      </div>
    </div>

    <div class="min-h-screen bg-blueGray-50" :class="{ 'opacity-50': showStartupLoader, 'pt-12': isSystemDown && !showStartupLoader }">
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

            <!-- Navigation Links (Center) -->
            <nav class="flex-1 flex items-center justify-center" role="navigation" aria-label="Main navigation">
              <!-- Desktop Navigation -->
              <div class="hidden md:flex">
                <ul class="flex flex-row list-none space-x-1" role="menubar">
                  <li role="none">
                    <router-link
                      to="/dashboard"
                      :class="[$route.name === 'dashboard' ? 'text-white bg-indigo-500' : 'text-indigo-200 hover:text-white hover:bg-white hover:bg-opacity-10']"
                      class="text-xs uppercase py-2 px-3 font-bold inline-flex items-center rounded-lg cursor-pointer transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-white focus:ring-opacity-50"
                      role="menuitem"
                      aria-label="Go to Dashboard"
                    >
                      <i class="fas fa-tachometer-alt mr-2 text-sm" aria-hidden="true"></i>
                      Dashboard
                    </router-link>
                  </li>
                  <li role="none">
                    <router-link
                      to="/chat"
                      :class="[$route.name?.startsWith('chat') ? 'text-white bg-indigo-500' : 'text-indigo-200 hover:text-white hover:bg-white hover:bg-opacity-10']"
                      class="text-xs uppercase py-2 px-3 font-bold inline-flex items-center rounded-lg cursor-pointer transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-white focus:ring-opacity-50"
                      role="menuitem"
                      aria-label="Go to AI Assistant Chat"
                    >
                      <i class="fas fa-comments mr-2 text-sm" aria-hidden="true"></i>
                      AI Assistant
                    </router-link>
                  </li>
                  <li role="none">
                    <router-link
                      to="/knowledge"
                      :class="[$route.name?.startsWith('knowledge') ? 'text-white bg-indigo-500' : 'text-indigo-200 hover:text-white hover:bg-white hover:bg-opacity-10']"
                      class="text-xs uppercase py-2 px-3 font-bold inline-flex items-center rounded-lg cursor-pointer transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-white focus:ring-opacity-50"
                      role="menuitem"
                      aria-label="Go to Knowledge Base"
                    >
                      <i class="fas fa-brain mr-2 text-sm" aria-hidden="true"></i>
                      Knowledge Base
                    </router-link>
                  </li>
                  <li role="none">
                    <router-link
                      to="/tools"
                      :class="[$route.name?.startsWith('tools') ? 'text-white bg-indigo-500' : 'text-indigo-200 hover:text-white hover:bg-white hover:bg-opacity-10']"
                      class="text-xs uppercase py-2 px-3 font-bold inline-flex items-center rounded-lg cursor-pointer transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-white focus:ring-opacity-50"
                      role="menuitem"
                      aria-label="Go to Tools"
                    >
                      <i class="fas fa-tools mr-2 text-sm" aria-hidden="true"></i>
                      Tools
                    </router-link>
                  </li>
                  <li role="none">
                    <router-link
                      to="/monitoring"
                      :class="[$route.name?.startsWith('monitoring') ? 'text-white bg-indigo-500' : 'text-indigo-200 hover:text-white hover:bg-white hover:bg-opacity-10']"
                      class="text-xs uppercase py-2 px-3 font-bold inline-flex items-center rounded-lg cursor-pointer transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-white focus:ring-opacity-50"
                      role="menuitem"
                      aria-label="Go to Monitoring"
                    >
                      <i class="fas fa-chart-bar mr-2 text-sm" aria-hidden="true"></i>
                      Monitoring
                    </router-link>
                  </li>
                  <li role="none">
                    <router-link
                      to="/secrets"
                      :class="[$route.name === 'secrets' ? 'text-white bg-indigo-500' : 'text-indigo-200 hover:text-white hover:bg-white hover:bg-opacity-10']"
                      class="text-xs uppercase py-2 px-3 font-bold inline-flex items-center rounded-lg cursor-pointer transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-white focus:ring-opacity-50"
                      role="menuitem"
                      aria-label="Go to Secrets Manager"
                    >
                      <i class="fas fa-key mr-2 text-sm" aria-hidden="true"></i>
                      Secrets
                    </router-link>
                  </li>
                  <li role="none">
                    <router-link
                      to="/settings"
                      :class="[$route.name === 'settings' ? 'text-white bg-indigo-500' : 'text-indigo-200 hover:text-white hover:bg-white hover:bg-opacity-10']"
                      class="text-xs uppercase py-2 px-3 font-bold inline-flex items-center rounded-lg cursor-pointer transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-white focus:ring-opacity-50"
                      role="menuitem"
                      aria-label="Go to Settings"
                    >
                      <i class="fas fa-cog mr-2 text-sm" aria-hidden="true"></i>
                      Settings
                    </router-link>
                  </li>
                </ul>
              </div>
            </nav>

            <!-- User menu and Mobile menu button (Right side) -->
            <div class="flex items-center mr-2">
              <!-- User menu (Desktop) -->
              <div class="hidden md:flex items-center">
                <a class="text-white hover:text-indigo-200 px-3 py-2 flex items-center text-xs uppercase font-bold transition-colors duration-150">
                  <i class="fas fa-user-circle text-lg mr-2"></i>
                  Admin User
                </a>
              </div>

              <!-- Mobile menu button -->
              <div class="relative md:hidden" ref="mobileMenuContainer">
                <button
                  class="cursor-pointer text-white px-3 py-1 text-xl leading-none bg-transparent rounded border border-solid border-transparent focus:outline-none focus:ring-2 focus:ring-white focus:ring-opacity-50"
                  type="button"
                  @click="toggleNavbar"
                  :aria-label="appStore?.navbarOpen ? 'Close navigation menu' : 'Open navigation menu'"
                  :aria-expanded="appStore?.navbarOpen"
                  aria-controls="mobile-menu">
                  <i class="fas" :class="appStore?.navbarOpen ? 'fa-times' : 'fa-bars'" aria-hidden="true"></i>
                </button>

                <!-- Mobile Navigation Menu -->
                <nav
                  v-if="appStore?.navbarOpen"
                  id="mobile-menu"
                  class="fixed top-16 right-4 z-[99999] w-64"
                  role="navigation"
                  aria-label="Mobile navigation"
                  @click.stop>
                  <div class="mt-2 bg-white rounded-lg p-4 shadow-xl border border-blueGray-200" style="box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);">
                    <ul class="flex flex-col space-y-2" role="menu">
                      <li>
                        <router-link
                          to="/dashboard"
                          :class="[$route.name === 'dashboard' ? 'text-indigo-600 bg-indigo-100' : 'text-blueGray-700 hover:text-indigo-600 hover:bg-indigo-50']"
                          class="text-xs uppercase py-2 px-3 font-bold inline-flex items-center rounded-lg cursor-pointer transition-all duration-150 w-full focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-50"
                        >
                          <i class="fas fa-tachometer-alt mr-2 text-sm"></i>
                          Dashboard
                        </router-link>
                      </li>
                      <li>
                        <router-link
                          to="/chat"
                          :class="[$route.name?.startsWith('chat') ? 'text-indigo-600 bg-indigo-100' : 'text-blueGray-700 hover:text-indigo-600 hover:bg-indigo-50']"
                          class="text-xs uppercase py-2 px-3 font-bold inline-flex items-center rounded-lg cursor-pointer transition-all duration-150 w-full focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-50"
                        >
                          <i class="fas fa-comments mr-2 text-sm"></i>
                          AI Assistant
                        </router-link>
                      </li>
                      <li>
                        <router-link
                          to="/knowledge"
                          :class="[$route.name?.startsWith('knowledge') ? 'text-indigo-600 bg-indigo-100' : 'text-blueGray-700 hover:text-indigo-600 hover:bg-indigo-50']"
                          class="text-xs uppercase py-2 px-3 font-bold inline-flex items-center rounded-lg cursor-pointer transition-all duration-150 w-full focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-50"
                        >
                          <i class="fas fa-brain mr-2 text-sm"></i>
                          Knowledge Base
                        </router-link>
                      </li>
                      <li>
                        <router-link
                          to="/tools"
                          :class="[$route.name?.startsWith('tools') ? 'text-indigo-600 bg-indigo-100' : 'text-blueGray-700 hover:text-indigo-600 hover:bg-indigo-50']"
                          class="text-xs uppercase py-2 px-3 font-bold inline-flex items-center rounded-lg cursor-pointer transition-all duration-150 w-full focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-50"
                        >
                          <i class="fas fa-tools mr-2 text-sm"></i>
                          Tools
                        </router-link>
                      </li>
                      <li>
                        <router-link
                          to="/monitoring"
                          :class="[$route.name?.startsWith('monitoring') ? 'text-indigo-600 bg-indigo-100' : 'text-blueGray-700 hover:text-indigo-600 hover:bg-indigo-50']"
                          class="text-xs uppercase py-2 px-3 font-bold inline-flex items-center rounded-lg cursor-pointer transition-all duration-150 w-full focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-50"
                        >
                          <i class="fas fa-chart-bar mr-2 text-sm"></i>
                          Monitoring
                        </router-link>
                      </li>
                      <li>
                        <router-link
                          to="/secrets"
                          :class="[$route.name === 'secrets' ? 'text-indigo-600 bg-indigo-100' : 'text-blueGray-700 hover:text-indigo-600 hover:bg-indigo-50']"
                          class="text-xs uppercase py-2 px-3 font-bold inline-flex items-center rounded-lg cursor-pointer transition-all duration-150 w-full focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-50"
                        >
                          <i class="fas fa-key mr-2 text-sm"></i>
                          Secrets
                        </router-link>
                      </li>
                      <li>
                        <router-link
                          to="/settings"
                          :class="[$route.name === 'settings' ? 'text-indigo-600 bg-indigo-100' : 'text-blueGray-700 hover:text-indigo-600 hover:bg-indigo-50']"
                          class="text-xs uppercase py-2 px-3 font-bold inline-flex items-center rounded-lg cursor-pointer transition-all duration-150 w-full focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-opacity-50"
                        >
                          <i class="fas fa-cog mr-2 text-sm"></i>
                          Settings
                        </router-link>
                      </li>
                      <li class="border-t border-gray-200 pt-2 mt-2">
                        <div class="text-xs uppercase text-gray-500 font-bold px-3 py-1">
                          <i class="fas fa-user-circle mr-2"></i>
                          Admin User
                        </div>
                      </li>
                    </ul>
                  </div>
                </nav>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Content area -->
      <main id="main-content" class="px-4 md:px-10 mx-auto w-full" :class="appStore?.activeTab === 'chat' ? 'flex-1 flex flex-col' : ''" role="main">
        <div class="flex flex-wrap" :class="appStore?.activeTab === 'chat' ? 'flex-1 h-full' : 'mt-6'">
          <div class="w-full px-4" :class="appStore?.activeTab === 'chat' ? 'flex-1 h-full flex flex-col' : 'mb-12'">
            <!-- Router view for MVC navigation -->
            <router-view />
          </div>
        </div>
      </main>
      </div>
    </div>

  <!-- Global Elevation Dialog -->
  <ElevationDialog
    ref="elevationDialog"
    :show="showElevationDialog"
    :operation="elevationOperation"
    :command="elevationCommand"
    :reason="elevationReason"
    :risk-level="elevationRiskLevel"
    :request-id="elevationRequestId"
    @approved="onElevationApproved"
    @cancelled="onElevationCancelled"
    @close="onElevationClose"
  />

    <!-- RUM Dashboard for Development -->
    <RumDashboard />

    <!-- Global Error Notifications -->
    <ErrorNotifications />
  </ErrorBoundary>
</template>

<script>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useAppStore } from '@/stores/useAppStore'
import { useChatStore } from '@/stores/useChatStore'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import { ApiClient } from './utils/ApiClient.js';
// Core components loaded immediately (small and always needed)
import PhaseProgressionIndicator from './components/PhaseProgressionIndicator.vue';
import ElevationDialog from './components/ElevationDialog.vue';
import ErrorNotifications from './components/ErrorNotifications.vue';
import ErrorBoundary from './components/ErrorBoundary.vue';
import StartupLoader from './components/StartupLoader.vue';

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
    PhaseProgressionIndicator,
    ElevationDialog,
    RumDashboard,
    ErrorNotifications,
    ErrorBoundary,
    StartupLoader
  },
  setup() {
    // Use Pinia stores instead of local refs
    const appStore = useAppStore()
    const chatStore = useChatStore()
    const knowledgeStore = useKnowledgeStore()

    const mobileMenuContainer = ref(null);

    // Sub-tab states for new grouped sections (kept local as they're UI-only)
    const activeToolTab = ref('terminal');
    const activeMonitoringTab = ref('voice');

    // Simple tab switching using store
    const updateRoute = (tab) => {
      appStore.updateRoute(tab);
    };

    // Dashboard stats (computed from stores)
    const activeSessions = ref(1);
    const knowledgeItems = computed(() => knowledgeStore.documentCount);
    const tasksCompleted = ref(89); // This could come from a tasks store later
    const performance = ref(92); // This could come from system metrics

    // Connection statuses from store
    const backendStatus = ref({ text: 'Checking...', class: 'warning', message: 'Connecting to backend...' });
    const llmStatus = ref({ text: 'Checking...', class: 'warning', message: 'Connecting to LLM...' });
    const redisStatus = ref({ text: 'Checking...', class: 'warning', message: 'Connecting to Redis...' });

    const pageTitle = computed(() => {
      const titles = {
        dashboard: 'Dashboard',
        chat: 'AI Assistant',
        voice: 'Voice Interface',
        knowledge: 'Knowledge Base',
        terminal: 'Terminal',
        settings: 'Settings',
        files: 'File Manager',
        monitor: 'System Monitor'
      };
      return titles[appStore.activeTab] || 'AutoBot';
    });

    const toggleNavbar = () => {
      appStore.toggleNavbar();
    };

    const closeNavbarOnClickOutside = (event) => {
      if (appStore?.navbarOpen && mobileMenuContainer.value && !mobileMenuContainer.value.contains(event.target)) {
        appStore.navbarOpen = false;
      }
    };

    const newChat = () => {
      appStore.generateNewChatId();
    };


    const refreshStats = () => {
    };

    // Phase progression event handlers
    const onPhaseSuccess = (message) => {
      // Phase operation successful
      // Could add toast notification here
    };

    const onPhaseError = (message) => {
      console.error('Phase operation failed:', message);
      // Could add error toast notification here
    };

    const onValidationComplete = (result) => {
      // Validation completed
      // Could update dashboard stats or show results
    };

    const onPhaseValidated = (data) => {
      // Phase validated
      // Could show validation details
    };

    // Elevation Dialog state
    const elevationDialog = ref(null);
    const showElevationDialog = ref(false);
    const elevationOperation = ref('');
    const elevationCommand = ref('');
    const elevationReason = ref('');
    const elevationRiskLevel = ref('MEDIUM');
    const elevationRequestId = ref('');

    // Startup loader state and system shutdown detection
    // Only show startup loader if we haven't completed startup in this session
    const hasCompletedStartup = sessionStorage.getItem('autobot_startup_completed') === 'true'
    const showStartupLoader = ref(!hasCompletedStartup)
    const isSystemDown = ref(false)
    const systemDownMessage = ref('')
    const lastSuccessfulCheck = ref(Date.now())
    let systemHealthCheck = null
    
    const checkSystemHealth = async () => {
      try {
        const controller = new AbortController()
        const timeoutId = setTimeout(() => controller.abort(), 8000) // 8 second timeout
        
        const response = await fetch('/api/system/health', {
          signal: controller.signal,
          cache: 'no-cache',
          headers: {
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
          }
        })
        
        clearTimeout(timeoutId)
        
        if (response.ok) {
          // System is responding
          if (isSystemDown.value) {
            console.log('System is back online - clearing startup flag and reloading page')
            hideSystemDownOverlay()
            // Clear startup completed flag so splash screen shows on reload
            sessionStorage.removeItem('autobot_startup_completed')
            // System recovered - reload page to get fresh state
            window.location.reload()
          }
          lastSuccessfulCheck.value = Date.now()
          isSystemDown.value = false
          systemDownMessage.value = ''
        } else {
          throw new Error(`Health check failed with status: ${response.status}`)
        }
      } catch (error) {
        const timeSinceLastCheck = Date.now() - lastSuccessfulCheck.value
        const consecutiveFailures = Math.floor(timeSinceLastCheck / 10000) // Number of 10-second intervals failed
        
        // Only trigger system down after 3 consecutive failures (30+ seconds) AND if this isn't an abort/timeout error
        if (timeSinceLastCheck > 30000 && consecutiveFailures >= 3 && !isSystemDown.value) {
          // Additional check: make sure this isn't just a temporary network hiccup
          // by trying a simpler request
          try {
            const simpleCheck = await fetch('/api/health', {
              method: 'GET',
              cache: 'no-cache',
              signal: AbortSignal.timeout(3000)
            })
            
            if (simpleCheck.ok) {
              // Simple endpoint works, so system is probably fine
              lastSuccessfulCheck.value = Date.now()
              return
            }
          } catch (simpleError) {
            // Both health checks failed, system is likely down
          }
          
          console.log('System appears to be down after 30+ seconds of failures:', error.message)
          console.log(`Debug: timeSinceLastCheck=${timeSinceLastCheck}ms, consecutiveFailures=${consecutiveFailures}`)
          isSystemDown.value = true
          systemDownMessage.value = 'AutoBot system is restarting or updating. Please wait...'
          
          // Show system down overlay
          showSystemDownOverlay()
        } else if (timeSinceLastCheck > 60000) {
          // After 60 seconds, log but don't show overlay (might be network issue)
          console.warn(`System health check failing for ${Math.round(timeSinceLastCheck/1000)}s, but not showing overlay`)
        }
      }
    }
    
    const showSystemDownOverlay = () => {
      // Create or update system down overlay
      let overlay = document.getElementById('system-down-overlay')
      if (!overlay) {
        overlay = document.createElement('div')
        overlay.id = 'system-down-overlay'
        overlay.style.cssText = `
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: linear-gradient(135deg, #1e3a8a 0%, #991b1b 100%);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 99999;
          color: white;
          font-family: system-ui, -apple-system, sans-serif;
        `
        
        overlay.innerHTML = `
          <div style="text-align: center; max-width: 500px; padding: 2rem;">
            <div style="font-size: 4rem; margin-bottom: 1rem; animation: pulse 2s infinite;">🔄</div>
            <h1 style="font-size: 2rem; font-weight: bold; margin-bottom: 1rem; color: #fbbf24;">AutoBot System Update</h1>
            <p style="font-size: 1.1rem; margin-bottom: 2rem; opacity: 0.9;">
              The system is restarting or updating. This usually takes 30-60 seconds.
            </p>
            <div style="background: rgba(255, 255, 255, 0.1); border-radius: 20px; padding: 1.5rem; backdrop-filter: blur(10px);">
              <div style="display: flex; align-items: center; gap: 0.5rem; justify-content: center; margin-bottom: 1rem;">
                <span style="font-size: 1.2rem;">🤖</span>
                <span style="font-weight: 500;">Checking system status...</span>
              </div>
              <div style="font-size: 0.9rem; opacity: 0.7;">Please keep this page open</div>
            </div>
            <style>
              @keyframes pulse {
                0%, 100% { transform: scale(1); }
                50% { transform: scale(1.1); }
              }
            </style>
          </div>
        `
        
        document.body.appendChild(overlay)
      }
    }
    
    const hideSystemDownOverlay = () => {
      const overlay = document.getElementById('system-down-overlay')
      if (overlay) {
        overlay.remove()
      }
    }
    
    const startSystemHealthMonitoring = () => {
      // Start monitoring after a 30-second delay to avoid startup conflicts
      console.log('Scheduling system health monitoring to start in 30 seconds')
      setTimeout(() => {
        if (!isSystemDown.value) {
          // Check every 15 seconds (less frequent to reduce false positives)
          systemHealthCheck = setInterval(checkSystemHealth, 15000)
          console.log('System health monitoring started - checking every 15 seconds')
        } else {
          console.log('System health monitoring not started - system already marked as down')
        }
      }, 30000)
    }
    
    const stopSystemHealthMonitoring = () => {
      if (systemHealthCheck) {
        clearInterval(systemHealthCheck)
        systemHealthCheck = null
      }
    }

    const onStartupReady = () => {
      console.log('Startup complete - hiding loader')
      showStartupLoader.value = false
      // Mark that we've completed startup to prevent showing it again
      sessionStorage.setItem('autobot_startup_completed', 'true')
      startSystemHealthMonitoring()
    }

    const onStartupSkip = () => {
      console.log('Startup skipped by user')
      showStartupLoader.value = false
      // Mark that we've completed startup to prevent showing it again
      sessionStorage.setItem('autobot_startup_completed', 'true')
      startSystemHealthMonitoring()
    }

    // Elevation Dialog handlers
    const onElevationApproved = (data) => {
      showElevationDialog.value = false;
    };

    const onElevationCancelled = (requestId) => {
      showElevationDialog.value = false;
    };

    const onElevationClose = () => {
      showElevationDialog.value = false;
    };


    const checkConnectionStatus = async () => {
      try {
        const apiClient = new ApiClient();
        const data = await apiClient.get('/api/system/health');
        backendStatus.value = { text: 'Connected', class: 'connected', message: 'Backend is running' };
        llmStatus.value = data.llm_status ?
          { text: 'Ready', class: 'connected', message: 'LLM is ready' } :
          { text: 'Error', class: 'error', message: 'LLM connection failed' };
        redisStatus.value = data.redis_status ?
          { text: 'Connected', class: 'connected', message: 'Redis is running' } :
          { text: 'Error', class: 'error', message: 'Redis connection failed' };
      } catch (error) {
        // Backend not running - this is expected in frontend-only mode
        backendStatus.value = { text: 'Frontend Only', class: 'warning', message: 'Backend not connected (demo mode)' };
        llmStatus.value = { text: 'Demo Mode', class: 'warning', message: 'Backend required for LLM' };
        redisStatus.value = { text: 'Demo Mode', class: 'warning', message: 'Backend required for Redis' };
      }
    };

    let statusCheckInterval;

    onMounted(() => {
      checkConnectionStatus();
      statusCheckInterval = setInterval(checkConnectionStatus, 10000);

      // Add click-outside listener for mobile menu
      document.addEventListener('click', closeNavbarOnClickOutside);

      // If startup was already completed, start health monitoring immediately
      if (hasCompletedStartup) {
        console.log('Startup already completed, starting health monitoring')
        startSystemHealthMonitoring()
      }

      // Simulate dashboard updates
      setInterval(() => {
        activeSessions.value = Math.floor(Math.random() * 5) + 1;
        performance.value = Math.floor(Math.random() * 20) + 80;
      }, 5000);
    });

    onUnmounted(() => {
      if (statusCheckInterval) {
        clearInterval(statusCheckInterval);
      }
      stopSystemHealthMonitoring();
      hideSystemDownOverlay();
      // Remove click-outside listener
      document.removeEventListener('click', closeNavbarOnClickOutside);
    });

    // Global error handler for ErrorBoundary
    const handleGlobalError = (error, instance, info) => {
      console.error('Global error caught:', error);
      // You can add additional global error handling here
      // e.g., send to analytics, show user notification, etc.
    };

    return {
      // Store instances for template access
      appStore,
      chatStore,
      knowledgeStore,
      // Local reactive refs
      mobileMenuContainer,
      activeToolTab,
      activeMonitoringTab,
      // Computed values
      backendStatus,
      llmStatus,
      redisStatus,
      pageTitle,
      activeSessions,
      knowledgeItems,
      tasksCompleted,
      performance,
      // Methods
      toggleNavbar,
      updateRoute,
      newChat,
      refreshStats,
      // Elevation Dialog
      elevationDialog,
      showElevationDialog,
      elevationOperation,
      elevationCommand,
      elevationReason,
      elevationRiskLevel,
      elevationRequestId,
      onElevationApproved,
      onElevationCancelled,
      onElevationClose,
      handleGlobalError,
      // Phase progression handlers
      onPhaseSuccess,
      onPhaseError,
      onValidationComplete,
      onPhaseValidated,
      // Startup loader and system monitoring
      showStartupLoader,
      onStartupReady,
      onStartupSkip,
      isSystemDown,
      systemDownMessage
    };
  }
};
</script>

<style>
@import './assets/vue-notus.css';
@import url('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css');

/* Accessibility improvements */
.sr-only {
  position: absolute !important;
  width: 1px !important;
  height: 1px !important;
  padding: 0 !important;
  margin: -1px !important;
  overflow: hidden !important;
  clip: rect(0, 0, 0, 0) !important;
  white-space: nowrap !important;
  border: 0 !important;
}

.focus\:not-sr-only:focus {
  position: static !important;
  width: auto !important;
  height: auto !important;
  padding: inherit !important;
  margin: inherit !important;
  overflow: visible !important;
  clip: auto !important;
  white-space: normal !important;
}

/* Enhanced focus indicators */
button:focus,
a:focus,
[tabindex]:focus {
  outline: 2px solid #3b82f6 !important;
  outline-offset: 2px !important;
}

/* Vue Notus Color Mappings for App.vue */
.bg-blueGray-50 { background-color: var(--blue-gray-50); }
.bg-blueGray-100 { background-color: var(--blue-gray-100); }
.bg-blueGray-200 { background-color: var(--blue-gray-200); }
.bg-blueGray-400 { background-color: var(--blue-gray-400); }
.bg-blueGray-800 { background-color: var(--blue-gray-800); }
.bg-blueGray-900 { background-color: var(--blue-gray-900); }

.text-blueGray-200 { color: var(--blue-gray-200); }
.text-blueGray-400 { color: var(--blue-gray-400); }
.text-blueGray-600 { color: var(--blue-gray-600); }
.text-blueGray-700 { color: var(--blue-gray-700); }

.text-indigo-500 { color: var(--indigo-500); }
.bg-indigo-50 { background-color: var(--indigo-50); }
.bg-indigo-500 { background-color: var(--indigo-500); }
.bg-indigo-600 { background-color: var(--indigo-600); }
.bg-indigo-700 { background-color: var(--indigo-700); }
.bg-indigo-800 { background-color: var(--indigo-800); }

.text-emerald-500 { color: var(--emerald-500); }
.bg-emerald-500 { background-color: var(--emerald-500); }
.text-red-500 { color: var(--red-500); }
.bg-red-500 { background-color: var(--red-500); }
.bg-orange-500 { background-color: var(--orange-500); }
.text-orange-500 { color: var(--orange-500); }

.border-blueGray-200 { border-color: var(--blue-gray-200); }

.hover\\:text-blueGray-500:hover { color: var(--blue-gray-500); }
.hover\\:text-white:hover { color: white; }
.active\\:bg-indigo-600:active { background-color: var(--indigo-600); }

/* Gradient backgrounds */
.from-indigo-500 { --tw-gradient-from: var(--indigo-500); }
.to-indigo-700 { --tw-gradient-to: var(--indigo-700); }
.from-indigo-600 { --tw-gradient-from: var(--indigo-600); }
.to-indigo-800 { --tw-gradient-to: var(--indigo-800); }
.bg-gradient-to-br {
  background: linear-gradient(to bottom right, var(--tw-gradient-from, var(--indigo-500)), var(--tw-gradient-to, var(--indigo-700)));
}
.bg-gradient-to-r {
  background: linear-gradient(to right, var(--tw-gradient-from, var(--indigo-500)), var(--tw-gradient-to, var(--indigo-600)));
}

/* Light blue colors for dashboard cards */
.bg-lightBlue-500 { background-color: #0ea5e9; }
.text-lightBlue-500 { color: #0ea5e9; }

/* Table styling */
.divide-y > * + * { border-top-width: 1px; }
.divide-blueGray-200 > * + * { border-color: var(--blue-gray-200); }
.min-w-full { min-width: 100%; }
.overflow-x-auto { overflow-x: auto; }
.h-8 { height: 2rem; }
.w-8 { width: 2rem; }
.-m-12 { margin: -3rem; }
.-mt-6 { margin-top: -1.5rem; }
.mt-0 { margin-top: 0; }
.grid { display: grid; }
.grid-cols-1 { grid-template-columns: repeat(1, minmax(0, 1fr)); }
.gap-4 { gap: 1rem; }
.bg-yellow-100 { background-color: #fef3c7; }
.text-yellow-800 { color: #92400e; }
.mb-4 { margin-bottom: 1rem; }
.space-y-2 > * + * { margin-top: 0.5rem; }
.text-indigo-200 { color: #c7d2fe; }
.bg-opacity-10 { background-color: rgba(255, 255, 255, 0.1); }
.bg-opacity-20 { background-color: rgba(255, 255, 255, 0.2); }
.hover\:bg-opacity-10:hover { background-color: rgba(255, 255, 255, 0.1); }
.h-screen { height: 100vh; }
.justify-start { justify-content: flex-start; }
.top-full { top: 100%; }
.backdrop-blur-sm { backdrop-filter: blur(4px); }
.bg-opacity-95 { background-color: rgba(255, 255, 255, 0.95); }
.border-opacity-20 { border-color: rgba(255, 255, 255, 0.2); }
.mx-4 { margin-left: 1rem; margin-right: 1rem; }
.mt-2 { margin-top: 0.5rem; }
.hover\:bg-indigo-50:hover { background-color: var(--indigo-50); }
.hover\:text-indigo-600:hover { color: var(--indigo-600); }
.w-64 { width: 16rem; }

/* Essential layout utilities missing from Vue Notus */
.items-center { align-items: center; }
.justify-between { justify-content: space-between; }
.flex-wrap { flex-wrap: wrap; }
.flex-nowrap { flex-wrap: nowrap; }
.flex-col { flex-direction: column; }
.flex-row { flex-direction: row; }
.min-h-full { min-height: 100%; }
.min-h-screen { min-height: 100vh; }
.list-none { list-style: none; }
.block { display: block; }
.relative { position: relative; }
.absolute { position: absolute; }
.fixed { position: fixed; }
.z-10 { z-index: 10; }
.z-40 { z-index: 40; }
.z-50 { z-index: 50; }
.z-60 { z-index: 60; }
.z-70 { z-index: 70; }
.overflow-hidden { overflow: hidden; }
.overflow-y-auto { overflow-y: auto; }

/* Animation classes for system status */
.animate-pulse {
  animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

.animate-spin {
  animation: spin 1s linear infinite;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: .5;
  }
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
.overflow-x-hidden { overflow-x: hidden; }
.mx-auto { margin-left: auto; margin-right: auto; }
.mt-auto { margin-top: auto; }
.mt-4 { margin-top: 1rem; }
.mt-6 { margin-top: 1.5rem; }
.mb-3 { margin-bottom: 0.75rem; }
.mb-6 { margin-bottom: 1.5rem; }
.mb-12 { margin-bottom: 3rem; }
.ml-3 { margin-left: 0.75rem; }
.mr-2 { margin-right: 0.5rem; }
.pt-6 { padding-top: 1.5rem; }
.pt-8 { padding-top: 2rem; }
.pt-12 { padding-top: 3rem; }
.pb-16 { padding-bottom: 4rem; }
.pb-32 { padding-bottom: 8rem; }
.px-0 { padding-left: 0; padding-right: 0; }
.px-3 { padding-left: 0.75rem; padding-right: 0.75rem; }
.px-4 { padding-left: 1rem; padding-right: 1rem; }
.px-6 { padding-left: 1.5rem; padding-right: 1.5rem; }
.py-1 { padding-top: 0.25rem; padding-bottom: 0.25rem; }
.py-3 { padding-top: 0.75rem; padding-bottom: 0.75rem; }
.py-4 { padding-top: 1rem; padding-bottom: 1rem; }
.w-full { width: 100%; }
.w-12 { width: 3rem; }
.h-12 { height: 3rem; }
.h-auto { height: auto; }
.max-w-full { max-width: 100%; }
.flex-grow { flex-grow: 1; }
.flex-initial { flex: 0 1 auto; }
.flex-auto { flex: 1 1 auto; }
.flex-1 { flex: 1 1 0%; }
.whitespace-nowrap { white-space: nowrap; }
.cursor-pointer { cursor: pointer; }
.uppercase { text-transform: uppercase; }
.font-bold { font-weight: 700; }
.font-semibold { font-weight: 600; }
.text-xs { font-size: 0.75rem; line-height: 1rem; }
.text-sm { font-size: 0.875rem; line-height: 1.25rem; }
.text-lg { font-size: 1.125rem; line-height: 1.75rem; }
.text-xl { font-size: 1.25rem; line-height: 1.75rem; }
.text-2xl { font-size: 1.5rem; line-height: 2rem; }
.tracking-wider { letter-spacing: 0.05em; }
.space-y-2 > * + * { margin-top: 0.5rem; }
.space-y-3 > * + * { margin-top: 0.75rem; }
.space-x-2 > * + * { margin-left: 0.5rem; }
.space-x-4 > * + * { margin-left: 1rem; }

.inline-flex { display: inline-flex; }
.ml-auto { margin-left: auto; }
.flex-shrink-0 { flex-shrink: 0; }
.justify-center { justify-content: center; }

/* Medium screen grid utilities */
@media (min-width: 768px) {
  .md\\:grid-cols-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

/* Large screen grid utilities */
@media (min-width: 1024px) {
  .lg\\:grid-cols-4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}

/* Responsive utilities */
@media (min-width: 768px) {
  .md\\:left-0 { left: 0; }
  .md\\:block { display: block; }
  .md\\:fixed { position: fixed; }
  .md\\:top-0 { top: 0; }
  .md\\:bottom-0 { bottom: 0; }
  .md\\:w-64 { width: 16rem; }
  .md\\:flex { display: flex; }
  .md\\:flex-col { flex-direction: column; }
  .md\\:flex-row { flex-direction: row; }
  .md\\:flex-nowrap { flex-wrap: nowrap; }
  .md\\:items-stretch { align-items: stretch; }
  .md\\:min-h-full { min-height: 100%; }
  .md\\:min-w-full { min-width: 100%; }
  .md\\:opacity-100 { opacity: 1; }
  .md\\:relative { position: relative; }
  .md\\:mt-4 { margin-top: 1rem; }
  .md\\:shadow-none { box-shadow: none; }
  .md\\:overflow-y-auto { overflow-y: auto; }
  .md\\:overflow-hidden { overflow: hidden; }
  .md\\:hidden { display: none; }
  .md\\:ml-64 { margin-left: 16rem; }
  .md\\:flex-nowrap { flex-wrap: nowrap; }
  .md\\:justify-start { justify-content: flex-start; }
  .md\\:px-10 { padding-left: 2.5rem; padding-right: 2.5rem; }
  .md\\:pt-16 { padding-top: 4rem; }
  .md\\:pt-32 { padding-top: 8rem; }
}

/* Transitions */
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.3s ease;
}

.fade-slide-enter-from {
  transform: translateY(10px);
  opacity: 0;
}

.fade-slide-leave-to {
  transform: translateY(-10px);
  opacity: 0;
}

/* Custom scrollbar */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: #f1f5f9;
}

::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}
</style>
