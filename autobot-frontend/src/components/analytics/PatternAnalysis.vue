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

    <!-- Interrupted State (#1250) -->
    <div v-else-if="wasInterrupted" class="interrupted-state">
      <i class="fas fa-info-circle"></i>
      Previous analysis was interrupted by a server restart.
      <button @click="runAnalysis" :disabled="!rootPath" class="rerun-btn">
        <i class="fas fa-redo"></i> Re-run Analysis
      </button>
      <button @click="reset" class="dismiss-btn">
        <i class="fas fa-times"></i> Dismiss
      </button>
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
  wasInterrupted,
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
/* Issue #704: Migrated to CSS design tokens */

.pattern-analysis-section {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  margin-bottom: var(--spacing-4);
}

.pattern-analysis-section h3 {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  margin: 0 0 var(--spacing-4) 0;
  font-size: var(--text-lg);
  color: var(--text-primary);
}

.pattern-analysis-section h3 i {
  color: var(--color-purple);
}

.total-count {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  font-weight: var(--font-normal);
}

.section-action-btn {
  margin-left: auto;
  padding: var(--spacing-1-5) var(--spacing-3);
  background: var(--color-purple);
  color: var(--text-on-primary);
  border: none;
  border-radius: var(--radius-default);
  cursor: pointer;
  font-size: var(--text-sm);
  display: flex;
  align-items: center;
  gap: var(--spacing-1-5);
  transition: background var(--duration-200) var(--ease-in-out);
}

.section-action-btn:hover:not(:disabled) {
  background: var(--color-purple-dark);
}

.section-action-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.loading-state,
.error-state,
.empty-state {
  padding: var(--spacing-5);
  text-align: center;
  color: var(--text-secondary);
}

.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-2-5);
}

.mini-progress {
  width: 200px;
  height: 4px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-xs);
  overflow: hidden;
}

.mini-progress-bar {
  height: 100%;
  background: var(--color-purple);
  transition: width var(--duration-300) var(--ease-in-out);
}

.error-state {
  color: var(--color-error);
}

.interrupted-state {
  color: var(--color-info);
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  flex-wrap: wrap;
}

.rerun-btn {
  padding: var(--spacing-1) var(--spacing-2-5);
  background: var(--color-purple);
  color: var(--text-on-primary);
  border: none;
  border-radius: var(--radius-default);
  cursor: pointer;
  font-size: var(--text-sm);
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
}

.rerun-btn:hover:not(:disabled) {
  background: var(--color-purple-dark);
}

.rerun-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.dismiss-btn {
  padding: var(--spacing-1) var(--spacing-2);
  background: transparent;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-default);
  color: var(--text-secondary);
  cursor: pointer;
  font-size: var(--text-sm);
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-1);
}

.dismiss-btn:hover {
  border-color: var(--text-secondary);
}

.retry-btn {
  margin-left: var(--spacing-2-5);
  padding: var(--spacing-1) var(--spacing-2);
  background: transparent;
  border: 1px solid currentColor;
  border-radius: var(--radius-default);
  color: inherit;
  cursor: pointer;
}

/* Summary Cards */
.pattern-summary-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-4);
}

.summary-card {
  background: var(--bg-tertiary);
  padding: var(--spacing-3);
  border-radius: var(--radius-md);
  text-align: center;
}

.summary-value {
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
}

.summary-label {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin-top: var(--spacing-1);
}

.summary-card.grade-a .summary-value { color: var(--color-success); }
.summary-card.grade-b .summary-value { color: var(--color-success-light); }
.summary-card.grade-c .summary-value { color: var(--color-warning); }
.summary-card.grade-d .summary-value { color: var(--color-error); }

/* Severity Distribution */
.severity-distribution {
  display: flex;
  gap: var(--spacing-2);
  flex-wrap: wrap;
  margin-bottom: var(--spacing-4);
}

.severity-badge {
  padding: var(--spacing-1) var(--spacing-2-5);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
}

.severity-badge.severity-critical { background: var(--color-error-bg); color: var(--color-error); }
.severity-badge.severity-high { background: var(--color-warning-bg); color: var(--chart-orange); }
.severity-badge.severity-medium { background: var(--color-warning-bg); color: var(--color-warning); }
.severity-badge.severity-low { background: var(--color-success-bg); color: var(--color-success); }
.severity-badge.severity-info { background: var(--color-info-bg); color: var(--color-info); }

/* Accordion */
.accordion-group {
  margin-bottom: var(--spacing-3);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.accordion-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2-5) var(--spacing-3-5);
  background: var(--bg-tertiary);
  cursor: pointer;
  user-select: none;
}

.accordion-header:hover {
  background: var(--bg-hover);
}

.header-title {
  flex: 1;
  font-weight: var(--font-medium);
}

.header-count {
  color: var(--text-secondary);
  font-size: var(--text-sm);
}

.accordion-content {
  padding: var(--spacing-3);
  background: var(--bg-secondary);
}

/* Pattern Items */
.pattern-item {
  padding: var(--spacing-3);
  margin-bottom: var(--spacing-2);
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  border-left: 3px solid var(--border-default);
}

.pattern-item.severity-critical { border-left-color: var(--color-error); }
.pattern-item.severity-high { border-left-color: var(--chart-orange); }
.pattern-item.severity-medium { border-left-color: var(--color-warning); }
.pattern-item.severity-low { border-left-color: var(--color-success); }

.pattern-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2);
}

.pattern-title {
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.pattern-badge {
  padding: var(--spacing-0-5) var(--spacing-2);
  background: var(--color-purple);
  color: var(--text-on-primary);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
}

.pattern-details {
  display: flex;
  gap: var(--spacing-4);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2);
}

.detail-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-1);
}

.pattern-locations {
  margin: var(--spacing-2) 0;
}

.location-item {
  font-size: var(--text-xs);
  padding: var(--spacing-0-5) 0;
}

.location-item code {
  color: var(--color-info);
}

.function-name {
  color: var(--color-success);
  margin-left: var(--spacing-2);
}

.more-locations {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  font-style: italic;
}

.pattern-suggestion {
  font-size: var(--text-sm);
  color: var(--color-success);
  margin-top: var(--spacing-2);
  padding-top: var(--spacing-2);
  border-top: 1px solid var(--border-default);
}

/* Code Comparison */
.code-comparison {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-3);
  margin-top: var(--spacing-2);
}

.code-block {
  padding: var(--spacing-2);
  background: var(--code-bg);
  border-radius: var(--radius-default);
  font-size: var(--text-xs);
}

.code-block pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
}

.code-label {
  display: block;
  font-size: var(--text-xs);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-1);
}

/* Complexity Table */
.complexity-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--text-sm);
}

.complexity-table th {
  text-align: left;
  padding: var(--spacing-2);
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  font-weight: var(--font-medium);
}

.complexity-table td {
  padding: var(--spacing-2);
  border-bottom: 1px solid var(--border-default);
}

.location-cell code {
  color: var(--color-info);
  font-size: var(--text-xs);
}

.metric-cell {
  text-align: center;
  font-weight: var(--font-medium);
}

.metric-good { color: var(--color-success); }
.metric-moderate { color: var(--color-warning); }
.metric-warning { color: var(--chart-orange); }
.metric-critical { color: var(--color-error); }

/* Refactoring Items */
.refactoring-item {
  padding: var(--spacing-3);
  margin-bottom: var(--spacing-2);
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
  border-left: 3px solid var(--color-purple);
}

.refactoring-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-2);
}

.refactoring-title {
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.effort-badge {
  padding: var(--spacing-0-5) var(--spacing-2);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
}

.effort-low { background: var(--color-success-bg); color: var(--color-success); }
.effort-medium { background: var(--color-warning-bg); color: var(--color-warning); }
.effort-high { background: var(--color-warning-bg); color: var(--chart-orange); }
.effort-very-high { background: var(--color-error-bg); color: var(--color-error); }

.refactoring-description {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--spacing-2);
}

.refactoring-benefits {
  display: flex;
  gap: var(--spacing-1-5);
  flex-wrap: wrap;
  margin-bottom: var(--spacing-2);
}

.benefit-tag {
  padding: var(--spacing-0-5) var(--spacing-2);
  background: var(--color-success-bg);
  color: var(--color-success);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
}

.refactoring-impact {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  display: flex;
  gap: var(--spacing-4);
}

/* Storage Stats */
.storage-stats {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-3);
  background: var(--bg-tertiary);
  border-radius: var(--radius-default);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-top: var(--spacing-3);
}

.clear-btn {
  margin-left: auto;
  padding: var(--spacing-1) var(--spacing-2);
  background: transparent;
  border: 1px solid var(--color-error);
  color: var(--color-error);
  border-radius: var(--radius-default);
  cursor: pointer;
  font-size: var(--text-xs);
}

.clear-btn:hover {
  background: var(--color-error-bg);
}

/* Timestamp */
.scan-timestamp {
  margin-top: var(--spacing-3);
  padding-top: var(--spacing-3);
  border-top: 1px solid var(--border-default);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.analysis-time {
  margin-left: var(--spacing-2);
  color: var(--color-success);
}

/* Empty State */
.empty-state {
  padding: var(--spacing-10) var(--spacing-5);
}

.empty-state i {
  font-size: var(--text-4xl);
  margin-bottom: var(--spacing-4);
  opacity: 0.5;
}

.empty-hint {
  font-size: var(--text-sm);
  max-width: 400px;
  margin: var(--spacing-2) auto 0;
}

.show-more {
  text-align: center;
  padding: var(--spacing-2);
  font-size: var(--text-xs);
}

.muted {
  color: var(--text-secondary);
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
