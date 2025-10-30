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
          @change="updateCacheConfig('enabled', $event.target.checked)"
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
          @input="updateCacheConfig('defaultTTL', parseInt($event.target.value))"
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
          @input="updateCacheConfig('maxCacheSizeMB', parseInt($event.target.value))"
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
        <div
          v-if="cacheActivity.length === 0"
          class="no-activity"
        >
          No cache activity recorded
        </div>
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
            <h5>{{ dbName.charAt(0).toUpperCase() + dbName.slice(1) }} (DB {{ dbInfo.database }})</h5>
            <div class="db-details">
              <span class="key-count">{{ dbInfo.key_count || 0 }} keys</span>
              <span class="memory-usage">{{ dbInfo.memory_usage || '0B' }}</span>
              <span :class="['connection-status', dbInfo.connected ? 'connected' : 'disconnected']">
                {{ dbInfo.connected ? 'Connected' : 'Disconnected' }}
              </span>
            </div>
          </div>
          <button
            @click="$emit('clear-redis-cache', dbName)"
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

</script>

<style scoped>
.settings-section {
  margin-bottom: 30px;
  background: #ffffff;
  border: 1px solid #e1e5e9;
  border-radius: 8px;
  padding: 24px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.settings-section h3 {
  margin: 0 0 20px 0;
  color: #2c3e50;
  font-weight: 600;
  font-size: 18px;
  border-bottom: 2px solid #3498db;
  padding-bottom: 8px;
}

.cache-unavailable-warning {
  background: #fff3cd;
  border: 1px solid #ffeaa7;
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
  color: #856404;
  font-size: 20px;
  margin-top: 2px;
}

.warning-text h4 {
  margin: 0 0 8px 0;
  color: #856404;
  font-size: 16px;
  font-weight: 600;
}

.warning-text p {
  margin: 0 0 8px 0;
  color: #856404;
  line-height: 1.4;
}

.warning-text small {
  color: #6c5014;
  font-size: 13px;
  line-height: 1.3;
}

.cache-configuration {
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 6px;
  padding: 20px;
  margin-bottom: 20px;
}

.cache-configuration h4 {
  margin: 0 0 15px 0;
  color: #495057;
  font-size: 16px;
  font-weight: 600;
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 12px 0;
  border-bottom: 1px solid #f0f0f0;
}

.setting-item:last-child {
  border-bottom: none;
  margin-bottom: 0;
}

.setting-item label {
  font-weight: 500;
  color: #34495e;
  flex: 1;
  margin-right: 16px;
  cursor: pointer;
}

.setting-item input {
  min-width: 150px;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
  transition: border-color 0.2s ease;
}

.setting-item input[type="checkbox"] {
  min-width: auto;
  width: 20px;
  height: 20px;
  cursor: pointer;
  accent-color: #007acc;
}

.setting-item input:focus {
  outline: none;
  border-color: #007acc;
  box-shadow: 0 0 0 2px rgba(0, 122, 204, 0.2);
}

.save-btn {
  background: #28a745;
  color: white;
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
  background: #218838;
}

.save-btn:disabled {
  background: #6c757d;
  cursor: not-allowed;
}

.cache-activity {
  margin-bottom: 20px;
}

.cache-activity h4 {
  margin: 0 0 15px 0;
  color: #495057;
  font-size: 16px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.small-btn {
  background: #007acc;
  color: white;
  border: none;
  padding: 4px 8px;
  border-radius: 3px;
  cursor: pointer;
  font-size: 12px;
}

.small-btn:hover {
  background: #005999;
}

.activity-log {
  background: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 6px;
  max-height: 200px;
  overflow-y: auto;
  padding: 10px;
}

.no-activity {
  color: #6c757d;
  font-style: italic;
  text-align: center;
  padding: 20px;
}

.activity-item {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid #e9ecef;
  font-size: 13px;
}

.activity-item:last-child {
  border-bottom: none;
}

.activity-item.info {
  color: #17a2b8;
}

.activity-item.warning {
  color: #ffc107;
}

.activity-item.error {
  color: #dc3545;
}

.cache-stats {
  margin-bottom: 20px;
}

.cache-stats h4 {
  margin: 0 0 15px 0;
  color: #495057;
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
  background: #e2e3e5;
  color: #6c757d;
}

.stats-error {
  background: #f8d7da;
  color: #721c24;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
}

.stat-item {
  background: #e9ecef;
  padding: 12px 16px;
  border-radius: 6px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.stat-item label {
  font-weight: 500;
  color: #495057;
}

.stat-item span {
  font-weight: 600;
  color: #007acc;
}

.cache-alternative-info {
  background: #d1ecf1;
  border: 1px solid #bee5eb;
  border-radius: 6px;
  padding: 20px;
  margin-top: 20px;
}

.cache-alternative-info h4 {
  margin: 0 0 16px 0;
  color: #0c5460;
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
  background: rgba(255, 255, 255, 0.7);
  border-radius: 4px;
}

.info-item i {
  color: #0c5460;
  font-size: 16px;
  margin-top: 2px;
}

.info-item div {
  color: #0c5460;
  line-height: 1.4;
}

.cache-section {
  margin-bottom: 30px;
  border: 1px solid #dee2e6;
  border-radius: 8px;
  overflow: hidden;
}

.cache-section h4 {
  margin: 0;
  padding: 16px 20px;
  background: #f8f9fa;
  border-bottom: 1px solid #dee2e6;
  color: #495057;
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
  background: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 6px;
  transition: border-color 0.2s ease;
}

.redis-db-item:hover {
  border-color: #007acc;
}

.db-info {
  flex: 1;
}

.db-info h5 {
  margin: 0 0 8px 0;
  color: #2c3e50;
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
  background: #e9ecef;
  color: #495057;
}

.connection-status.connected {
  background: #d4edda;
  color: #155724;
}

.connection-status.disconnected {
  background: #f8d7da;
  color: #721c24;
}

.clear-db-btn {
  background: #dc3545;
  color: white;
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
  background: #c82333;
}

.clear-db-btn:disabled {
  background: #6c757d;
  cursor: not-allowed;
}

.redis-all-control {
  padding: 20px;
  border-top: 1px solid #dee2e6;
  background: #f8f9fa;
  text-align: center;
}

.clear-all-redis-btn {
  background: #dc3545;
  color: white;
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
  background: #c82333;
}

.clear-all-redis-btn:disabled {
  background: #6c757d;
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
  color: white;
}

.clear-type-btn.knowledge {
  background: #6f42c1;
}

.clear-type-btn.knowledge:hover:not(:disabled) {
  background: #5a359e;
}

.clear-type-btn.llm {
  background: #20c997;
}

.clear-type-btn.llm:hover:not(:disabled) {
  background: #1ba085;
}

.clear-type-btn.config {
  background: #fd7e14;
}

.clear-type-btn.config:hover:not(:disabled) {
  background: #e8680d;
}

.clear-type-btn:disabled {
  background: #6c757d !important;
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
  background: #dc3545;
  color: white;
}

.clear-btn:hover:not(:disabled) {
  background: #c82333;
}

.clear-btn:disabled {
  background: #6c757d;
  cursor: not-allowed;
}

.refresh-btn,
.warmup-btn {
  background: #007acc;
  color: white;
}

.refresh-btn:hover,
.warmup-btn:hover:not(:disabled) {
  background: #005999;
}

.warmup-btn:disabled {
  background: #6c757d;
  cursor: not-allowed;
}

/* Dark theme support */
@media (prefers-color-scheme: dark) {
  .settings-section {
    background: #2d2d2d;
    border-color: #404040;
  }

  .settings-section h3 {
    color: #ffffff;
    border-bottom-color: #4fc3f7;
  }

  .cache-unavailable-warning {
    background: #664d03;
    border-color: #b08800;
  }

  .warning-content i,
  .warning-text h4,
  .warning-text p {
    color: #ffecb5;
  }

  .warning-text small {
    color: #ffeaa7;
  }

  .cache-configuration {
    background: #383838;
    border-color: #555;
  }

  .cache-configuration h4,
  .cache-activity h4,
  .cache-stats h4 {
    color: #ffffff;
  }

  .setting-item {
    border-bottom-color: #404040;
  }

  .setting-item label {
    color: #e0e0e0;
  }

  .setting-item input {
    background: #404040;
    border-color: #555;
    color: #ffffff;
  }

  .activity-log {
    background: #383838;
    border-color: #555;
  }

  .activity-item {
    border-bottom-color: #555;
  }

  .stat-item {
    background: #404040;
  }

  .stat-item label {
    color: #e0e0e0;
  }

  .cache-alternative-info {
    background: #184956;
    border-color: #2e8a9a;
  }

  .cache-alternative-info h4,
  .info-item i,
  .info-item div {
    color: #d1ecf1;
  }

  .info-item {
    background: rgba(255, 255, 255, 0.1);
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