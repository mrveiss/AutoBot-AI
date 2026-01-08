<template>
  <div v-if="isSettingsLoaded" class="settings-section">
    <h3>Cache Management</h3>

    <!-- Cache API Unavailable Warning -->
    <div v-if="!cacheApiAvailable" class="cache-unavailable-warning">
      <div class="warning-content">
        <i class="fas fa-exclamation-triangle"></i>
        <div class="warning-text">
          <h4>Cache API Unavailable</h4>
          <p>
            The cache management API is not available in the current backend configuration.
            Cache features are disabled to prevent errors.
          </p>
          <small>
            This is normal when using the fast backend for development.
            Cache functionality would be available in the full backend configuration.
          </small>
        </div>
      </div>
    </div>

    <!-- Cache Configuration -->
    <div v-if="cacheApiAvailable" class="cache-configuration">
      <h4>Cache Configuration</h4>
      <div class="setting-item">
        <label for="cache-enabled">Enable Caching</label>
        <input
          id="cache-enabled"
          type="checkbox"
          :checked="cacheConfig.enabled"
          @change="handleCheckboxChange('enabled')"
        />
      </div>
      <div class="setting-item">
        <label for="default-ttl">Default TTL (seconds)</label>
        <input
          id="default-ttl"
          type="number"
          :value="cacheConfig.defaultTTL"
          min="10"
          max="86400"
          @input="handleNumberInputChange('defaultTTL')"
        />
      </div>
      <div class="setting-item">
        <label for="max-cache-size">Max Cache Size (MB)</label>
        <input
          id="max-cache-size"
          type="number"
          :value="cacheConfig.maxCacheSizeMB"
          min="10"
          max="1000"
          @input="handleNumberInputChange('maxCacheSizeMB')"
        />
      </div>

      <button
        @click="$emit('save-cache-config')"
        class="save-btn"
        :disabled="isSaving"
      >
        <i class="fas fa-save"></i> Save Cache Configuration
      </button>
    </div>

    <!-- Cache Activity Log -->
    <div v-if="cacheApiAvailable" class="cache-activity">
      <h4>
        Cache Activity
        <button @click="$emit('refresh-cache-activity')" class="small-btn">
          <i class="fas fa-refresh"></i>
        </button>
      </h4>
      <div class="activity-log">
        <EmptyState
          v-if="cacheActivity.length === 0"
          icon="fas fa-chart-line"
          message="No cache activity recorded"
        />
        <div
          v-for="(activity, index) in cacheActivity"
          :key="activity.id || index"
          :class="['activity-item', activity.type || 'info']"
        >
          <span class="timestamp">{{ activity.timestamp }}</span>
          <span class="message">{{ activity.message || activity.operation }}</span>
        </div>
      </div>
    </div>

    <!-- Cache Statistics -->
    <div v-if="cacheApiAvailable && cacheStats" class="cache-stats">
      <h4>Cache Statistics</h4>
      <div v-if="cacheStats.status === 'unavailable'" class="stats-unavailable">
        <p>{{ cacheStats.message }}</p>
      </div>
      <div v-else-if="cacheStats.status === 'error'" class="stats-error">
        <p>{{ cacheStats.message }}</p>
      </div>
      <div v-else class="stats-grid">
        <div class="stat-item">
          <label>Total Items:</label>
          <span>{{ cacheStats.totalItems || 0 }}</span>
        </div>
        <div class="stat-item">
          <label>Memory Usage:</label>
          <span>{{ formatBytes(cacheStats.memoryUsage || 0) }}</span>
        </div>
        <div class="stat-item">
          <label>Hit Rate:</label>
          <span>{{ ((cacheStats.hitRate || 0) * 100).toFixed(1) }}%</span>
        </div>
        <div class="stat-item">
          <label>Expired Items:</label>
          <span>{{ cacheStats.expiredItems || 0 }}</span>
        </div>
      </div>
    </div>

    <!-- Redis Database Cache Controls -->
    <div v-if="cacheApiAvailable" class="cache-section">
      <h4>Redis Database Caches</h4>
      <div class="redis-cache-grid">
        <div v-for="(dbInfo, dbName) in redisStats" :key="dbName" class="redis-db-item">
          <div class="db-info">
            <h5>{{ formatDbName(dbName) }} (DB {{ dbInfo.database }})</h5>
            <div class="db-details">
              <span class="key-count">{{ dbInfo.key_count || 0 }} keys</span>
              <span class="memory-usage">{{ dbInfo.memory_usage || '0B' }}</span>
              <span :class="['connection-status', dbInfo.connected ? 'connected' : 'disconnected']">
                {{ dbInfo.connected ? 'Connected' : 'Disconnected' }}
              </span>
            </div>
          </div>
          <button
            @click="$emit('clear-redis-cache', String(dbName))"
            :disabled="isClearing || !dbInfo.connected"
            class="clear-db-btn"
          >
            <i class="fas fa-trash-alt"></i> Clear {{ dbName }}
          </button>
        </div>
      </div>

      <!-- Redis All Databases Control -->
      <div class="redis-all-control">
        <button
          @click="$emit('clear-redis-cache', 'all')"
          :disabled="isClearing"
          class="clear-all-redis-btn"
        >
          <i class="fas fa-database"></i> Clear All Redis Databases
        </button>
      </div>
    </div>

    <!-- Application Cache Controls -->
    <div v-if="cacheApiAvailable" class="cache-section">
      <h4>Application Caches</h4>
      <div class="app-cache-controls">
        <button
          @click="$emit('clear-cache-type', 'knowledge')"
          :disabled="isClearing"
          class="clear-type-btn knowledge"
        >
          <i class="fas fa-brain"></i> Clear Knowledge Cache
        </button>
        <button
          @click="$emit('clear-cache-type', 'llm')"
          :disabled="isClearing"
          class="clear-type-btn llm"
        >
          <i class="fas fa-robot"></i> Clear LLM Cache
        </button>
        <button
          @click="$emit('clear-cache-type', 'config')"
          :disabled="isClearing"
          class="clear-type-btn config"
        >
          <i class="fas fa-cog"></i> Clear Config Cache
        </button>
      </div>
    </div>

    <!-- General Cache Controls -->
    <div v-if="cacheApiAvailable" class="cache-controls">
      <button
        @click="$emit('refresh-cache-stats')"
        class="refresh-btn"
      >
        <i class="fas fa-refresh"></i> Refresh Stats
      </button>
      <button
        @click="$emit('warmup-caches')"
        :disabled="isClearing"
        class="warmup-btn"
      >
        <i class="fas fa-fire"></i> Warm Up Caches
      </button>
    </div>

    <!-- Alternative Cache Information (when API unavailable) -->
    <div v-if="!cacheApiAvailable" class="cache-alternative-info">
      <h4>Alternative Cache Information</h4>
      <div class="alternative-info-content">
        <div class="info-item">
          <i class="fas fa-info-circle"></i>
          <div>
            <strong>Browser Cache:</strong>
            Your browser is still caching API responses and static assets automatically.
          </div>
        </div>
        <div class="info-item">
          <i class="fas fa-database"></i>
          <div>
            <strong>Redis Cache:</strong>
            Redis databases are still operational for session storage and data persistence.
          </div>
        </div>
        <div class="info-item">
          <i class="fas fa-server"></i>
          <div>
            <strong>Full Backend:</strong>
            Switch to the full backend configuration to access advanced cache management features.
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { formatFileSize as formatBytes } from '@/utils/formatHelpers'
import EmptyState from '@/components/ui/EmptyState.vue'
interface CacheActivity {
  id: string
  timestamp: string
  message: string
  type: string
  operation?: string
}

interface RedisDbInfo {
  database: number
  key_count: number
  memory_usage: string
  connected: boolean
  error?: string
}

interface CacheStats {
  totalItems?: number
  memoryUsage?: number
  hitRate?: number
  expiredItems?: number
  redis_databases?: { [key: string]: RedisDbInfo }
  total_redis_keys?: number
  status?: string
  message?: string
}

interface CacheConfig {
  enabled: boolean
  defaultTTL: number
  maxCacheSizeMB: number
}

interface Props {
  isSettingsLoaded: boolean
  cacheConfig: CacheConfig
  cacheActivity: CacheActivity[]
  cacheStats: CacheStats | null
  isSaving: boolean
  isClearing: boolean
  cacheApiAvailable: boolean
}

interface Emits {
  (e: 'cache-config-changed', key: string, value: any): void
  (e: 'save-cache-config'): void
  (e: 'refresh-cache-activity'): void
  (e: 'refresh-cache-stats'): void
  (e: 'clear-cache', type: 'all' | 'expired'): void
  (e: 'clear-redis-cache', database: string): void
  (e: 'clear-cache-type', cacheType: string): void
  (e: 'warmup-caches'): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const redisStats = computed(() => props.cacheStats?.redis_databases || {})

const updateCacheConfig = (key: string, value: any) => {
  emit('cache-config-changed', key, value)
}

// Issue #156 Fix: Typed event handlers to replace inline $event.target usage
const handleCheckboxChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  updateCacheConfig(key, target.checked)
}

const handleNumberInputChange = (key: string) => (event: Event) => {
  const target = event.target as HTMLInputElement
  updateCacheConfig(key, parseInt(target.value))
}

// Issue #156 Fix: Helper to format database name with proper typing
const formatDbName = (dbName: string | number): string => {
  const nameStr = String(dbName)
  return nameStr.charAt(0).toUpperCase() + nameStr.slice(1)
}

</script>

<style scoped>
/* Issue #704: Migrated to CSS design tokens */

.settings-section {
  margin-bottom: 30px;
  background: var(--bg-primary);
  border: 1px solid var(--border-default);
  border-radius: 8px;
  padding: 24px;
  box-shadow: var(--shadow-sm);
}

.settings-section h3 {
  margin: 0 0 20px 0;
  color: var(--text-primary);
  font-weight: 600;
  font-size: 18px;
  border-bottom: 2px solid var(--color-primary);
  padding-bottom: 8px;
}

.cache-unavailable-warning {
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning);
  border-radius: 6px;
  padding: 16px;
  margin-bottom: 20px;
}

.warning-content {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.warning-content i {
  color: var(--color-warning-text);
  font-size: 20px;
  margin-top: 2px;
}

.warning-text h4 {
  margin: 0 0 8px 0;
  color: var(--color-warning-text);
  font-size: 16px;
  font-weight: 600;
}

.warning-text p {
  margin: 0 0 8px 0;
  color: var(--color-warning-text);
  line-height: 1.4;
}

.warning-text small {
  color: var(--color-warning-text);
  font-size: 13px;
  line-height: 1.3;
  opacity: 0.85;
}

.cache-configuration {
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: 6px;
  padding: 20px;
  margin-bottom: 20px;
}

.cache-configuration h4 {
  margin: 0 0 15px 0;
  color: var(--text-secondary);
  font-size: 16px;
  font-weight: 600;
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 12px 0;
  border-bottom: 1px solid var(--border-subtle);
}

.setting-item:last-child {
  border-bottom: none;
  margin-bottom: 0;
}

.setting-item label {
  font-weight: 500;
  color: var(--text-secondary);
  flex: 1;
  margin-right: 16px;
  cursor: pointer;
}

.setting-item input {
  min-width: 150px;
  padding: 8px 12px;
  border: 1px solid var(--border-default);
  border-radius: 4px;
  font-size: 14px;
  transition: border-color 0.2s ease;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.setting-item input[type="checkbox"] {
  min-width: auto;
  width: 20px;
  height: 20px;
  cursor: pointer;
  accent-color: var(--color-primary);
}

.setting-item input:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: 0 0 0 2px var(--color-primary-alpha);
}

.save-btn {
  background: var(--color-success);
  color: var(--text-on-primary);
  border: none;
  padding: 10px 20px;
  border-radius: 5px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: background-color 0.2s ease;
  display: flex;
  align-items: center;
  gap: 8px;
}

.save-btn:hover:not(:disabled) {
  background: var(--color-success-hover);
}

.save-btn:disabled {
  background: var(--text-tertiary);
  cursor: not-allowed;
}

.cache-activity {
  margin-bottom: 20px;
}

.cache-activity h4 {
  margin: 0 0 15px 0;
  color: var(--text-secondary);
  font-size: 16px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.small-btn {
  background: var(--color-primary);
  color: var(--text-on-primary);
  border: none;
  padding: 4px 8px;
  border-radius: 3px;
  cursor: pointer;
  font-size: 12px;
}

.small-btn:hover {
  background: var(--color-primary-hover);
}

.activity-log {
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: 6px;
  max-height: 200px;
  overflow-y: auto;
  padding: 10px;
}

.activity-item {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid var(--border-light);
  font-size: 13px;
}

.activity-item:last-child {
  border-bottom: none;
}

.activity-item.info {
  color: var(--color-info);
}

.activity-item.warning {
  color: var(--color-warning);
}

.activity-item.error {
  color: var(--color-danger);
}

.cache-stats {
  margin-bottom: 20px;
}

.cache-stats h4 {
  margin: 0 0 15px 0;
  color: var(--text-secondary);
  font-size: 16px;
  font-weight: 600;
}

.stats-unavailable,
.stats-error {
  padding: 16px;
  border-radius: 6px;
  text-align: center;
}

.stats-unavailable {
  background: var(--bg-tertiary);
  color: var(--text-tertiary);
}

.stats-error {
  background: var(--color-danger-bg);
  color: var(--color-danger-text);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
}

.stat-item {
  background: var(--bg-tertiary);
  padding: 12px 16px;
  border-radius: 6px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.stat-item label {
  font-weight: 500;
  color: var(--text-secondary);
}

.stat-item span {
  font-weight: 600;
  color: var(--color-primary);
}

.cache-alternative-info {
  background: var(--color-info-bg);
  border: 1px solid var(--color-info-border);
  border-radius: 6px;
  padding: 20px;
  margin-top: 20px;
}

.cache-alternative-info h4 {
  margin: 0 0 16px 0;
  color: var(--color-info-text);
  font-size: 16px;
  font-weight: 600;
}

.alternative-info-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.info-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  background: var(--bg-primary-alpha);
  border-radius: 4px;
}

.info-item i {
  color: var(--color-info-text);
  font-size: 16px;
  margin-top: 2px;
}

.info-item div {
  color: var(--color-info-text);
  line-height: 1.4;
}

.cache-section {
  margin-bottom: 30px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  overflow: hidden;
}

.cache-section h4 {
  margin: 0;
  padding: 16px 20px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border-light);
  color: var(--text-secondary);
  font-size: 16px;
  font-weight: 600;
}

.redis-cache-grid {
  padding: 20px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 16px;
}

.redis-db-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: 6px;
  transition: border-color 0.2s ease;
}

.redis-db-item:hover {
  border-color: var(--color-primary);
}

.db-info {
  flex: 1;
}

.db-info h5 {
  margin: 0 0 8px 0;
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 600;
}

.db-details {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
}

.db-details span {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 4px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.connection-status.connected {
  background: var(--color-success-bg);
  color: var(--color-success-text);
}

.connection-status.disconnected {
  background: var(--color-danger-bg);
  color: var(--color-danger-text);
}

.clear-db-btn {
  background: var(--color-danger);
  color: var(--text-on-primary);
  border: none;
  padding: 8px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 4px;
  transition: background-color 0.2s ease;
}

.clear-db-btn:hover:not(:disabled) {
  background: var(--color-danger-hover);
}

.clear-db-btn:disabled {
  background: var(--text-tertiary);
  cursor: not-allowed;
}

.redis-all-control {
  padding: 20px;
  border-top: 1px solid var(--border-light);
  background: var(--bg-secondary);
  text-align: center;
}

.clear-all-redis-btn {
  background: var(--color-danger);
  color: var(--text-on-primary);
  border: none;
  padding: 12px 24px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  transition: background-color 0.2s ease;
}

.clear-all-redis-btn:hover:not(:disabled) {
  background: var(--color-danger-hover);
}

.clear-all-redis-btn:disabled {
  background: var(--text-tertiary);
  cursor: not-allowed;
}

.app-cache-controls {
  padding: 20px;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.clear-type-btn {
  border: none;
  padding: 12px 20px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: all 0.2s ease;
  color: var(--text-on-primary);
}

.clear-type-btn.knowledge {
  background: var(--color-purple);
}

.clear-type-btn.knowledge:hover:not(:disabled) {
  background: var(--color-purple-hover);
}

.clear-type-btn.llm {
  background: var(--color-teal);
}

.clear-type-btn.llm:hover:not(:disabled) {
  background: var(--color-teal-hover);
}

.clear-type-btn.config {
  background: var(--color-orange);
}

.clear-type-btn.config:hover:not(:disabled) {
  background: var(--color-orange-hover);
}

.clear-type-btn:disabled {
  background: var(--text-tertiary) !important;
  cursor: not-allowed;
}

.cache-controls {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  padding: 0 20px 20px 20px;
}

.clear-btn,
.refresh-btn {
  border: none;
  padding: 10px 16px;
  border-radius: 5px;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: background-color 0.2s ease;
  display: flex;
  align-items: center;
  gap: 8px;
}

.clear-btn {
  background: var(--color-danger);
  color: var(--text-on-primary);
}

.clear-btn:hover:not(:disabled) {
  background: var(--color-danger-hover);
}

.clear-btn:disabled {
  background: var(--text-tertiary);
  cursor: not-allowed;
}

.refresh-btn,
.warmup-btn {
  background: var(--color-primary);
  color: var(--text-on-primary);
}

.refresh-btn:hover,
.warmup-btn:hover:not(:disabled) {
  background: var(--color-primary-hover);
}

.warmup-btn:disabled {
  background: var(--text-tertiary);
  cursor: not-allowed;
}

/* Dark theme support - tokens automatically apply correct values */
@media (prefers-color-scheme: dark) {
  .settings-section {
    background: var(--bg-primary);
    border-color: var(--border-default);
  }

  .settings-section h3 {
    color: var(--text-primary);
    border-bottom-color: var(--color-primary);
  }

  .cache-unavailable-warning {
    background: var(--color-warning-bg);
    border-color: var(--color-warning);
  }

  .warning-content i,
  .warning-text h4,
  .warning-text p {
    color: var(--color-warning-text);
  }

  .warning-text small {
    color: var(--color-warning-text);
  }

  .cache-configuration {
    background: var(--bg-secondary);
    border-color: var(--border-default);
  }

  .cache-configuration h4,
  .cache-activity h4,
  .cache-stats h4 {
    color: var(--text-primary);
  }

  .setting-item {
    border-bottom-color: var(--border-default);
  }

  .setting-item label {
    color: var(--text-secondary);
  }

  .setting-item input {
    background: var(--bg-tertiary);
    border-color: var(--border-default);
    color: var(--text-primary);
  }

  .activity-log {
    background: var(--bg-secondary);
    border-color: var(--border-default);
  }

  .activity-item {
    border-bottom-color: var(--border-default);
  }

  .stat-item {
    background: var(--bg-tertiary);
  }

  .stat-item label {
    color: var(--text-secondary);
  }

  .cache-alternative-info {
    background: var(--color-info-bg);
    border-color: var(--color-info-border);
  }

  .cache-alternative-info h4,
  .info-item i,
  .info-item div {
    color: var(--color-info-text);
  }

  .info-item {
    background: var(--bg-primary-alpha);
  }
}

/* Mobile responsive */
@media (max-width: 768px) {
  .settings-section {
    padding: 16px;
    margin-bottom: 20px;
  }

  .setting-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .setting-item label {
    margin-right: 0;
    margin-bottom: 4px;
  }

  .setting-item input {
    min-width: auto;
    width: 100%;
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }

  .cache-controls {
    justify-content: stretch;
  }

  .clear-btn,
  .refresh-btn {
    flex: 1;
    justify-content: center;
  }

  .alternative-info-content {
    gap: 8px;
  }

  .info-item {
    padding: 8px;
  }
}
</style>
