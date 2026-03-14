<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import EmptyState from '@/components/ui/EmptyState.vue'
import DependencyTreemap from '@/components/charts/DependencyTreemap.vue'
import ModuleImportsChart from '@/components/charts/ModuleImportsChart.vue'
import ImportTreeChart from '@/components/charts/ImportTreeChart.vue'
import FunctionCallGraph from '@/components/charts/FunctionCallGraph.vue'

const { t: _t } = useI18n()

interface DependencyNode {
  id: string
  name: string
  type?: string
}
interface DependencyEdge {
  source: string
  target: string
  type?: string
}
interface ModuleData {
  name: string
  path?: string
  import_count: number
  [key: string]: unknown
}
interface ExternalDependency {
  name: string
  usage_count?: number
  package?: string
  [key: string]: unknown
}
type CircularDependency =
  | string[]
  | { modules: string[]; cycle?: string[]; length?: number; severity?: string }
interface DependencySummary {
  total_modules?: number
  total_import_relationships?: number
  external_dependency_count?: number
  circular_dependency_count?: number
}
interface DependencyGraph {
  nodes: DependencyNode[]
  edges: DependencyEdge[]
  summary?: DependencySummary
  modules?: ModuleData[]
  external_dependencies?: ExternalDependency[]
  circular_dependencies?: CircularDependency[]
  import_relationships?: DependencyEdge[]
}
interface ImportTreeNode {
  name: string
  path: string
  children?: ImportTreeNode[]
  imports?: string[]
}
interface OrphanedFunction {
  id: string
  name: string
  full_name: string
  module: string
  class: string | null
  file: string
  line: number
  is_async: boolean
}

interface Props {
  dependencyData: DependencyGraph | null
  dependencyLoading: boolean
  dependencyError: string
  importTreeData: ImportTreeNode[]
  importTreeLoading: boolean
  importTreeError: string
  callGraphData: DependencyGraph
  callGraphSummary: Record<string, unknown> | null
  callGraphOrphaned: OrphanedFunction[]
  callGraphLoading: boolean
  callGraphError: string
}

defineProps<Props>()

const emit = defineEmits<{
  'load-dependency-data': []
  'load-import-tree': []
  'load-call-graph': []
  'file-navigate': [filePath: string]
  'function-select': [functionId: string]
}>()
</script>

<template>
  <!-- Dependency Analysis Section -->
  <div class="dependency-section">
    <div class="section-header">
      <h3><i class="fas fa-project-diagram"></i> {{ $t('analytics.codebase.dependencies.title') }}</h3>
      <button @click="emit('load-dependency-data')" class="refresh-btn" :disabled="dependencyLoading">
        <i :class="dependencyLoading ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
      </button>
    </div>

    <div v-if="dependencyLoading" class="charts-loading">
      <i class="fas fa-spinner fa-spin"></i>
      <span>{{ $t('analytics.codebase.dependencies.analyzing') }}</span>
    </div>

    <div v-else-if="dependencyError" class="charts-error">
      <i class="fas fa-exclamation-triangle"></i>
      <span>{{ dependencyError }}</span>
      <button @click="emit('load-dependency-data')" class="btn-link">{{ $t('analytics.codebase.actions.retry') }}</button>
    </div>

    <div v-else-if="dependencyData" class="dependency-grid">
      <!-- Summary Stats -->
      <div v-if="dependencyData.summary" class="chart-summary">
        <div class="summary-stat">
          <span class="summary-value">{{ dependencyData.summary.total_modules?.toLocaleString() || 0 }}</span>
          <span class="summary-label">{{ $t('analytics.codebase.dependencies.pythonModules') }}</span>
        </div>
        <div class="summary-stat">
          <span class="summary-value">{{ dependencyData.summary.total_import_relationships?.toLocaleString() || 0 }}</span>
          <span class="summary-label">{{ $t('analytics.codebase.dependencies.importRelationships') }}</span>
        </div>
        <div class="summary-stat">
          <span class="summary-value">{{ dependencyData.summary.external_dependency_count || 0 }}</span>
          <span class="summary-label">{{ $t('analytics.codebase.dependencies.externalPackages') }}</span>
        </div>
        <div class="summary-stat" :class="{ 'race-highlight': (dependencyData.summary.circular_dependency_count ?? 0) > 0 }">
          <span class="summary-value">{{ dependencyData.summary.circular_dependency_count || 0 }}</span>
          <span class="summary-label">{{ $t('analytics.codebase.dependencies.circularDependencies') }}</span>
        </div>
      </div>

      <!-- Charts Row: External Dependencies + Top Importing Modules -->
      <div class="charts-row">
        <DependencyTreemap
          v-if="dependencyData.external_dependencies && dependencyData.external_dependencies.length > 0"
          :data="(dependencyData.external_dependencies as any)"
          :title="$t('analytics.codebase.charts.externalDependencies')"
          :subtitle="$t('analytics.codebase.charts.packageUsageAcrossCodebase')"
          :height="350"
          class="chart-item"
        />
        <div v-else class="chart-empty-slot">
          <EmptyState icon="fas fa-cube" message="No external dependencies found" />
        </div>
        <ModuleImportsChart
          v-if="dependencyData.modules && dependencyData.modules.length > 0"
          :data="(dependencyData.modules.filter(m => m.import_count > 0) as any)"
          :title="$t('analytics.codebase.charts.modulesWithMostImports')"
          :subtitle="$t('analytics.codebase.charts.filesWithHighestDependencyCount')"
          :height="350"
          :maxModules="12"
          class="chart-item"
        />
        <div v-else class="chart-empty-slot">
          <EmptyState icon="fas fa-file-import" message="No module data available" />
        </div>
      </div>

      <!-- Circular Dependencies Warning -->
      <div v-if="dependencyData.circular_dependencies && dependencyData.circular_dependencies.length > 0" class="circular-deps-warning">
        <div class="warning-header">
          <i class="fas fa-exclamation-triangle"></i>
          <span>{{ $t('analytics.codebase.dependencies.circularDetected') }}</span>
        </div>
        <div class="circular-deps-list">
          <div
            v-for="(cycle, index) in dependencyData.circular_dependencies.slice(0, 10)"
            :key="index"
            class="circular-dep-item"
          >
            <i class="fas fa-sync-alt"></i>
            <span>{{ Array.isArray(cycle) ? cycle.join(' ↔ ') : (cycle.modules || []).join(' ↔ ') }}</span>
          </div>
        </div>
        <div v-if="dependencyData.circular_dependencies.length > 10" class="show-more">
          <span class="muted">and {{ dependencyData.circular_dependencies.length - 10 }} more...</span>
        </div>
      </div>

      <!-- Top External Dependencies Table -->
      <div v-if="dependencyData.external_dependencies && dependencyData.external_dependencies.length > 0" class="external-deps-table">
        <h4><i class="fas fa-cube"></i> {{ $t('analytics.codebase.dependencies.topExternal') }}</h4>
        <div class="deps-table-content">
          <div
            v-for="(dep, index) in dependencyData.external_dependencies.slice(0, 20)"
            :key="index"
            class="dep-row"
          >
            <span class="dep-name">{{ dep.package }}</span>
            <span class="dep-count">{{ dep.usage_count }} imports</span>
          </div>
        </div>
      </div>
    </div>

    <EmptyState
      v-else
      icon="fas fa-project-diagram"
      :message="$t('analytics.codebase.dependencies.noData')"
    >
      <template #actions>
        <button @click="emit('load-dependency-data')" class="btn-primary" :disabled="dependencyLoading">
          <i class="fas fa-project-diagram"></i> {{ $t('analytics.codebase.dependencies.analyze') }}
        </button>
      </template>
    </EmptyState>
  </div>

  <!-- Import Tree Section -->
  <div class="import-tree-section">
    <div class="section-header">
      <h3><i class="fas fa-sitemap"></i> {{ $t('analytics.codebase.importTree.title') }}</h3>
      <button @click="emit('load-import-tree')" class="refresh-btn" :disabled="importTreeLoading">
        <i :class="importTreeLoading ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
        {{ importTreeLoading ? $t('analytics.codebase.actions.loading') : $t('analytics.codebase.actions.refresh') }}
      </button>
    </div>

    <!-- Error state -->
    <div v-if="importTreeError" class="section-error">
      <i class="fas fa-exclamation-triangle"></i>
      <span>{{ importTreeError }}</span>
      <button @click="emit('load-import-tree')" class="btn-link">{{ $t('analytics.codebase.actions.retry') }}</button>
    </div>

    <!-- Import Tree Content -->
    <div v-else-if="importTreeData && importTreeData.length > 0" class="import-tree-content">
      <ImportTreeChart
        :data="importTreeData"
        :title="$t('analytics.codebase.charts.fileImportRelationships')"
        :subtitle="$t('analytics.codebase.charts.clickToExpandImports')"
        :height="500"
        :loading="importTreeLoading"
        :error="importTreeError"
        @navigate="(path: string) => emit('file-navigate', path)"
      />
    </div>

    <!-- Empty state -->
    <EmptyState
      v-else-if="!importTreeLoading"
      icon="fas fa-sitemap"
      :message="$t('analytics.codebase.importTree.noData')"
      variant="info"
    >
      <template #actions>
        <button @click="emit('load-import-tree')" class="btn-primary" :disabled="importTreeLoading">
          <i class="fas fa-sitemap"></i> {{ $t('analytics.codebase.importTree.analyze') }}
        </button>
      </template>
    </EmptyState>
  </div>

  <!-- Function Call Graph Section -->
  <div class="call-graph-section">
    <div class="section-header">
      <h3><i class="fas fa-project-diagram"></i> {{ $t('analytics.codebase.callGraph.title') }}</h3>
      <button @click="emit('load-call-graph')" class="refresh-btn" :disabled="callGraphLoading">
        <i :class="callGraphLoading ? 'fas fa-spinner fa-spin' : 'fas fa-sync-alt'"></i>
        {{ callGraphLoading ? $t('analytics.codebase.actions.loading') : $t('analytics.codebase.actions.refresh') }}
      </button>
    </div>

    <!-- Error state -->
    <div v-if="callGraphError" class="section-error">
      <i class="fas fa-exclamation-triangle"></i>
      <span>{{ callGraphError }}</span>
      <button @click="emit('load-call-graph')" class="btn-link">{{ $t('analytics.codebase.actions.retry') }}</button>
    </div>

    <!-- Call Graph Content -->
    <div v-else-if="callGraphData && callGraphData.nodes?.length > 0" class="call-graph-content">
      <FunctionCallGraph
        :data="callGraphData"
        :summary="(callGraphSummary as any)"
        :orphaned-functions="callGraphOrphaned"
        :title="$t('analytics.codebase.charts.functionCallRelationships')"
        :subtitle="$t('analytics.codebase.charts.viewFunctionCalls')"
        :height="600"
        :loading="callGraphLoading"
        :error="callGraphError"
        @select="(id: string) => emit('function-select', id)"
      />
    </div>

    <!-- Empty state -->
    <EmptyState
      v-else-if="!callGraphLoading"
      icon="fas fa-project-diagram"
      :message="$t('analytics.codebase.callGraph.noData')"
      variant="info"
    >
      <template #actions>
        <button @click="emit('load-call-graph')" class="btn-primary" :disabled="callGraphLoading">
          <i class="fas fa-project-diagram"></i> {{ $t('analytics.codebase.callGraph.analyze') }}
        </button>
      </template>
    </EmptyState>
  </div>
</template>

<style scoped>
/* Shared button styles */
.btn-primary {
  padding: 10px 20px;
  border: none;
  border-radius: var(--radius-lg);
  font-weight: var(--font-semibold);
  cursor: pointer;
  transition: var(--transition-all);
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--chart-green);
  color: var(--text-on-success);
}

.btn-primary:hover:not(:disabled) {
  background: var(--color-success-dark);
  transform: translateY(-1px);
}

.btn-primary:disabled {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  cursor: not-allowed;
  transform: none;
}

.btn-link {
  background: none;
  border: none;
  color: var(--chart-blue);
  cursor: pointer;
  text-decoration: underline;
  font-size: 0.9em;
}

.btn-link:hover {
  color: var(--color-info-dark);
}

.refresh-btn {
  background: var(--bg-tertiary);
  border: 1px solid var(--bg-hover);
  color: var(--text-secondary);
  padding: 6px 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.refresh-btn:hover {
  background: var(--bg-hover);
  color: var(--text-on-primary);
}

/* Charts loading / error shared states */
.charts-loading,
.charts-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  gap: 12px;
  color: var(--text-muted);
}

.charts-loading i {
  font-size: 32px;
  color: var(--chart-blue);
}

.charts-error i {
  font-size: 32px;
  color: var(--color-error);
}

.charts-error {
  color: var(--color-error-light);
}

/* Chart summary grid */
.chart-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.summary-stat {
  background: rgba(51, 65, 85, 0.5);
  border-radius: 8px;
  padding: 16px;
  text-align: center;
  border: 1px solid rgba(71, 85, 105, 0.5);
  transition: all 0.2s ease;
}

.summary-stat:hover {
  background: rgba(51, 65, 85, 0.7);
  border-color: rgba(59, 130, 246, 0.5);
}

.summary-stat.race-highlight {
  background: rgba(249, 115, 22, 0.2);
  border-color: rgba(249, 115, 22, 0.5);
}

.summary-stat.race-highlight:hover {
  background: rgba(249, 115, 22, 0.3);
}

.summary-value {
  font-size: 2rem;
  font-weight: 700;
  color: var(--text-secondary);
  line-height: 1;
}

.summary-stat.race-highlight .summary-value {
  color: var(--chart-orange);
}

.summary-label {
  font-size: 0.85rem;
  color: var(--text-muted);
  margin-top: 4px;
  display: block;
}

/* Charts row */
.charts-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.chart-item {
  min-height: 350px;
}

.chart-empty-slot {
  background: rgba(30, 41, 59, 0.5);
  border-radius: 8px;
  padding: 16px;
  border: 1px solid rgba(71, 85, 105, 0.5);
  min-height: 350px;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* Responsive charts */
@media (max-width: 1200px) {
  .chart-summary {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 900px) {
  .charts-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 600px) {
  .chart-summary {
    grid-template-columns: 1fr;
  }

  .summary-value {
    font-size: 1.5rem;
  }
}

/* Dependency Section */
.dependency-section {
  margin-top: 32px;
  padding: 24px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 12px;
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.dependency-section .section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(71, 85, 105, 0.5);
}

.dependency-section .section-header h3 {
  margin: 0;
  color: var(--text-secondary);
  font-size: 1.25rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.dependency-section .section-header h3 i {
  color: var(--chart-purple);
}

.dependency-grid {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* Circular Dependencies Warning */
.circular-deps-warning {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 8px;
  padding: 16px;
}

.circular-deps-warning .warning-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--color-error-light);
  margin-bottom: 12px;
}

.circular-deps-warning .warning-header i {
  color: var(--color-error);
}

.circular-deps-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.circular-dep-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 4px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.circular-dep-item i {
  color: var(--color-warning);
}

.show-more {
  text-align: center;
  padding: 12px;
  background: var(--bg-secondary);
  border-radius: 6px;
  margin-top: 8px;
}

.muted {
  color: var(--text-tertiary);
  font-style: italic;
}

/* External Dependencies Table */
.external-deps-table {
  background: rgba(30, 41, 59, 0.5);
  border-radius: 8px;
  padding: 16px;
  border: 1px solid rgba(71, 85, 105, 0.3);
}

.external-deps-table h4 {
  margin: 0 0 16px 0;
  color: var(--text-secondary);
  font-size: 1rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.external-deps-table h4 i {
  color: var(--chart-teal);
}

.deps-table-content {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px;
}

.dep-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: rgba(51, 65, 85, 0.4);
  border-radius: 4px;
  transition: background 0.2s ease;
}

.dep-row:hover {
  background: rgba(51, 65, 85, 0.6);
}

.dep-name {
  font-family: 'JetBrains Mono', monospace;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.dep-count {
  font-size: 0.8rem;
  color: var(--text-muted);
  background: rgba(59, 130, 246, 0.2);
  padding: 2px 8px;
  border-radius: 4px;
}

/* Import Tree Section */
.import-tree-section {
  margin-top: 32px;
  padding: 24px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 12px;
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.import-tree-section .section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.import-tree-section .section-header h3 {
  margin: 0;
  color: var(--text-secondary);
  font-size: 1.1rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 10px;
}

.import-tree-section .section-header h3 i {
  color: var(--chart-teal);
}

.import-tree-section .section-error {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 8px;
  color: var(--color-error-light);
}

.import-tree-section .section-error i {
  color: var(--color-error);
}

.import-tree-content {
  margin-top: 16px;
}

/* Call Graph Section */
.call-graph-section {
  margin-top: 32px;
  padding: 24px;
  background: rgba(30, 41, 59, 0.5);
  border-radius: 12px;
  border: 1px solid rgba(71, 85, 105, 0.5);
}

.call-graph-section .section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.call-graph-section .section-header h3 {
  margin: 0;
  color: var(--text-secondary);
  font-size: 1.1rem;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 10px;
}

.call-graph-section .section-header h3 i {
  color: var(--chart-purple);
}

.call-graph-section .section-error {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 8px;
  color: var(--color-error-light);
}

.call-graph-section .section-error i {
  color: var(--color-error);
}

.call-graph-content {
  margin-top: 16px;
}
</style>
