<script setup lang="ts">
import { BaseButton } from '@autobot/ui'
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * DevSpeedupView - code templates and action history
 * Issue #902 - Developer Speedup Tools
 * Issue #1359: i18n string extraction
 */

import { ref, computed } from 'vue'
import { useDevSpeedup } from '@/composables/useDevSpeedup'
import { createLogger } from '@/utils/debugUtils'
import Icon from '@/components/ui/Icon.vue'

const logger = createLogger('DevSpeedupView')

const {
  templates,
  actionHistory,
  isLoading,
  error,
  fetchTemplates,
} = useDevSpeedup({ autoFetch: true })

const selectedCategory = ref<string | undefined>(undefined)

async function handleFetchTemplates() {
  await fetchTemplates(selectedCategory.value)
}

function copyToClipboard(text: string) {
  navigator.clipboard.writeText(text)
  logger.debug('Copied to clipboard')
}

const templateCategories = computed(() => {
  const cats = new Set<string>()
  templates.value.forEach(tmpl => cats.add(tmpl.category))
  return Array.from(cats)
})
</script>

<template>
  <div class="dev-speedup-view">
    <!-- Page Header -->
    <div class="page-header">
      <div class="page-header-content">
        <h2 class="page-title">{{ $t('views.devSpeedup.title') }}</h2>
        <p class="page-subtitle">{{ $t('views.devSpeedup.subtitle') }}</p>
      </div>
      <div v-if="actionHistory.length > 0" class="actions-summary">
        <div class="actions-label">{{ $t('views.devSpeedup.actionsToday') }}</div>
        <div class="actions-count">{{ actionHistory.length }}</div>
      </div>
    </div>

    <!-- Error Alert -->
    <div v-if="error" class="alert alert-error">
      <Icon name="exclamation-circle" />
      <div class="alert-content">
        <strong>{{ $t('views.devSpeedup.error') }}</strong>
        <p>{{ error }}</p>
      </div>
    </div>

    <!-- Templates -->
    <div class="tab-content">
      <div class="tab-panel">
        <div class="card template-filter">
          <div class="card-body filter-row">
            <select v-model="selectedCategory" class="field-select filter-select">
              <option :value="undefined">{{ $t('views.devSpeedup.allCategories') }}</option>
              <option v-for="cat in templateCategories" :key="cat" :value="cat">{{ cat }}</option>
            </select>
            <BaseButton size="sm" @click="handleFetchTemplates" :disabled="isLoading">{{ $t('views.devSpeedup.refresh') }}</BaseButton>
          </div>
        </div>

        <div v-if="templates.length > 0" class="templates-list">
          <div v-for="template in templates" :key="template.id" class="card">
            <div class="card-body">
              <div class="template-header">
                <div>
                  <h3 class="template-name">{{ template.name }}</h3>
                  <div class="template-tags">
                    <span class="badge badge-info">{{ template.language }}</span>
                    <span class="badge badge-purple">{{ template.category }}</span>
                  </div>
                </div>
                <BaseButton variant="ghost" size="xs" @click="copyToClipboard(template.template)">{{ $t('views.devSpeedup.copy') }}</BaseButton>
              </div>
              <p class="template-desc">{{ template.description }}</p>
              <p v-if="template.variables.length > 0" class="template-vars">
                {{ $t('views.devSpeedup.variables') }}: {{ template.variables.join(', ') }}
              </p>
              <pre class="code-block"><code>{{ template.template }}</code></pre>
            </div>
          </div>
        </div>

        <div v-else class="empty-state">
          <Icon name="file-code" />
          <p>{{ $t('views.devSpeedup.noTemplates') }}</p>
        </div>
      </div>

    </div>
  </div>
</template>

<style scoped>
.dev-speedup-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-primary);
}

.actions-summary {
  text-align: right;
  flex-shrink: 0;
}

.actions-label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.actions-count {
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--color-primary);
}

/* Alert */
.alert {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-3);
  padding: var(--spacing-4);
  margin: 0 var(--spacing-5);
  border-radius: var(--radius-md);
}

.alert-error {
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  color: var(--color-error);
}

.alert-content p {
  margin: var(--spacing-1) 0 0;
  font-size: var(--text-sm);
}

/* Tab content */
.tab-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-5);
}

.tab-panel {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-5);
}

.badge-purple { background: rgba(147, 51, 234, 0.1); color: var(--color-purple); }

/* Snippets / Templates lists */
.templates-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
}

.template-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: var(--spacing-3);
}

.template-tags {
  display: flex;
  gap: var(--spacing-2);
  flex-wrap: wrap;
}

.template-tags { margin-top: var(--spacing-1); }

.template-name {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: var(--spacing-0);
}

.template-desc {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0 0 var(--spacing-3);
}

.template-vars {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin: 0 0 var(--spacing-3);
}

/* Code blocks */
.code-block {
  background: var(--code-bg);
  color: var(--code-text);
  padding: var(--spacing-4);
  border-radius: var(--radius-md);
  overflow-x: auto;
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  margin: var(--spacing-0);
}

/* Filter row */
.filter-row {
  display: flex;
  gap: var(--spacing-4);
  align-items: center;
}

.filter-select { flex: 1; }

/* Empty state */
.empty-state {
  text-align: center;
  padding: var(--spacing-12) var(--spacing-4);
  color: var(--text-secondary);
}

.empty-state svg {
  width: var(--text-3xl);
  height: var(--text-3xl);
  margin: 0 auto var(--spacing-3);
  display: block;
  color: var(--text-muted);
}

.empty-state p { margin: var(--spacing-0); font-size: var(--text-sm); }

  .filter-row { flex-direction: column; }
</style>
