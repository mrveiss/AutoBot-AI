<template>
  <div id="app" class="h-screen bg-gray-100 flex flex-col overflow-hidden">
    <!-- Skip Navigation Links -->
    <div class="skip-links">
      <a href="#main-content" class="skip-link sr-only-focusable">Skip to main content</a>
      <a href="#navigation" class="skip-link sr-only-focusable">Skip to navigation</a>
    </div>

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
          <nav id="navigation" class="hidden lg:block" role="navigation" aria-label="Main navigation">
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
                  to="/automation"
                  :class="{
                    'bg-white text-indigo-700': $route.path.startsWith('/automation'),
                    'text-white hover:bg-indigo-500': !$route.path.startsWith('/automation')
                  }"
                  class="px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200"
                >
                  <div class="flex items-center space-x-1">
                    <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                      <path fill-rule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" clip-rule="evenodd"></path>
                    </svg>
                    <span>Automation</span>
                  </div>
                </router-link>

                <router-link
                  to="/analytics"
                  :class="{
                    'bg-white text-indigo-700': $route.path.startsWith('/analytics'),
                    'text-white hover:bg-indigo-500': !$route.path.startsWith('/analytics')
                  }"
                  class="px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200"
                >
                  <div class="flex items-center space-x-1">
                    <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                      <path d="M2 10a8 8 0 018-8v8h8a8 8 0 11-16 0z"></path>
                      <path d="M12 2.252A8.014 8.014 0 0117.748 8H12V2.252z"></path>
                    </svg>
                    <span>Analytics</span>
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

                <!-- Issue #729: Link to SLM Admin for infrastructure operations -->
                <a
                  :href="slmAdminUrl"
                  target="_blank"
                  class="px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200 text-white hover:bg-indigo-500"
                  title="Open SLM Admin for infrastructure management"
                >
                  <div class="flex items-center space-x-1">
                    <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                      <path fill-rule="evenodd" d="M2 5a2 2 0 012-2h12a2 2 0 012 2v10a2 2 0 01-2 2H4a2 2 0 01-2-2V5zm3.293 1.293a1 1 0 011.414 0l3 3a1 1 0 010 1.414l-3 3a1 1 0 01-1.414-1.414L7.586 10 5.293 7.707a1 1 0 010-1.414zM11 12a1 1 0 100 2h3a1 1 0 100-2h-3z" clip-rule="evenodd"></path>
                    </svg>
                    <span>SLM Admin</span>
                    <svg class="w-3 h-3 opacity-50" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                      <path d="M11 3a1 1 0 100 2h2.586l-6.293 6.293a1 1 0 101.414 1.414L15 6.414V9a1 1 0 102 0V4a1 1 0 00-1-1h-5z"></path>
                      <path d="M5 5a2 2 0 00-2 2v8a2 2 0 002 2h8a2 2 0 002-2v-3a1 1 0 10-2 0v3H5V7h3a1 1 0 000-2H5z"></path>
                    </svg>
                  </div>
                </a>
              </div>
            </div>
          </nav>

          <!-- Right side - Status and controls -->
          <div class="flex items-center space-x-4">
            <!-- Dark Mode Toggle -->
            <DarkModeToggle />

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
              to="/automation"
              @click="closeMobileNav"
              :class="{
                'bg-white text-indigo-700': $route.path.startsWith('/automation'),
                'text-white hover:bg-indigo-600': !$route.path.startsWith('/automation')
              }"
              class="w-full text-left px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200 block"
            >
              <div class="flex items-center space-x-2">
                <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                  <path fill-rule="evenodd" d="M11.3 1.046A1 1 0 0112 2v5h4a1 1 0 01.82 1.573l-7 10A1 1 0 018 18v-5H4a1 1 0 01-.82-1.573l7-10a1 1 0 011.12-.38z" clip-rule="evenodd"></path>
                </svg>
                <span>Automation</span>
              </div>
            </router-link>

            <router-link
              to="/analytics"
              @click="closeMobileNav"
              :class="{
                'bg-white text-indigo-700': $route.path.startsWith('/analytics'),
                'text-white hover:bg-indigo-600': !$route.path.startsWith('/analytics')
              }"
              class="w-full text-left px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200 block"
            >
              <div class="flex items-center space-x-2">
                <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                  <path d="M2 10a8 8 0 018-8v8h8a8 8 0 11-16 0z"></path>
                  <path d="M12 2.252A8.014 8.014 0 0117.748 8H12V2.252z"></path>
                </svg>
                <span>Analytics</span>
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

            <!-- Issue #729: Link to SLM Admin for infrastructure operations -->
            <a
              :href="slmAdminUrl"
              @click="closeMobileNav"
              class="w-full text-left px-3 py-2 rounded-md text-sm font-medium transition-colors duration-200 block text-white hover:bg-indigo-600"
            >
              <div class="flex items-center space-x-2">
                <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                  <path fill-rule="evenodd" d="M2 5a2 2 0 012-2h12a2 2 0 012 2v10a2 2 0 01-2 2H4a2 2 0 01-2-2V5zm3.293 1.293a1 1 0 011.414 0l3 3a1 1 0 010 1.414l-3 3a1 1 0 01-1.414-1.414L7.586 10 5.293 7.707a1 1 0 010-1.414zM11 12a1 1 0 100 2h3a1 1 0 100-2h-3z" clip-rule="evenodd"></path>
                </svg>
                <span>SLM Admin</span>
                <svg class="w-3 h-3 opacity-50" fill="currentColor" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                  <path d="M11 3a1 1 0 100 2h2.586l-6.293 6.293a1 1 0 101.414 1.414L15 6.414V9a1 1 0 102 0V4a1 1 0 00-1-1h-5z"></path>
                  <path d="M5 5a2 2 0 00-2 2v8a2 2 0 002 2h8a2 2 0 002-2v-3a1 1 0 10-2 0v3H5V7h3a1 1 0 000-2H5z"></path>
                </svg>
              </div>
            </a>
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

    <!-- System Status Modal -->
    <Teleport to="body">
      <div
        v-if="showSystemStatus"
        class="fixed inset-0 z-50 overflow-y-auto"
        @click="showSystemStatus = false"
      >
        <div class="flex min-h-full items-end justify-center p-4 text-center sm:items-center sm:p-0">
          <div class="fixed inset-0 bg-gray-500 bg-opacity-75 transition-opacity"></div>

          <div
            @click.stop
            class="relative transform overflow-hidden rounded-lg bg-white px-4 pb-4 pt-5 text-left shadow-xl transition-all sm:my-8 sm:w-full sm:max-w-lg sm:p-6"
          >
            <!-- Header -->
            <div class="flex items-center justify-between border-b border-gray-200 pb-3 mb-4">
              <h3 class="text-lg font-medium text-gray-900 flex items-center">
                <div class="w-6 h-6 bg-indigo-600 rounded flex items-center justify-center mr-2">
                  <span class="text-white text-xs font-bold">AB</span>
                </div>
                AutoBot System Status
              </h3>
              <button
                @click="showSystemStatus = false"
                class="rounded-md text-gray-400 hover:text-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <svg class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <!-- System Overview -->
            <div class="mb-4">
              <div
                :class="{
                  'bg-green-50 border-green-200': systemStatus.isHealthy && !systemStatus.hasIssues,
                  'bg-yellow-50 border-yellow-200': !systemStatus.isHealthy && !systemStatus.hasIssues,
                  'bg-red-50 border-red-200': systemStatus.hasIssues
                }"
                class="rounded-lg border p-3 flex items-center"
              >
                <div
                  :class="{
                    'bg-green-400': systemStatus.isHealthy && !systemStatus.hasIssues,
                    'bg-yellow-400': !systemStatus.isHealthy && !systemStatus.hasIssues,
                    'bg-red-400': systemStatus.hasIssues,
                    'animate-pulse': systemStatus.hasIssues
                  }"
                  class="w-3 h-3 rounded-full mr-3"
                ></div>
                <div>
                  <p class="font-medium text-gray-900">{{ getSystemStatusText() }}</p>
                  <p class="text-sm text-gray-600">{{ getSystemStatusDescription() }}</p>
                </div>
              </div>
            </div>

            <!-- Services Status -->
            <div class="space-y-3">
              <h4 class="font-medium text-gray-900">Services</h4>
              <div class="space-y-2">
                <div
                  v-for="service in systemServices"
                  :key="service.name"
                  class="flex items-center justify-between p-2 rounded border"
                >
                  <div class="flex items-center">
                    <div
                      :class="{
                        'bg-green-400': service.status === 'healthy',
                        'bg-yellow-400': service.status === 'warning',
                        'bg-red-400': service.status === 'error'
                      }"
                      class="w-2 h-2 rounded-full mr-2"
                    ></div>
                    <span class="text-sm font-medium">{{ service.name }}</span>
                  </div>
                  <span
                    :class="{
                      'text-green-600': service.status === 'healthy',
                      'text-yellow-600': service.status === 'warning',
                      'text-red-600': service.status === 'error'
                    }"
                    class="text-xs"
                  >
                    {{ service.statusText }}
                  </span>
                </div>
              </div>
            </div>

            <!-- Action Buttons -->
            <div class="mt-6 flex justify-between">
              <button
                @click="refreshSystemStatus"
                class="inline-flex items-center px-3 py-2 border border-gray-300 shadow-sm text-sm leading-4 font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
              >
                <svg class="w-4 h-4 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path>
                </svg>
                Refresh
              </button>
              <button
                @click="showSystemStatus = false"
                class="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- System Status Notifications (limit to last 5 to prevent teleport accumulation) -->
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

    <!-- CAPTCHA Human-in-the-Loop Notification (Issue #206) -->
    <CaptchaNotification />

    <!-- Toast Notifications Container (Issue #502) -->
    <ToastContainer />

    <!-- Host Selection Dialog for Agent SSH Actions -->
    <HostSelectionDialog
      :show="hostSelectionState.showDialog"
      :command="hostSelectionState.pendingRequest?.command"
      :purpose="hostSelectionState.pendingRequest?.purpose"
      :request-id="hostSelectionState.pendingRequest?.requestId"
      @selected="onHostSelected"
      @cancelled="onHostSelectionCancelled"
      @close="onHostSelectionClose"
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

  <!-- Issue #729: RUM Dashboard moved to slm-admin -->
</template>

<script lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useRouter } from 'vue-router';
import { useAppStore } from '@/stores/useAppStore'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('App');
import { useChatStore } from '@/stores/useChatStore'
import { useKnowledgeStore } from '@/stores/useKnowledgeStore'
import { useSystemStatus } from '@/composables/useSystemStatus'
import SystemStatusNotification from '@/components/ui/SystemStatusNotification.vue';
import CaptchaNotification from '@/components/research/CaptchaNotification.vue';
import ToastContainer from '@/components/ui/ToastContainer.vue';
import HostSelectionDialog from '@/components/ui/HostSelectionDialog.vue';
import { useHostSelection } from '@/composables/useHostSelection';
import { cacheBuster } from '@/utils/CacheBuster.js';
import { optimizedHealthMonitor } from '@/utils/OptimizedHealthMonitor.js';
import { initializeNotificationBridge } from '@/utils/notificationBridge';
import { smartMonitoringController, getAdaptiveInterval } from '@/config/OptimizedPerformance.js';
import { clearAllSystemNotifications, resetHealthMonitor } from '@/utils/ClearNotifications.js';
import UnifiedLoadingView from '@/components/ui/UnifiedLoadingView.vue';
import { getSLMAdminUrl } from '@/config/ssot-config';

export default {
  name: 'App',

  components: {
    SystemStatusNotification,
    CaptchaNotification,
    ToastContainer,
    HostSelectionDialog,
    UnifiedLoadingView,
    DarkModeToggle: () => import('@/components/ui/DarkModeToggle.vue'),
  },

  setup() {
    // Store references
    const appStore = useAppStore();
    const chatStore = useChatStore();
    const knowledgeStore = useKnowledgeStore();
    const router = useRouter();

    // FIXED: Use useSystemStatus composable instead of duplicate logic
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

    // Host selection composable for agent SSH actions
    const {
      showDialog: hostSelectionShowDialog,
      pendingRequest: hostSelectionPendingRequest,
      handleHostSelected,
      handleDialogCancelled,
      handleDialogClose
    } = useHostSelection()

    // Create reactive state object for host selection
    const hostSelectionState = computed(() => ({
      showDialog: hostSelectionShowDialog.value,
      pendingRequest: hostSelectionPendingRequest.value
    }))

    // Host selection event handlers
    const onHostSelected = (result: { host: any; rememberChoice: boolean }) => {
      handleHostSelected(result)
    }

    const onHostSelectionCancelled = () => {
      handleDialogCancelled()
    }

    const onHostSelectionClose = () => {
      handleDialogClose()
    }

    // Reactive data (non-status related)
    const showMobileNav = ref(false);
    let notificationCleanup: number | null = null;

    // Computed properties
    const isLoading = computed(() => appStore?.isLoading || false);
    const hasErrors = computed(() => false); // No errors property in store

    // Methods
    const toggleMobileNav = () => {
      showMobileNav.value = !showMobileNav.value;
    };

    const closeMobileNav = () => {
      showMobileNav.value = false;
    };

    const closeNavbarOnClickOutside = (event: MouseEvent) => {
      // Close mobile nav when clicking outside
      const target = event.target as HTMLElement | null;
      if (showMobileNav.value && target && !target.closest('#mobile-nav') && !target.closest('[aria-controls="mobile-nav"]')) {
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
        // Knowledge store doesn't have clearCache method
        // Clear by refreshing stats
        if (knowledgeStore && typeof knowledgeStore.refreshStats === 'function') {
          await knowledgeStore.refreshStats();
        }

        // Reload the page
        window.location.reload();
      } catch (error) {
        logger.error('Error clearing caches:', error);
      }
    };

    const handleGlobalError = (error: Error) => {
      logger.error('Global error:', error);
      if (appStore && typeof appStore.addSystemNotification === 'function') {
        appStore.addSystemNotification({
          severity: 'error',
          title: 'Application Error',
          message: error.message || 'An unexpected error occurred'
        });
      }
    };

    // Unified loading event handlers
    const handleLoadingComplete = () => {
      logger.debug('Loading completed successfully');
      if (appStore && typeof appStore.setLoading === 'function') {
        appStore.setLoading(false);
      }
    };

    const handleLoadingError = (error: string | Error) => {
      logger.error('Loading error:', error);
      handleGlobalError(error instanceof Error ? error : new Error(String(error)));
    };

    const handleLoadingTimeout = () => {
      logger.warn('Loading timed out - continuing with available content');
      if (appStore && typeof appStore.addSystemNotification === 'function') {
        appStore.addSystemNotification({
          severity: 'warning',
          title: 'Loading Timeout',
          message: 'Some components took longer than expected to load, but the application is ready to use.'
        });
      }
    };

    // OPTIMIZED: Intelligent system health monitoring
    const startOptimizedHealthCheck = () => {
      logger.debug('Starting optimized health monitoring system...');

      // Listen for health changes from optimized monitor
      optimizedHealthMonitor.onHealthChange((healthData) => {
        // Update app store with health status
        if (appStore && typeof appStore.setBackendStatus === 'function') {
          const backendStatus = healthData.status.backend;

          // Determine status text based on backend health
          let statusText = 'Disconnected';
          let statusClass: 'success' | 'warning' | 'error' = 'error';

          if (backendStatus === 'healthy') {
            statusText = 'Connected';
            statusClass = 'success';
          } else if (backendStatus === 'degraded') {
            statusText = 'Degraded';
            statusClass = 'warning';
          }

          appStore.setBackendStatus({
            text: statusText,
            class: statusClass
          });
        }

        // Update smart monitoring controller (filter out 'unknown' state)
        const healthState = healthData.status.overall;
        if (healthState !== 'unknown') {
          smartMonitoringController.setSystemHealth(healthState);
        }
      });

      logger.debug('Optimized health monitoring initialized');
    };

    // OPTIMIZED: Smart notification cleanup with adaptive intervals
    const startOptimizedNotificationCleanup = () => {
      if (notificationCleanup) {
        clearInterval(notificationCleanup);
      }

      // Use adaptive interval based on system state
      const cleanupInterval = getAdaptiveInterval('NOTIFICATION_CLEANUP', 'healthy', false);

      notificationCleanup = setInterval(() => {
        if (appStore && appStore.systemNotifications && appStore.systemNotifications.length > 5) {
          logger.debug('Cleaning up excessive notifications:', appStore.systemNotifications.length);
          // Keep only the last 5 notifications
          const recentNotifications = appStore.systemNotifications.slice(-5);
          appStore.systemNotifications.splice(0, appStore.systemNotifications.length, ...recentNotifications);
        }
      }, cleanupInterval);

      logger.debug(`Notification cleanup scheduled every ${Math.round(cleanupInterval/60000)} minutes`);
    };

    const stopOptimizedNotificationCleanup = () => {
      if (notificationCleanup) {
        clearInterval(notificationCleanup);
        notificationCleanup = null;
      }
    };

    // Router event monitoring - OPTIMIZED: Event-driven instead of polling
    const setupRouterMonitoring = () => {
      // Monitor router navigation events
      router.afterEach((to, from) => {
        logger.debug(`Navigation: ${from.path} → ${to.path}`);

        // Update user activity in smart monitoring controller
        smartMonitoringController.userActivity.lastActivity = Date.now();
        smartMonitoringController.userActivity.isActive = true;
      });

      // Monitor router errors
      router.onError((error) => {
        logger.error('Router error:', error);
        handleGlobalError(error);
      });
    };

    // Lifecycle hooks
    onMounted(async () => {
      logger.debug('Initializing optimized AutoBot application...');

      // Add global click listener for mobile nav
      document.addEventListener('click', closeNavbarOnClickOutside);

      // Set up global error handling
      window.addEventListener('error', (event) => {
        handleGlobalError(event.error || event);
      });

      window.addEventListener('unhandledrejection', (event) => {
        handleGlobalError(event.reason);
      });

      // CRITICAL FIX: Clear any stuck system notifications on startup
      logger.debug('Clearing stuck system notifications on startup...');
      clearAllSystemNotifications();
      resetHealthMonitor();

      // Initialize notification bridge for ErrorHandler integration (Issue #502)
      initializeNotificationBridge();
      logger.debug('NotificationBridge initialized for ErrorHandler integration');

      // OPTIMIZED: Initialize new performance-aware systems
      try {
        // Initialize cache buster
        if (cacheBuster && typeof cacheBuster.initialize === 'function') {
          cacheBuster.initialize();
        }

        // OPTIMIZED: Start optimized health monitoring
        startOptimizedHealthCheck();

        // FIXED: Use useSystemStatus composable's refresh method
        logger.debug('Initializing system status with composable...');
        try {
          await refreshSystemStatus();
          updateSystemStatus();
        } catch (statusError) {
          logger.warn('System status initialization failed, but Vue app will continue:', statusError);
          // Don't throw - let Vue app mount successfully
        }

        // OPTIMIZED: Setup router monitoring (event-driven)
        setupRouterMonitoring();

        logger.debug('Optimized monitoring systems initialized successfully');

      } catch (error) {
        logger.error('Error initializing optimized systems:', error);
        // Don't let initialization errors prevent app mounting
      }

      // OPTIMIZED: Start adaptive notification cleanup
      startOptimizedNotificationCleanup();

      // Set loading to false once initialization is complete
      if (appStore && typeof appStore.setLoading === 'function') {
        appStore.setLoading(false);
      }

      logger.debug('✅ Optimized AutoBot initialized - monitoring restored with <50ms performance budget');
    });

    onUnmounted(() => {
      logger.debug('Cleaning up optimized monitoring systems...');

      // Clean up listeners
      document.removeEventListener('click', closeNavbarOnClickOutside);
      stopOptimizedNotificationCleanup();

      // Destroy optimized health monitor
      if (optimizedHealthMonitor && typeof optimizedHealthMonitor.destroy === 'function') {
        optimizedHealthMonitor.destroy();
      }
    });

    // SLM Admin URL from SSOT config (Issue #729)
    const slmAdminUrl = computed(() => getSLMAdminUrl());

    return {
      // Store references
      appStore,
      chatStore,
      knowledgeStore,

      // Reactive data
      showMobileNav,

      // System status (from composable)
      showSystemStatus,
      systemStatus,
      systemServices,

      // Computed
      isLoading,
      hasErrors,
      slmAdminUrl,

      // Methods
      toggleMobileNav,
      closeMobileNav,
      clearAllCaches,
      handleGlobalError,

      // Unified loading handlers
      handleLoadingComplete,
      handleLoadingError,
      handleLoadingTimeout,

      // System status methods (from composable)
      toggleSystemStatus,
      getSystemStatusTooltip,
      getSystemStatusText,
      getSystemStatusDescription,
      refreshSystemStatus,
      updateSystemStatus,

      // Host selection (for agent SSH actions)
      hostSelectionState,
      onHostSelected,
      onHostSelectionCancelled,
      onHostSelectionClose,
    };
  }
};
</script>

<style scoped>
/* Skip Navigation Links */
.skip-links {
  position: relative;
  z-index: 9999;
}

.skip-link {
  position: absolute;
  top: -40px;
  left: 0;
  background: #000;
  color: #fff;
  padding: 8px 16px;
  text-decoration: none;
  border-radius: 0 0 4px 0;
  font-size: 14px;
  font-weight: 500;
  transition: top 0.2s ease-in-out;
  z-index: 10000;
}

.skip-link:focus {
  top: 0;
  outline: 2px solid #fff;
  outline-offset: 2px;
}

/* Navigation link focus indicators */
nav a:focus-visible {
  outline: 2px solid rgba(255, 255, 255, 0.8);
  outline-offset: 2px;
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.3);
}

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
