<template>
  <div class="pattern-analysis-section analytics-section">
    <h3>
      <i class="fas fa-puzzle-piece"></i> Code Pattern Analysis
      <span v-if="totalPatterns > 0" class="total-count">({{ totalPatterns }} patterns)</span>
      <button @click="runAnalysis" :disabled="analyzing || !rootPath" class="section-action-btn">
        <i :class="analyzing ? 'fas fa-spinner fa-spin' : 'fas fa-search'"></i>
        {{ analyzing ? 'Analyzing...' : 'Analyze Patterns' }}
      </button>
    </h3>

    <!-- Loading State -->
    <div v-if="analyzing" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      <span v-if="taskStatus">{{ taskStatus.current_step || 'Analyzing code patterns...' }}</span>
      <span v-else>Starting pattern analysis...</span>
      <div v-if="taskStatus?.progress" class="mini-progress">
        <div class="mini-progress-bar" :style="{ width: taskStatus.progress + '%' }"></div>
      </div>
    </div>

    <!-- Error State -->
    <div v-else-if="error" class="error-state">
      <i class="fas fa-exclamation-triangle"></i> {{ error }}
      <button @click="reset" class="retry-btn">
        <i class="fas fa-redo"></i> Reset
      </button>
    </div>

    <!-- Results -->
    <div v-else-if="hasResults" class="section-content">
      <!-- Summary Cards -->
      <div class="pattern-summary-cards">
        <div class="summary-card">
          <div class="summary-value">{{ analysisReport?.analysis_summary?.files_analyzed || 0 }}</div>
          <div class="summary-label">Files Analyzed</div>
        </div>
        <div class="summary-card">
          <div class="summary-value">{{ totalPatterns }}</div>
          <div class="summary-label">Patterns Found</div>
        </div>
        <div class="summary-card">
          <div class="summary-value">{{ analysisReport?.analysis_summary?.potential_loc_reduction || 0 }}</div>
          <div class="summary-label">LOC Reduction</div>
        </div>
        <div class="summary-card" :class="'grade-' + (analysisReport?.analysis_summary?.complexity_score || 'N').toLowerCase()">
          <div class="summary-value">{{ analysisReport?.analysis_summary?.complexity_score || 'N/A' }}</div>
          <div class="summary-label">Complexity Grade</div>
        </div>
      </div>

      <!-- Severity Distribution -->
      <div v-if="Object.keys(severityCounts).length > 0" class="severity-distribution">
        <span v-for="(count, severity) in severityCounts" :key="severity" :class="'severity-badge severity-' + severity">
          {{ severity }}: {{ count }}
        </span>
      </div>

      <!-- Duplicate Patterns Section -->
      <div v-if="duplicatePatterns.length > 0" class="accordion-group">
        <div class="accordion-header" @click="expandedSections.duplicates = !expandedSections.duplicates">
          <i :class="expandedSections.duplicates ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"></i>
          <span class="header-title"><i class="fas fa-clone"></i> Duplicate Code</span>
          <span class="header-count">({{ duplicatePatterns.length }})</span>
        </div>
        <div v-show="expandedSections.duplicates" class="accordion-content">
          <div v-for="(dup, index) in duplicatePatterns.slice(0, 20)" :key="'dup-' + index"
               class="pattern-item" :class="'severity-' + dup.severity">
            <div class="pattern-header">
              <span class="pattern-title">{{ dup.description }}</span>
              <span class="pattern-badge">{{ (dup.similarity_score * 100).toFixed(0) }}% similar</span>
            </div>
            <div class="pattern-details">
              <div class="detail-row">
                <i class="fas fa-map-marker-alt"></i>
                <span>{{ dup.locations?.length || 0 }} locations</span>
              </div>
              <div class="detail-row">
                <i class="fas fa-compress-alt"></i>
                <span>{{ dup.code_reduction_potential }} lines saveable</span>
              </div>
            </div>
            <div class="pattern-locations">
              <div v-for="(loc, locIdx) in dup.locations?.slice(0, 3)" :key="locIdx" class="location-item">
                <code>{{ loc.file_path }}:{{ loc.start_line }}</code>
                <span v-if="loc.function_name" class="function-name">{{ loc.function_name }}</span>
              </div>
              <div v-if="(dup.locations?.length || 0) > 3" class="more-locations">
                +{{ (dup.locations?.length || 0) - 3 }} more locations
              </div>
            </div>
            <div class="pattern-suggestion">
              <i class="fas fa-lightbulb"></i> {{ dup.suggestion }}
            </div>
          </div>
          <div v-if="duplicatePatterns.length > 20" class="show-more">
            <span class="muted">Showing 20 of {{ duplicatePatterns.length }} duplicate patterns</span>
          </div>
        </div>
      </div>

      <!-- Regex Opportunities Section -->
      <div v-if="regexOpportunities.length > 0" class="accordion-group">
        <div class="accordion-header" @click="expandedSections.regex = !expandedSections.regex">
          <i :class="expandedSections.regex ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"></i>
          <span class="header-title"><i class="fas fa-asterisk"></i> Regex Opportunities</span>
          <span class="header-count">({{ regexOpportunities.length }})</span>
        </div>
        <div v-show="expandedSections.regex" class="accordion-content">
          <div v-for="(opp, index) in regexOpportunities.slice(0, 15)" :key="'regex-' + index"
               class="pattern-item" :class="'severity-' + opp.severity">
            <div class="pattern-header">
              <span class="pattern-title">{{ opp.description }}</span>
              <span class="pattern-badge">{{ opp.performance_gain }}</span>
            </div>
            <div class="pattern-location">
              <code>{{ opp.locations?.[0]?.file_path }}:{{ opp.locations?.[0]?.start_line }}</code>
            </div>
            <div class="code-comparison">
              <div class="code-block current">
                <span class="code-label">Current:</span>
                <pre>{{ truncateCode(opp.current_code) }}</pre>
              </div>
              <div class="code-block suggested">
                <span class="code-label">Suggested:</span>
                <code>{{ opp.suggested_regex }}</code>
              </div>
            </div>
          </div>
          <div v-if="regexOpportunities.length > 15" class="show-more">
            <span class="muted">Showing 15 of {{ regexOpportunities.length }} opportunities</span>
          </div>
        </div>
      </div>

      <!-- Complexity Hotspots Section -->
      <div v-if="complexityHotspots.length > 0" class="accordion-group">
        <div class="accordion-header" @click="expandedSections.complexity = !expandedSections.complexity">
          <i :class="expandedSections.complexity ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"></i>
          <span class="header-title"><i class="fas fa-brain"></i> Complexity Hotspots</span>
          <span class="header-count">({{ complexityHotspots.length }})</span>
        </div>
        <div v-show="expandedSections.complexity" class="accordion-content">
          <table class="complexity-table">
            <thead>
              <tr>
                <th>Location</th>
                <th>CC</th>
                <th>Cognitive</th>
                <th>MI</th>
                <th>Nesting</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(hotspot, index) in complexityHotspots.slice(0, 20)" :key="'cx-' + index"
                  :class="'severity-row-' + hotspot.severity">
                <td class="location-cell">
                  <code>{{ formatLocation(hotspot.locations?.[0]) }}</code>
                </td>
                <td class="metric-cell" :class="getMetricClass(hotspot.cyclomatic_complexity, 'cc')">
                  {{ hotspot.cyclomatic_complexity }}
                </td>
                <td class="metric-cell" :class="getMetricClass(hotspot.cognitive_complexity, 'cognitive')">
                  {{ hotspot.cognitive_complexity }}
                </td>
                <td class="metric-cell" :class="getMetricClass(hotspot.maintainability_index, 'mi')">
                  {{ hotspot.maintainability_index.toFixed(1) }}
                </td>
                <td class="metric-cell">{{ hotspot.nesting_depth }}</td>
              </tr>
            </tbody>
          </table>
          <div v-if="complexityHotspots.length > 20" class="show-more">
            <span class="muted">Showing 20 of {{ complexityHotspots.length }} hotspots</span>
          </div>
        </div>
      </div>

      <!-- Refactoring Suggestions Section -->
      <div v-if="refactoringSuggestions.length > 0" class="accordion-group">
        <div class="accordion-header" @click="expandedSections.refactoring = !expandedSections.refactoring">
          <i :class="expandedSections.refactoring ? 'fas fa-chevron-down' : 'fas fa-chevron-right'"></i>
          <span class="header-title"><i class="fas fa-magic"></i> Refactoring Suggestions</span>
          <span class="header-count">({{ refactoringSuggestions.length }})</span>
        </div>
        <div v-show="expandedSections.refactoring" class="accordion-content">
          <div v-for="(suggestion, index) in refactoringSuggestions.slice(0, 15)" :key="'ref-' + index"
               class="refactoring-item" :class="'severity-' + suggestion.severity">
            <div class="refactoring-header">
              <span class="refactoring-title">{{ suggestion.title }}</span>
              <span class="effort-badge" :class="'effort-' + suggestion.estimated_effort.toLowerCase().replace(' ', '-')">
                {{ suggestion.estimated_effort }}
              </span>
            </div>
            <div class="refactoring-description">{{ suggestion.description }}</div>
            <div class="refactoring-benefits">
              <span v-for="(benefit, bIdx) in suggestion.benefits?.slice(0, 3)" :key="bIdx" class="benefit-tag">
                {{ benefit }}
              </span>
            </div>
            <div class="refactoring-impact">
              <span v-if="suggestion.estimated_loc_reduction > 0">
                <i class="fas fa-minus-circle"></i> {{ suggestion.estimated_loc_reduction }} LOC
              </span>
              <span v-if="suggestion.estimated_complexity_reduction > 0">
                <i class="fas fa-chart-line"></i> -{{ suggestion.estimated_complexity_reduction }} complexity
              </span>
            </div>
          </div>
          <div v-if="refactoringSuggestions.length > 15" class="show-more">
            <span class="muted">Showing 15 of {{ refactoringSuggestions.length }} suggestions</span>
          </div>
        </div>
      </div>

      <!-- Storage Stats -->
      <div v-if="storageStats" class="storage-stats">
        <i class="fas fa-database"></i>
        {{ storageStats.total_patterns }} patterns in ChromaDB
        <button @click="clearStorage" class="clear-btn" title="Clear stored patterns">
          <i class="fas fa-trash-alt"></i>
        </button>
      </div>

      <!-- Timestamp -->
      <div v-if="analysisReport?.analysis_summary?.timestamp" class="scan-timestamp">
        <i class="fas fa-clock"></i>
        Last scan: {{ formatTimestamp(analysisReport.analysis_summary.timestamp) }}
        <span v-if="analysisReport?.analysis_summary?.duration_seconds" class="analysis-time">
          ({{ analysisReport.analysis_summary.duration_seconds.toFixed(1) }}s)
        </span>
      </div>
    </div>

    <!-- Empty State -->
    <div v-else class="empty-state">
      <i class="fas fa-puzzle-piece"></i>
      <p>No pattern analysis available</p>
      <p class="empty-hint">Click 'Analyze Patterns' to detect duplicates, complexity hotspots, and optimization opportunities.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { watch, onMounted, reactive } from 'vue'
import { usePatternAnalysis } from '@/composables/usePatternAnalysis'

// Props
const props = defineProps<{
  rootPath: string
  autoLoad?: boolean
}>()

// Emits
const emit = defineEmits<{
  (e: 'analysis-complete', report: any): void
  (e: 'error', message: string): void
}>()

// Use composable
const {
  loading,
  analyzing,
  error,
  taskStatus,
  analysisReport,
  duplicatePatterns,
  regexOpportunities,
  complexityHotspots,
  refactoringSuggestions,
  storageStats,
  expandedSections,
  totalPatterns,
  severityCounts,
  hasResults,
  analyzePatterns,
  getSummary,
  getCachedSummary,
  getDuplicates,
  getRegexOpportunities,
  getComplexityHotspots,
  getRefactoringSuggestions,
  getStorageStats,
  clearStorage: clearStorageApi,
  reset,
  loadCachedData
} = usePatternAnalysis()

// Track which sections have been loaded (lazy loading)
const sectionsLoaded = reactive({
  duplicates: false,
  regex: false,
  complexity: false,
  refactoring: false
})

// Run full analysis
const runAnalysis = async () => {
  if (!props.rootPath) return

  const success = await analyzePatterns(props.rootPath, {
    enableRegex: true,
    enableComplexity: true,
    enableDuplicates: true,
    runInBackground: true
  })

  if (success && analysisReport.value) {
    emit('analysis-complete', analysisReport.value)
  }
}

// Clear storage handler
const clearStorage = async () => {
  if (confirm('Clear all stored patterns from ChromaDB?')) {
    await clearStorageApi()
    await getStorageStats()
  }
}

// Utility functions
const truncateCode = (code: string, maxLength: number = 100): string => {
  if (!code) return ''
  return code.length > maxLength ? code.substring(0, maxLength) + '...' : code
}

const formatLocation = (loc: any): string => {
  if (!loc) return 'N/A'
  let result = `${loc.file_path}:${loc.start_line}`
  if (loc.function_name) result += ` (${loc.function_name})`
  return result
}

const formatTimestamp = (ts: string): string => {
  try {
    return new Date(ts).toLocaleString()
  } catch {
    return ts
  }
}

const getMetricClass = (value: number, type: string): string => {
  if (type === 'cc') {
    if (value <= 5) return 'metric-good'
    if (value <= 10) return 'metric-moderate'
    if (value <= 20) return 'metric-warning'
    return 'metric-critical'
  }
  if (type === 'cognitive') {
    if (value <= 10) return 'metric-good'
    if (value <= 20) return 'metric-moderate'
    if (value <= 40) return 'metric-warning'
    return 'metric-critical'
  }
  if (type === 'mi') {
    if (value >= 80) return 'metric-good'
    if (value >= 65) return 'metric-moderate'
    if (value >= 50) return 'metric-warning'
    return 'metric-critical'
  }
  return ''
}

// Watch for error
watch(error, (newError) => {
  if (newError) {
    emit('error', newError)
  }
})

// Lazy loading watchers - load section data when expanded
watch(() => expandedSections.duplicates, async (expanded) => {
  if (expanded && !sectionsLoaded.duplicates && duplicatePatterns.value.length === 0) {
    sectionsLoaded.duplicates = true
    await getDuplicates(props.rootPath)
  }
})

watch(() => expandedSections.regex, async (expanded) => {
  if (expanded && !sectionsLoaded.regex && regexOpportunities.value.length === 0) {
    sectionsLoaded.regex = true
    await getRegexOpportunities(props.rootPath)
  }
})

watch(() => expandedSections.complexity, async (expanded) => {
  if (expanded && !sectionsLoaded.complexity && complexityHotspots.value.length === 0) {
    sectionsLoaded.complexity = true
    await getComplexityHotspots(props.rootPath)
  }
})

watch(() => expandedSections.refactoring, async (expanded) => {
  if (expanded && !sectionsLoaded.refactoring && refactoringSuggestions.value.length === 0) {
    sectionsLoaded.refactoring = true
    await getRefactoringSuggestions(props.rootPath)
  }
})

// Auto-load on mount - use fast cached loading (Issue #208)
onMounted(async () => {
  if (props.autoLoad) {
    // Fast path: load from cache in parallel
    await loadCachedData()
  }
})

// Watch for path changes
watch(() => props.rootPath, async (newPath) => {
  if (newPath && props.autoLoad) {
    // Reset section loading state when path changes
    sectionsLoaded.duplicates = false
    sectionsLoaded.regex = false
    sectionsLoaded.complexity = false
    sectionsLoaded.refactoring = false
    await getSummary(newPath)
  }
})

// Expose methods for parent component access (Issue #208)
defineExpose({
  runAnalysis,
  getSummary,
  getDuplicates,
  getRegexOpportunities,
  getComplexityHotspots,
  getRefactoringSuggestions,
  getStorageStats,
  clearStorage,
  reset,
  // State for external access
  loading,
  analyzing,
  error,
  hasResults,
  analysisReport,
})
</script>

<style scoped>
.pattern-analysis-section {
  background: var(--card-bg, #1e1e2e);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}

.pattern-analysis-section h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 16px 0;
  font-size: 1.1rem;
  color: var(--text-primary, #e0e0e0);
}

.pattern-analysis-section h3 i {
  color: var(--accent-purple, #9c27b0);
}

.total-count {
  font-size: 0.85rem;
  color: var(--text-secondary, #888);
  font-weight: normal;
}

.section-action-btn {
  margin-left: auto;
  padding: 6px 12px;
  background: var(--accent-purple, #9c27b0);
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85rem;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: background 0.2s;
}

.section-action-btn:hover:not(:disabled) {
  background: var(--accent-purple-dark, #7b1fa2);
}

.section-action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.loading-state,
.error-state,
.empty-state {
  padding: 20px;
  text-align: center;
  color: var(--text-secondary, #888);
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.mini-progress {
  width: 200px;
  height: 4px;
  background: var(--bg-tertiary, #2a2a3e);
  border-radius: 2px;
  overflow: hidden;
}

.mini-progress-bar {
  height: 100%;
  background: var(--accent-purple, #9c27b0);
  transition: width 0.3s;
}

.error-state {
  color: var(--error-color, #f44336);
}

.retry-btn {
  margin-left: 10px;
  padding: 4px 8px;
  background: transparent;
  border: 1px solid currentColor;
  border-radius: 4px;
  color: inherit;
  cursor: pointer;
}

/* Summary Cards */
.pattern-summary-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.summary-card {
  background: var(--bg-tertiary, #2a2a3e);
  padding: 12px;
  border-radius: 6px;
  text-align: center;
}

.summary-value {
  font-size: 1.5rem;
  font-weight: bold;
  color: var(--text-primary, #e0e0e0);
}

.summary-label {
  font-size: 0.75rem;
  color: var(--text-secondary, #888);
  margin-top: 4px;
}

.summary-card.grade-a .summary-value { color: #4caf50; }
.summary-card.grade-b .summary-value { color: #8bc34a; }
.summary-card.grade-c .summary-value { color: #ffc107; }
.summary-card.grade-d .summary-value { color: #f44336; }

/* Severity Distribution */
.severity-distribution {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.severity-badge {
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 0.75rem;
  font-weight: 500;
}

.severity-badge.severity-critical { background: #f4433620; color: #f44336; }
.severity-badge.severity-high { background: #ff980020; color: #ff9800; }
.severity-badge.severity-medium { background: #ffc10720; color: #ffc107; }
.severity-badge.severity-low { background: #4caf5020; color: #4caf50; }
.severity-badge.severity-info { background: #2196f320; color: #2196f3; }

/* Accordion */
.accordion-group {
  margin-bottom: 12px;
  border: 1px solid var(--border-color, #333);
  border-radius: 6px;
  overflow: hidden;
}

.accordion-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--bg-tertiary, #2a2a3e);
  cursor: pointer;
  user-select: none;
}

.accordion-header:hover {
  background: var(--bg-hover, #333);
}

.header-title {
  flex: 1;
  font-weight: 500;
}

.header-count {
  color: var(--text-secondary, #888);
  font-size: 0.85rem;
}

.accordion-content {
  padding: 12px;
  background: var(--bg-secondary, #252535);
}

/* Pattern Items */
.pattern-item {
  padding: 12px;
  margin-bottom: 8px;
  background: var(--bg-tertiary, #2a2a3e);
  border-radius: 6px;
  border-left: 3px solid var(--accent-color, #666);
}

.pattern-item.severity-critical { border-left-color: #f44336; }
.pattern-item.severity-high { border-left-color: #ff9800; }
.pattern-item.severity-medium { border-left-color: #ffc107; }
.pattern-item.severity-low { border-left-color: #4caf50; }

.pattern-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.pattern-title {
  font-weight: 500;
  color: var(--text-primary, #e0e0e0);
}

.pattern-badge {
  padding: 2px 8px;
  background: var(--accent-purple, #9c27b0);
  color: white;
  border-radius: 10px;
  font-size: 0.75rem;
}

.pattern-details {
  display: flex;
  gap: 16px;
  font-size: 0.85rem;
  color: var(--text-secondary, #888);
  margin-bottom: 8px;
}

.detail-row {
  display: flex;
  align-items: center;
  gap: 4px;
}

.pattern-locations {
  margin: 8px 0;
}

.location-item {
  font-size: 0.8rem;
  padding: 2px 0;
}

.location-item code {
  color: var(--accent-blue, #2196f3);
}

.function-name {
  color: var(--accent-green, #4caf50);
  margin-left: 8px;
}

.more-locations {
  font-size: 0.75rem;
  color: var(--text-secondary, #888);
  font-style: italic;
}

.pattern-suggestion {
  font-size: 0.85rem;
  color: var(--accent-green, #4caf50);
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border-color, #333);
}

/* Code Comparison */
.code-comparison {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 8px;
}

.code-block {
  padding: 8px;
  background: var(--bg-code, #1a1a2a);
  border-radius: 4px;
  font-size: 0.8rem;
}

.code-block pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}

.code-label {
  display: block;
  font-size: 0.7rem;
  color: var(--text-secondary, #888);
  margin-bottom: 4px;
}

/* Complexity Table */
.complexity-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

.complexity-table th {
  text-align: left;
  padding: 8px;
  background: var(--bg-tertiary, #2a2a3e);
  color: var(--text-secondary, #888);
  font-weight: 500;
}

.complexity-table td {
  padding: 8px;
  border-bottom: 1px solid var(--border-color, #333);
}

.location-cell code {
  color: var(--accent-blue, #2196f3);
  font-size: 0.8rem;
}

.metric-cell {
  text-align: center;
  font-weight: 500;
}

.metric-good { color: #4caf50; }
.metric-moderate { color: #ffc107; }
.metric-warning { color: #ff9800; }
.metric-critical { color: #f44336; }

/* Refactoring Items */
.refactoring-item {
  padding: 12px;
  margin-bottom: 8px;
  background: var(--bg-tertiary, #2a2a3e);
  border-radius: 6px;
  border-left: 3px solid var(--accent-purple, #9c27b0);
}

.refactoring-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.refactoring-title {
  font-weight: 500;
  color: var(--text-primary, #e0e0e0);
}

.effort-badge {
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 0.75rem;
}

.effort-low { background: #4caf5020; color: #4caf50; }
.effort-medium { background: #ffc10720; color: #ffc107; }
.effort-high { background: #ff980020; color: #ff9800; }
.effort-very-high { background: #f4433620; color: #f44336; }

.refactoring-description {
  font-size: 0.85rem;
  color: var(--text-secondary, #888);
  margin-bottom: 8px;
}

.refactoring-benefits {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.benefit-tag {
  padding: 2px 8px;
  background: var(--accent-green, #4caf50)20;
  color: var(--accent-green, #4caf50);
  border-radius: 10px;
  font-size: 0.7rem;
}

.refactoring-impact {
  font-size: 0.8rem;
  color: var(--text-secondary, #888);
  display: flex;
  gap: 16px;
}

/* Storage Stats */
.storage-stats {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--bg-tertiary, #2a2a3e);
  border-radius: 4px;
  font-size: 0.85rem;
  color: var(--text-secondary, #888);
  margin-top: 12px;
}

.clear-btn {
  margin-left: auto;
  padding: 4px 8px;
  background: transparent;
  border: 1px solid var(--error-color, #f44336);
  color: var(--error-color, #f44336);
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.75rem;
}

.clear-btn:hover {
  background: var(--error-color, #f44336)20;
}

/* Timestamp */
.scan-timestamp {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border-color, #333);
  font-size: 0.8rem;
  color: var(--text-secondary, #888);
}

.analysis-time {
  margin-left: 8px;
  color: var(--accent-green, #4caf50);
}

/* Empty State */
.empty-state {
  padding: 40px 20px;
}

.empty-state i {
  font-size: 3rem;
  margin-bottom: 16px;
  opacity: 0.5;
}

.empty-hint {
  font-size: 0.85rem;
  max-width: 400px;
  margin: 8px auto 0;
}

.show-more {
  text-align: center;
  padding: 8px;
  font-size: 0.8rem;
}

.muted {
  color: var(--text-secondary, #888);
}

/* Responsive */
@media (max-width: 768px) {
  .pattern-summary-cards {
    grid-template-columns: repeat(2, 1fr);
  }

  .code-comparison {
    grid-template-columns: 1fr;
  }
}
</style>
