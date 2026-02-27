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
import ApiClient from '@/utils/ApiClient'
import GUIAutomationControls from '@/components/vision/GUIAutomationControls.vue'
import {
  visionMultimodalApiClient,
  type AutomationOpportunity,
} from '@/utils/VisionMultimodalApiClient'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('VisualBrowserPanel')

const loading = ref(false)
const error = ref<string | null>(null)
const url = ref('https://www.google.com')
const screenshot = ref<string | null>(null)
const currentUrl = ref<string | null>(null)
const pageTitle = ref<string | null>(null)
const isConnected = ref(false)
const statusChecked = ref(false)

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
    const data = await ApiClient.get('/api/playwright/worker-status') as Record<string, unknown>
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

  let targetUrl = url.value.trim()
  if (!targetUrl.includes('://') && !targetUrl.startsWith('localhost')) {
    if (targetUrl.includes('.') || targetUrl.startsWith('localhost')) {
      targetUrl = `https://${targetUrl}`
    } else {
      targetUrl = `https://duckduckgo.com/?q=${encodeURIComponent(targetUrl)}`
    }
  }
  url.value = targetUrl

  try {
    const nav = await ApiClient.post('/api/playwright/navigate', { url: targetUrl }) as Record<string, unknown>
    currentUrl.value = (nav.url as string) || targetUrl
    pageTitle.value = (nav.title as string) || null
    isConnected.value = true
    await captureScreenshot()
  } catch (e: unknown) {
    const err = e as { response?: { data?: { detail?: string } }; message?: string }
    error.value = err?.response?.data?.detail ?? (e instanceof Error ? e.message : 'Navigation failed')
    logger.error('Navigation failed:', e)
  } finally {
    loading.value = false
  }
}

async function captureScreenshot(): Promise<void> {
  try {
    const data = await ApiClient.post('/api/playwright/worker-screenshot', {}) as Record<string, unknown>
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
    const nav = await ApiClient.post('/api/playwright/back', {}) as Record<string, unknown>
    if (nav.url) { currentUrl.value = nav.url as string; url.value = nav.url as string }
    if (nav.title) pageTitle.value = nav.title as string
    await captureScreenshot()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Back navigation failed'
  } finally {
    loading.value = false
  }
}

async function goForward(): Promise<void> {
  if (!isConnected.value) return
  loading.value = true
  error.value = null
  try {
    const nav = await ApiClient.post('/api/playwright/forward', {}) as Record<string, unknown>
    if (nav.url) { currentUrl.value = nav.url as string; url.value = nav.url as string }
    if (nav.title) pageTitle.value = nav.title as string
    await captureScreenshot()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Forward navigation failed'
  } finally {
    loading.value = false
  }
}

async function reload(): Promise<void> {
  if (!isConnected.value) return
  loading.value = true
  error.value = null
  try {
    await ApiClient.post('/api/playwright/reload', {})
    await captureScreenshot()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Reload failed'
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
          <span class="status-label">{{ !statusChecked ? 'Checking...' : isConnected ? 'Connected' : 'Disconnected' }}</span>
        </div>

        <span v-if="pageTitle" class="page-title">{{ pageTitle }}</span>
      </div>

      <!-- Address Bar Row -->
      <div class="address-row">
        <!-- Back / Forward / Reload -->
        <div class="nav-controls">
          <button @click="goBack" :disabled="!isConnected || loading" class="nav-btn" title="Back">
            <i class="fas fa-arrow-left"></i>
          </button>
          <button @click="goForward" :disabled="!isConnected || loading" class="nav-btn" title="Forward">
            <i class="fas fa-arrow-right"></i>
          </button>
          <button @click="reload" :disabled="!isConnected || loading" class="nav-btn" title="Reload">
            <i class="fas fa-redo" :class="{ 'fa-spin': loading }"></i>
          </button>
        </div>

        <!-- URL Input -->
        <div class="url-bar">
          <i class="fas fa-globe url-icon"></i>
          <input
            v-model="url"
            @keydown="handleKeydown"
            type="text"
            class="url-input"
            placeholder="Enter URL or search…"
          />
        </div>

        <!-- Go button -->
        <button @click="navigate" :disabled="loading" class="go-btn">
          <i class="fas fa-search" v-if="!loading"></i>
          <i class="fas fa-spinner fa-spin" v-else></i>
        </button>

        <!-- Screenshot button -->
        <button @click="captureScreenshot" :disabled="!isConnected || loading" class="nav-btn screenshot-btn" title="Refresh Screenshot">
          <i class="fas fa-camera"></i>
        </button>

        <!-- Automation toggle (#1242) -->
        <button
          @click="toggleAutomation"
          class="nav-btn automation-toggle-btn"
          :class="{ 'automation-active': showAutomation }"
          title="Toggle GUI Automation Panel"
        >
          <i class="fas fa-robot"></i>
        </button>
      </div>
    </div>

    <!-- Error Banner -->
    <div v-if="error" class="error-banner">
      <i class="fas fa-exclamation-triangle"></i>
      <span>{{ error }}</span>
      <button @click="error = null" class="error-dismiss"><i class="fas fa-times"></i></button>
    </div>

    <!-- Content Area (viewport + optional automation panel) (#1242) -->
    <div class="browser-content">
      <!-- Viewport -->
      <div class="browser-viewport">
        <!-- Loading Spinner -->
        <div v-if="loading && !screenshot" class="viewport-state">
          <i class="fas fa-spinner fa-spin viewport-icon"></i>
          <p class="viewport-msg">Loading…</p>
        </div>

        <!-- Disconnected / not started -->
        <div v-else-if="!isConnected" class="viewport-state">
          <i class="fas fa-globe viewport-icon viewport-icon--dim"></i>
          <h3 class="viewport-title">Browser</h3>
          <p class="viewport-msg">Enter a URL above and press Enter or click the search icon to start browsing.</p>
        </div>

        <!-- Screenshot Display -->
        <img
          v-else-if="screenshot"
          :src="`data:image/png;base64,${screenshot}`"
          alt="Browser screenshot"
          class="screenshot-img"
          :class="{ 'screenshot-img--loading': loading }"
        />

        <!-- Connected but no screenshot yet -->
        <div v-else class="viewport-state">
          <i class="fas fa-camera viewport-icon viewport-icon--dim"></i>
          <p class="viewport-msg">No screenshot yet — navigate to a URL to capture the browser view.</p>
          <button @click="captureScreenshot" class="capture-btn">
            <i class="fas fa-camera mr-2"></i>Capture Screenshot
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
  font-size: var(--text-sm);
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
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 0;
}

.viewport-state {
  text-align: center;
  padding: var(--spacing-12) var(--spacing-6);
  color: var(--text-secondary);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-3);
}

.viewport-icon {
  font-size: 3rem;
  color: var(--text-secondary);
}

.viewport-icon--dim {
  opacity: 0.35;
}

.viewport-title {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0;
}

.viewport-msg {
  font-size: var(--text-sm);
  color: var(--text-muted);
  max-width: 360px;
  margin: 0;
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
  transition: width 0.25s ease, opacity 0.25s ease;
}

.slide-panel-enter-from,
.slide-panel-leave-to {
  width: 0;
  opacity: 0;
  overflow: hidden;
}
</style>
