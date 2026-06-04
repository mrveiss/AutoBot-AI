<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2026 mrveiss -->
<!-- Author: mrveiss -->
<!-- WebResearchPanel — 4-tab web research UI (MVA-344) -->

<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ScrapeTab from '@/components/knowledge/web-research/ScrapeTab.vue'
import CrawlTab from '@/components/knowledge/web-research/CrawlTab.vue'
import SiteMapTab from '@/components/knowledge/web-research/SiteMapTab.vue'
import ExtractTab from '@/components/knowledge/web-research/ExtractTab.vue'

const { t } = useI18n()

type TabId = 'scrape' | 'crawl' | 'sitemap' | 'extract'

const activeTab = ref<TabId>('scrape')

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

    <!-- Tab bar -->
    <div class="wrp-tabs" role="tablist" :aria-label="t('knowledge.webResearch.tabListAriaLabel')">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        class="wrp-tab"
        :class="{ 'wrp-tab--active': activeTab === tab.id }"
        role="tab"
        :aria-selected="activeTab === tab.id"
        :aria-label="tab.ariaLabel"
        @click="activeTab = tab.id"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- Tab content -->
    <div class="wrp-content" role="tabpanel">
      <ScrapeTab v-if="activeTab === 'scrape'" />
      <CrawlTab v-else-if="activeTab === 'crawl'" />
      <SiteMapTab v-else-if="activeTab === 'sitemap'" />
      <ExtractTab v-else-if="activeTab === 'extract'" />
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
  padding: 20px 24px 16px;
  border-bottom: 1px solid var(--border-primary);
}

.wrp-header__content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.wrp-header__title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 1.25rem;
  font-weight: 600;
  margin: 0;
  color: var(--text-primary);
}

.wrp-header__icon {
  width: 22px;
  height: 22px;
  color: var(--accent-primary, #00d4ff);
  flex-shrink: 0;
}

.wrp-header__subtitle {
  font-size: 0.875rem;
  color: var(--text-muted);
  margin: 0;
}

/* ── Tab bar ────────────────────────────────────────────────────────────── */

.wrp-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--border-primary);
  background: var(--bg-secondary);
  padding: 0 16px;
  overflow-x: auto;
}

.wrp-tab {
  padding: 12px 18px;
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
  color: var(--accent-primary, #00d4ff);
  border-bottom-color: var(--accent-primary, #00d4ff);
}

.wrp-tab:focus-visible {
  outline: 2px solid var(--accent-primary, #00d4ff);
  outline-offset: -2px;
}

/* ── Content ────────────────────────────────────────────────────────────── */

.wrp-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}
</style>

<!-- Shared tab styles (unscoped so child components can consume them) -->
<style>
/* ── Form layout ─────────────────────────────────────────────────────────── */

.wr-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-bottom: 24px;
}

.wr-form-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.wr-form-row--inline {
  flex-direction: row;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 16px;
}

.wr-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.wr-field--checkbox {
  justify-content: flex-end;
  padding-bottom: 2px;
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
  padding: 8px 12px;
  background: var(--bg-tertiary, var(--bg-secondary));
  border: 1px solid var(--border-primary);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.875rem;
  outline: none;
  transition: border-color 0.15s;
}

.wr-input:focus {
  border-color: var(--accent-primary, #00d4ff);
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
  padding: 8px 12px;
  background: var(--bg-tertiary, var(--bg-secondary));
  border: 1px solid var(--border-primary);
  border-radius: 6px;
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
  padding: 10px 12px;
  background: var(--bg-tertiary, var(--bg-secondary));
  border: 1px solid var(--border-primary);
  border-radius: 6px;
  color: var(--text-primary);
  font-size: 0.8rem;
  font-family: monospace;
  resize: vertical;
  outline: none;
  transition: border-color 0.15s;
}

.wr-textarea:focus {
  border-color: var(--accent-primary, #00d4ff);
}

.wr-checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.875rem;
  color: var(--text-secondary, var(--text-primary));
  cursor: pointer;
}

.wr-field-error {
  font-size: 0.8rem;
  color: var(--status-error, #f87171);
  margin: 0;
}

/* ── Buttons ─────────────────────────────────────────────────────────────── */

.wr-form-actions {
  display: flex;
  gap: 12px;
  align-items: center;
}

.wr-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 9px 18px;
  font-size: 0.875rem;
  font-weight: 500;
  border-radius: 6px;
  border: none;
  cursor: pointer;
  transition: background 0.15s, opacity 0.15s;
  outline: none;
}

.wr-btn:focus-visible {
  outline: 2px solid var(--accent-primary, #00d4ff);
  outline-offset: 2px;
}

.wr-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.wr-btn--primary {
  background: var(--accent-primary, #00d4ff);
  color: var(--bg-primary, #0a0a0a);
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
  width: 14px;
  height: 14px;
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
  gap: 12px;
  padding: 16px 0;
}

.wr-skeleton {
  background: linear-gradient(90deg, var(--bg-secondary) 25%, var(--bg-tertiary, #1a1a1a) 50%, var(--bg-secondary) 75%);
  background-size: 200% 100%;
  border-radius: 4px;
  animation: wr-shimmer 1.4s infinite;
  height: 16px;
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
  gap: 10px;
  padding: 16px 0;
}

.wr-progress-bar {
  height: 4px;
  background: var(--bg-secondary);
  border-radius: 2px;
  overflow: hidden;
}

.wr-progress-bar__fill {
  height: 100%;
  background: var(--accent-primary, #00d4ff);
  border-radius: 2px;
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
  gap: 12px;
  padding: 14px 16px;
  background: color-mix(in srgb, var(--status-error, #f87171) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--status-error, #f87171) 30%, transparent);
  border-radius: 8px;
  font-size: 0.875rem;
  color: var(--status-error, #f87171);
}

.wr-error__icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  margin-top: 1px;
}

.wr-error__retry {
  margin-left: auto;
  padding: 4px 12px;
  font-size: 0.8rem;
  background: transparent;
  border: 1px solid currentColor;
  border-radius: 4px;
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
  gap: 16px;
  padding: 48px 24px;
  color: var(--text-muted);
  text-align: center;
}

.wr-empty__icon {
  width: 48px;
  height: 48px;
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
  gap: 12px;
}

.wr-result__header {
  display: flex;
  align-items: center;
  gap: 10px;
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
  color: var(--accent-primary, #00d4ff);
  word-break: break-all;
  text-decoration: none;
}

.wr-result__url a:hover {
  text-decoration: underline;
}

.wr-result__content {
  background: var(--bg-secondary);
  border: 1px solid var(--border-primary);
  border-radius: 6px;
  padding: 14px 16px;
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
  color: var(--text-code, #a3e635);
}

.wr-result__content--markdown {
  font-family: inherit;
  font-size: 0.875rem;
}

/* ── Badges ──────────────────────────────────────────────────────────────── */

.wr-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 99px;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.wr-badge--success {
  background: color-mix(in srgb, var(--status-success, #4ade80) 15%, transparent);
  color: var(--status-success, #4ade80);
}

.wr-badge--error {
  background: color-mix(in srgb, var(--status-error, #f87171) 15%, transparent);
  color: var(--status-error, #f87171);
}

.wr-badge--warning {
  background: color-mix(in srgb, var(--status-warning, #fbbf24) 15%, transparent);
  color: var(--status-warning, #fbbf24);
}

.wr-badge--info {
  background: color-mix(in srgb, var(--accent-primary, #00d4ff) 15%, transparent);
  color: var(--accent-primary, #00d4ff);
}

/* ── URL list ────────────────────────────────────────────────────────────── */

.wr-url-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 420px;
  overflow-y: auto;
  border: 1px solid var(--border-primary);
  border-radius: 6px;
  background: var(--bg-secondary);
  padding: 8px 0;
}

.wr-url-list__item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
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
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  color: var(--text-muted);
}

.wr-url-list__content {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.wr-url-list__link {
  color: var(--accent-primary, #00d4ff);
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
  gap: 12px;
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
  padding: 24px;
}
</style>
