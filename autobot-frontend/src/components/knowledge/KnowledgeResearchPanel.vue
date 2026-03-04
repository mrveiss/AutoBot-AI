// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2026 mrveiss
// Author: mrveiss

<script setup lang="ts">
/**
 * KnowledgeResearchPanel — Observable live research with browser stream.
 *
 * Left: Research query control + found source cards with Accept/Reject actions.
 * Right: Live screenshot stream of the Playwright browser on .25 (reuses the
 *        same screenshot-over-HTTP approach as VisualBrowserPanel.vue).
 *
 * Issue #1256: Observable Research Panel (Live Browser Collaboration).
 */

import { ref, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import ApiClient from '@/utils/ApiClient'
import { getBackendWsUrl } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('KnowledgeResearchPanel')

const { t } = useI18n()

// ── State ──────────────────────────────────────────────────────────────────

const query = ref('')
const isResearching = ref(false)
const statusText = ref(t('knowledge.research.statusReady'))
const errorMsg = ref<string | null>(null)

const screenshot = ref<string | null>(null)
const browserConnected = ref(false)
const screenshotLoading = ref(false)

let screenshotInterval: ReturnType<typeof setInterval> | null = null
let ws: WebSocket | null = null

interface SourceCard {
  url: string
  title: string
  snippet: string
  score: number | null
  domain: string
  recommendation: string | null
  decision: 'accepted' | 'rejected' | null
}

const sources = ref<SourceCard[]>([])

// ── Browser screenshot polling ─────────────────────────────────────────────

async function checkBrowserStatus(): Promise<void> {
  try {
    const data = await ApiClient.get('/api/playwright/worker-status') as Record<string, unknown>
    browserConnected.value = data.status === 'connected' || data.browser_connected === true
  } catch (e) {
    logger.warn('Browser status check failed:', e)
    browserConnected.value = false
  }
}

async function fetchScreenshot(): Promise<void> {
  if (screenshotLoading.value) return
  screenshotLoading.value = true
  try {
    const data = await ApiClient.post('/api/playwright/worker-screenshot', {}) as Record<string, unknown>
    if (data.screenshot) {
      screenshot.value = data.screenshot as string
      browserConnected.value = true
    }
  } catch (e) {
    logger.warn('Screenshot fetch failed:', e)
  } finally {
    screenshotLoading.value = false
  }
}

function startScreenshotPolling(): void {
  if (screenshotInterval) return
  fetchScreenshot()
  screenshotInterval = setInterval(fetchScreenshot, 3000)
}

function stopScreenshotPolling(): void {
  if (screenshotInterval) {
    clearInterval(screenshotInterval)
    screenshotInterval = null
  }
}

// ── Source card helpers ────────────────────────────────────────────────────

function findOrCreateSource(url: string, title: string): SourceCard {
  const existing = sources.value.find(s => s.url === url)
  if (existing) return existing
  const card: SourceCard = {
    url,
    title: title || url,
    snippet: '',
    score: null,
    domain: _extractDomain(url),
    recommendation: null,
    decision: null,
  }
  sources.value.unshift(card)
  return card
}

function _extractDomain(url: string): string {
  try {
    return new URL(url).hostname
  } catch {
    return url
  }
}

function scoreColor(score: number | null): string {
  if (score === null) return 'var(--text-muted)'
  if (score >= 0.8) return 'var(--color-success)'
  if (score >= 0.6) return 'var(--color-warning)'
  return 'var(--color-error)'
}

// ── WebSocket research session ─────────────────────────────────────────────

function _buildWsUrl(): string {
  const base = getBackendWsUrl()
  return `${base}/api/ws/knowledge/research`
}

function _handleEvent(event: Record<string, unknown>): void {
  const ev = event.event as string
  logger.debug('Research event:', ev, event)

  if (ev === 'research:searching') {
    statusText.value = t('knowledge.research.statusSearching', { engine: (event.engine as string) || 'browser' })
  } else if (ev === 'research:result_found') {
    statusText.value = t('knowledge.research.statusFound', { title: (event.title as string) || (event.url as string) })
    const card = findOrCreateSource(event.url as string, event.title as string)
    card.snippet = (event.snippet as string) || ''
  } else if (ev === 'research:content_extracted') {
    statusText.value = t('knowledge.research.statusExtracted', { domain: _extractDomain(event.url as string) })
  } else if (ev === 'research:quality_assessed') {
    const card = findOrCreateSource(event.url as string, '')
    card.score = typeof event.score === 'number' ? event.score : null
    card.recommendation = (event.recommendation as string) || null
    statusText.value = t('knowledge.research.statusAssessed', { domain: _extractDomain(event.url as string), score: card.score !== null ? (card.score * 100).toFixed(0) + '%' : '—' })
  } else if (ev === 'research:stored') {
    const card = findOrCreateSource(event.url as string, event.title as string)
    card.decision = 'accepted'
    statusText.value = t('knowledge.research.statusStored', { domain: _extractDomain(event.url as string) })
  } else if (ev === 'research:completed') {
    isResearching.value = false
    stopScreenshotPolling()
    statusText.value = t('knowledge.research.statusDone', { found: event.total_found || 0, stored: event.stored || 0 })
  } else if (ev === 'research:error') {
    isResearching.value = false
    stopScreenshotPolling()
    errorMsg.value = (event.message as string) || t('knowledge.research.errorGeneric')
    statusText.value = t('knowledge.research.statusError')
  }
}

function closeWs(): void {
  if (ws) {
    ws.close()
    ws = null
  }
}

async function startResearch(): Promise<void> {
  const q = query.value.trim()
  if (!q) return

  errorMsg.value = null
  sources.value = []
  isResearching.value = true
  statusText.value = t('knowledge.research.statusConnecting')
  closeWs()

  await checkBrowserStatus()
  startScreenshotPolling()

  try {
    const wsUrl = _buildWsUrl()
    logger.info('Connecting research WS:', wsUrl)
    ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      statusText.value = t('knowledge.research.statusStarting')
      ws!.send(JSON.stringify({ action: 'start', query: q, store: true }))
    }

    ws.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data) as Record<string, unknown>
        _handleEvent(data)
      } catch (e) {
        logger.warn('Failed to parse WS message:', e)
      }
    }

    ws.onerror = (e) => {
      logger.error('Research WS error:', e)
      errorMsg.value = t('knowledge.research.errorWebSocket')
      isResearching.value = false
      stopScreenshotPolling()
    }

    ws.onclose = () => {
      if (isResearching.value) {
        isResearching.value = false
        stopScreenshotPolling()
        statusText.value = t('knowledge.research.statusDisconnected')
      }
    }
  } catch (e) {
    logger.error('Failed to open research WS:', e)
    errorMsg.value = t('knowledge.research.errorConnect')
    isResearching.value = false
    stopScreenshotPolling()
  }
}

function stopResearch(): void {
  closeWs()
  isResearching.value = false
  stopScreenshotPolling()
  statusText.value = t('knowledge.research.statusStopped')
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !isResearching.value) startResearch()
}

// ── Source card actions ────────────────────────────────────────────────────

async function acceptSource(card: SourceCard): Promise<void> {
  card.decision = 'accepted'
  try {
    await ApiClient.post('/api/knowledge/verification/approve', {
      source_url: card.url,
      title: card.title,
    })
  } catch (e) {
    logger.warn('Accept source API call failed (non-critical):', e)
  }
}

function rejectSource(card: SourceCard): void {
  card.decision = 'rejected'
}

// ── Cleanup ────────────────────────────────────────────────────────────────

onUnmounted(() => {
  closeWs()
  stopScreenshotPolling()
})
</script>

<template>
  <div class="research-panel">
    <!-- Split layout -->
    <div class="panel-split">
      <!-- LEFT: Research control + source cards -->
      <div class="panel-left">
        <!-- Query bar -->
        <div class="query-bar">
          <div class="query-input-wrap">
            <svg class="query-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              v-model="query"
              type="text"
              class="query-input"
              :placeholder="$t('knowledge.research.queryPlaceholder')"
              :disabled="isResearching"
              @keydown="handleKeydown"
            />
          </div>
          <button
            v-if="!isResearching"
            class="btn-primary"
            :disabled="!query.trim()"
            @click="startResearch"
          >
            {{ $t('knowledge.research.btnResearch') }}
          </button>
          <button
            v-else
            class="btn-stop"
            @click="stopResearch"
          >
            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
              <rect x="4" y="4" width="16" height="16" rx="2" stroke-width="2" />
            </svg>
            {{ $t('knowledge.research.btnStop') }}
          </button>
        </div>

        <!-- Error -->
        <div v-if="errorMsg" class="error-banner">
          <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span>{{ errorMsg }}</span>
          <button class="error-dismiss" @click="errorMsg = null">
            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <!-- Sources heading -->
        <div class="sources-header">
          <span class="sources-title">{{ $t('knowledge.research.foundSources') }}</span>
          <span class="sources-count" v-if="sources.length">{{ sources.length }}</span>
        </div>

        <!-- Source cards list -->
        <div class="sources-list">
          <!-- Empty state -->
          <div v-if="!sources.length && !isResearching" class="sources-empty">
            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="40" height="40" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
                d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            <p>{{ $t('knowledge.research.emptyState') }}</p>
          </div>

          <!-- Searching spinner -->
          <div v-if="!sources.length && isResearching" class="sources-searching">
            <svg class="spin-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" width="24" height="24" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            <span>{{ $t('knowledge.research.searching') }}</span>
          </div>

          <!-- Cards -->
          <div
            v-for="card in sources"
            :key="card.url"
            class="source-card"
            :class="{
              'source-card--accepted': card.decision === 'accepted',
              'source-card--rejected': card.decision === 'rejected',
            }"
          >
            <div class="card-header">
              <span class="card-domain">{{ card.domain }}</span>
              <span
                v-if="card.score !== null"
                class="card-score"
                :style="{ color: scoreColor(card.score) }"
              >
                {{ (card.score * 100).toFixed(0) }}%
              </span>
            </div>

            <p class="card-title">{{ card.title }}</p>

            <p v-if="card.snippet" class="card-snippet">{{ card.snippet }}</p>

            <div class="card-footer">
              <a :href="card.url" target="_blank" rel="noopener noreferrer" class="card-link">
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="12" height="12" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                    d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                </svg>
                {{ $t('knowledge.research.open') }}
              </a>

              <div class="card-actions" v-if="!card.decision">
                <button class="btn-accept" @click="acceptSource(card)" :title="$t('knowledge.research.acceptTitle')">
                  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                  </svg>
                  {{ $t('knowledge.research.accept') }}
                </button>
                <button class="btn-reject" @click="rejectSource(card)" :title="$t('knowledge.research.rejectTitle')">
                  <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                  {{ $t('knowledge.research.reject') }}
                </button>
              </div>

              <span v-else class="card-decision" :class="`card-decision--${card.decision}`">
                {{ card.decision === 'accepted' ? $t('knowledge.research.accepted') : $t('knowledge.research.rejected') }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- RIGHT: Browser stream -->
      <div class="panel-right">
        <div class="browser-header">
          <div class="browser-status">
            <span
              class="status-dot"
              :class="{
                'status-dot--connected': browserConnected,
                'status-dot--disconnected': !browserConnected,
              }"
            ></span>
            <span class="status-label">
              {{ browserConnected ? $t('knowledge.research.browserConnected') : $t('knowledge.research.browserDisconnected') }}
            </span>
          </div>
          <button
            class="screenshot-refresh-btn"
            :disabled="screenshotLoading || !browserConnected"
            :title="$t('knowledge.research.refreshScreenshot')"
            @click="fetchScreenshot"
          >
            <svg
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
              width="14"
              height="14"
              :class="{ 'spin-icon': screenshotLoading }"
              aria-hidden="true"
            >
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
        </div>

        <!-- Viewport -->
        <div class="browser-viewport">
          <!-- Screenshot -->
          <img
            v-if="screenshot"
            :src="`data:image/png;base64,${screenshot}`"
            :alt="$t('knowledge.research.liveBrowserView')"
            class="screenshot-img"
            :class="{ 'screenshot-img--loading': screenshotLoading }"
          />

          <!-- No screenshot yet -->
          <div v-else class="viewport-empty">
            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" width="48" height="48" aria-hidden="true">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
                d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
            <p>{{ isResearching ? $t('knowledge.research.waitingBrowser') : $t('knowledge.research.startQuery') }}</p>
          </div>
        </div>

        <!-- Status bar -->
        <div class="status-bar">
          <span
            class="status-indicator"
            :class="{ 'status-indicator--active': isResearching }"
          ></span>
          <span class="status-text">{{ statusText }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── Layout ──────────────────────────────────────────────────────────────── */

.research-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--bg-primary);
  overflow: hidden;
}

.panel-split {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* ── Left panel ──────────────────────────────────────────────────────────── */

.panel-left {
  width: 380px;
  min-width: 320px;
  max-width: 420px;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border-default);
  overflow: hidden;
  background: var(--bg-secondary);
}

/* ── Query bar ───────────────────────────────────────────────────────────── */

.query-bar {
  display: flex;
  gap: var(--spacing-2);
  padding: var(--spacing-3);
  border-bottom: 1px solid var(--border-default);
  flex-shrink: 0;
  align-items: center;
}

.query-input-wrap {
  flex: 1;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  background: var(--bg-input);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: 0 var(--spacing-3);
  transition: border-color var(--duration-150);
}

.query-input-wrap:focus-within {
  border-color: var(--color-info);
}

.query-icon {
  width: 16px;
  height: 16px;
  color: var(--text-muted);
  flex-shrink: 0;
}

.query-input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-primary);
  font-size: var(--text-sm);
  padding: var(--spacing-2) 0;
}

.query-input::placeholder {
  color: var(--text-muted);
}

.query-input:disabled {
  opacity: 0.6;
}

.btn-primary {
  flex-shrink: 0;
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--color-info);
  color: #fff;
  border: none;
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--text-sm);
  font-weight: 500;
  white-space: nowrap;
  transition: background var(--duration-150);
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-info-hover, var(--color-info));
  filter: brightness(1.1);
}

.btn-primary:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.btn-stop {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  flex-shrink: 0;
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--color-error-bg);
  color: var(--color-error);
  border: 1px solid var(--color-error-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: var(--text-sm);
  font-weight: 500;
  white-space: nowrap;
  transition: background var(--duration-150);
}

.btn-stop:hover {
  background: var(--color-error);
  color: #fff;
}

/* ── Error banner ────────────────────────────────────────────────────────── */

.error-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--color-error-bg);
  border-bottom: 1px solid var(--color-error-border);
  color: var(--color-error);
  font-size: var(--text-xs);
  flex-shrink: 0;
}

.error-dismiss {
  margin-left: auto;
  background: none;
  border: none;
  color: inherit;
  cursor: pointer;
  padding: 2px;
  display: flex;
  align-items: center;
}

/* ── Sources section ─────────────────────────────────────────────────────── */

.sources-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-3);
  border-bottom: 1px solid var(--border-default);
  flex-shrink: 0;
}

.sources-title {
  font-size: var(--text-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: var(--text-tertiary);
}

.sources-count {
  background: var(--color-info-bg);
  color: var(--color-info);
  font-size: 11px;
  font-weight: 600;
  border-radius: 10px;
  padding: 1px 7px;
}

.sources-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-2);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
}

.sources-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-10) var(--spacing-4);
  color: var(--text-muted);
  text-align: center;
  font-size: var(--text-sm);
}

.sources-searching {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-4);
  color: var(--text-secondary);
  font-size: var(--text-sm);
  justify-content: center;
}

/* ── Source card ─────────────────────────────────────────────────────────── */

.source-card {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--spacing-3);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2);
  transition: border-color var(--duration-150);
}

.source-card--accepted {
  border-color: var(--color-success);
  background: var(--color-success-bg, rgba(34,197,94,0.05));
}

.source-card--rejected {
  border-color: var(--border-default);
  opacity: 0.5;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-2);
}

.card-domain {
  font-size: var(--text-xs);
  color: var(--color-info);
  font-family: var(--font-mono);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 220px;
}

.card-score {
  font-size: var(--text-xs);
  font-weight: 700;
  flex-shrink: 0;
}

.card-title {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  margin: 0;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-snippet {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-2);
  flex-wrap: wrap;
}

.card-link {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: var(--text-xs);
  color: var(--text-muted);
  text-decoration: none;
  transition: color var(--duration-150);
}

.card-link:hover {
  color: var(--color-info);
}

.card-actions {
  display: flex;
  gap: var(--spacing-1-5);
}

.btn-accept,
.btn-reject {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-weight: 500;
  cursor: pointer;
  transition: background var(--duration-150), color var(--duration-150);
}

.btn-accept {
  background: var(--color-success-bg, rgba(34,197,94,0.1));
  color: var(--color-success);
  border: 1px solid var(--color-success);
}

.btn-accept:hover {
  background: var(--color-success);
  color: #fff;
}

.btn-reject {
  background: var(--color-error-bg);
  color: var(--color-error);
  border: 1px solid var(--color-error-border);
}

.btn-reject:hover {
  background: var(--color-error);
  color: #fff;
}

.card-decision {
  font-size: var(--text-xs);
  font-weight: 600;
}

.card-decision--accepted {
  color: var(--color-success);
}

.card-decision--rejected {
  color: var(--text-muted);
}

/* ── Right panel ─────────────────────────────────────────────────────────── */

.panel-right {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg-primary);
  overflow: hidden;
}

/* ── Browser header ──────────────────────────────────────────────────────── */

.browser-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-default);
  gap: var(--spacing-3);
}

.browser-status {
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  font-size: var(--text-xs);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-dot--connected {
  background: var(--color-success);
}

.status-dot--disconnected {
  background: var(--color-error);
}

.status-label {
  color: var(--text-secondary);
}

.screenshot-refresh-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: color var(--duration-150), background var(--duration-150);
}

.screenshot-refresh-btn:hover:not(:disabled) {
  color: var(--text-primary);
  background: var(--bg-hover);
}

.screenshot-refresh-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ── Browser viewport ────────────────────────────────────────────────────── */

.browser-viewport {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-primary);
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

.viewport-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-12) var(--spacing-6);
  color: var(--text-muted);
  text-align: center;
}

.viewport-empty p {
  font-size: var(--text-sm);
  max-width: 320px;
  margin: 0;
}

/* ── Status bar ──────────────────────────────────────────────────────────── */

.status-bar {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-secondary);
  border-top: 1px solid var(--border-default);
  font-size: var(--text-xs);
}

.status-indicator {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-muted);
  flex-shrink: 0;
}

.status-indicator--active {
  background: var(--color-info);
  animation: pulse 1.5s ease-in-out infinite;
}

.status-text {
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Spin animation ──────────────────────────────────────────────────────── */

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.spin-icon {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* ── Responsive ──────────────────────────────────────────────────────────── */

@media (max-width: 900px) {
  .panel-split {
    flex-direction: column;
  }

  .panel-left {
    width: 100%;
    max-width: 100%;
    min-width: 0;
    border-right: none;
    border-bottom: 1px solid var(--border-default);
    max-height: 50vh;
  }

  .panel-right {
    min-height: 300px;
  }
}
</style>
