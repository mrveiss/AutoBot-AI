<template>
  <div class="plugins-view view-container">
    <div class="plugins-content">
      <!-- Header -->
      <div class="plugins-header">
        <div class="header-content">
          <h1 class="page-title">Plugin Manager</h1>
          <p class="page-subtitle">Browse, install, and manage AutoBot plugins</p>
        </div>
        <button class="btn-refresh" :disabled="loading" @click="refresh" title="Refresh">
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

      <!-- Tabs -->
      <div class="tab-bar">
        <button
          class="tab-btn"
          :class="{ active: activeTab === 'installed' }"
          @click="activeTab = 'installed'"
        >
          <svg class="tab-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"
            />
          </svg>
          Installed
          <span class="tab-badge">{{ plugins.length }}</span>
        </button>
        <button
          class="tab-btn"
          :class="{ active: activeTab === 'discover' }"
          @click="switchToDiscover"
        >
          <svg class="tab-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
          Discover
          <span class="tab-badge">{{ discovered.length }}</span>
        </button>
      </div>

      <!-- Installed Tab -->
      <div v-if="activeTab === 'installed'">
        <div v-if="loading" class="loading-state">
          <svg class="spinner" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path
              class="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
          <span>Loading plugins...</span>
        </div>

        <div v-else-if="plugins.length === 0" class="empty-state">
          <svg class="empty-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="1.5"
              d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
            />
          </svg>
          <p class="empty-title">No plugins loaded</p>
          <p class="empty-subtitle">
            Switch to the <strong>Discover</strong> tab to browse and install available plugins.
          </p>
        </div>

        <div v-else class="plugin-grid">
          <div
            v-for="plugin in plugins"
            :key="plugin.name"
            class="plugin-card"
            @click="openDetail(plugin)"
          >
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
              <span :class="['status-badge', `status-${plugin.status}`]">{{ plugin.status }}</span>
            </div>

            <div class="card-body">
              <h3 class="plugin-name">{{ plugin.display_name }}</h3>
              <p class="plugin-desc">{{ plugin.description }}</p>
              <p class="plugin-meta">v{{ plugin.version }} · {{ plugin.author }}</p>
              <div v-if="plugin.hooks.length > 0" class="hooks-list">
                <span v-for="hook in plugin.hooks.slice(0, 3)" :key="hook" class="hook-tag">
                  {{ hook }}
                </span>
                <span v-if="plugin.hooks.length > 3" class="hook-tag hook-more">
                  +{{ plugin.hooks.length - 3 }}
                </span>
              </div>
            </div>

            <div class="card-actions" @click.stop>
              <button
                v-if="plugin.status === 'disabled' || plugin.status === 'loaded'"
                class="action-btn action-enable"
                :disabled="actionLoading[plugin.name]"
                @click="handleEnable(plugin.name)"
                title="Enable"
              >
                Enable
              </button>
              <button
                v-else-if="plugin.status === 'enabled'"
                class="action-btn action-disable"
                :disabled="actionLoading[plugin.name]"
                @click="handleDisable(plugin.name)"
                title="Disable"
              >
                Disable
              </button>
              <button
                class="action-btn action-reload"
                :disabled="actionLoading[plugin.name]"
                @click="handleReload(plugin.name)"
                title="Reload"
              >
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" class="btn-icon">
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                  />
                </svg>
              </button>
              <button
                class="action-btn action-unload"
                :disabled="actionLoading[plugin.name]"
                @click="handleUnload(plugin.name)"
                title="Unload"
              >
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" class="btn-icon">
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                  />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- Discover Tab -->
      <div v-if="activeTab === 'discover'">
        <div v-if="loading" class="loading-state">
          <svg class="spinner" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
            <path
              class="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
          <span>Discovering plugins...</span>
        </div>

        <div v-else-if="uninstalledPlugins.length === 0" class="empty-state">
          <svg class="empty-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="1.5"
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
          <p class="empty-title">No new plugins found</p>
          <p class="empty-subtitle">
            All discovered plugins are already installed, or no plugin directories are configured.
          </p>
        </div>

        <div v-else class="plugin-grid">
          <div
            v-for="manifest in uninstalledPlugins"
            :key="manifest.name"
            class="plugin-card discover-card"
          >
            <div class="card-header">
              <div class="plugin-icon plugin-icon-discover">
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M11 4a2 2 0 114 0v1a1 1 0 001 1h3a1 1 0 011 1v3a1 1 0 01-1 1h-1a2 2 0 100 4h1a1 1 0 011 1v3a1 1 0 01-1 1h-3a1 1 0 01-1-1v-1a2 2 0 10-4 0v1a1 1 0 01-1 1H7a1 1 0 01-1-1v-3a1 1 0 00-1-1H4a2 2 0 110-4h1a1 1 0 001-1V7a1 1 0 011-1h3a1 1 0 001-1V4z"
                  />
                </svg>
              </div>
              <span class="status-badge status-unloaded">available</span>
            </div>

            <div class="card-body">
              <h3 class="plugin-name">{{ manifest.display_name }}</h3>
              <p class="plugin-desc">{{ manifest.description }}</p>
              <p class="plugin-meta">v{{ manifest.version }} · {{ manifest.author }}</p>
              <div v-if="manifest.dependencies.length > 0" class="deps-list">
                <span class="deps-label">Requires:</span>
                <span v-for="dep in manifest.dependencies" :key="dep" class="hook-tag">
                  {{ dep }}
                </span>
              </div>
            </div>

            <div class="card-actions">
              <button
                class="action-btn action-install"
                :disabled="actionLoading[manifest.name]"
                @click="handleLoad(manifest.name)"
              >
                <svg fill="none" stroke="currentColor" viewBox="0 0 24 24" class="btn-icon">
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                  />
                </svg>
                Install
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Plugin Detail Modal -->
    <div v-if="selectedPlugin" class="modal-overlay" @click.self="closeDetail">
      <div class="modal-panel" role="dialog" aria-modal="true" aria-label="Plugin details">
        <div class="modal-header">
          <h2 class="modal-title">{{ selectedPlugin.display_name }}</h2>
          <button class="modal-close" @click="closeDetail" aria-label="Close">
            <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div class="modal-body">
          <!-- Info Grid -->
          <dl class="info-grid">
            <dt>Name</dt><dd>{{ selectedPlugin.name }}</dd>
            <dt>Version</dt><dd>{{ selectedPlugin.version }}</dd>
            <dt>Author</dt><dd>{{ selectedPlugin.author }}</dd>
            <dt>Status</dt>
            <dd>
              <span :class="['status-badge', `status-${selectedPlugin.status}`]">
                {{ selectedPlugin.status }}
              </span>
            </dd>
            <dt v-if="selectedPlugin.hooks.length > 0">Hooks</dt>
            <dd v-if="selectedPlugin.hooks.length > 0">
              <span v-for="hook in selectedPlugin.hooks" :key="hook" class="hook-tag">
                {{ hook }}
              </span>
            </dd>
          </dl>

          <p class="modal-desc">{{ selectedPlugin.description }}</p>

          <!-- Config Editor -->
          <div class="config-section">
            <div class="config-header">
              <h3 class="config-title">Configuration</h3>
              <button
                v-if="!editingConfig"
                class="config-edit-btn"
                @click="startEditConfig"
              >
                Edit
              </button>
            </div>

            <div v-if="configLoading" class="config-loading">Loading config...</div>

            <div v-else-if="editingConfig">
              <textarea
                v-model="configText"
                class="config-editor"
                rows="8"
                spellcheck="false"
                aria-label="Plugin configuration JSON"
              />
              <div v-if="configError" class="config-error">{{ configError }}</div>
              <div class="config-actions">
                <button class="action-btn action-enable" @click="saveConfig">Save</button>
                <button class="action-btn action-disable" @click="cancelEditConfig">Cancel</button>
              </div>
            </div>

            <pre v-else-if="pluginConfig !== null" class="config-display">{{ JSON.stringify(pluginConfig, null, 2) }}</pre>
            <p v-else class="config-empty">No configuration stored for this plugin.</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// Issue #929 - Plugin Manager UI
import { ref, computed, onMounted } from 'vue'
import { usePlugins, type PluginInfo, type PluginManifest } from '@/composables/usePlugins'

const {
  plugins,
  discovered,
  loading,
  error,
  listPlugins,
  discoverPlugins,
  loadPlugin,
  unloadPlugin,
  reloadPlugin,
  enablePlugin,
  disablePlugin,
  getPluginConfig,
  updatePluginConfig,
} = usePlugins()

const activeTab = ref<'installed' | 'discover'>('installed')
const actionLoading = ref<Record<string, boolean>>({})

// Modal state
const selectedPlugin = ref<PluginInfo | null>(null)
const pluginConfig = ref<Record<string, unknown> | null>(null)
const configLoading = ref(false)
const editingConfig = ref(false)
const configText = ref('')
const configError = ref('')

// Plugins that are in discover but not already in installed list
const uninstalledPlugins = computed<PluginManifest[]>(() => {
  const loadedNames = new Set(plugins.value.map((p) => p.name))
  return discovered.value.filter((m) => !loadedNames.has(m.name))
})

async function refresh() {
  await listPlugins()
}

async function switchToDiscover() {
  activeTab.value = 'discover'
  if (discovered.value.length === 0) {
    await discoverPlugins()
  }
}

async function handleLoad(name: string) {
  actionLoading.value[name] = true
  try {
    await loadPlugin(name)
    await discoverPlugins()
    activeTab.value = 'installed'
  } finally {
    actionLoading.value[name] = false
  }
}

async function handleUnload(name: string) {
  actionLoading.value[name] = true
  try {
    await unloadPlugin(name)
  } finally {
    actionLoading.value[name] = false
  }
}

async function handleReload(name: string) {
  actionLoading.value[name] = true
  try {
    await reloadPlugin(name)
  } finally {
    actionLoading.value[name] = false
  }
}

async function handleEnable(name: string) {
  actionLoading.value[name] = true
  try {
    await enablePlugin(name)
  } finally {
    actionLoading.value[name] = false
  }
}

async function handleDisable(name: string) {
  actionLoading.value[name] = true
  try {
    await disablePlugin(name)
  } finally {
    actionLoading.value[name] = false
  }
}

async function openDetail(plugin: PluginInfo) {
  selectedPlugin.value = plugin
  editingConfig.value = false
  configError.value = ''
  configLoading.value = true
  pluginConfig.value = await getPluginConfig(plugin.name)
  configLoading.value = false
}

function closeDetail() {
  selectedPlugin.value = null
  editingConfig.value = false
  configError.value = ''
}

function startEditConfig() {
  configText.value = JSON.stringify(pluginConfig.value ?? {}, null, 2)
  configError.value = ''
  editingConfig.value = true
}

function cancelEditConfig() {
  editingConfig.value = false
  configError.value = ''
}

async function saveConfig() {
  if (!selectedPlugin.value) return
  configError.value = ''
  let parsed: Record<string, unknown>
  try {
    parsed = JSON.parse(configText.value)
  } catch {
    configError.value = 'Invalid JSON — please fix before saving.'
    return
  }
  const ok = await updatePluginConfig(selectedPlugin.value.name, parsed)
  if (ok) {
    pluginConfig.value = parsed
    editingConfig.value = false
  } else {
    configError.value = error.value ?? 'Failed to save configuration.'
  }
}

onMounted(async () => {
  await listPlugins()
})
</script>

<style scoped>
/* ============================================
 * PLUGINS VIEW — Design Tokens
 * Issue #929 — Plugin Manager UI
 * ============================================ */

.plugins-content {
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
  padding: var(--spacing-md) var(--spacing-md) var(--spacing-xl);
}

/* ---- Header ---- */
.plugins-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: var(--spacing-xl);
}

.page-title {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 var(--spacing-xs) 0;
}

.page-subtitle {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0;
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
  gap: var(--spacing-xs);
  transition: background var(--duration-150) var(--ease-in-out), color var(--duration-150) var(--ease-in-out);
}

.btn-refresh:hover:not(:disabled) {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.btn-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.refresh-icon {
  width: 16px;
  height: 16px;
}

.refresh-icon.spinning {
  animation: spin 1s linear infinite;
}

/* ---- Error Banner ---- */
.error-banner {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  border-radius: var(--radius-md);
  padding: var(--spacing-sm) var(--spacing-md);
  margin-bottom: var(--spacing-lg);
  color: var(--color-error);
  font-size: var(--text-sm);
}

.error-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

/* ---- Tabs ---- */
.tab-bar {
  display: flex;
  gap: var(--spacing-xs);
  border-bottom: 1px solid var(--border-default);
  margin-bottom: var(--spacing-xl);
}

.tab-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-secondary);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  transition: color var(--duration-150) var(--ease-in-out), border-color var(--duration-150) var(--ease-in-out);
  margin-bottom: -1px;
}

.tab-btn:hover {
  color: var(--text-primary);
}

.tab-btn.active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
}

.tab-icon {
  width: 16px;
  height: 16px;
}

.tab-badge {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 10px;
  min-width: 20px;
  text-align: center;
}

.tab-btn.active .tab-badge {
  background: var(--color-primary);
  color: white;
}

/* ---- Loading / Empty States ---- */
.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--spacing-2xl) var(--spacing-lg);
  color: var(--text-secondary);
  gap: var(--spacing-md);
}

.spinner {
  width: 32px;
  height: 32px;
  animation: spin 1s linear infinite;
  color: var(--color-primary);
}

.empty-icon {
  width: 48px;
  height: 48px;
  opacity: 0.4;
}

.empty-title {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.empty-subtitle {
  font-size: var(--text-sm);
  text-align: center;
  max-width: 380px;
  margin: 0;
}

/* ---- Plugin Grid ---- */
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
  cursor: pointer;
  transition: border-color var(--duration-150) var(--ease-in-out), box-shadow var(--duration-150) var(--ease-in-out);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.plugin-card:hover {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 1px var(--color-primary), 0 2px 8px rgba(0, 0, 0, 0.15);
}

.discover-card {
  cursor: default;
}

.discover-card:hover {
  border-color: var(--border-default);
  box-shadow: none;
  opacity: 1;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.plugin-icon {
  width: 36px;
  height: 36px;
  background: var(--color-primary);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  flex-shrink: 0;
}

.plugin-icon svg {
  width: 20px;
  height: 20px;
}

.plugin-icon-discover {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

/* ---- Status Badges ---- */
.status-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 10px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.status-enabled {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.status-loaded {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.status-disabled {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.status-unloaded {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.status-error {
  background: var(--color-error-bg);
  color: var(--color-error);
}

/* ---- Card Body ---- */
.card-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.plugin-name {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.plugin-desc {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0;
  line-height: var(--leading-relaxed);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.plugin-meta {
  font-size: 11px;
  color: var(--text-tertiary, var(--text-secondary));
  margin: 0;
}

.hooks-list,
.deps-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.deps-label {
  font-size: 11px;
  color: var(--text-secondary);
}

.hook-tag {
  font-size: 11px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  padding: 1px 6px;
  border-radius: 4px;
  border: 1px solid var(--border-default);
}

.hook-more {
  background: transparent;
}

/* ---- Card Actions ---- */
.card-actions {
  display: flex;
  gap: var(--spacing-xs);
  flex-wrap: wrap;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  font-weight: 500;
  cursor: pointer;
  border: 1px solid transparent;
  transition: background var(--duration-150) var(--ease-in-out), opacity var(--duration-150) var(--ease-in-out);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-btn .btn-icon {
  width: 14px;
  height: 14px;
}

.action-enable {
  background: var(--color-success-bg);
  color: var(--color-success);
  border-color: var(--color-success-border, rgba(34, 197, 94, 0.3));
}

.action-enable:hover:not(:disabled) {
  opacity: 0.85;
}

.action-disable {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border-color: var(--border-default);
}

.action-disable:hover:not(:disabled) {
  opacity: 0.85;
}

.action-reload {
  background: var(--color-info-bg);
  color: var(--color-info);
  border-color: var(--color-info-border, rgba(59, 130, 246, 0.3));
  padding: 4px 8px;
}

.action-reload:hover:not(:disabled) {
  opacity: 0.85;
}

.action-unload {
  background: var(--color-error-bg);
  color: var(--color-error);
  border-color: var(--color-error-border);
  padding: 4px 8px;
}

.action-unload:hover:not(:disabled) {
  opacity: 0.85;
}

.action-install {
  background: var(--color-primary);
  color: white;
  border-color: var(--color-primary);
}

.action-install:hover:not(:disabled) {
  opacity: 0.9;
}

/* ---- Modal ---- */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: var(--z-modal);
  padding: var(--spacing-md);
}

.modal-panel {
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  width: 100%;
  max-width: 560px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.4);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--spacing-lg) var(--spacing-xl);
  border-bottom: 1px solid var(--border-default);
}

.modal-title {
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--text-primary);
  margin: 0;
}

.modal-close {
  background: transparent;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: var(--spacing-xs);
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  transition: color var(--duration-150) var(--ease-in-out);
}

.modal-close:hover {
  color: var(--text-primary);
}

.modal-close svg {
  width: 20px;
  height: 20px;
}

.modal-body {
  padding: var(--spacing-xl);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.info-grid {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: var(--spacing-xs) var(--spacing-md);
  font-size: var(--text-sm);
  margin: 0;
}

.info-grid dt {
  color: var(--text-secondary);
  font-weight: 500;
}

.info-grid dd {
  color: var(--text-primary);
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.modal-desc {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: var(--leading-relaxed);
  margin: 0;
}

/* ---- Config Editor ---- */
.config-section {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.config-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.config-title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.config-edit-btn {
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-sm);
  padding: 2px 10px;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  cursor: pointer;
  transition: background var(--duration-150) var(--ease-in-out), color var(--duration-150) var(--ease-in-out);
}

.config-edit-btn:hover {
  background: var(--bg-tertiary);
  color: var(--text-primary);
}

.config-loading {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  padding: var(--spacing-sm);
}

.config-display {
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  font-size: 12px;
  font-family: var(--font-mono);
  color: var(--text-primary);
  overflow-x: auto;
  white-space: pre-wrap;
  margin: 0;
}

.config-editor {
  width: 100%;
  background: var(--bg-secondary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  padding: var(--spacing-md);
  font-size: 12px;
  font-family: var(--font-mono);
  color: var(--text-primary);
  resize: vertical;
  box-sizing: border-box;
}

.config-editor:focus {
  outline: none;
  border-color: var(--color-primary);
}

.config-error {
  font-size: var(--text-sm);
  color: var(--color-error);
  padding: var(--spacing-xs) 0;
}

.config-actions {
  display: flex;
  gap: var(--spacing-xs);
}

.config-empty {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0;
  font-style: italic;
}

/* ---- Animations ---- */
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* ---- Responsive ---- */
@media (max-width: 768px) {
  .plugins-content {
    padding: var(--spacing-sm);
  }

  .plugin-grid {
    grid-template-columns: 1fr;
  }

  .modal-panel {
    max-height: 95vh;
  }
}
</style>
