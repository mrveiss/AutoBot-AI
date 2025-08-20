<template>
  <div class="codebase-analytics">
    <div class="analytics-header">
      <h2>
        <i class="fas fa-chart-line"></i>
        Codebase Analytics & Usage Statistics
      </h2>
      <p class="subtitle">
        Analyze declaration usage, find code duplicates, and discover refactoring opportunities
      </p>
    </div>

    <!-- Control Panel -->
    <div class="control-panel">
      <div class="control-group">
        <label for="root-path">Project Root Path:</label>
        <div class="path-input-group">
          <input
            id="root-path"
            v-model="rootPath"
            type="text"
            placeholder="/path/to/your/project"
            class="path-input"
          />
          <button @click="autoDetectPath" class="auto-detect-btn" title="Auto-detect current project">
            <i class="fas fa-magic"></i>
          </button>
        </div>
      </div>

      <div class="action-buttons">
        <button @click="indexCodebase" :disabled="indexing || !rootPath" class="btn-primary">
          <i :class="indexing ? 'fas fa-spinner fa-spin' : 'fas fa-database'"></i>
          {{ indexing ? 'Indexing...' : 'Index Codebase' }}
        </button>
        <button @click="runFullAnalysis" :disabled="analyzing || !rootPath" class="btn-secondary">
          <i :class="analyzing ? 'fas fa-spinner fa-spin' : 'fas fa-chart-bar'"></i>
          {{ analyzing ? 'Analyzing...' : 'Analyze All' }}
        </button>
      </div>
    </div>

    <!-- Status Cards -->
    <div class="status-grid">
      <div class="status-card">
        <h3><i class="fas fa-server"></i> Index Status</h3>
        <div v-if="indexStatus" class="status-content">
          <div class="stat-item">
            <span class="label">Files Indexed:</span>
            <span class="value">{{ indexStatus.total_files_indexed || 0 }}</span>
          </div>
          <div class="stat-item">
            <span class="label">NPU Available:</span>
            <span class="value" :class="indexStatus.npu_available ? 'success' : 'warning'">
              {{ indexStatus.npu_available ? 'Yes' : 'No' }}
            </span>
          </div>
          <div class="stat-item">
            <span class="label">Cache Keys:</span>
            <span class="value">{{ indexStatus.cache_keys || 0 }}</span>
          </div>
        </div>
        <div v-else class="empty-state">
          Run indexing to see status
        </div>
      </div>

      <div class="status-card">
        <h3><i class="fas fa-code"></i> Language Distribution</h3>
        <div v-if="indexStatus?.languages" class="language-chart">
          <div
            v-for="(count, language) in indexStatus.languages"
            :key="language"
            class="language-bar"
          >
            <span class="language-name">{{ language }}</span>
            <div class="bar-container">
              <div
                class="bar-fill"
                :style="{ width: (count / maxLanguageCount * 100) + '%' }"
              ></div>
            </div>
            <span class="language-count">{{ count }}</span>
          </div>
        </div>
        <div v-else class="empty-state">
          No language data available
        </div>
      </div>
    </div>

    <!-- Analysis Results Tabs -->
    <div class="analysis-tabs" v-if="hasAnalysisData">
      <div class="tab-buttons">
        <button
          v-for="tab in analysisTabs"
          :key="tab.id"
          @click="activeAnalysisTab = tab.id"
          :class="['tab-btn', { active: activeAnalysisTab === tab.id }]"
        >
          <i :class="tab.icon"></i>
          {{ tab.label }}
        </button>
      </div>

      <!-- Declarations Analysis -->
      <div v-if="activeAnalysisTab === 'declarations'" class="tab-content">
        <div class="analysis-header">
          <h3>Declaration Usage Analysis</h3>
          <div class="analysis-summary" v-if="declarationAnalysis?.summary">
            <div class="summary-stat">
              <span class="label">Total Declarations:</span>
              <span class="value">{{ declarationAnalysis.summary.total_declarations }}</span>
            </div>
            <div class="summary-stat">
              <span class="label">Most Reused:</span>
              <span class="value">{{ declarationAnalysis.summary.most_reused_declaration }}</span>
            </div>
            <div class="summary-stat">
              <span class="label">Max Usage:</span>
              <span class="value">{{ declarationAnalysis.summary.max_usage_count }}</span>
            </div>
          </div>
        </div>

        <div class="declarations-grid" v-if="declarationAnalysis?.declarations_by_type">
          <div
            v-for="(declarations, type) in declarationAnalysis.declarations_by_type"
            :key="type"
            class="declaration-category"
          >
            <h4>{{ type.charAt(0).toUpperCase() + type.slice(1) }}</h4>
            <div class="declaration-list">
              <div
                v-for="decl in declarations.slice(0, 10)"
                :key="decl.name"
                class="declaration-item"
              >
                <div class="decl-header">
                  <span class="decl-name">{{ decl.name }}</span>
                  <span class="reusability-score" :class="getScoreClass(decl.reusability_score)">
                    {{ decl.reusability_score.toFixed(1) }}
                  </span>
                </div>
                <div class="decl-stats">
                  <span class="stat">
                    <i class="fas fa-code"></i>
                    {{ decl.definition_count }} def
                  </span>
                  <span class="stat">
                    <i class="fas fa-link"></i>
                    {{ decl.usage_count }} uses
                  </span>
                  <span class="stat">
                    <i class="fas fa-file"></i>
                    {{ decl.files.length }} files
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Reusability Insights -->
        <div class="insights-section" v-if="declarationAnalysis?.reusability_insights">
          <div class="insight-category">
            <h4><i class="fas fa-star"></i> Highly Reusable</h4>
            <div class="insight-list">
              <div
                v-for="item in declarationAnalysis.reusability_insights.highly_reusable.slice(0, 5)"
                :key="item.name"
                class="insight-item good"
              >
                <span class="item-name">{{ item.name }}</span>
                <span class="item-score">{{ item.reusability_score.toFixed(1) }}</span>
              </div>
            </div>
          </div>

          <div class="insight-category">
            <h4><i class="fas fa-exclamation-triangle"></i> Underutilized</h4>
            <div class="insight-list">
              <div
                v-for="item in declarationAnalysis.reusability_insights.underutilized.slice(0, 5)"
                :key="item.name"
                class="insight-item warning"
              >
                <span class="item-name">{{ item.name }}</span>
                <span class="item-usage">{{ item.usage_count }}/{{ item.definition_count }}</span>
              </div>
            </div>
          </div>

          <div class="insight-category">
            <h4><i class="fas fa-copy"></i> Potential Duplicates</h4>
            <div class="insight-list">
              <div
                v-for="item in declarationAnalysis.reusability_insights.potential_duplicates.slice(0, 5)"
                :key="item.name"
                class="insight-item danger"
              >
                <span class="item-name">{{ item.name }}</span>
                <span class="item-count">{{ item.definition_count }} definitions</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Duplicates Analysis -->
      <div v-if="activeAnalysisTab === 'duplicates'" class="tab-content">
        <div class="analysis-header">
          <h3>Code Duplication Analysis</h3>
          <div class="analysis-summary" v-if="duplicateAnalysis?.summary">
            <div class="summary-stat">
              <span class="label">Patterns Analyzed:</span>
              <span class="value">{{ duplicateAnalysis.summary.patterns_analyzed }}</span>
            </div>
            <div class="summary-stat">
              <span class="label">Candidates Found:</span>
              <span class="value">{{ duplicateAnalysis.summary.duplicate_candidates_found }}</span>
            </div>
            <div class="summary-stat">
              <span class="label">Similar Blocks:</span>
              <span class="value">{{ duplicateAnalysis.summary.total_similar_blocks }}</span>
            </div>
          </div>
        </div>

        <div class="duplicate-candidates" v-if="duplicateAnalysis?.duplicate_candidates">
          <div
            v-for="candidate in duplicateAnalysis.duplicate_candidates"
            :key="candidate.pattern"
            class="candidate-card"
          >
            <div class="candidate-header">
              <h4>{{ candidate.pattern }}</h4>
              <span class="priority-badge" :class="getPriorityClass(candidate.refactor_priority)">
                Priority: {{ candidate.refactor_priority.toFixed(1) }}
              </span>
            </div>
            <p class="potential-savings">{{ candidate.potential_savings }}</p>

            <div class="similar-blocks">
              <h5>Similar Code Blocks:</h5>
              <div class="block-list">
                <div
                  v-for="(block, index) in candidate.similar_blocks.slice(0, 3)"
                  :key="index"
                  class="code-block"
                >
                  <div class="block-header">
                    <span class="file-path">{{ block.file_path }}</span>
                    <span class="line-number">Line {{ block.line_number }}</span>
                    <span class="confidence">{{ (block.confidence * 100).toFixed(0) }}% match</span>
                  </div>
                  <pre class="code-content">{{ block.content }}</pre>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="recommendations" v-if="duplicateAnalysis?.recommendations">
          <h4><i class="fas fa-lightbulb"></i> Recommendations</h4>
          <ul class="recommendation-list">
            <li v-for="rec in duplicateAnalysis.recommendations" :key="rec">
              {{ rec }}
            </li>
          </ul>
        </div>
      </div>

      <!-- Refactoring Suggestions -->
      <div v-if="activeAnalysisTab === 'refactoring'" class="tab-content">
        <div class="analysis-header">
          <h3>Intelligent Refactoring Suggestions</h3>
        </div>

        <div class="suggestions-grid" v-if="refactoringSuggestions?.refactor_suggestions">
          <div
            v-for="suggestion in refactoringSuggestions.refactor_suggestions"
            :key="suggestion.type"
            class="suggestion-card"
            :class="suggestion.priority"
          >
            <div class="suggestion-header">
              <h4>{{ suggestion.type }}</h4>
              <span class="priority-badge" :class="suggestion.priority">
                {{ suggestion.priority.toUpperCase() }}
              </span>
            </div>
            <p class="suggestion-description">{{ suggestion.description }}</p>

            <div class="suggestion-details">
              <div class="detail-item">
                <span class="label">Impact:</span>
                <span class="value">{{ suggestion.impact }}</span>
              </div>
              <div class="detail-item">
                <span class="label">Effort:</span>
                <span class="value">{{ suggestion.effort }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="next-steps" v-if="refactoringSuggestions?.next_steps">
          <h4><i class="fas fa-tasks"></i> Next Steps</h4>
          <ol class="steps-list">
            <li v-for="step in refactoringSuggestions.next_steps" :key="step">
              {{ step }}
            </li>
          </ol>
        </div>
      </div>
    </div>

    <!-- Empty State -->
    <div v-else class="empty-analysis-state">
      <i class="fas fa-chart-bar"></i>
      <h3>No Analysis Data</h3>
      <p>Run the analysis to see detailed codebase insights</p>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import apiClient from '../utils/ApiClient'

export default {
  name: 'CodebaseAnalytics',
  setup() {
    // Reactive data
    const rootPath = ref('/home/kali/Desktop/AutoBot')
    const indexing = ref(false)
    const analyzing = ref(false)
    const activeAnalysisTab = ref('declarations')

    // Analysis data
    const indexStatus = ref(null)
    const declarationAnalysis = ref(null)
    const duplicateAnalysis = ref(null)
    const refactoringSuggestions = ref(null)

    // Computed
    const maxLanguageCount = computed(() => {
      if (!indexStatus.value?.languages) return 0
      return Math.max(...Object.values(indexStatus.value.languages))
    })

    const hasAnalysisData = computed(() => {
      return declarationAnalysis.value || duplicateAnalysis.value || refactoringSuggestions.value
    })

    const analysisTabs = [
      { id: 'declarations', label: 'Declarations', icon: 'fas fa-code' },
      { id: 'duplicates', label: 'Duplicates', icon: 'fas fa-copy' },
      { id: 'refactoring', label: 'Suggestions', icon: 'fas fa-magic' }
    ]

    // Methods
    const autoDetectPath = () => {
      rootPath.value = '/home/kali/Desktop/AutoBot'
    }

    const indexCodebase = async () => {
      if (!rootPath.value) return

      indexing.value = true
      try {
        const response = await apiClient.post('/code_search/index', {
          root_path: rootPath.value,
          force_reindex: false
        })

        if (response.data) {
          console.log('Indexing completed:', response.data)
          await getIndexStatus()
        }
      } catch (error) {
        console.error('Indexing failed:', error)
      } finally {
        indexing.value = false
      }
    }

    const getIndexStatus = async () => {
      try {
        const response = await apiClient.get('/code_search/analytics/stats')
        if (response.data) {
          indexStatus.value = response.data.index_statistics
        }
      } catch (error) {
        console.error('Failed to get index status:', error)
      }
    }

    const runDeclarationAnalysis = async () => {
      if (!rootPath.value) return

      try {
        const response = await apiClient.post('/code_search/analytics/declarations', {
          root_path: rootPath.value
        })

        if (response.data) {
          declarationAnalysis.value = response.data
        }
      } catch (error) {
        console.error('Declaration analysis failed:', error)
      }
    }

    const runDuplicateAnalysis = async () => {
      if (!rootPath.value) return

      try {
        const response = await apiClient.post('/code_search/analytics/duplicates', {
          root_path: rootPath.value
        })

        if (response.data) {
          duplicateAnalysis.value = response.data
        }
      } catch (error) {
        console.error('Duplicate analysis failed:', error)
      }
    }

    const getRefactoringSuggestions = async () => {
      if (!rootPath.value) return

      try {
        const response = await apiClient.post('/code_search/analytics/refactor-suggestions', {
          root_path: rootPath.value
        })

        if (response.data) {
          refactoringSuggestions.value = response.data
        }
      } catch (error) {
        console.error('Refactoring suggestions failed:', error)
      }
    }

    const runFullAnalysis = async () => {
      if (!rootPath.value) return

      analyzing.value = true
      try {
        await Promise.all([
          runDeclarationAnalysis(),
          runDuplicateAnalysis(),
          getRefactoringSuggestions()
        ])
      } catch (error) {
        console.error('Full analysis failed:', error)
      } finally {
        analyzing.value = false
      }
    }

    // Utility functions
    const getScoreClass = (score) => {
      if (score >= 7) return 'excellent'
      if (score >= 4) return 'good'
      if (score >= 2) return 'fair'
      return 'poor'
    }

    const getPriorityClass = (priority) => {
      if (priority >= 8) return 'high'
      if (priority >= 5) return 'medium'
      return 'low'
    }

    // Lifecycle
    onMounted(() => {
      getIndexStatus()
    })

    return {
      rootPath,
      indexing,
      analyzing,
      activeAnalysisTab,
      indexStatus,
      declarationAnalysis,
      duplicateAnalysis,
      refactoringSuggestions,
      maxLanguageCount,
      hasAnalysisData,
      analysisTabs,
      autoDetectPath,
      indexCodebase,
      runFullAnalysis,
      getScoreClass,
      getPriorityClass
    }
  }
}
</script>

<style scoped>
.codebase-analytics {
  padding: 1.5rem;
  max-width: 1400px;
  margin: 0 auto;
}

.analytics-header {
  text-align: center;
  margin-bottom: 2rem;
}

.analytics-header h2 {
  color: #1f2937;
  font-size: 2rem;
  margin-bottom: 0.5rem;
}

.analytics-header .subtitle {
  color: #6b7280;
  font-size: 1.1rem;
}

.control-panel {
  background: white;
  border-radius: 12px;
  padding: 1.5rem;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
  margin-bottom: 2rem;
}

.control-group {
  margin-bottom: 1rem;
}

.control-group label {
  display: block;
  font-weight: 600;
  color: #374151;
  margin-bottom: 0.5rem;
}

.path-input-group {
  display: flex;
  gap: 0.5rem;
}

.path-input {
  flex: 1;
  padding: 0.75rem;
  border: 2px solid #e5e7eb;
  border-radius: 8px;
  font-family: 'Fira Code', monospace;
}

.auto-detect-btn {
  padding: 0.75rem;
  background: #6366f1;
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.auto-detect-btn:hover {
  background: #4f46e5;
}

.action-buttons {
  display: flex;
  gap: 1rem;
  margin-top: 1rem;
}

.btn-primary, .btn-secondary {
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.btn-primary {
  background: #10b981;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #059669;
}

.btn-secondary {
  background: #6366f1;
  color: white;
}

.btn-secondary:hover:not(:disabled) {
  background: #4f46e5;
}

.btn-primary:disabled, .btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.status-card {
  background: white;
  border-radius: 12px;
  padding: 1.5rem;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
}

.status-card h3 {
  color: #1f2937;
  margin-bottom: 1rem;
  font-size: 1.1rem;
}

.stat-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0;
  border-bottom: 1px solid #f3f4f6;
}

.stat-item:last-child {
  border-bottom: none;
}

.stat-item .label {
  color: #6b7280;
  font-weight: 500;
}

.stat-item .value {
  font-weight: 600;
  color: #1f2937;
}

.stat-item .value.success {
  color: #10b981;
}

.stat-item .value.warning {
  color: #f59e0b;
}

.language-chart {
  space-y: 0.75rem;
}

.language-bar {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 0.75rem;
}

.language-name {
  width: 80px;
  font-size: 0.875rem;
  font-weight: 500;
  color: #374151;
}

.bar-container {
  flex: 1;
  height: 20px;
  background: #f3f4f6;
  border-radius: 10px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #6366f1, #8b5cf6);
  transition: width 0.3s ease;
}

.language-count {
  width: 40px;
  text-align: right;
  font-size: 0.875rem;
  font-weight: 600;
  color: #374151;
}

.empty-state {
  text-align: center;
  color: #6b7280;
  font-style: italic;
}

.analysis-tabs {
  background: white;
  border-radius: 12px;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.tab-buttons {
  display: flex;
  border-bottom: 1px solid #e5e7eb;
}

.tab-btn {
  flex: 1;
  padding: 1rem;
  background: #f9fafb;
  border: none;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  font-weight: 500;
}

.tab-btn:hover {
  background: #f3f4f6;
}

.tab-btn.active {
  background: white;
  color: #6366f1;
  border-bottom: 3px solid #6366f1;
}

.tab-content {
  padding: 2rem;
}

.analysis-header {
  margin-bottom: 2rem;
}

.analysis-header h3 {
  color: #1f2937;
  margin-bottom: 1rem;
}

.analysis-summary {
  display: flex;
  gap: 2rem;
  flex-wrap: wrap;
}

.summary-stat {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.summary-stat .label {
  color: #6b7280;
  font-size: 0.875rem;
}

.summary-stat .value {
  font-weight: 700;
  font-size: 1.25rem;
  color: #1f2937;
}

.declarations-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.declaration-category h4 {
  color: #1f2937;
  margin-bottom: 1rem;
  font-size: 1.1rem;
}

.declaration-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.declaration-item {
  background: #f9fafb;
  border-radius: 8px;
  padding: 1rem;
  border-left: 4px solid #e5e7eb;
}

.decl-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.5rem;
}

.decl-name {
  font-family: 'Fira Code', monospace;
  font-weight: 600;
  color: #1f2937;
}

.reusability-score {
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 700;
}

.reusability-score.excellent {
  background: #10b981;
  color: white;
}

.reusability-score.good {
  background: #06b6d4;
  color: white;
}

.reusability-score.fair {
  background: #f59e0b;
  color: white;
}

.reusability-score.poor {
  background: #ef4444;
  color: white;
}

.decl-stats {
  display: flex;
  gap: 1rem;
}

.decl-stats .stat {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.875rem;
  color: #6b7280;
}

.insights-section {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 1.5rem;
}

.insight-category h4 {
  color: #1f2937;
  margin-bottom: 1rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.insight-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.insight-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.75rem;
  border-radius: 6px;
  font-size: 0.875rem;
}

.insight-item.good {
  background: #d1fae5;
  border-left: 4px solid #10b981;
}

.insight-item.warning {
  background: #fef3c7;
  border-left: 4px solid #f59e0b;
}

.insight-item.danger {
  background: #fee2e2;
  border-left: 4px solid #ef4444;
}

.item-name {
  font-family: 'Fira Code', monospace;
  font-weight: 500;
}

.duplicate-candidates {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.candidate-card {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 1.5rem;
}

.candidate-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.candidate-header h4 {
  color: #1f2937;
  margin: 0;
}

.priority-badge {
  padding: 0.25rem 0.75rem;
  border-radius: 20px;
  font-size: 0.75rem;
  font-weight: 600;
}

.priority-badge.high {
  background: #fee2e2;
  color: #dc2626;
}

.priority-badge.medium {
  background: #fef3c7;
  color: #d97706;
}

.priority-badge.low {
  background: #dbeafe;
  color: #2563eb;
}

.potential-savings {
  color: #6b7280;
  margin-bottom: 1rem;
}

.similar-blocks h5 {
  color: #374151;
  margin-bottom: 1rem;
}

.block-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.code-block {
  background: #f9fafb;
  border-radius: 6px;
  overflow: hidden;
}

.block-header {
  background: #e5e7eb;
  padding: 0.5rem 1rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 0.875rem;
}

.file-path {
  font-family: 'Fira Code', monospace;
  color: #374151;
}

.line-number {
  color: #6b7280;
}

.confidence {
  font-weight: 600;
  color: #059669;
}

.code-content {
  padding: 1rem;
  margin: 0;
  font-family: 'Fira Code', monospace;
  font-size: 0.875rem;
  line-height: 1.5;
  overflow-x: auto;
}

.suggestions-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.suggestion-card {
  border-radius: 8px;
  padding: 1.5rem;
  border-left: 4px solid;
}

.suggestion-card.high {
  background: #fee2e2;
  border-left-color: #dc2626;
}

.suggestion-card.medium {
  background: #fef3c7;
  border-left-color: #d97706;
}

.suggestion-card.low {
  background: #dbeafe;
  border-left-color: #2563eb;
}

.suggestion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.suggestion-header h4 {
  color: #1f2937;
  margin: 0;
}

.suggestion-description {
  color: #4b5563;
  margin-bottom: 1rem;
  line-height: 1.5;
}

.suggestion-details {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.detail-item {
  display: flex;
  gap: 0.5rem;
}

.detail-item .label {
  font-weight: 600;
  color: #374151;
}

.detail-item .value {
  color: #6b7280;
}

.recommendations, .next-steps {
  margin-top: 2rem;
}

.recommendations h4, .next-steps h4 {
  color: #1f2937;
  margin-bottom: 1rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.recommendation-list, .steps-list {
  padding-left: 1.5rem;
}

.recommendation-list li, .steps-list li {
  color: #4b5563;
  margin-bottom: 0.5rem;
  line-height: 1.5;
}

.empty-analysis-state {
  text-align: center;
  padding: 4rem 2rem;
  color: #6b7280;
}

.empty-analysis-state i {
  font-size: 4rem;
  margin-bottom: 1rem;
  opacity: 0.5;
}

.empty-analysis-state h3 {
  font-size: 1.5rem;
  margin-bottom: 0.5rem;
}
</style>
