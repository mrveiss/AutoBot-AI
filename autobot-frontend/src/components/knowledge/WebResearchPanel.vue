<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2026 mrveiss -->
<!-- Author: mrveiss -->
<!-- WebResearchPanel — 4-tab web research UI (MVA-344) -->

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTabs } from '@/composables/useTabs'
import { useWebResearchStore } from '@/stores/useWebResearchStore'
import ScrapeTab from '@/components/knowledge/web-research/ScrapeTab.vue'
import CrawlTab from '@/components/knowledge/web-research/CrawlTab.vue'
import SiteMapTab from '@/components/knowledge/web-research/SiteMapTab.vue'
import ExtractTab from '@/components/knowledge/web-research/ExtractTab.vue'

const { t } = useI18n()

// #11665: pre-flight — hydrate settings/status from the backend on mount and
// block submits when the researcher is unavailable or research is disabled.
const store = useWebResearchStore()
const bannerDismissed = ref(false)

const researchBlocked = computed(() => !store.researcherAvailable || !store.isEnabled)
const bannerText = computed(() =>
  !store.researcherAvailable
    ? t('knowledge.webResearch.banner.unavailable')
    : t('knowledge.webResearch.banner.disabled')
)

onMounted(() => {
  store.loadFromBackend()
})

const TAB_IDS = ['scrape', 'crawl', 'sitemap', 'extract'] as const
type TabId = (typeof TAB_IDS)[number]

const { activeTab, tabAttrs, panelAttrs, handleKeydown, tablistRef } = useTabs(TAB_IDS)

interface Tab {
  id: TabId
  label: string
  ariaLabel: string
}

const tabs: Tab[] = [
  {
    id: 'scrape',
    label: t('knowledge.webResearch.tabs.scrape'),
    ariaLabel: t('knowledge.webResearch.tabs.scrapeAriaLabel'),
  },
  {
    id: 'crawl',
    label: t('knowledge.webResearch.tabs.crawl'),
    ariaLabel: t('knowledge.webResearch.tabs.crawlAriaLabel'),
  },
  {
    id: 'sitemap',
    label: t('knowledge.webResearch.tabs.siteMap'),
    ariaLabel: t('knowledge.webResearch.tabs.siteMapAriaLabel'),
  },
  {
    id: 'extract',
    label: t('knowledge.webResearch.tabs.extract'),
    ariaLabel: t('knowledge.webResearch.tabs.extractAriaLabel'),
  },
]
</script>

<template>
  <div class="web-research-panel">
    <!-- Header -->
    <div class="wrp-header">
      <div class="wrp-header__content">
        <h2 class="wrp-header__title">
          <svg class="wrp-header__icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          {{ t('knowledge.webResearch.title') }}
        </h2>
        <p class="wrp-header__subtitle">{{ t('knowledge.webResearch.subtitle') }}</p>
      </div>
    </div>

    <!-- Pre-flight banner (#11665) -->
    <div v-if="researchBlocked && !bannerDismissed" class="wrp-banner" role="alert">
      <svg class="wrp-banner__icon" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
      <span class="wrp-banner__text">{{ bannerText }}</span>
      <button
        type="button"
        class="wrp-banner__dismiss"
        :aria-label="t('knowledge.webResearch.banner.dismiss')"
        @click="bannerDismissed = true"
      >
        <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true" class="wrp-banner__dismiss-icon">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <!-- Tab bar -->
    <div
      ref="tablistRef"
      class="wrp-tabs"
      role="tablist"
      :aria-label="t('knowledge.webResearch.tabListAriaLabel')"
    >
      <button
        v-for="tab in tabs"
        :key="tab.id"
        v-bind="tabAttrs(tab.id)"
        class="wrp-tab"
        :class="{ 'wrp-tab--active': activeTab === tab.id }"
        :aria-label="tab.ariaLabel"
        @click="activeTab = tab.id"
        @keydown="handleKeydown"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- Tab panels -->
    <div v-if="activeTab === 'scrape'" v-bind="panelAttrs('scrape')" class="wrp-content">
      <ScrapeTab :disabled="researchBlocked" />
    </div>
    <div v-else-if="activeTab === 'crawl'" v-bind="panelAttrs('crawl')" class="wrp-content">
      <CrawlTab :disabled="researchBlocked" />
    </div>
    <div v-else-if="activeTab === 'sitemap'" v-bind="panelAttrs('sitemap')" class="wrp-content">
      <SiteMapTab :disabled="researchBlocked" />
    </div>
    <div v-else-if="activeTab === 'extract'" v-bind="panelAttrs('extract')" class="wrp-content">
      <ExtractTab :disabled="researchBlocked" />
    </div>
  </div>
</template>

<style scoped>
/* ── Layout ─────────────────────────────────────────────────────────────── */

.web-research-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-primary);
  color: var(--text-primary);
}

/* ── Header ─────────────────────────────────────────────────────────────── */

.wrp-header {
  padding: var(--spacing-5) var(--spacing-6) var(--spacing-4);
  border-bottom: 1px solid var(--border-primary);
}

.wrp-header__content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.wrp-header__title {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  font-size: 1.25rem;
  font-weight: 600;
  margin: 0;
  color: var(--text-primary);
}

.wrp-header__icon {
  width: 22px;
  height: 22px;
  color: var(--color-primary);
  flex-shrink: 0;
}

.wrp-header__subtitle {
  font-size: 0.875rem;
  color: var(--text-muted);
  margin: 0;
}

/* ── Pre-flight banner (#11665) ─────────────────────────────────────────── */

.wrp-banner {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-2-5);
  margin: var(--spacing-3) var(--spacing-6) 0;
  padding: var(--spacing-3) var(--spacing-3-5);
  background: color-mix(in srgb, var(--status-warning) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--status-warning) 35%, transparent);
  border-radius: var(--radius-lg);
  font-size: 0.875rem;
  color: var(--text-primary);
}

.wrp-banner__icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  margin-top: var(--spacing-px);
  color: var(--status-warning);
}

.wrp-banner__text {
  flex: 1;
  line-height: 1.5;
}

.wrp-banner__dismiss {
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--text-muted);
  padding: 0;
  display: flex;
  align-items: center;
  flex-shrink: 0;
}

.wrp-banner__dismiss:hover {
  color: var(--text-primary);
}

.wrp-banner__dismiss-icon {
  width: var(--spacing-4);
  height: var(--spacing-4);
}

/* ── Tab bar ────────────────────────────────────────────────────────────── */

.wrp-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--border-primary);
  background: var(--bg-secondary);
  padding: 0 var(--spacing-4);
  overflow-x: auto;
}

.wrp-tab {
  padding: var(--spacing-3) 18px;
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-muted);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  white-space: nowrap;
  transition: color 0.15s, border-color 0.15s;
  outline: none;
}

.wrp-tab:hover {
  color: var(--text-primary);
}

.wrp-tab--active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
}

.wrp-tab:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: -2px;
}

/* ── Content ────────────────────────────────────────────────────────────── */

.wrp-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-6);
}
</style>

<!-- Shared tab styles (unscoped so child components can consume them) -->
<style>
/* ── Form layout ─────────────────────────────────────────────────────────── */

.wr-form {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-6);
}

.wr-form-row {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1-5);
}

.wr-form-row--inline {
  flex-direction: row;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--spacing-4);
}

.wr-field {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1-5);
}

.wr-field--checkbox {
  justify-content: flex-end;
  padding-bottom: var(--spacing-0-5);
}

/* ── Inputs ──────────────────────────────────────────────────────────────── */

.wr-label {
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.wr-input {
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-tertiary, var(--bg-secondary));
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: 0.875rem;
  outline: none;
  transition: border-color 0.15s;
}

.wr-input:focus {
  border-color: var(--color-primary);
}

.wr-input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.wr-input--number {
  width: 90px;
}

.wr-input--filter {
  flex: 1;
  min-width: 0;
}

.wr-select {
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-tertiary, var(--bg-secondary));
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: 0.875rem;
  outline: none;
  cursor: pointer;
}

.wr-select:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.wr-textarea {
  padding: var(--spacing-2-5) var(--spacing-3);
  background: var(--bg-tertiary, var(--bg-secondary));
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: 0.8rem;
  font-family: monospace;
  resize: vertical;
  outline: none;
  transition: border-color 0.15s;
}

.wr-textarea:focus {
  border-color: var(--color-primary);
}

.wr-checkbox-label {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  font-size: 0.875rem;
  color: var(--text-secondary, var(--text-primary));
  cursor: pointer;
}

.wr-field-error {
  font-size: 0.8rem;
  color: var(--color-error);
  margin: 0;
}

/* ── Buttons ─────────────────────────────────────────────────────────────── */

.wr-form-actions {
  display: flex;
  gap: var(--spacing-3);
  align-items: center;
}

.wr-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: 9px 18px;
  font-size: 0.875rem;
  font-weight: 500;
  border-radius: var(--radius-md);
  border: none;
  cursor: pointer;
  transition: background 0.15s, opacity 0.15s;
  outline: none;
}

.wr-btn:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.wr-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.wr-btn--primary {
  background: var(--color-primary);
  color: var(--bg-primary);
}

.wr-btn--primary:not(:disabled):hover {
  filter: brightness(1.1);
}

.wr-btn--ghost {
  background: transparent;
  color: var(--text-muted);
  border: 1px solid var(--border-primary);
}

.wr-btn--ghost:not(:disabled):hover {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

/* ── Spinner ─────────────────────────────────────────────────────────────── */

.wr-spinner {
  display: inline-block;
  width: var(--spacing-3-5);
  height: var(--spacing-3-5);
  border: 2px solid transparent;
  border-top-color: currentColor;
  border-radius: 50%;
  animation: wr-spin 0.7s linear infinite;
}

@keyframes wr-spin {
  to { transform: rotate(360deg); }
}

/* ── Skeleton ────────────────────────────────────────────────────────────── */

.wr-skeleton-block {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
  padding: var(--spacing-4) 0;
}

.wr-skeleton {
  background: linear-gradient(90deg, var(--bg-secondary) 25%, var(--bg-tertiary) 50%, var(--bg-secondary) 75%);
  background-size: 200% 100%;
  border-radius: var(--radius-default);
  animation: wr-shimmer 1.4s infinite;
  height: var(--spacing-4);
}

.wr-skeleton--title { height: 22px; width: 40%; }
.wr-skeleton--line { width: 100%; }
.wr-skeleton--short { width: 60%; }

@keyframes wr-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* ── Progress bar ────────────────────────────────────────────────────────── */

.wr-progress-block {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-2-5);
  padding: var(--spacing-4) 0;
}

.wr-progress-bar {
  height: var(--spacing-1);
  background: var(--bg-secondary);
  border-radius: var(--radius-xs);
  overflow: hidden;
}

.wr-progress-bar__fill {
  height: 100%;
  background: var(--color-primary);
  border-radius: var(--radius-xs);
  transition: width 0.3s ease;
}

.wr-progress-bar__fill--indeterminate {
  width: 40%;
  animation: wr-progress-slide 1.4s ease-in-out infinite;
}

@keyframes wr-progress-slide {
  0% { transform: translateX(-150%); }
  100% { transform: translateX(350%); }
}

.wr-progress-status {
  font-size: 0.8rem;
  color: var(--text-muted);
  margin: 0;
}

/* ── Error state ─────────────────────────────────────────────────────────── */

.wr-error {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-3);
  padding: var(--spacing-3-5) var(--spacing-4);
  background: color-mix(in srgb, var(--color-error) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-error) 30%, transparent);
  border-radius: var(--radius-lg);
  font-size: 0.875rem;
  color: var(--color-error);
}

.wr-error__icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  margin-top: var(--spacing-px);
}

.wr-error__retry {
  margin-left: auto;
  padding: var(--spacing-1) var(--spacing-3);
  font-size: 0.8rem;
  background: transparent;
  border: 1px solid currentColor;
  border-radius: var(--radius-default);
  color: inherit;
  cursor: pointer;
  white-space: nowrap;
}

/* ── Empty state ─────────────────────────────────────────────────────────── */

.wr-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-4);
  padding: var(--spacing-12) var(--spacing-6);
  color: var(--text-muted);
  text-align: center;
}

.wr-empty__icon {
  width: var(--spacing-12);
  height: var(--spacing-12);
  opacity: 0.4;
}

.wr-empty p {
  font-size: 0.9rem;
  margin: 0;
}

/* ── Result block ────────────────────────────────────────────────────────── */

.wr-result {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-3);
}

.wr-result__header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2-5);
  flex-wrap: wrap;
}

.wr-result__title {
  font-size: 1rem;
  font-weight: 600;
  margin: 0;
  color: var(--text-primary);
}

.wr-result__meta {
  font-size: 0.75rem;
  color: var(--text-muted);
  margin-left: auto;
}

.wr-result__url a {
  font-size: 0.8rem;
  color: var(--color-primary);
  word-break: break-all;
  text-decoration: none;
}

.wr-result__url a:hover {
  text-decoration: underline;
}

.wr-result__content {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  padding: var(--spacing-3-5) var(--spacing-4);
  font-size: 0.8rem;
  font-family: monospace;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-y: auto;
  max-height: 400px;
  color: var(--text-primary);
  line-height: 1.6;
}

.wr-result__content--json {
  color: var(--code-string);
}

.wr-result__content--markdown {
  font-family: inherit;
  font-size: 0.875rem;
}

/* ── Badges ──────────────────────────────────────────────────────────────── */

.wr-badge {
  display: inline-flex;
  align-items: center;
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: 99px;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.wr-badge--success {
  background: color-mix(in srgb, var(--color-success) 15%, transparent);
  color: var(--color-success);
}

.wr-badge--error {
  background: color-mix(in srgb, var(--color-error) 15%, transparent);
  color: var(--color-error);
}

.wr-badge--warning {
  background: color-mix(in srgb, var(--color-warning) 15%, transparent);
  color: var(--color-warning);
}

.wr-badge--info {
  background: color-mix(in srgb, var(--color-primary) 15%, transparent);
  color: var(--color-primary);
}

/* ── URL list ────────────────────────────────────────────────────────────── */

.wr-url-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  max-height: 420px;
  overflow-y: auto;
  border: 1px solid var(--border-primary);
  border-radius: var(--radius-md);
  background: var(--bg-secondary);
  padding: var(--spacing-2) 0;
}

.wr-url-list__item {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-1-5) var(--spacing-3-5);
  font-size: 0.8rem;
}

.wr-url-list__item--failed {
  opacity: 0.5;
}

.wr-url-list__depth {
  color: var(--text-muted);
  font-size: 0.7rem;
  letter-spacing: 0.05em;
  flex-shrink: 0;
}

.wr-url-list__tree-icon {
  width: var(--spacing-3-5);
  height: var(--spacing-3-5);
  flex-shrink: 0;
  color: var(--text-muted);
}

.wr-url-list__content {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-0-5);
  min-width: 0;
}

.wr-url-list__link {
  color: var(--color-primary);
  text-decoration: none;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wr-url-list__link:hover {
  text-decoration: underline;
}

.wr-url-list__title {
  font-size: 0.7rem;
  color: var(--text-muted);
}

/* ── Filter row ──────────────────────────────────────────────────────────── */

.wr-filter-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
}

.wr-filter-count {
  font-size: 0.75rem;
  color: var(--text-muted);
  white-space: nowrap;
}

.wr-empty-filter {
  text-align: center;
  font-size: 0.875rem;
  color: var(--text-muted);
  padding: var(--spacing-6);
}
</style>
