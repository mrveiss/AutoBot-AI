<template>
  <div class="chromium-browser-container">
    <!-- Browser Header -->
    <div class="browser-header bg-autobot-bg-tertiary border-b border-autobot-border p-2 flex items-center justify-between">
      <div class="flex items-center gap-3">
        <div class="flex gap-1">
          <div class="w-3 h-3 bg-red-500 rounded-full"></div>
          <div class="w-3 h-3 bg-yellow-500 rounded-full"></div>
          <div class="w-3 h-3 bg-green-500 rounded-full"></div>
        </div>
        <div class="flex items-center gap-2 text-sm">
          <Icon name="globe" />
          <span class="font-medium">{{ $t('desktop.popoutBrowser.title') }}</span>
          <span v-if="sessionId" class="text-xs text-autobot-text-muted">{{ $t('desktop.popoutBrowser.sessionLabel', { id: sessionId.slice(0, 8) }) }}</span>
        </div>
      </div>

      <div class="flex items-center gap-2">
        <!-- Browser Controls -->
        <div class="flex items-center gap-1">
          <button @click="refreshBrowser" class="browser-btn" :disabled="isRefreshing" :title="$t('desktop.popoutBrowser.refresh')" :aria-label="$t('desktop.popoutBrowser.refresh')">
            <Icon name="sync-alt" />
          </button>

          <button @click="navigateHome" class="browser-btn" :title="$t('desktop.popoutBrowser.home')" :aria-label="$t('desktop.popoutBrowser.home')">
            <Icon name="home" />
          </button>

          <button @click="showDevTools = !showDevTools" class="browser-btn" :title="$t('desktop.popoutBrowser.devTools')" :aria-label="$t('desktop.popoutBrowser.devTools')">
            <Icon name="code" />
          </button>

          <button @click="openVncPopout" class="browser-btn" style="color: var(--color-primary)" :title="$t('desktop.popoutBrowser.openVnc')" :aria-label="$t('desktop.popoutBrowser.openVnc')">
            <Icon name="desktop" />
          </button>
        </div>

        <!-- Playwright Automation Controls -->
        <div class="border-l border-autobot-border pl-2 flex items-center gap-1">
          <!-- Templates sidebar toggle (#5136 Phase 5) -->
          <button
            @click="showTemplatePanel = !showTemplatePanel"
            class="browser-btn"
            :class="{ 'text-color-primary': showTemplatePanel }"
            :title="$t('desktop.popoutBrowser.templates')"
            :aria-label="$t('desktop.popoutBrowser.templates')"
          >
            <Icon name="layer-group" />
          </button>

          <button @click="showPlaywrightPanel = !showPlaywrightPanel" class="browser-btn" :title="$t('desktop.popoutBrowser.playwrightAutomation')" :aria-label="$t('desktop.popoutBrowser.playwrightAutomation')">
            <Icon name="robot" />
          </button>

          <button @click="runFrontendTest" class="browser-btn" :disabled="isTestingFrontend" :title="$t('desktop.popoutBrowser.testFrontend')" :aria-label="$t('desktop.popoutBrowser.testFrontend')">
            <Icon name="vial" />
          </button>

          <button @click="performWebSearch" class="browser-btn" :disabled="isSearching" :title="$t('desktop.popoutBrowser.webSearch')" :aria-label="$t('desktop.popoutBrowser.webSearch')">
            <Icon name="search" />
          </button>

          <button @click="sendTestMessage" class="browser-btn" :disabled="isSendingMessage" :title="$t('desktop.popoutBrowser.testMessage')" :aria-label="$t('desktop.popoutBrowser.testMessage')">
            <Icon name="paper-plane" />
          </button>
        </div>

        <div class="border-l border-autobot-border pl-2">
          <button @click="$emit('close')" class="browser-btn text-red-600" :title="$t('desktop.popoutBrowser.close')" :aria-label="$t('desktop.popoutBrowser.close')">
            <Icon name="times" />
          </button>
        </div>
      </div>
    </div>

    <!-- Address Bar -->
    <div class="address-bar bg-autobot-bg-secondary border-b border-autobot-border p-3 flex items-center gap-3">
      <button @click="goBack" :disabled="!canGoBack || isGoingBack" class="nav-btn" :title="$t('desktop.popoutBrowser.back')" :aria-label="$t('desktop.popoutBrowser.back')">
        <Icon name="arrow-left" />
      </button>
      <button @click="goForward" :disabled="!canGoForward || isGoingForward" class="nav-btn" :title="$t('desktop.popoutBrowser.forward')" :aria-label="$t('desktop.popoutBrowser.forward')">
        <Icon name="arrow-right" />
      </button>
      <div class="flex-1 flex items-center bg-autobot-bg-tertiary rounded-lg px-3 py-2" :class="{ 'opacity-50': isNavigating }">
        <Icon name="lock" class="text-green-500 text-sm mr-2" />
        <input
          v-model="addressBarUrl"
          @keyup.enter="navigateToUrl(addressBarUrl)"
          class="flex-1 bg-transparent text-sm outline-hidden"
          :placeholder="$t('desktop.popoutBrowser.addressPlaceholder')"
        />
        <button @click="navigateToUrl(addressBarUrl)" :disabled="isNavigating" class="ml-2 text-autobot-text-secondary hover:text-autobot-text-primary">
          <Icon name="search" />
        </button>
      </div>
      <div class="text-xs text-autobot-text-muted">
        {{ Math.round(zoomLevel) }}% | {{ pageLoadTime }}ms
      </div>
      <!-- Region-marking toggle (#5136 / #6446) -->
      <button
        @click="toggleRegionMarking"
        :disabled="isSnapshotLoading || !sessionId || sessionId === 'manual-browser'"
        class="nav-btn"
        :class="{ 'text-color-primary': markRegionsMode }"
        :title="markRegionsMode ? $t('desktop.popoutBrowser.exitRegionMode') : $t('desktop.popoutBrowser.markRegions')"
        :aria-label="markRegionsMode ? $t('desktop.popoutBrowser.exitRegionMode') : $t('desktop.popoutBrowser.markRegions')"
      >
        <Icon :name="isSnapshotLoading ? 'spinner' : 'th'" :class="isSnapshotLoading ? 'animate-spin' : ''" />
      </button>
      <!-- AI Propose button (MVA-1380) — only shown in region-marking mode -->
      <button
        v-if="markRegionsMode"
        @click="showAiGoalInput = !showAiGoalInput"
        :disabled="isAiProposing"
        class="nav-btn"
        :class="{ 'text-color-primary': showAiGoalInput }"
        title="AI Propose regions"
        aria-label="AI Propose regions"
      >
        <Icon :name="isAiProposing ? 'spinner' : 'magic'" :class="isAiProposing ? 'animate-spin' : ''" />
      </button>
    </div>
    <!-- AI goal input strip (MVA-1380) -->
    <div v-if="markRegionsMode && showAiGoalInput" class="flex items-center gap-2 px-3 py-2 border-b" style="border-color: var(--border-default); background: var(--color-bg-secondary)">
      <input
        v-model="aiGoalText"
        type="text"
        placeholder="Describe what you want to extract (e.g. product prices, article titles)…"
        class="flex-1 text-sm rounded px-2 py-1 bg-autobot-bg-primary text-autobot-text-primary border border-autobot-border"
        @keydown.enter="runAiPropose"
      />
      <button
        @click="runAiPropose"
        :disabled="isAiProposing || !aiGoalText.trim()"
        class="px-3 py-1 text-sm rounded font-medium"
        style="background: var(--color-primary); color: #fff"
      >
        {{ isAiProposing ? 'Proposing…' : 'Propose' }}
      </button>
    </div>

    <!-- Playwright Automation Panel -->
    <div v-if="showPlaywrightPanel" class="automation-panel border-b p-4" style="background: var(--color-info-bg); border-color: rgba(59,130,246,0.2)">
      <div class="flex items-center justify-between mb-4">
        <div class="flex items-center gap-2">
          <Icon name="robot" />
          <span class="font-medium text-autobot-text-primary">{{ $t('desktop.popoutBrowser.browserAutomation') }}</span>
          <span class="text-sm px-2 py-1 rounded" style="background: var(--color-info-bg); color: var(--color-info)">{{ playwrightStatus }}</span>
        </div>
        <button
          @click="showPlaywrightPanel = false"
          class="text-autobot-text-muted hover:text-autobot-text-secondary"
          :aria-label="$t('common.close')"
        >
          <Icon name="times" />
        </button>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <!-- Web Search -->
        <div class="automation-card">
          <div class="flex items-center gap-2 mb-2">
            <Icon name="search" class="text-green-500" />
            <span class="text-sm font-medium">{{ $t('desktop.popoutBrowser.webSearch') }}</span>
          </div>
          <div class="space-y-2">
            <input
              v-model="searchQuery"
              @keyup.enter="performWebSearch"
              class="w-full px-3 py-1 text-sm border border-autobot-border rounded"
              :placeholder="$t('desktop.popoutBrowser.searchPlaceholder')"
            />
            <button @click="performWebSearch" :disabled="isSearching" class="w-full btn-sm btn-primary">
              <Icon :name="isSearching ? 'spinner' : 'search'" :class="isSearching ? 'animate-spin mr-1' : 'mr-1'" />
              {{ isSearching ? $t('desktop.popoutBrowser.searching') : $t('desktop.popoutBrowser.searchButton') }}
            </button>
          </div>
        </div>

        <!-- Frontend Testing -->
        <div class="automation-card">
          <div class="flex items-center gap-2 mb-2">
            <Icon name="vial" />
            <span class="text-sm font-medium">{{ $t('desktop.popoutBrowser.frontendTest') }}</span>
          </div>
          <button @click="runFrontendTest" :disabled="isTestingFrontend" class="w-full btn-sm btn-primary">
              <Icon :name="isTestingFrontend ? 'spinner' : 'play'" :class="isTestingFrontend ? 'animate-spin mr-1' : 'mr-1'" />
              {{ isTestingFrontend ? $t('desktop.popoutBrowser.running') : $t('desktop.popoutBrowser.runTests') }}
          </button>
        </div>

        <!-- Automation Results -->
        <div class="automation-card">
          <div class="flex items-center gap-2 mb-2">
            <Icon name="chart-bar" class="text-purple-500" />
            <span class="text-sm font-medium">{{ $t('desktop.popoutBrowser.results') }}</span>
          </div>
          <div class="text-xs text-autobot-text-secondary space-y-1">
            <div v-if="automationResults.lastSearch">
              {{ $t('desktop.popoutBrowser.searchResultCount', { count: (automationResults.lastSearch as SearchData).results?.length || 0 }) }}
            </div>
            <div v-if="automationResults.lastTest">
              {{ $t('desktop.popoutBrowser.testResultCount', { passed: (automationResults.lastTest as TestData).passed || 0, total: (automationResults.lastTest as TestData).total || 0 }) }}
            </div>
            <div v-if="isSearching || isTestingFrontend || isSendingMessage" style="color: var(--color-info)">
              <Icon name="spinner" class="animate-spin mr-1" />{{ $t('desktop.popoutBrowser.running') }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Browser + Templates layout -->
    <div class="browser-main-area flex-1 flex min-h-0" :style="browserContentStyle">

    <!-- Templates sidebar (#5136 Phase 5) -->
    <div v-if="showTemplatePanel" class="templates-sidebar border-r border-autobot-border" style="width: 280px; flex-shrink: 0;">
      <ScrapeTemplatePanel />
    </div>

    <!-- Browser Content Area -->
    <div class="browser-content flex-1 relative">
      <!-- VNC Browser with Playwright Integration -->
      <div v-if="browserMode === 'vnc'" class="w-full h-full relative">
        <!-- API Connection Status Overlay -->
        <LoadingBoundary
          v-if="browserStatus === 'connecting'"
          :loading="true"
          :timeout-ms="10000"
          @loading-timeout="handlePlaywrightTimeout"
          class="absolute inset-0 bg-autobot-bg-tertiary z-10"
        >
          <template #loading-message>
            <p class="text-sm text-autobot-text-secondary">{{ $t('desktop.popoutBrowser.connectingPlaywright') }}</p>
          </template>
        </LoadingBoundary>

        <!-- API Error Overlay -->
        <div v-if="browserStatus === 'error'" class="absolute inset-0 flex items-center justify-center z-10" style="background: var(--color-error-bg)">
          <div class="text-center p-4">
            <Icon name="exclamation-triangle" class="text-2xl mb-2" />
            <p class="text-sm mb-2" style="color: var(--color-error)">{{ $t('desktop.popoutBrowser.playwrightConnectionFailed') }}</p>
            <BaseButton variant="primary" size="sm" @click="initializeBrowser" :loading="isInitializingBrowser">
              <Icon name="redo" class="mr-1" />
              {{ $t('desktop.popoutBrowser.retryConnection') }}
            </BaseButton>
          </div>
        </div>

        <!-- Loading state while VNC URL is being fetched -->
        <div v-if="!vncUrl" class="w-full h-full flex items-center justify-center bg-gray-900 text-white">
          <div class="text-center p-8">
            <Icon name="robot" class="text-6xl mb-4 text-blue-400" />
            <h3 class="text-xl font-semibold mb-2">{{ $t('desktop.popoutBrowser.headlessBrowserMode') }}</h3>
            <p class="text-gray-300 mb-4">
              {{ $t('desktop.popoutBrowser.headlessDesc') }}
            </p>
            <p class="text-sm text-gray-400 mb-4">
              {{ $t('desktop.popoutBrowser.headlessInstructions') }}
            </p>
            <div class="bg-gray-800 rounded p-4 text-left max-w-md mx-auto">
              <div class="text-xs text-gray-400 mb-2">{{ $t('desktop.popoutBrowser.currentStatus') }}</div>
              <div class="text-sm">
                <div>{{ $t('desktop.popoutBrowser.statusLabel') }} <span class="text-green-400">{{ browserStatus }}</span></div>
                <div v-if="currentUrl">{{ $t('desktop.popoutBrowser.urlLabel') }} <span class="text-blue-300">{{ currentUrl }}</span></div>
                <div v-if="pageTitle">{{ $t('desktop.popoutBrowser.titleLabel') }} <span class="text-gray-200">{{ pageTitle }}</span></div>
              </div>
            </div>
          </div>
        </div>

        <!-- VNC iframe for live browser display with headed Playwright -->
        <!-- Using v-if instead of v-show to prevent iframe from loading at all -->
        <iframe
          v-if="vncUrl && (browserStatus === 'connected' || browserStatus === 'ready') && !markRegionsMode"
          ref="vncIframe"
          :src="vncUrl"
          class="w-full h-full border-none"
          allow="clipboard-read; clipboard-write"
        ></iframe>

        <!-- Region-marking overlay (#5136 / #6446): replaces VNC when active -->
        <div v-if="markRegionsMode && regionSnapshot" class="absolute inset-0 z-20 bg-autobot-bg-primary">
          <InteractiveScreenshot
            :screenshot="regionSnapshot"
            :regions="pageRegions"
            :mark-regions-mode="true"
            :interactive="false"
            @regions-selected="handleRegionsSelected"
          />
        </div>
      </div>

      <!-- Playwright Automation Status Panel -->
      <div v-if="showPlaywrightPanel && browserStatus === 'connected'" class="playwright-status-panel">
        <div class="bg-autobot-bg-secondary rounded-lg shadow-lg p-4 border border-autobot-border">
          <div class="mb-4">
            <div class="flex items-center justify-between mb-2">
              <h4 class="text-sm font-medium text-autobot-text-primary">{{ $t('desktop.popoutBrowser.browserSession') }}</h4>
              <StatusBadge variant="success" size="sm">{{ $t('desktop.popoutBrowser.connected') }}</StatusBadge>
            </div>
            <div class="text-xs text-autobot-text-secondary">
              <div class="flex items-center gap-2">
                <Icon name="link" />
                <span class="text-sm" style="color: var(--text-link)">{{ currentUrl }}</span>
              </div>
            </div>
          </div>

          <!-- Recent results -->
          <div v-if="automationResults.lastSearch || automationResults.lastTest" class="bg-autobot-bg-secondary rounded-lg p-4 shadow-sm border border-autobot-border">
            <h4 class="text-sm font-medium text-autobot-text-primary mb-3">{{ $t('desktop.popoutBrowser.recentResults') }}</h4>

            <div v-if="automationResults.lastSearch" class="mb-3 p-3 rounded" style="background: var(--color-info-bg)">
              <div class="flex items-center gap-2 mb-1">
                <Icon name="search" />
                <span class="text-sm font-medium">{{ $t('desktop.popoutBrowser.webSearch') }}</span>
              </div>
              <p class="text-xs text-autobot-text-secondary">{{ $t('desktop.popoutBrowser.foundResults', { count: (automationResults.lastSearch as SearchData).results?.length || 0 }) }}</p>
            </div>

            <div v-if="automationResults.lastTest" class="p-3 rounded" style="background: var(--color-success-bg)">
              <div class="flex items-center gap-2 mb-1">
                <Icon name="vial" class="text-green-500" />
                <span class="text-sm font-medium">{{ $t('desktop.popoutBrowser.frontendTest') }}</span>
              </div>
              <p class="text-xs text-autobot-text-secondary">{{ $t('desktop.popoutBrowser.testResultCount', { passed: (automationResults.lastTest as TestData).passed, total: (automationResults.lastTest as TestData).total }) }}</p>
            </div>
          </div>

          <!-- Getting started -->
          <EmptyState
            v-else
            icon="rocket"
            :message="$t('desktop.popoutBrowser.getStarted')"
            compact
          />
        </div>
      </div>

      <!-- Manual Browser View (No Session) -->
      <div v-if="!sessionId || sessionId === 'manual-browser'" class="flex items-center justify-center h-full bg-autobot-bg-tertiary">
        <EmptyState
          icon="globe"
          :title="$t('desktop.popoutBrowser.manualBrowserMode')"
          :message="$t('desktop.popoutBrowser.manualBrowserDesc')"
        >
          <template #actions>
            <BaseButton variant="primary" @click="initializeBrowser" :loading="isInitializingBrowser">
              <Icon name="rocket" class="mr-2" />
              {{ isInitializingBrowser ? $t('desktop.popoutBrowser.launching') : $t('desktop.popoutBrowser.launchSession') }}
            </BaseButton>
            <p class="text-sm text-autobot-text-muted mt-3">
              {{ $t('desktop.popoutBrowser.launchDesc') }}
            </p>
          </template>
        </EmptyState>
      </div>

      <!-- Session Loading -->
      <LoadingBoundary
        v-else-if="loading"
        :loading="true"
        :timeout-ms="15000"
        @loading-timeout="handleSessionTimeout"
        class="h-full"
      >
        <template #loading-message>
          <div class="text-center">
            <p class="text-autobot-text-secondary">{{ $t('desktop.popoutBrowser.initializingSession') }}</p>
            <p class="text-sm text-autobot-text-muted mt-2">{{ $t('desktop.popoutBrowser.sessionId', { id: sessionId || $t('desktop.popoutBrowser.notAvailable') }) }}</p>
          </div>
        </template>
      </LoadingBoundary>

      <!-- Developer Tools Overlay -->
      <div v-if="showDevTools" class="absolute bottom-0 left-0 right-0 h-1/3 bg-gray-900 border-t border-gray-600">
        <div class="flex items-center justify-between bg-gray-800 p-2 text-white text-sm">
          <span>{{ $t('desktop.popoutBrowser.developerConsole') }}</span>
          <button @click="showDevTools = false" class="text-gray-400 hover:text-white" :aria-label="$t('common.close')">
            <Icon name="times" />
          </button>
        </div>
        <div class="h-full overflow-auto p-2 text-green-400 font-mono text-xs bg-black">
          <div v-for="(log, index) in consoleLogs" :key="index" class="mb-1">
            <span class="text-autobot-text-muted">{{ log.timestamp }}</span>
            <span :class="getLogColor(log.level)">{{ log.message }}</span>
          </div>
        </div>
      </div>

      <!-- Interaction Overlay -->
      <div v-if="showInteractionOverlay" class="absolute inset-0 bg-black/50 flex items-center justify-center">
        <div class="bg-autobot-bg-elevated rounded-lg p-6 max-w-md mx-4">
          <div class="flex items-center mb-4">
            <Icon name="exclamation-triangle" class="text-2xl mr-3" />
            <h3 class="text-lg font-semibold">{{ $t('desktop.popoutBrowser.interactionRequired') }}</h3>
          </div>
          <p class="text-autobot-text-primary mb-4">{{ interactionMessage }}</p>
          <div class="flex gap-3">
            <BaseButton variant="primary" @click="handleInteraction('wait')">
              <Icon name="clock" class="mr-1" />
              {{ $t('desktop.popoutBrowser.waitAndMonitor') }}
            </BaseButton>
            <BaseButton variant="secondary" @click="handleInteraction('takeover')">
              <Icon name="hand-paper" class="mr-1" />
              {{ $t('desktop.popoutBrowser.takeControl') }}
            </BaseButton>
            <BaseButton variant="outline-solid" @click="hideInteractionOverlay">
              {{ $t('desktop.popoutBrowser.dismiss') }}
            </BaseButton>
          </div>
        </div>
      </div>
    </div>
    </div><!-- end browser-main-area -->
  </div>
</template>

<script lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import type { Ref } from 'vue'
import type { AutomationResults, SearchData, TestData, MessageData } from '@/types/browser'
import appConfig from '@/config/AppConfig.js'
import { useBrowserSessionData } from '@/composables/desktop/useBrowserSessionData'
import type { PlaywrightNavigationResponse, PageRegion, SnapshotWithRegionsResult } from '@/composables/desktop/useBrowserSessionData'
import InteractiveScreenshot from '@/components/browser/InteractiveScreenshot.vue'
import ScrapeTemplatePanel from '@/components/browser/ScrapeTemplatePanel.vue'
import LoadingBoundary from '@/components/ui/LoadingBoundary.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import Icon from '@/components/ui/Icon.vue'
import { NetworkConstants } from '@/constants/network'
import { useAsyncHandler } from '@/composables/useErrorHandler'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'

// Create scoped logger for PopoutChromiumBrowser
const logger = createLogger('PopoutChromiumBrowser')

interface ConsoleLogEntry {
  timestamp: string
  level: string
  message: string
}

export default {
  name: 'PopoutChromiumBrowser',
  components: {
    LoadingBoundary,
    EmptyState,
    StatusBadge,
    BaseButton,
    Icon,
    InteractiveScreenshot,
    ScrapeTemplatePanel,
  },
  props: {
    sessionId: {
      type: String,
      required: true
    },
    initialUrl: {
      type: String,
      default: 'about:blank'
    },
    canResize: {
      type: Boolean,
      default: true
    },
    autoPopout: {
      type: Boolean,
      default: false
    }
  },
  emits: ['close', 'navigate', 'interact', 'popout', 'dock'],
  setup(props: any, { emit }: any) {
    // Browser session data composable (replaces inline fetchWithAuth/apiClient calls)
    const browserApi = useBrowserSessionData()

    // Core state
    const loading = ref(false)
    const browserStatus = ref('initializing')
    const currentUrl = ref(props.initialUrl)
    const pageTitle = ref('')
    const addressBarUrl = ref(props.initialUrl)
    const isPopout = ref(false)
    const isFullscreen = ref(false)
    const showDevTools = ref(false)
    const showInteractionOverlay = ref(false)
    const interactionMessage = ref('')

    // Template sidebar state (#5136 Phase 5)
    const showTemplatePanel = ref(false)

    // Playwright API integration state with proper typing
    const showPlaywrightPanel = ref(false)
    const playwrightStatus = ref('checking')
    const searchQuery = ref('')
    const automationResults = ref<AutomationResults>({
      lastSearch: null,
      lastTest: null,
      lastMessage: null
    })

    // Browser modes - VNC for actual browser display and takeover
    const browserMode = ref('vnc') // 'vnc', 'api', 'native', 'remote'
    const vncUrl = ref('') // Will be loaded async
    const playwrightApiUrl = ref(`${getApiBase()}/playwright`) // Use getApiBase() for configurable prefix
    const remoteDebugUrl = ref('') // Will be loaded async if needed

    // Resize observer
    const resizeObserver: Ref<ResizeObserver | null> = ref(null)

    // Navigation state
    const canGoBack = ref(false)
    const canGoForward = ref(false)
    const isSecure = ref(false)
    const zoomLevel = ref(100)
    const pageLoadTime = ref(0)

    // Console logs for dev tools
    const consoleLogs: Ref<ConsoleLogEntry[]> = ref([])

    // Refs
    const vncIframe: Ref<HTMLIFrameElement | null> = ref(null)
    const webview: Ref<any | null> = ref(null)
    const remoteIframe: Ref<HTMLIFrameElement | null> = ref(null)

    // Region-marking state (#5136 / #6446) — snapshot-with-regions wire-in
    const markRegionsMode = ref(false)
    const pageRegions = ref<PageRegion[]>([])
    const regionSnapshot = ref<string | null>(null)
    const isSnapshotLoading = ref(false)

    // AI propose state (MVA-1380)
    const showAiGoalInput = ref(false)
    const aiGoalText = ref('')
    const isAiProposing = ref(false)

    // Computed styles with responsive sizing
    const browserContentStyle = computed(() => ({
      height: isPopout.value ? '80vh' : '60vh',
      minHeight: '400px',
      maxHeight: '90vh'
    }))

    // Helper function to add console logs
    const addConsoleLog = (level: string, message: string) => {
      consoleLogs.value.push({
        timestamp: new Date().toLocaleTimeString(),
        level,
        message
      })

      // Keep only last 100 logs
      if (consoleLogs.value.length > 100) {
        consoleLogs.value.shift()
      }
    }

    // ========================================
    // API Operations with useAsyncHandler
    // ========================================

    // 1. Initialize Browser (Sequential API calls)
    const { execute: initializeBrowser, loading: isInitializingBrowser } = useAsyncHandler(
      async () => {
        browserStatus.value = 'connecting'

        // Issue #552: Fixed path to match backend /api/research-browser/
        const sessionData = await browserApi.fetchSession(props.sessionId)

        // Second API call - try to connect to Playwright service
        const healthResponse = await browserApi.fetchPlaywrightHealth(playwrightApiUrl.value)

        return { sessionData, healthResponse }
      },
      {
        onSuccess: (result) => {
          if (result.sessionData) {
            currentUrl.value = result.sessionData.url || props.initialUrl
            addressBarUrl.value = currentUrl.value
          }

          if (result.healthResponse && result.healthResponse.ok) {
            playwrightStatus.value = 'connected'
            browserStatus.value = 'connected'
            addConsoleLog('info', 'Connected to Playwright automation service')
          } else {
            logger.warn('Playwright service not available, using VNC only')
            playwrightStatus.value = 'unavailable'
            browserStatus.value = 'connected' // Still connected via VNC
            addConsoleLog('warn', 'Playwright automation not available')
          }

          browserStatus.value = 'ready'
          addConsoleLog('info', 'Browser session initialized successfully')
        },
        onError: (error) => {
          browserStatus.value = 'error'
          addConsoleLog('error', `Browser initialization failed: ${error.message}`)
        },
        logErrors: true,
        errorPrefix: '[PopoutChromiumBrowser]'
      }
    )

    // 2. Navigate to URL
    const { execute: navigateToUrlHandler, loading: isNavigating } = useAsyncHandler(
      async (url: string) => {
        if (!url.trim()) return null

        let targetUrl = url.trim()

        // Handle search queries vs URLs
        if (!targetUrl.includes('://') && !targetUrl.startsWith('localhost') && !targetUrl.includes('.')) {
          targetUrl = `https://duckduckgo.com/?q=${encodeURIComponent(targetUrl)}`
        } else if (!targetUrl.includes('://')) {
          targetUrl = `https://${targetUrl}`
        }

        const startTime = Date.now()

        // Update current URL immediately for UI
        currentUrl.value = targetUrl
        addressBarUrl.value = targetUrl
        isSecure.value = targetUrl.startsWith('https://')

        // Try Playwright navigation if available
        let playwrightResult: PlaywrightNavigationResponse | null = null
        if (playwrightStatus.value === 'connected') {
          playwrightResult = await browserApi.navigateTo(
            playwrightApiUrl.value,
            targetUrl,
            props.sessionId
          )
        }

        return {
          targetUrl,
          playwrightResult,
          loadTime: Date.now() - startTime
        }
      },
      {
        onSuccess: (result) => {
          if (result && result.playwrightResult) {
            const navResponse = result.playwrightResult
            currentUrl.value = navResponse.final_url || result.targetUrl
            addressBarUrl.value = navResponse.final_url || result.targetUrl
            addConsoleLog('info', `Navigation completed: ${navResponse.final_url}`)
          } else if (result) {
            addConsoleLog('info', `Navigated to: ${result.targetUrl}`)
          }

          if (result) {
            pageLoadTime.value = result.loadTime
            emit('navigate', { url: result.targetUrl, sessionId: props.sessionId })
          }
        },
        onError: (error) => {
          addConsoleLog('error', `Navigation failed: ${error.message}`)
        },
        logErrors: true,
        errorPrefix: '[PopoutChromiumBrowser]'
      }
    )

    // Wrapper function to maintain API
    const navigateToUrl = async (url: string) => {
      await navigateToUrlHandler(url)
    }

    // 3. Go Back
    const { execute: goBack, loading: isGoingBack } = useAsyncHandler(
      async () => {
        if (browserMode.value !== 'vnc') {
          if (webview.value && webview.value.canGoBack()) {
            webview.value.goBack()
            canGoBack.value = webview.value.canGoBack()
            canGoForward.value = webview.value.canGoForward()
            return null // No API call needed
          }
          return null
        }

        return await browserApi.navigateBack()
      },
      {
        onSuccess: (result) => {
          if (result) {
            const navResponse = result as PlaywrightNavigationResponse
            if (navResponse.final_url) {
              currentUrl.value = navResponse.final_url
              addressBarUrl.value = navResponse.final_url
              addConsoleLog('info', `Navigated back to: ${navResponse.final_url}`)
            }
          }
        },
        onError: (error) => {
          addConsoleLog('error', `Back navigation failed: ${error.message}`)
        },
        logErrors: true,
        errorPrefix: '[PopoutChromiumBrowser]'
      }
    )

    // 4. Go Forward
    const { execute: goForward, loading: isGoingForward } = useAsyncHandler(
      async () => {
        if (browserMode.value !== 'vnc') {
          if (webview.value && webview.value.canGoForward()) {
            webview.value.goForward()
            canGoBack.value = webview.value.canGoBack()
            canGoForward.value = webview.value.canGoForward()
            return null // No API call needed
          }
          return null
        }

        return await browserApi.navigateForward()
      },
      {
        onSuccess: (result) => {
          if (result) {
            const navResponse = result as PlaywrightNavigationResponse
            if (navResponse.final_url) {
              currentUrl.value = navResponse.final_url
              addressBarUrl.value = navResponse.final_url
              addConsoleLog('info', `Navigated forward to: ${navResponse.final_url}`)
            }
          }
        },
        onError: (error) => {
          addConsoleLog('error', `Forward navigation failed: ${error.message}`)
        },
        logErrors: true,
        errorPrefix: '[PopoutChromiumBrowser]'
      }
    )

    // 5. Refresh Browser
    const { execute: refreshBrowser, loading: isRefreshing } = useAsyncHandler(
      async () => {
        if (browserMode.value !== 'vnc') {
          if (webview.value) {
            webview.value.reload()
            return null // No API call needed
          }
          // Fallback to navigation
          return 'navigate-fallback'
        }

        return await browserApi.reloadPage()
      },
      {
        onSuccess: async (result) => {
          if (result === 'navigate-fallback') {
            await navigateToUrl(currentUrl.value)
            return
          }

          if (result && typeof result === 'object') {
            const navResponse = result as PlaywrightNavigationResponse
            if (navResponse.final_url) {
              currentUrl.value = navResponse.final_url
              addressBarUrl.value = navResponse.final_url
              addConsoleLog('info', `Page refreshed: ${navResponse.final_url}`)
            }
          }
        },
        onError: (error) => {
          addConsoleLog('error', `Refresh failed: ${error.message}`)
        },
        logErrors: true,
        errorPrefix: '[PopoutChromiumBrowser]'
      }
    )

    // 6. Perform Web Search
    const { execute: performWebSearch, loading: isSearching } = useAsyncHandler(
      async () => {
        if (!searchQuery.value.trim()) return null

        addConsoleLog('info', `Starting web search for: ${searchQuery.value}`)

        return await browserApi.webSearch(playwrightApiUrl.value, searchQuery.value)
      },
      {
        onSuccess: (data) => {
          if (data) {
            automationResults.value.lastSearch = data as unknown as SearchData
            addConsoleLog('info', `Search completed: ${(data as any).results?.length || 0} results found`)
          }
        },
        onError: (error) => {
          addConsoleLog('error', `Web search failed: ${error.message}`)
        },
        logErrors: true,
        errorPrefix: '[PopoutChromiumBrowser]'
      }
    )

    // 7. Run Frontend Test
    const { execute: runFrontendTest, loading: isTestingFrontend } = useAsyncHandler(
      async () => {
        addConsoleLog('info', 'Starting frontend tests...')

        return await browserApi.runFrontendTests(playwrightApiUrl.value)
      },
      {
        onSuccess: (data) => {
          if (data) {
            const tests = (data as any).tests
            const passed = tests?.filter((t: any) => t.status === 'PASS').length || 0
            const total = tests?.length || 0

            automationResults.value.lastTest = { passed, total, data } as TestData
            addConsoleLog('info', `Frontend test completed: ${passed}/${total} tests passed`)
          }
        },
        onError: (error) => {
          addConsoleLog('error', `Frontend test failed: ${error.message}`)
        },
        logErrors: true,
        errorPrefix: '[PopoutChromiumBrowser]'
      }
    )

    // 8. Send Test Message
    const { execute: sendTestMessage, loading: isSendingMessage } = useAsyncHandler(
      async () => {
        addConsoleLog('info', 'Sending test message...')

        return await browserApi.sendTestMessage(playwrightApiUrl.value)
      },
      {
        onSuccess: (data) => {
          if (data) {
            automationResults.value.lastMessage = data as unknown as MessageData
            const steps = (data as any).steps
            const successSteps = steps?.filter((s: any) => s.status === 'SUCCESS').length || 0
            addConsoleLog('info', `Test message completed: ${successSteps} steps successful`)
          }
        },
        onError: (error) => {
          addConsoleLog('error', `Test message failed: ${error.message}`)
        },
        logErrors: true,
        errorPrefix: '[PopoutChromiumBrowser]'
      }
    )

    // ========================================
    // Helper Functions
    // ========================================

    const navigateHome = () => {
      navigateToUrl('about:blank')
    }

    const openVncPopout = () => {
      // Create VNC popout window
      const vncWindow = window.open(
        vncUrl.value,
        'autobot-vnc',
        'width=1200,height=800,menubar=no,toolbar=no,location=no,status=no'
      )

      if (vncWindow) {
        addConsoleLog('info', 'VNC browser opened in new window')
      }
    }

    // Interaction handlers
    const handleInteraction = (action: string) => {
      emit('interact', { action, sessionId: props.sessionId })
      hideInteractionOverlay()
    }

    const hideInteractionOverlay = () => {
      showInteractionOverlay.value = false
      interactionMessage.value = ''
    }

    // Region-marking toggle (#5136 / #6446)
    const toggleRegionMarking = async (): Promise<void> => {
      if (markRegionsMode.value) {
        markRegionsMode.value = false
        pageRegions.value = []
        regionSnapshot.value = null
        return
      }
      isSnapshotLoading.value = true
      try {
        const result: SnapshotWithRegionsResult = await browserApi.snapshotWithRegions(props.sessionId)
        regionSnapshot.value = result.screenshot
        pageRegions.value = result.regions
        markRegionsMode.value = true
        logger.info(`Region snapshot: ${result.regions.length} regions detected`)
      } catch (e) {
        logger.warn('Region snapshot failed:', e)
        addConsoleLog('warn', `Region snapshot failed: ${e instanceof Error ? e.message : String(e)}`)
      } finally {
        isSnapshotLoading.value = false
      }
    }

    const handleRegionsSelected = (selected: Array<{ selector: string; xpath: string; label: string }>): void => {
      logger.info(`Regions selected: ${selected.length}`)
      emit('interact', { action: 'regions_selected', sessionId: props.sessionId, regions: selected })
      markRegionsMode.value = false
    }

    // AI-propose regions (MVA-1380)
    const runAiPropose = async (): Promise<void> => {
      if (!aiGoalText.value.trim() || isAiProposing.value) return
      isAiProposing.value = true
      try {
        const proposed = await browserApi.aiProposeRegions(props.sessionId, aiGoalText.value.trim())
        if (proposed.length > 0) {
          pageRegions.value = proposed
          logger.info(`AI proposed ${proposed.length} regions`)
        } else {
          addConsoleLog('warn', 'AI propose returned no matching regions')
        }
        showAiGoalInput.value = false
      } catch (e) {
        logger.warn('AI propose failed:', e)
        addConsoleLog('warn', `AI propose failed: ${e instanceof Error ? e.message : String(e)}`)
      } finally {
        isAiProposing.value = false
      }
    }

    // Utility functions
    const getLogColor = (level: string): string => {
      switch (level) {
        case 'error': return 'text-red-400'
        case 'warn': return 'text-yellow-400'
        case 'info': return 'text-blue-400'
        default: return 'text-green-400'
      }
    }

    // ========================================
    // Lifecycle
    // ========================================

    onMounted(async () => {
      // Load VNC URL for real-time browser viewing on Browser VM
      // Playwright now runs in headed mode with VNC on port 6080
      try {
        vncUrl.value = await appConfig.getVncUrl('playwright', {
          autoconnect: true,
          resize: 'scale'
        })
        logger.debug('Loaded VNC URL for headed mode:', vncUrl.value)
      } catch (error) {
        logger.error('Failed to load VNC URL:', error)
      }

      // Initialize Playwright connection
      initializeBrowser()

      // Set up resize observer for responsive behavior
      if (props.canResize) {
        resizeObserver.value = new ResizeObserver(() => {
          // Handle resize events
        })
      }
    })

    onUnmounted(() => {
      if (resizeObserver.value) {
        resizeObserver.value.disconnect()
      }
    })

    // Watch for prop changes
    watch(() => props.sessionId, (newSessionId) => {
      if (newSessionId) {
        initializeBrowser()
      }
    })

    // LoadingBoundary event handlers
    const handlePlaywrightConnected = () => {
      browserStatus.value = 'connected'
    }

    const handlePlaywrightError = (error: any) => {
      logger.error('Playwright connection error:', error)
      browserStatus.value = 'error'
      addConsoleLog('error', `Playwright connection failed: ${error.message || error}`)
    }

    const handlePlaywrightTimeout = () => {
      logger.warn('Playwright connection timeout')
      browserStatus.value = 'error'
      addConsoleLog('warning', 'Playwright connection timed out')
    }

    const handleSessionInitialized = () => {
      loading.value = false
      browserStatus.value = 'ready'
    }

    const handleSessionError = (error: any) => {
      logger.error('Session initialization error:', error)
      loading.value = false
      browserStatus.value = 'error'
      addConsoleLog('error', `Session initialization failed: ${error.message || error}`)
    }

    const handleSessionTimeout = () => {
      logger.warn('Session initialization timeout')
      loading.value = false
      browserStatus.value = 'error'
      addConsoleLog('warning', 'Session initialization timed out')
    }

    return {
      // State
      loading,
      browserStatus,
      currentUrl,
      pageTitle,
      addressBarUrl,
      isPopout,
      isFullscreen,
      showDevTools,
      showInteractionOverlay,
      interactionMessage,
      browserMode,
      vncUrl,
      playwrightApiUrl,
      remoteDebugUrl,
      canGoBack,
      canGoForward,
      isSecure,
      zoomLevel,
      pageLoadTime,
      consoleLogs,

      // Template sidebar (#5136 Phase 5)
      showTemplatePanel,

      // Playwright state
      showPlaywrightPanel,
      playwrightStatus,
      searchQuery,
      automationResults,

      // Loading states (NEW - expose for UI)
      isInitializingBrowser,
      isNavigating,
      isGoingBack,
      isGoingForward,
      isRefreshing,
      isSearching,
      isTestingFrontend,
      isSendingMessage,

      // Refs
      vncIframe,
      webview,
      remoteIframe,

      // Computed
      browserContentStyle,

      // Methods
      initializeBrowser,
      navigateToUrl,
      goBack,
      goForward,
      refreshBrowser,
      navigateHome,
      openVncPopout,
      performWebSearch,
      runFrontendTest,
      sendTestMessage,
      handleInteraction,
      hideInteractionOverlay,
      addConsoleLog,
      getLogColor,

      // Region-marking (#5136 / #6446)
      markRegionsMode,
      pageRegions,
      regionSnapshot,
      isSnapshotLoading,
      toggleRegionMarking,
      handleRegionsSelected,

      // AI propose (MVA-1380)
      showAiGoalInput,
      aiGoalText,
      isAiProposing,
      runAiPropose,

      // LoadingBoundary event handlers
      handlePlaywrightConnected,
      handlePlaywrightError,
      handlePlaywrightTimeout,
      handleSessionInitialized,
      handleSessionError,
      handleSessionTimeout
    }
  }
}
</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */
.chromium-browser-container {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-tertiary);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-lg);
}

.browser-header {
  flex-shrink: 0;
}

.address-bar {
  flex-shrink: 0;
}

.browser-main-area {
  flex: 1;
  display: flex;
  min-height: 0;
}

.templates-sidebar {
  flex-shrink: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.browser-content {
  flex: 1;
  position: relative;
  min-height: 0;
}

.browser-btn {
  padding: var(--spacing-1-5) var(--spacing-2);
  border: none;
  background: transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background-color var(--duration-200);
  font-size: var(--text-sm);
}

.browser-btn:hover {
  background-color: var(--bg-tertiary-transparent);
}

.browser-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.nav-btn {
  padding: var(--spacing-2) var(--spacing-3);
  border: 1px solid var(--border-default);
  background: var(--bg-surface);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-200);
}

.nav-btn:hover:not(:disabled) {
  background-color: var(--bg-tertiary);
}

.nav-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.automation-panel {
  flex-shrink: 0;
}

.automation-card {
  background: var(--bg-surface);
  padding: var(--spacing-3);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-light);
}

.playwright-status-panel {
  position: absolute;
  top: var(--spacing-5);
  right: var(--spacing-5);
  width: 300px;
  z-index: 20;
}

</style>
