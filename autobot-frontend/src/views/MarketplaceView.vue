<template>
  <div class="marketplace-view view-container">
    <div class="marketplace-content">
      <!-- Header -->
      <div class="marketplace-header">
        <div class="header-content">
          <h1 class="page-title">{{ $t('views.marketplace.title') }}</h1>
          <p class="page-subtitle">{{ $t('views.marketplace.subtitle') }}</p>
        </div>
        <button class="btn-refresh" :disabled="loading" @click="load" :title="$t('views.marketplace.refresh')" :aria-label="$t('views.marketplace.refresh')">
          <svg
            class="refresh-icon"
            :class="{ spinning: loading }"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
            />
          </svg>
        </button>
      </div>

      <!-- Error Banner -->
      <div v-if="error" class="error-banner">
        <svg class="error-icon" fill="currentColor" viewBox="0 0 20 20">
          <path
            fill-rule="evenodd"
            d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z"
            clip-rule="evenodd"
          />
        </svg>
        <span>{{ error }}</span>
      </div>

      <!-- Filters -->
      <div class="filters-bar">
        <div class="search-wrapper">
          <svg class="search-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            v-model="searchQuery"
            class="search-input"
            type="text"
            :placeholder="$t('views.marketplace.searchPlaceholder')"
            @input="onSearch"
          />
        </div>

        <!-- Issue #6481: Marketplace source selector -->
        <select v-model="selectedSourceId" class="filter-select" @change="onSourceChange">
          <option v-for="src in sources" :key="src.id" :value="src.id">
            {{ src.name }}
          </option>
        </select>

        <select v-model="selectedCategory" class="filter-select" @change="onFilter">
          <option value="all">{{ $t('views.marketplace.allCategories') }}</option>
          <option v-for="cat in categories" :key="cat" :value="cat">{{ cat }}</option>
        </select>

        <select v-model="sortBy" class="filter-select" @change="onFilter">
          <option value="downloads">{{ $t('views.marketplace.sortDownloads') }}</option>
          <option value="rating">{{ $t('views.marketplace.sortRating') }}</option>
          <option value="name">{{ $t('views.marketplace.sortName') }}</option>
        </select>

        <button
          class="btn-filter-toggle"
          :class="{ active: showInstalledOnly }"
          @click="showInstalledOnly = !showInstalledOnly"
        >
          {{ $t('views.marketplace.installedOnly') }}
          <span class="count-badge">{{ installedNames.size }}</span>
        </button>

        <!-- Issue #6481: Manage marketplace sources -->
        <button class="btn-manage-sources" @click="manageSourcesOpen = true">
          {{ $t('views.marketplace.manageSources') }}
        </button>
      </div>

      <!-- Stats -->
      <div class="stats-row">
        <span class="stats-text">
          {{ $t('views.marketplace.showing', { count: visibleEntries.length, total: entries.length }) }}
        </span>
        <span class="stats-text">
          {{ $t('views.marketplace.installedCount', { count: installedNames.size }) }}
        </span>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="loading-state">
        <svg class="spinner" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        <span>{{ $t('views.marketplace.loading') }}</span>
      </div>

      <!-- Empty -->
      <div v-else-if="visibleEntries.length === 0" class="empty-state">
        <svg class="empty-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="1.5"
            d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"
          />
        </svg>
        <p class="empty-title">{{ $t('views.marketplace.noResults') }}</p>
        <p class="empty-subtitle">{{ $t('views.marketplace.noResultsHint') }}</p>
      </div>

      <!-- Grid -->
      <div v-else class="plugin-grid">
        <div v-for="entry in visibleEntries" :key="entry.name" class="plugin-card">
          <div class="card-header">
            <div class="plugin-icon">
              <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M11 4a2 2 0 114 0v1a1 1 0 001 1h3a1 1 0 011 1v3a1 1 0 01-1 1h-1a2 2 0 100 4h1a1 1 0 011 1v3a1 1 0 01-1 1h-3a1 1 0 01-1-1v-1a2 2 0 10-4 0v1a1 1 0 01-1 1H7a1 1 0 01-1-1v-3a1 1 0 00-1-1H4a2 2 0 110-4h1a1 1 0 001-1V7a1 1 0 011-1h3a1 1 0 001-1V4z"
                />
              </svg>
            </div>
            <span :class="['status-badge', installedNames.has(entry.name) ? 'status-installed' : 'status-available']">
              {{ installedNames.has(entry.name) ? $t('views.marketplace.installed') : $t('views.marketplace.available') }}
            </span>
          </div>

          <div class="card-body">
            <h3 class="plugin-name">{{ entry.display_name }}</h3>
            <p class="plugin-desc">{{ entry.description }}</p>
            <p class="plugin-meta">v{{ entry.version }} &middot; {{ entry.author }}</p>

            <div class="plugin-stats">
              <span class="stat-item">
                <svg class="stat-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                {{ entry.downloads.toLocaleString() }}
              </span>
              <span class="stat-item">
                <svg class="stat-icon star-icon" fill="currentColor" viewBox="0 0 20 20">
                  <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
                </svg>
                {{ entry.rating.toFixed(1) }}
              </span>
              <span class="category-tag">{{ entry.category }}</span>
            </div>

            <div v-if="entry.tags.length > 0" class="tags-list">
              <span v-for="tag in entry.tags.slice(0, 4)" :key="tag" class="tag-chip">{{ tag }}</span>
              <span v-if="entry.tags.length > 4" class="tag-chip tag-more">+{{ entry.tags.length - 4 }}</span>
            </div>
          </div>

          <div class="card-actions">
            <a
              v-if="entry.source_url"
              :href="entry.source_url"
              target="_blank"
              rel="noopener noreferrer"
              class="action-btn action-source"
            >
              {{ $t('views.marketplace.source') }}
            </a>
            <button
              v-if="!installedNames.has(entry.name)"
              class="action-btn action-install"
              :disabled="actionLoading[entry.name]"
              @click="handleInstall(entry.name)"
            >
              <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" class="btn-icon">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              {{ $t('views.marketplace.install') }}
            </button>
            <button
              v-else
              class="action-btn action-uninstall"
              :disabled="actionLoading[entry.name]"
              @click="handleUninstall(entry.name)"
            >
              {{ $t('views.marketplace.uninstall') }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Issue #6481: Manage marketplace sources modal -->
    <MarketplaceSourcesModal
      :open="manageSourcesOpen"
      @close="manageSourcesOpen = false"
      @updated="onSourcesUpdated"
    />
  </div>
</template>

<script setup lang="ts">
// Issue #1803 - Plugin and agent marketplace
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'
import { useMarketplaceSources } from '@/composables/useMarketplaceSources'
import MarketplaceSourcesModal from '@/components/plugins/MarketplaceSourcesModal.vue'

const { t } = useI18n()
const logger = createLogger('MarketplaceView')

interface MarketplaceEntry {
  name: string
  version: string
  display_name: string
  description: string
  author: string
  category: string
  tags: string[]
  entry_point: string
  dependencies: string[]
  hooks: string[]
  downloads: number
  rating: number
  source_url: string
}

const entries = ref<MarketplaceEntry[]>([])
const installedNames = ref<Set<string>>(new Set())
const categories = ref<string[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const actionLoading = ref<Record<string, boolean>>({})

const searchQuery = ref('')
const selectedCategory = ref('all')
const sortBy = ref('downloads')
const showInstalledOnly = ref(false)

// Issue #6481: marketplace sources
const { sources, listSources } = useMarketplaceSources()
const selectedSourceId = ref<string>('builtin')
const manageSourcesOpen = ref(false)

// If the currently selected source is removed, fall back to built-in and
// refetch so the grid reflects the new selection (#6528).
watch(sources, async (next) => {
  if (selectedSourceId.value !== 'builtin' && !next.some(s => s.id === selectedSourceId.value)) {
    selectedSourceId.value = 'builtin'
    await fetchCatalog()
  }
}, { deep: true })

const visibleEntries = computed<MarketplaceEntry[]>(() => {
  if (!showInstalledOnly.value) return entries.value
  return entries.value.filter((e: MarketplaceEntry) => installedNames.value.has(e.name))
})

async function fetchCategories(): Promise<void> {
  try {
    const data = await ApiClient.get<Record<string, unknown>>(`${getApiBase()}/marketplace/categories`)
    categories.value = (data.categories as string[] ?? []).filter((c) => c !== 'all')
  } catch (err) {
    logger.error('Failed to fetch categories', err)
  }
}

async function fetchInstalled(): Promise<void> {
  try {
    const data = await ApiClient.get<Record<string, unknown>>(`${getApiBase()}/marketplace/installed`)
    installedNames.value = new Set(data.installed as string[] ?? [])
  } catch (err) {
    logger.error('Failed to fetch installed list', err)
  }
}

async function fetchCatalog(): Promise<void> {
  const params = new URLSearchParams({ sort_by: sortBy.value })
  if (selectedCategory.value !== 'all') params.set('category', selectedCategory.value)
  if (searchQuery.value.trim()) params.set('search', searchQuery.value.trim())
  // Issue #6481: include selected source so the backend fetches the right catalog
  if (selectedSourceId.value) params.set('source_id', selectedSourceId.value)
  const data = await ApiClient.get<Record<string, unknown>>(`${getApiBase()}/marketplace/catalog?${params.toString()}`)
  entries.value = data.entries as MarketplaceEntry[] ?? []
}

async function load(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    await Promise.all([listSources(), fetchInstalled(), fetchCategories()])
    await fetchCatalog()
  } catch (err) {
    logger.error('Marketplace load failed', err)
    error.value = err instanceof Error ? err.message : t('views.marketplace.loadError')
  } finally {
    loading.value = false
  }
}

async function onSearch(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    await fetchCatalog()
  } catch (err) {
    logger.error('Marketplace search failed', err)
    error.value = err instanceof Error ? err.message : t('views.marketplace.loadError')
  } finally {
    loading.value = false
  }
}

async function onFilter(): Promise<void> {
  await onSearch()
}

async function onSourceChange(): Promise<void> {
  await onSearch()
}

async function onSourcesUpdated(): Promise<void> {
  await listSources()
}

async function handleInstall(name: string): Promise<void> {
  actionLoading.value[name] = true
  error.value = null
  try {
    // #6524: include source_id so backend resolves against the same catalog
    // the user was browsing (otherwise plugins from custom marketplaces 404).
    await ApiClient.post<any>(`${getApiBase()}/marketplace/install`, {
      plugin_name: name,
      source_id: selectedSourceId.value,
    })
    installedNames.value = new Set([...installedNames.value, name])
    await fetchCatalog()
  } catch (err) {
    logger.error('Install failed for', name, err)
    error.value = err instanceof Error ? err.message : t('views.marketplace.installError')
  } finally {
    actionLoading.value[name] = false
  }
}

async function handleUninstall(name: string): Promise<void> {
  actionLoading.value[name] = true
  error.value = null
  try {
    await ApiClient.delete<any>(`${getApiBase()}/marketplace/install/${encodeURIComponent(name)}`)
    const next = new Set(installedNames.value)
    next.delete(name)
    installedNames.value = next
  } catch (err) {
    logger.error('Uninstall failed for', name, err)
    error.value = err instanceof Error ? err.message : t('views.marketplace.uninstallError')
  } finally {
    actionLoading.value[name] = false
  }
}

onMounted(async () => {
  await load()
})
</script>

<style scoped src="@/design-system/styles/marketplace-plugins-shared.css"></style>

<style scoped>
/* ============================================
 * MARKETPLACE VIEW
 * Issue #1803 — Plugin and agent marketplace
 * ============================================ */

.marketplace-content {
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--spacing-md) var(--spacing-md) var(--spacing-xl);
}

/* ---- Header ---- */
.marketplace-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-xl);
}

.btn-refresh {
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--spacing-xs) var(--spacing-sm);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  transition: background var(--duration-150) var(--ease-in-out), color var(--duration-150) var(--ease-in-out);
}

/* ---- Filters ---- */
.filters-bar {
  display: flex;
  gap: var(--spacing-sm);
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: var(--spacing-md);
}

.search-wrapper {
  position: relative;
  flex: 1;
  min-width: 200px;
}

.search-icon {
  position: absolute;
  left: var(--spacing-sm);
  top: 50%;
  transform: translateY(-50%);
  width: 16px;
  height: 16px;
  color: var(--text-secondary);
  pointer-events: none;
}

.search-input {
  width: 100%;
  padding: var(--spacing-1-5) var(--spacing-3) var(--spacing-1-5) var(--spacing-8);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-sm);
  box-sizing: border-box;
}

.search-input:focus {
  outline: none;
  border-color: var(--color-primary);
}

.search-input:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.filter-select {
  padding: var(--spacing-1-5) var(--spacing-2-5);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: var(--text-sm);
  cursor: pointer;
}

.filter-select:focus {
  outline: none;
  border-color: var(--color-primary);
}

.filter-select:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.btn-filter-toggle {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-1-5) var(--spacing-3);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: background var(--duration-150) var(--ease-in-out), color var(--duration-150) var(--ease-in-out), border-color var(--duration-150) var(--ease-in-out);
}

.btn-filter-toggle.active {
  background: var(--color-primary);
  color: white;
  border-color: var(--color-primary);
}

.btn-filter-toggle:hover:not(.active) {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

/* Issue #6481: manage marketplace sources button */
.btn-manage-sources {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-1-5) var(--spacing-3);
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  font-size: var(--text-sm);
  cursor: pointer;
  transition: background var(--duration-150) var(--ease-in-out), color var(--duration-150) var(--ease-in-out);
}

.btn-manage-sources:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.count-badge {
  font-size: var(--text-xs);
  padding: var(--spacing-px) var(--spacing-1-5);
  border-radius: var(--radius-xl);
  min-width: 20px;
  text-align: center;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.btn-filter-toggle.active .count-badge {
  background: rgba(255, 255, 255, 0.25);
  color: white;
}

/* ---- Stats ---- */
.stats-row {
  display: flex;
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-lg);
}

.stats-text {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

/* ---- Loading / Empty ---- */
.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--spacing-2xl) var(--spacing-lg);
  color: var(--text-secondary);
  gap: var(--spacing-md);
}

/* ---- Grid ---- */
.plugin-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: var(--spacing-lg);
}

.plugin-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  padding: var(--spacing-md);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  transition: border-color var(--duration-150) var(--ease-in-out), box-shadow var(--duration-150) var(--ease-in-out);
}

.status-badge {
  font-size: var(--text-xs);
  font-weight: 600;
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-xl);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.status-installed {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.status-available {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.plugin-stats {
  display: flex;
  gap: var(--spacing-sm);
  align-items: center;
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.stat-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

.stat-icon {
  width: 12px;
  height: 12px;
}

.star-icon {
  color: var(--color-warning);
}

.category-tag {
  background: var(--bg-tertiary);
  border: 1px solid var(--border-default);
  padding: var(--spacing-px) var(--spacing-1-5);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
  color: var(--text-secondary);
  text-transform: capitalize;
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-1);
}

.tag-chip {
  font-size: var(--text-xs);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  padding: var(--spacing-px) var(--spacing-1-5);
  border-radius: var(--radius-default);
  border: 1px solid var(--border-default);
}

.tag-more {
  background: transparent;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
  padding: var(--spacing-1) var(--spacing-3);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  border: 1px solid transparent;
  text-decoration: none;
  transition: opacity var(--duration-150) var(--ease-in-out);
}

.btn-icon {
  width: 14px;
  height: 14px;
}

.action-uninstall {
  background: var(--color-error-bg);
  color: var(--color-error);
  border-color: var(--color-error-border);
}

.action-uninstall:hover:not(:disabled) {
  opacity: 0.85;
}

.action-source {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border-color: var(--border-default);
}

.action-source:hover {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

/* ---- Responsive ---- */
@media (max-width: 768px) {
  .marketplace-content {
    padding: var(--spacing-sm);
  }

  .filters-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .search-wrapper {
    min-width: unset;
  }

  .plugin-grid {
    grid-template-columns: 1fr;
  }
}
</style>
