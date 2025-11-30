<template>
  <div class="log-viewer">
    <!-- Screen reader status announcements -->
    <div role="status" aria-live="polite" aria-atomic="true" class="sr-only">
      {{ screenReaderStatus }}
    </div>

    <div class="log-controls">
      <div class="log-selector">
        <label for="log-source-select">Log Source:</label>
        <select id="log-source-select" v-model="selectedSource" @change="loadLog">
          <option value="">Select a log source...</option>
          <option value="unified">🔗 All Sources (Unified)</option>
          <optgroup label="📄 File Logs">
            <option v-for="file in logSources.file_logs" :key="file.name" :value="`file:${file.name}`">
              {{ file.name }} ({{ file.size_mb }}MB)
            </option>
          </optgroup>
          <optgroup label="🐳 Docker Containers">
            <option v-for="container in logSources.container_logs" :key="container.name" :value="`container:${container.name}`">
              {{ container.name }} ({{ container.status }})
            </option>
          </optgroup>
        </select>
      </div>
      
      <div class="log-filters">
        <label for="log-level-select" class="sr-only">Log Level</label>
        <select id="log-level-select" v-model="selectedLevel" @change="loadLog">
          <option value="">All Levels</option>
          <option value="DEBUG">🐛 Debug</option>
          <option value="INFO">ℹ️ Info</option>
          <option value="WARNING">⚠️ Warning</option>
          <option value="ERROR">❌ Error</option>
          <option value="CRITICAL">🚨 Critical</option>
        </select>

        <label for="max-lines-input" class="sr-only">Maximum lines to display</label>
        <input
          id="max-lines-input"
          type="number"
          v-model.number="maxLines"
          @change="loadLog"
          min="10"
          max="1000"
          step="10"
          placeholder="Lines"
          aria-label="Maximum number of log lines to display"
        />
      </div>

      <div class="log-actions">
        <button @click="refreshFiles" :disabled="loading" aria-label="Refresh log sources">
          <i class="fas fa-sync-alt" :class="{ 'fa-spin': loading }" aria-hidden="true"></i> Refresh
        </button>
        <button @click="toggleAutoScroll" :class="{ active: autoScroll }" aria-label="Toggle auto scroll">
          <i class="fas fa-arrow-down" aria-hidden="true"></i> Auto Scroll
        </button>
        <button @click="searchLogs" v-if="selectedSource" aria-label="Search logs">
          <i class="fas fa-search" aria-hidden="true"></i> Search
        </button>
      </div>
    </div>

    <div class="search-panel" v-if="showSearch">
      <label for="log-search-input" class="sr-only">Search in logs</label>
      <input
        id="log-search-input"
        v-model="searchQuery"
        @keyup.enter="performSearch"
        placeholder="Search in logs..."
        class="search-input"
        aria-label="Search query"
      />
      <button @click="performSearch" :disabled="!searchQuery" aria-label="Perform search">Search</button>
      <button @click="showSearch = false" aria-label="Cancel search">Cancel</button>
    </div>

    <div
      class="log-content"
      ref="logContentRef"
      role="log"
      aria-live="polite"
      aria-atomic="false"
      aria-relevant="additions"
      :aria-label="`Log output from ${selectedSource || 'no source'}`"
    >
      <div v-if="loading" class="loading">
        <i class="fas fa-spinner fa-spin" aria-hidden="true"></i> Loading...
      </div>

      <div v-else-if="error" class="error" role="alert">
        <i class="fas fa-exclamation-triangle" aria-hidden="true"></i> {{ error }}
      </div>

      <EmptyState
        v-else-if="!selectedSource"
        icon="fas fa-file-alt"
        message="Select a log source to view"
        compact
      />

      <pre v-else class="log-text">{{ logContent }}</pre>
    </div>

    <div class="log-status">
      <span v-if="selectedSource">
        Lines: {{ lineCount }} | Source: {{ selectedSource }} | Updated: {{ lastUpdated }}
      </span>
      <span v-else>No source selected</span>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useApiService } from '@/composables/useApiService'
import { useAsyncOperation } from '@/composables/useAsyncOperation'
import { useWebSocket } from '@/composables/useWebSocket'
import EmptyState from '@/components/ui/EmptyState.vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('LogViewer')

export default {
  name: 'LogViewer',
  components: {
    EmptyState
  },
  setup() {
    const apiService = useApiService()
    // Use composable for async operations
    const { execute: refreshFilesOp, loading, error } = useAsyncOperation()
    const { execute: loadLogOp, loading: loadingLog } = useAsyncOperation()

    const logSources = ref({ file_logs: [], container_logs: [], total_sources: 0 })
    const selectedSource = ref('')
    const selectedLevel = ref('')
    const maxLines = ref(100)
    const logContent = ref('')
    const logs = ref([])
    const autoScroll = ref(true)
    const showSearch = ref(false)
    const searchQuery = ref('')
    const lineCount = ref(0)
    const logContentRef = ref(null)
    const lastUpdated = ref('')

    // Screen reader announcements
    const screenReaderStatus = ref('')
    const previousLogLength = ref(0)

    let refreshInterval = null

    // Compute WebSocket URL based on selected source
    const wsUrl = computed(() => {
      if (!selectedSource.value) return ''
      return `${apiService.getWebSocketUrl()}/api/logs/tail/${selectedSource.value}`
    })

    // Use WebSocket composable for log streaming
    const { isConnected: wsConnected, lastMessage: wsMessage, connect: wsConnect, disconnect: wsDisconnect } = useWebSocket(
      wsUrl,
      {
        autoConnect: false,
        autoReconnect: true,
        onMessage: (data) => {
          // Append incoming log data
          logContent.value += '\n' + data
          lineCount.value++

          // Limit content size to prevent memory issues
          const lines = logContent.value.split('\n')
          if (lines.length > 5000) {
            logContent.value = lines.slice(-4000).join('\n')
          }

          if (autoScroll.value) {
            nextTick(() => scrollToBottom())
          }
        },
        onError: (error) => {
          logger.error('WebSocket error:', error)
        }
      }
    )

    const refreshFilesFn = async () => {
      const response = await apiService.get('/api/logs/sources')
      logSources.value = response
    }

    const refreshFiles = async () => {
      await refreshFilesOp(refreshFilesFn).catch(err => {
        logger.error('Failed to load log sources:', err)
      })
    }

    const loadLogFn = async () => {
      // Disconnect WebSocket before loading new log
      wsDisconnect()
        
        let endpoint = '/api/logs/unified'
        let params = new URLSearchParams({
          lines: maxLines.value.toString()
        })
        
        if (selectedLevel.value) {
          params.append('level', selectedLevel.value)
        }
        
        // Handle different source types
        if (selectedSource.value !== 'unified') {
          const [sourceType, sourceName] = selectedSource.value.split(':')
          
          if (sourceType === 'file') {
            endpoint = `/api/logs/read/${sourceName}`
            params = new URLSearchParams({
              lines: maxLines.value.toString(),
              tail: 'true'
            })
          } else if (sourceType === 'container') {
            endpoint = `/api/logs/container/${sourceName}`
            params = new URLSearchParams({
              lines: maxLines.value.toString(),
              tail: 'true'
            })
            if (selectedLevel.value) {
              params.append('level', selectedLevel.value)
            }
          }
        }
        
        const response = await apiService.get(`${endpoint}?${params}`)
        
        // Handle different response formats
        if (response.logs) {
          // Unified or container logs (structured)
          logs.value = response.logs
          logContent.value = formatStructuredLogs(response.logs)
          lineCount.value = response.logs.length
        } else if (response.lines) {
          // File logs (raw or structured)
          if (Array.isArray(response.lines) && response.lines.length > 0 && typeof response.lines[0] === 'object') {
            // Structured logs
            logs.value = response.lines
            logContent.value = formatStructuredLogs(response.lines)
          } else {
            // Raw text lines
            logContent.value = response.lines.join('\n')
            logs.value = []
          }
          lineCount.value = response.lines.length
        } else {
          logContent.value = 'No log data available'
          logs.value = []
          lineCount.value = 0
        }
        
      lastUpdated.value = new Date().toLocaleTimeString()

      // Auto scroll to bottom
      if (autoScroll.value) {
        await nextTick()
        scrollToBottom()
      }
    }

    const loadLog = async () => {
      if (!selectedSource.value) return
      await loadLogOp(loadLogFn).catch(err => {
        logger.error('Load log error:', err)
      })
    }
    
    const formatStructuredLogs = (logEntries) => {
      return logEntries.map(entry => {
        const timestamp = entry.timestamp ? 
          (new Date(entry.timestamp).getTime() ? new Date(entry.timestamp).toLocaleTimeString() : new Date().toLocaleTimeString()) : 
          ''
        const level = entry.level || 'INFO'
        const service = entry.service || 'unknown'
        const sourceType = entry.source_type || 'file'
        const sourceIcon = sourceType === 'container' ? '🐳' : '📄'
        
        return `[${timestamp}] ${sourceIcon} ${service.toUpperCase()} [${level}] ${entry.message}`
      }).join('\n')
    }

    // WebSocket streaming replaced by useWebSocket composable
    const startWebSocket = () => {
      if (!selectedSource.value) return
      wsConnect()
    }

    const scrollToBottom = () => {
      if (logContentRef.value) {
        logContentRef.value.scrollTop = logContentRef.value.scrollHeight
      }
    }

    const toggleAutoScroll = () => {
      autoScroll.value = !autoScroll.value
      if (autoScroll.value) {
        scrollToBottom()
      }
    }

    const searchLogs = () => {
      showSearch.value = true
    }

    const performSearch = async () => {
      if (!searchQuery.value) return
      
      try {
        loading.value = true
        const response = await apiService.get('/api/logs/search', {
          query: searchQuery.value,
          source: selectedSource.value || null
        })
        
        if (response.results.length > 0) {
          // Format search results
          const resultText = response.results.map(r => 
            `[${r.file}:${r.line}] ${r.content}`
          ).join('\n')
          
          logContent.value = `Search results for "${searchQuery.value}":\n\n${resultText}`
          lineCount.value = response.count
        } else {
          logContent.value = `No results found for "${searchQuery.value}"`
          lineCount.value = 0
        }
        
        showSearch.value = false
        searchQuery.value = ''
      } catch (err) {
        error.value = `Search failed: ${err.message}`
      } finally {
        loading.value = false
      }
    }

    // Announce new log entries to screen readers
    watch(logContent, (newContent, oldContent) => {
      // Only announce when content is added (streaming or refresh)
      if (newContent && newContent.length > (oldContent?.length || 0)) {
        const currentLines = newContent.split('\n').length
        const newLinesCount = currentLines - previousLogLength.value

        if (newLinesCount > 0) {
          // Get the last few lines for preview
          const lines = newContent.split('\n')
          const recentLines = lines.slice(-Math.min(3, newLinesCount))
          const preview = recentLines.join(' ').substring(0, 150)

          screenReaderStatus.value = `${newLinesCount} new log ${newLinesCount === 1 ? 'entry' : 'entries'}: ${preview}...`

          // Clear announcement after 2 seconds
          setTimeout(() => {
            screenReaderStatus.value = ''
          }, 2000)
        }

        previousLogLength.value = currentLines
      }
    })

    onMounted(() => {
      refreshFiles()
      // Auto refresh file list every 30 seconds
      refreshInterval = setInterval(refreshFiles, 30000)
    })

    onUnmounted(() => {
      if (refreshInterval) {
        clearInterval(refreshInterval)
      }
      // WebSocket cleanup handled automatically by useWebSocket composable
    })

    return {
      logSources,
      selectedSource,
      selectedLevel,
      maxLines,
      logContent,
      logs,
      loading,
      error,
      autoScroll,
      showSearch,
      searchQuery,
      lineCount,
      lastUpdated,
      logContentRef,
      screenReaderStatus,
      refreshFiles,
      loadLog,
      toggleAutoScroll,
      searchLogs,
      performSearch,
      formatStructuredLogs
    }
  }
}
</script>

<style scoped>
.log-viewer {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--surface-ground);
  border-radius: 6px;
  overflow: hidden;
}

.log-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background: var(--surface-section);
  border-bottom: 1px solid var(--surface-border);
}

.log-selector {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.log-selector select {
  padding: 0.5rem 1rem;
  border: 1px solid var(--surface-border);
  border-radius: 4px;
  background: var(--surface-ground);
  color: var(--text-color);
  min-width: 300px;
}

.log-filters {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.log-filters select,
.log-filters input {
  padding: 0.5rem;
  border: 1px solid var(--surface-border);
  border-radius: 4px;
  background: var(--surface-ground);
  color: var(--text-color);
}

.log-filters input[type="number"] {
  width: 80px;
}

.log-actions {
  display: flex;
  gap: 0.5rem;
}

.log-actions button {
  padding: 0.5rem 1rem;
  border: 1px solid var(--surface-border);
  border-radius: 4px;
  background: var(--surface-card);
  color: var(--text-color);
  cursor: pointer;
  transition: all 0.2s;
}

.log-actions button:hover {
  background: var(--surface-hover);
}

.log-actions button.active {
  background: var(--primary-color);
  color: white;
}

.search-panel {
  display: flex;
  gap: 0.5rem;
  padding: 1rem;
  background: var(--surface-section);
  border-bottom: 1px solid var(--surface-border);
}

.search-input {
  flex: 1;
  padding: 0.5rem 1rem;
  border: 1px solid var(--surface-border);
  border-radius: 4px;
  background: var(--surface-ground);
  color: var(--text-color);
}

.log-content {
  flex: 1;
  overflow: auto;
  padding: 1rem;
  background: #1e1e1e;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
}

.log-text {
  margin: 0;
  color: #d4d4d4;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.loading,
.error {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-color-secondary);
  font-size: 1.2rem;
  gap: 0.5rem;
}

.error {
  color: var(--red-500);
}

.log-status {
  padding: 0.5rem 1rem;
  background: var(--surface-section);
  border-top: 1px solid var(--surface-border);
  color: var(--text-color-secondary);
  font-size: 0.875rem;
}
</style>