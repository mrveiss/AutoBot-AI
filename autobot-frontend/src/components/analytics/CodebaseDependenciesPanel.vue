<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import TruncationNotice from './TruncationNotice.vue'
import { useShowMore, BaseButton } from '@autobot/ui'
import { useI18n } from 'vue-i18n'
import EmptyState from '@/components/ui/EmptyState.vue'
import DependencyTreemap from '@/components/charts/DependencyTreemap.vue'
import ModuleImportsChart from '@/components/charts/ModuleImportsChart.vue'
import Icon from '@/components/ui/Icon.vue'

// Lazy-load Cytoscape-based components to defer ~300KB library loading
const ImportTreeChart = defineAsyncComponent(() => import('@/components/charts/ImportTreeChart.vue'))
const FunctionCallGraph = defineAsyncComponent(() => import('@/components/charts/FunctionCallGraph.vue'))

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

const props = defineProps<Props>()

// #12741: the notice under a capped list is its "show more" control.
const { visible, shown, showMore } = useShowMore(10, () => props.dependencyData)

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
      <h3><Icon name="project-diagram" /> {{ $t('analytics.codebase.dependencies.title') }}</h3>
      <button @click="emit('load-dependency-data')" class="refresh-btn" :disabled="dependencyLoading">
        <Icon :name="dependencyLoading ? 'spinner' : 'sync-alt'" :spin="dependencyLoading" />
      </button>
    </div>

    <div v-if="dependencyLoading" class="charts-loading">
      <Icon name="spinner" :spin="true" />
      <span>{{ $t('analytics.codebase.dependencies.analyzing') }}</span>
    </div>

    <div v-else-if="dependencyError" class="charts-error">
      <Icon name="exclamation-triangle" />
      <span>{{ dependencyError }}</span>
      <BaseButton variant="link" size="sm" @click="emit('load-dependency-data')">{{ $t('analytics.codebase.actions.retry') }}</BaseButton>
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
          <EmptyState icon="cube" message="No external dependencies found" />
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
          <EmptyState icon="file-import" message="No module data available" />
        </div>
      </div>

      <!-- Circular Dependencies Warning -->
      <div v-if="dependencyData.circular_dependencies && dependencyData.circular_dependencies.length > 0" class="circular-deps-warning">
        <div class="warning-header">
          <Icon name="exclamation-triangle" />
          <span>{{ $t('analytics.codebase.dependencies.circularDetected') }}</span>
        </div>
        <div class="circular-deps-list">
          <div
            v-for="(cycle, index) in visible('circular', dependencyData.circular_dependencies)"
            :key="index"
            class="circular-dep-item"
          >
            <Icon name="sync-alt" />
            <span>{{ Array.isArray(cycle) ? cycle.join(' ↔ ') : (cycle.modules || []).join(' ↔ ') }}</span>
          </div>
        </div>
        <TruncationNotice :shown="shown('circular', dependencyData.circular_dependencies.length)" :total="dependencyData.circular_dependencies.length" :step="10" @show-more="showMore('circular')" />
      </div>

      <!-- Top External Dependencies Table -->
      <div v-if="dependencyData.external_dependencies && dependencyData.external_dependencies.length > 0" class="external-deps-table">
        <h4><Icon name="cube" /> {{ $t('analytics.codebase.dependencies.topExternal') }}</h4>
        <div class="deps-table-content">
          <div
            v-for="(dep, index) in visible('external', dependencyData.external_dependencies, 20)"
            :key="index"
            class="dep-row"
          >
            <span class="dep-name">{{ dep.package }}</span>
            <span class="dep-count">{{ $t('analytics.codebase.shared.imports', { count: dep.usage_count }, dep.usage_count ?? 0) }}</span>
          </div>
          <TruncationNotice :shown="shown('external', dependencyData.external_dependencies.length, 20)" :total="dependencyData.external_dependencies.length" :step="20" @show-more="showMore('external', 20)" />
          <!-- The server returns the top 50 packages; the summary holds the real count. -->
          <TruncationNotice v-if="(dependencyData.summary?.external_dependency_count ?? 0) > dependencyData.external_dependencies.length" :shown="dependencyData.external_dependencies.length" :total="dependencyData.summary?.external_dependency_count ?? 0" server-limited />
        </div>
      </div>
    </div>

    <EmptyState
      v-else
      icon="project-diagram"
      :message="$t('analytics.codebase.dependencies.noData')"
    >
      <template #actions>
        <BaseButton variant="success" @click="emit('load-dependency-data')" :disabled="dependencyLoading">
          <Icon name="project-diagram" /> {{ $t('analytics.codebase.dependencies.analyze') }}
        </BaseButton>
      </template>
    </EmptyState>
  </div>

  <!-- Import Tree Section -->
  <div class="import-tree-section">
    <div class="section-header">
      <h3><Icon name="sitemap" /> {{ $t('analytics.codebase.importTree.title') }}</h3>
      <button @click="emit('load-import-tree')" class="refresh-btn" :disabled="importTreeLoading">
        <Icon :name="importTreeLoading ? 'spinner' : 'sync-alt'" :spin="importTreeLoading" />
        {{ importTreeLoading ? $t('analytics.codebase.actions.loading') : $t('analytics.codebase.actions.refresh') }}
      </button>
    </div>

    <!-- Error state -->
    <div v-if="importTreeError" class="section-error">
      <Icon name="exclamation-triangle" />
      <span>{{ importTreeError }}</span>
      <BaseButton variant="link" size="sm" @click="emit('load-import-tree')">{{ $t('analytics.codebase.actions.retry') }}</BaseButton>
    </div>

    <!-- Import Tree Content with Suspense -->
    <div v-else-if="importTreeData && importTreeData.length > 0" class="import-tree-content">
      <Suspense>
        <template #default>
          <ImportTreeChart
            :data="importTreeData"
            :title="$t('analytics.codebase.charts.fileImportRelationships')"
            :subtitle="$t('analytics.codebase.charts.clickToExpandImports')"
            :height="500"
            :loading="importTreeLoading"
            :error="importTreeError"
            @navigate="(path: string) => emit('file-navigate', path)"
          />
        </template>
        <template #fallback>
          <div class="loading-skeleton">
            <div class="skeleton-header"></div>
            <div class="skeleton-content"></div>
          </div>
        </template>
      </Suspense>
    </div>

    <!-- Empty state -->
    <EmptyState
      v-else-if="!importTreeLoading"
      icon="sitemap"
      :message="$t('analytics.codebase.importTree.noData')"
      variant="info"
    >
      <template #actions>
        <BaseButton variant="success" @click="emit('load-import-tree')" :disabled="importTreeLoading">
          <Icon name="sitemap" /> {{ $t('analytics.codebase.importTree.analyze') }}
        </BaseButton>
      </template>
    </EmptyState>
  </div>

  <!-- Function Call Graph Section -->
  <div class="call-graph-section">
    <div class="section-header">
      <h3><Icon name="project-diagram" /> {{ $t('analytics.codebase.callGraph.title') }}</h3>
      <button @click="emit('load-call-graph')" class="refresh-btn" :disabled="callGraphLoading">
        <Icon :name="callGraphLoading ? 'spinner' : 'sync-alt'" :spin="callGraphLoading" />
        {{ callGraphLoading ? $t('analytics.codebase.actions.loading') : $t('analytics.codebase.actions.refresh') }}
      </button>
    </div>

    <!-- Error state -->
    <div v-if="callGraphError" class="section-error">
      <Icon name="exclamation-triangle" />
      <span>{{ callGraphError }}</span>
      <BaseButton variant="link" size="sm" @click="emit('load-call-graph')">{{ $t('analytics.codebase.actions.retry') }}</BaseButton>
    </div>

    <!-- Call Graph Content with Suspense -->
    <div v-else-if="callGraphData && callGraphData.nodes?.length > 0" class="call-graph-content">
      <Suspense>
        <template #default>
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
        </template>
        <template #fallback>
          <div class="loading-skeleton">
            <div class="skeleton-header"></div>
            <div class="skeleton-content-large"></div>
          </div>
        </template>
      </Suspense>
    </div>

    <!-- Empty state -->
    <EmptyState
      v-else-if="!callGraphLoading"
      icon="project-diagram"
      :message="$t('analytics.codebase.callGraph.noData')"
      variant="info"
    >
      <template #actions>
        <BaseButton variant="success" @click="emit('load-call-graph')" :disabled="callGraphLoading">
          <Icon name="project-diagram" /> {{ $t('analytics.codebase.callGraph.analyze') }}
        </BaseButton>
      </template>
    </EmptyState>
  </div>
</template>

<style scoped src="@/design-system/styles/panel-dependencies-charts-shared.css"></style>

<style scoped>
.refresh-btn {
  background: var(--bg-tertiary);
  border: 1px solid var(--bg-hover);
  color: var(--text-secondary);
  padding: var(--spacing-1-5) var(--spacing-2);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--duration-200);
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
  gap: var(--spacing-3);
  color: var(--text-muted);
}

/* Chart summary grid */
.chart-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--spacing-4);
  margin-bottom: var(--spacing-4);
}

/* Charts row */
.charts-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-5);
}

.chart-item {
  min-height: 350px;
}

.chart-empty-slot {
  background: rgba(30, 41, 59, 0.5);
  border-radius: var(--radius-lg);
  padding: var(--spacing-4);
  border: 1px solid rgba(71, 85, 105, 0.5);
  min-height: 350px;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* Dependency Section */
.dependency-section {
  margin-top: var(--spacing-8);
  padding: var(--spacing-6);
  background: rgba(30, 41, 59, 0.5);
  border-radius: var(--radius-xl);
  border: 1px solid rgba(71, 85, 105, 0.5);
}

/* Loading Skeleton */
.loading-skeleton {
  min-height: 500px;
  display: flex;
  flex-direction: column;
  gap: var(--spacing-4);
  padding: var(--spacing-6);
  background: rgba(30, 41, 59, 0.3);
  border-radius: var(--radius-lg);
  border: 1px solid rgba(71, 85, 105, 0.3);
}

.skeleton-header {
  height: 24px;
  background: linear-gradient(90deg, rgba(71, 85, 105, 0.3) 0%, rgba(71, 85, 105, 0.5) 50%, rgba(71, 85, 105, 0.3) 100%);
  background-size: 200% 100%;
  animation: loading 1.5s infinite;
  border-radius: var(--radius-default);
  width: 40%;
}

.skeleton-content {
  flex: 1;
  background: linear-gradient(90deg, rgba(71, 85, 105, 0.2) 0%, rgba(71, 85, 105, 0.4) 50%, rgba(71, 85, 105, 0.2) 100%);
  background-size: 200% 100%;
  animation: loading 1.5s infinite;
  border-radius: var(--radius-default);
  min-height: 400px;
}

.skeleton-content-large {
  flex: 1;
  background: linear-gradient(90deg, rgba(71, 85, 105, 0.2) 0%, rgba(71, 85, 105, 0.4) 50%, rgba(71, 85, 105, 0.2) 100%);
  background-size: 200% 100%;
  animation: loading 1.5s infinite;
  border-radius: var(--radius-default);
  min-height: 550px;
}

@keyframes loading {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}
</style>
