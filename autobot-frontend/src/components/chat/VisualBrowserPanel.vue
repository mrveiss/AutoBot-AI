// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * VisualBrowserPanel — Screenshot-based visual browser for the chat browser tab.
 *
 * Replaces the broken VNC/session-based ChatBrowser with a simple
 * navigate → screenshot → display approach, matching the SLM BrowserTool
 * but using the user-frontend design tokens. Issue #1130.
 */

import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import ApiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import InteractiveScreenshot from '@/components/browser/InteractiveScreenshot.vue'
import GUIAutomationControls from '@/components/vision/GUIAutomationControls.vue'
import {
  visionMultimodalApiClient,
  type AutomationOpportunity,
} from '@/utils/VisionMultimodalApiClient'
import { createLogger } from '@/utils/debugUtils'
import { normalizeUrl } from '@/utils/urlUtils'
import Icon from '@/components/ui/Icon.vue'

const { t } = useI18n()
const logger = createLogger('VisualBrowserPanel')

const loading = ref(false)
const error = ref<string | null>(null)
const url = ref('https://www.google.com')
const screenshot = ref<string | null>(null)
const currentUrl = ref<string | null>(null)
const pageTitle = ref<string | null>(null)
const isConnected = ref(false)
const statusChecked = ref(false)
const viewportWidth = ref(1280)
const viewportHeight = ref(720)

// GUI Automation panel state (#1242)
const showAutomation = ref(false)
const automationOpportunities = ref<AutomationOpportunity[]>([])
const automationLoading = ref(false)

async function loadAutomationOpportunities(): Promise<void> {
  automationLoading.value = true
  try {
    const res = await visionMultimodalApiClient.getAutomationOpportunities()
    if (res.success && res.data) {
      automationOpportunities.value = res.data.opportunities || []
    }
  } catch (e) {
    logger.warn('Failed to load automation opportunities:', e)
  } finally {
    automationLoading.value = false
  }
}

function toggleAutomation(): void {
  showAutomation.value = !showAutomation.value
  if (showAutomation.value && automationOpportunities.value.length === 0) {
    loadAutomationOpportunities()
  }
}

async function checkStatus(): Promise<void> {
  try {
    const data = await ApiClient.get<any>(`${getApiBase()}/playwright/worker-status`) as Record<string, unknown>
    isConnected.value = data.status === 'connected' || data.browser_connected === true
  } catch (e) {
    logger.warn('Browser status check failed:', e)
    isConnected.value = false
  } finally {
    statusChecked.value = true
  }
}

async function navigate(): Promise<void> {
  if (!url.value.trim()) return
  loading.value = true
  error.value = null

  // #5139: normalise the raw input to a fully-qualified URL (#5575).
  const targetUrl = normalizeUrl(url.value)
  url.value = targetUrl

  try {
    const nav = await ApiClient.post<any>(`${getApiBase()}/playwright/navigate`, { url: targetUrl }) as Record<string, unknown>
    currentUrl.value = (nav.url as string) || targetUrl
    pageTitle.value = (nav.title as string) || null
    isConnected.value = true
    if (nav.screenshot) screenshot.value = nav.screenshot as string
    if (nav.viewportWidth) viewportWidth.value = nav.viewportWidth as number
    if (nav.viewportHeight) viewportHeight.value = nav.viewportHeight as number
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string }
    error.value = err?.response?.data?.detail ?? (e instanceof Error ? e.message : t('chat.visualBrowser.navigationFailed'))
    logger.error('Navigation failed:', e)
  } finally {
    loading.value = false
  }
}

async function captureScreenshot(): Promise<void> {
  try {
    const data = await ApiClient.post<any>(`${getApiBase()}/playwright/worker-screenshot`, {}) as Record<string, unknown>
    screenshot.value = (data.screenshot as string) || null
  } catch (e) {
    logger.warn('Screenshot failed:', e)
  }
}

async function goBack(): Promise<void> {
  if (!isConnected.value) return
  loading.value = true
  error.value = null
  try {
    const nav = await ApiClient.post<any>(`${getApiBase()}/playwright/back`, {}) as Record<string, unknown>
    if (nav.url) { currentUrl.value = nav.url as string; url.value = nav.url as string }
    if (nav.title) pageTitle.value = nav.title as string
    if (nav.screenshot) screenshot.value = nav.screenshot as string
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('chat.visualBrowser.backFailed')
  } finally {
    loading.value = false
  }
}

async function goForward(): Promise<void> {
  if (!isConnected.value) return
  loading.value = true
  error.value = null
  try {
    const nav = await ApiClient.post<any>(`${getApiBase()}/playwright/forward`, {}) as Record<string, unknown>
    if (nav.url) { currentUrl.value = nav.url as string; url.value = nav.url as string }
    if (nav.title) pageTitle.value = nav.title as string
    if (nav.screenshot) screenshot.value = nav.screenshot as string
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('chat.visualBrowser.forwardFailed')
  } finally {
    loading.value = false
  }
}

async function reload(): Promise<void> {
  if (!isConnected.value) return
  loading.value = true
  error.value = null
  try {
    const nav = await ApiClient.post<any>(`${getApiBase()}/playwright/reload`, {}) as Record<string, unknown>
    if (nav.screenshot) screenshot.value = nav.screenshot as string
  } catch (e) {
    error.value = e instanceof Error ? e.message : t('chat.visualBrowser.reloadFailed')
  } finally {
    loading.value = false
  }
}

async function handleInteract(payload: { action: string; params: Record<string, unknown> }): Promise<void> {
  if (!isConnected.value || loading.value) return
  loading.value = true
  try {
    const result = await ApiClient.post<any>(`${getApiBase()}/playwright/interact`, {
      action: payload.action,
      ...payload.params,
    }) as Record<string, unknown>
    if (result.screenshot) screenshot.value = result.screenshot as string
    if (result.url) { currentUrl.value = result.url as string; url.value = result.url as string }
    if (result.title) pageTitle.value = result.title as string
  } catch (e) {
    logger.warn('Interaction failed:', e)
  } finally {
    loading.value = false
  }
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter') navigate()
}

onMounted(() => {
  checkStatus()
})
</script>

<template>
  <div class="visual-browser-panel">
    <!-- Browser Chrome -->
    <div class="browser-chrome">
      <!-- Status Row -->
      <div class="status-row">
        <div class="status-indicator">
          <span
            class="status-dot"
            :class="{
              'status-dot--connected': isConnected,
              'status-dot--disconnected': statusChecked && !isConnected,
              'status-dot--pending': !statusChecked
            }"
          ></span>
          <span class="status-label">{{ !statusChecked ? $t('chat.visualBrowser.checking') : isConnected ? $t('chat.visualBrowser.connected') : $t('chat.visualBrowser.disconnected') }}</span>
        </div>

        <span v-if="pageTitle" class="page-title">{{ pageTitle }}</span>
      </div>

      <!-- Address Bar Row -->
      <div class="address-row">
        <!-- Back / Forward / Reload -->
        <div class="nav-controls">
          <button @click="goBack" :disabled="!isConnected || loading" class="nav-btn" :title="$t('chat.visualBrowser.back')" :aria-label="$t('chat.visualBrowser.back')">
            <Icon name="arrow-left" />
          </button>
          <button @click="goForward" :disabled="!isConnected || loading" class="nav-btn" :title="$t('chat.visualBrowser.forward')" :aria-label="$t('chat.visualBrowser.forward')">
            <Icon name="arrow-right" />
          </button>
          <button @click="reload" :disabled="!isConnected || loading" class="nav-btn" :title="$t('chat.visualBrowser.reload')" :aria-label="$t('chat.visualBrowser.reload')">

            <Icon name="redo" :spin="loading" />
          </button>
        </div>

        <!-- URL Input -->
        <div class="url-bar">
          <Icon name="globe" class="url-icon" />
          <input
            v-model="url"
            @keydown="handleKeydown"
            type="text"
            class="url-input"
            :placeholder="$t('chat.visualBrowser.urlPlaceholder')"
          />
        </div>

        <!-- Go button -->
        <button @click="navigate" :disabled="loading" class="go-btn" :aria-label="$t('chat.visualBrowser.go')">

          <Icon name="search" v-if="!loading" />
          <Icon name="spinner" :spin="true" v-else />
        </button>

        <!-- Screenshot button -->
        <button @click="captureScreenshot" :disabled="!isConnected || loading" class="nav-btn screenshot-btn" :title="$t('chat.visualBrowser.refreshScreenshot')" :aria-label="$t('chat.visualBrowser.refreshScreenshot')">
          <Icon name="camera" />
        </button>

        <!-- Automation toggle (#1242) -->
        <button
          @click="toggleAutomation"
          class="nav-btn automation-toggle-btn"
          :class="{ 'automation-active': showAutomation }"
          :title="$t('chat.visualBrowser.toggleAutomation')"
          :aria-label="$t('chat.visualBrowser.toggleAutomation')"
        >
          <Icon name="robot" />
        </button>
      </div>
    </div>

    <!-- Error Banner -->
    <div v-if="error" class="error-banner">
      <Icon name="exclamation-triangle" />
      <span>{{ error }}</span>
      <button @click="error = null" class="error-dismiss" :aria-label="$t('common.dismiss')"><Icon name="times" /></button>
    </div>

    <!-- Content Area (viewport + optional automation panel) (#1242) -->
    <div class="browser-content">
      <!-- Viewport -->
      <div class="browser-viewport">
        <!-- Loading Spinner -->
        <div v-if="loading && !screenshot" class="viewport-state">
          <Icon name="spinner" :spin="true" class="viewport-icon" />
          <p class="viewport-msg">{{ $t('common.loading') }}</p>
        </div>

        <!-- Disconnected / not started -->
        <div v-else-if="!isConnected" class="viewport-state">
          <Icon name="globe" class="viewport-icon viewport-icon--dim" />
          <h3 class="viewport-title">{{ $t('chat.visualBrowser.browserTitle') }}</h3>
          <p class="viewport-msg">{{ $t('chat.visualBrowser.startBrowsing') }}</p>
        </div>

        <!-- Interactive Screenshot Display (#1416) -->
        <InteractiveScreenshot
          v-else-if="screenshot"
          :screenshot="screenshot"
          :loading="loading"
          :interactive="isConnected"
          :viewport-width="viewportWidth"
          :viewport-height="viewportHeight"
          @interact="handleInteract"
        />

        <!-- Connected but no screenshot yet -->
        <div v-else class="viewport-state">
          <Icon name="camera" class="viewport-icon viewport-icon--dim" />
          <p class="viewport-msg">{{ $t('chat.visualBrowser.noScreenshot') }}</p>
          <button @click="captureScreenshot" class="capture-btn">
            <Icon name="camera" class="mr-2" />{{ $t('chat.visualBrowser.captureScreenshot') }}
          </button>
        </div>
      </div>

      <!-- GUI Automation Side Panel (#1242) -->
      <Transition name="slide-panel">
        <div v-if="showAutomation" class="automation-panel">
          <GUIAutomationControls
            :opportunities="automationOpportunities"
            :loading="automationLoading"
            @refresh="loadAutomationOpportunities"
          />
        </div>
      </Transition>
    </div>
  </div>
</template>

<style scoped>
.visual-browser-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-primary);
  overflow: hidden;
}

/* ---- Chrome ---- */
.browser-chrome {
  flex-shrink: 0;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
  padding: var(--spacing-2) var(--spacing-3);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.status-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
  font-size: var(--text-xs);
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot--connected { background: var(--color-success); }
.status-dot--disconnected { background: var(--color-error); }
.status-dot--pending { background: var(--color-warning); animation: pulse 1.5s infinite; }

@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

.status-label {
  color: var(--text-secondary);
}

.page-title {
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 320px;
}

/* ---- Address bar row ---- */
.address-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.nav-controls {
  display: flex;
  gap: var(--spacing-1);
  flex-shrink: 0;
}

.nav-btn {
  padding: var(--spacing-1-5) var(--spacing-2);
  border: none;
  background: transparent;
  color: var(--text-secondary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: color var(--duration-150), background var(--duration-150);
  font-size: var(--text-sm);
}

.nav-btn:hover:not(:disabled) {
  color: var(--text-primary);
  background: var(--bg-hover);
}

.nav-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.url-bar {
  flex: 1;
  display: flex;
  align-items: center;
  background: var(--bg-input);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: 0 var(--spacing-3);
  gap: var(--spacing-2);
  transition: border-color var(--duration-150);
}

.url-bar:focus-within {
  border-color: var(--color-primary);
}

.url-icon {
  color: var(--text-muted);
  width: var(--text-sm);
  height: var(--text-sm);
  flex-shrink: 0;
}

.url-input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-primary);
  font-size: var(--text-sm);
  padding: var(--spacing-2) 0;
}

.url-input:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.url-input::placeholder {
  color: var(--text-muted);
}

.go-btn {
  flex-shrink: 0;
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--text-sm);
  transition: background var(--duration-150);
}

.go-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.go-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.screenshot-btn {
  flex-shrink: 0;
}

/* Automation toggle active state (#1242) */
.automation-toggle-btn.automation-active {
  color: var(--color-primary);
  background: var(--color-primary-bg, rgba(59, 130, 246, 0.1));
}

/* ---- Error banner ---- */
.error-banner {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--color-error-bg);
  border-bottom: 1px solid var(--color-error-border);
  color: var(--color-error);
  font-size: var(--text-sm);
}

.error-dismiss {
  margin-left: auto;
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
  padding: var(--spacing-1);
}

/* ---- Viewport ---- */
.browser-viewport {
  flex: 1;
  overflow: auto;
  background: var(--bg-primary);
  min-height: 0;
}

.viewport-state {
  margin: auto;
  text-align: center;
  padding: var(--spacing-12) var(--spacing-6);
  color: var(--text-secondary);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-3);
}

.viewport-icon {
  width: var(--text-5xl);
  height: var(--text-5xl);
  color: var(--text-secondary);
}

.viewport-icon--dim {
  opacity: 0.35;
}

.viewport-title {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: var(--spacing-0);
}

.viewport-msg {
  font-size: var(--text-sm);
  color: var(--text-muted);
  max-width: 360px;
  margin: var(--spacing-0);
}

.capture-btn {
  padding: var(--spacing-2) var(--spacing-4);
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--text-sm);
  transition: background var(--duration-150);
}

.capture-btn:hover {
  background: var(--color-primary-hover);
}

.screenshot-img {
  display: block;
  max-width: 100%;
  height: auto;
  margin: auto;
  object-fit: contain;
  transition: opacity var(--duration-200);
}

.screenshot-img--loading {
  opacity: 0.6;
}

/* ---- Content area (viewport + automation panel) (#1242) ---- */
.browser-content {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
}

/* ---- Automation side panel (#1242) ---- */
.automation-panel {
  width: 360px;
  flex-shrink: 0;
  border-left: 1px solid var(--border-default);
  background: var(--bg-primary);
  overflow-y: auto;
  padding: var(--spacing-3);
}

/* Panel slide transition */
.slide-panel-enter-active,
.slide-panel-leave-active {
  transition: width var(--duration-250) var(--ease-out), opacity var(--duration-250) var(--ease-out);
}

.slide-panel-enter-from,
.slide-panel-leave-to {
  width: 0;
  opacity: 0;
  overflow: hidden;
}
</style>
