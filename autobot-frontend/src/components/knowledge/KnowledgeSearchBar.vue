<template>
  <div class="knowledge-search-bar">
    <!-- Search Mode Toggle -->
    <div class="search-mode-toggle">
      <div class="toggle-container">
        <button
          :class="['mode-button', { active: !search.useRagSearch.value }]"
          @click="search.useRagSearch.value = false"
        >
          <Icon name="search" />
          {{ $t('knowledge.search.traditionalSearch') }}
        </button>
        <button
          :class="['mode-button', 'rag-button', { active: search.useRagSearch.value }]"
          @click="search.useRagSearch.value = true"
        >
          <Icon name="brain" />
          {{ $t('knowledge.search.ragEnhanced') }}
        </button>
      </div>
      <div class="mode-description">
        <p v-if="!search.useRagSearch.value" class="traditional-desc">
          {{ $t('knowledge.search.traditionalDesc') }}
        </p>
        <p v-else class="rag-desc">
          {{ $t('knowledge.search.ragDesc') }}
        </p>
      </div>
    </div>

    <!-- Search Input -->
    <div class="search-input-container">
      <div class="search-input-wrapper">
        <input
          v-model="search.searchQuery.value"
          type="text"
          :placeholder="search.useRagSearch.value ? $t('knowledge.search.ragPlaceholder') : $t('knowledge.search.searchPlaceholder')"
          @keyup.enter="onSearch"
          class="search-input"
        >
        <button
          v-if="search.searchPerformed.value"
          @click="onClear"
          class="clear-button"
          :title="$t('knowledge.search.clear')"
        >
          <Icon name="times" />
        </button>
        <button
          @click="onSearch"
          :disabled="search.isSearching.value || !search.searchQuery.value.trim()"
          class="search-button"
        >
          <i v-if="search.isSearching.value" class="fas fa-spinner fa-spin"></i>
          <i v-else class="fas fa-search"></i>
          {{ search.isSearching.value ? $t('knowledge.search.searching') : $t('knowledge.search.searchBtn') }}
        </button>
      </div>
    </div>

    <!-- Filters disclosure: access-level chips + RAG options -->
    <details class="filters-row">
      <summary>{{ $t('knowledge.browser.filters') }}</summary>

      <!-- Access Level Filter -->
      <div class="access-level-filter">
        <label class="filter-label">
          <Icon name="shield-alt" />
          {{ $t('knowledge.search.filterByAccessLevel') }}
        </label>
        <div class="filter-chips">
          <button
            v-for="level in accessLevels"
            :key="level.value"
            :class="['filter-chip', { active: search.selectedAccessLevel.value === level.value }]"
            @click="search.toggleAccessLevel(level.value)"
          >
            <i :class="level.icon"></i>
            {{ level.label }}
          </button>
          <button
            v-if="search.selectedAccessLevel.value"
            @click="search.clearAccessLevelFilter()"
            class="clear-chip"
            :title="$t('knowledge.search.clearAccessLevelFilter')"
          >
            <Icon name="times" />
            {{ $t('knowledge.search.clear') }}
          </button>
        </div>
      </div>

      <!-- RAG Options -->
      <div v-if="search.useRagSearch.value" class="rag-options">
        <div class="option-group">
          <label>
            <input
              v-model="search.ragOptions.value.reformulateQuery"
              type="checkbox"
            >
            {{ $t('knowledge.search.autoEnhanceQuery') }}
          </label>
        </div>
        <div class="option-group">
          <label>
            <input
              v-model="search.ragOptions.value.enableReranking"
              type="checkbox"
            >
            <span class="reranking-label">
              {{ $t('knowledge.search.enableReranking') }}
              <span class="reranking-badge">{{ $t('knowledge.search.rerankingBadge') }}</span>
            </span>
          </label>
        </div>
        <div class="option-group">
          <label>
            {{ $t('knowledge.search.resultsLimit') }}
            <select v-model.number="search.ragOptions.value.limit" class="limit-select">
              <option value="5">5</option>
              <option value="10">10</option>
              <option value="15">15</option>
              <option value="20">20</option>
            </select>
          </label>
        </div>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import Icon from '@/components/ui/Icon.vue'
import type { useKnowledgeSearch } from '@/composables/knowledge/useKnowledgeSearch'

const props = defineProps<{ search: ReturnType<typeof useKnowledgeSearch> }>()
const emit = defineEmits<{ (e: 'search'): void; (e: 'clear'): void }>()
const { t } = useI18n()

const accessLevels = computed(() => [
  { value: 'autobot', label: t('knowledge.search.accessPlatform'), icon: 'fas fa-robot' },
  { value: 'general', label: t('knowledge.search.accessPublic'), icon: 'fas fa-globe' },
  { value: 'system', label: t('knowledge.search.accessSystem'), icon: 'fas fa-cog' },
  { value: 'user', label: t('knowledge.search.accessUser'), icon: 'fas fa-user' },
])

async function onSearch() {
  await props.search.handleSearch()
  emit('search')
}

function onClear() {
  props.search.searchQuery.value = ''
  props.search.clearResults()
  emit('clear')
}
</script>

<style scoped>
@reference "../../assets/tailwind.css";

/* Search Mode Toggle */
.search-mode-toggle {
  @apply mb-4;
}

.toggle-container {
  @apply flex bg-autobot-bg-secondary rounded-lg p-1 mb-2;
}

.mode-button {
  @apply flex-1 px-4 py-2 rounded-md text-sm font-medium transition-all duration-200 flex items-center justify-center gap-2;
}

.mode-button:not(.active) {
  @apply text-autobot-text-secondary hover:text-autobot-text-primary;
}

.mode-button.active {
  @apply bg-autobot-bg-card text-autobot-text-primary shadow-sm;
}

.mode-button.rag-button.active {
  background: var(--color-primary);
  color: var(--text-inverse);
}

.mode-description {
  @apply text-xs text-autobot-text-muted px-2;
}

.rag-desc {
  color: var(--color-info);
}

/* Search Input */
.search-input-container {
  @apply mb-4;
}

.search-input-wrapper {
  @apply flex gap-2;
}

.search-input {
  @apply flex-1 px-4 py-2 border border-autobot-border rounded-lg focus:ring-2 focus:border-transparent;
  --tw-ring-color: var(--color-primary);
}

.clear-button {
  @apply p-2 text-autobot-text-muted rounded-lg transition-colors;
  &:hover { color: var(--color-error); background: var(--color-error-bg); }
}

.search-button {
  @apply px-6 py-2 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2;
  background: var(--color-primary);
  color: var(--text-inverse);
}

.search-button:hover:not(:disabled) {
  filter: brightness(1.1);
}

/* Filters disclosure */
.filters-row {
  @apply mb-4;
}

.filters-row summary {
  @apply cursor-pointer text-sm font-medium text-autobot-text-secondary py-1 select-none;
}

/* Access Level Filter */
.access-level-filter {
  @apply mt-3 p-3 bg-autobot-bg-tertiary rounded-lg border border-autobot-border;
}

.filter-label {
  @apply text-sm font-medium text-autobot-text-secondary flex items-center gap-2 mb-2;
}

.filter-chips {
  @apply flex flex-wrap gap-2;
}

.filter-chip {
  @apply px-3 py-1.5 text-sm font-medium rounded-full border-2 transition-all flex items-center gap-1.5;
  @apply border-autobot-border bg-autobot-bg-card text-autobot-text-secondary hover:bg-autobot-bg-secondary;
}

.filter-chip.active {
  border-color: var(--color-primary);
  background: var(--color-info-bg);
  color: var(--color-info);
}

.filter-chip i {
  @apply text-xs;
}

.clear-chip {
  @apply px-3 py-1.5 text-sm font-medium rounded-full border-2 transition-all flex items-center gap-1.5;
  @apply bg-autobot-bg-card;
  border-color: rgba(239, 68, 68, 0.5);
  color: var(--color-error);
  &:hover { background: var(--color-error-bg); border-color: var(--color-error); }
}

/* RAG Options */
.rag-options {
  @apply mt-3 p-3 rounded-lg;
  background: var(--color-info-bg);
  border: 1px solid rgba(59, 130, 246, 0.2);
}

.option-group {
  @apply flex items-center gap-2 text-sm text-autobot-text-secondary;
}

.option-group + .option-group {
  @apply mt-2;
}

.limit-select {
  @apply ml-2 px-2 py-1 border border-autobot-border rounded text-xs;
}

.reranking-label {
  @apply flex items-center gap-2;
}

.reranking-badge {
  @apply text-xs px-2 py-0.5 rounded-full font-normal;
  background: var(--color-info-bg);
  color: var(--color-info);
}
</style>
