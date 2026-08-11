<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2026 mrveiss -->
<!-- Author: mrveiss -->

<!-- Issue #13506: "what breaks if I change this" over the resolved code graph. -->
<template>
  <div class="impact-panel analytics-section">
    <h3>
      <Icon name="sitemap" /> {{ $t('analytics.codebase.impact.title') }}
    </h3>
    <p class="section-hint">{{ $t('analytics.codebase.impact.hint') }}</p>

    <form class="impact-form" @submit.prevent="run">
      <input
        v-model="nodeId"
        type="text"
        class="impact-input"
        :placeholder="$t('analytics.codebase.impact.nodeIdPlaceholder')"
        :aria-label="$t('analytics.codebase.impact.nodeIdLabel')"
      />
      <button type="submit" class="action-btn primary" :disabled="loading || !nodeId.trim()">
        <Icon :name="loading ? 'spinner' : 'search'" :class="{ 'fa-spin': loading }" />
        {{ loading ? $t('analytics.codebase.impact.analyzing') : $t('analytics.codebase.impact.analyze') }}
      </button>
    </form>

    <div v-if="error" class="impact-error">
      <Icon name="exclamation-triangle" />
      <span>{{ error }}</span>
    </div>

    <!-- "The graph was never built" is a different answer from "no callers",
         and must not render as an empty result. -->
    <EmptyState
      v-else-if="notIndexed"
      icon="database"
      :title="$t('analytics.codebase.impact.notIndexedTitle')"
      :description="$t('analytics.codebase.impact.notIndexedBody')"
    />

    <div v-else-if="result" class="impact-result">
      <!-- #13468: the whole point of the contract. A depth-capped or
           partially-resolved walk is a LOWER BOUND, and saying so has to be
           impossible to miss — a partial list shown as complete reads as
           evidence that nothing else is affected. -->
      <div v-if="isPartial" class="impact-partial" role="status">
        <Icon name="exclamation-triangle" />
        <div>
          <strong>{{ $t('analytics.codebase.impact.partialTitle') }}</strong>
          <p>
            {{
              result.depth_capped
                ? $t('analytics.codebase.impact.partialDepth', {
                    depth: result.max_depth,
                    frontier: result.depth_capped_frontier?.length ?? 0,
                  })
                : $t('analytics.codebase.impact.partialUnresolved', {
                    count: result.unresolved_edge_count ?? 0,
                  })
            }}
          </p>
        </div>
      </div>

      <div class="impact-summary">
        <div class="impact-metric">
          <span class="metric-value">{{ callerCount }}</span>
          <span class="metric-label">
            {{ isPartial
              ? $t('analytics.codebase.impact.callersAtLeast')
              : $t('analytics.codebase.impact.callers') }}
          </span>
        </div>
        <div class="impact-metric">
          <span class="metric-value">{{ result.resolved_edge_count ?? 0 }}</span>
          <span class="metric-label">{{ $t('analytics.codebase.impact.edgesResolved') }}</span>
        </div>
        <!-- Reported beside the resolved count, never folded into one score. -->
        <div class="impact-metric" :class="{ warn: (result.unresolved_edge_count ?? 0) > 0 }">
          <span class="metric-value">{{ result.unresolved_edge_count ?? 0 }}</span>
          <span class="metric-label">{{ $t('analytics.codebase.impact.edgesUnresolved') }}</span>
        </div>
        <div class="impact-metric">
          <span class="metric-value">{{ result.depth_reached ?? 0 }}/{{ result.max_depth ?? 0 }}</span>
          <span class="metric-label">{{ $t('analytics.codebase.impact.depth') }}</span>
        </div>
      </div>

      <div v-if="callerCount > 0" class="impact-list">
        <h4>{{ $t('analytics.codebase.impact.callersHeading') }}</h4>
        <ul>
          <li v-for="id in result.reached" :key="id"><code>{{ id }}</code></li>
        </ul>
      </div>
      <EmptyState
        v-else
        icon="check-circle"
        :title="$t('analytics.codebase.impact.noCallersTitle')"
        :description="$t('analytics.codebase.impact.noCallersBody')"
      />

      <details v-if="(result.unresolved_edge_count ?? 0) > 0" class="impact-skipped">
        <summary>
          {{ $t('analytics.codebase.impact.skippedHeading', { count: result.unresolved_edge_count }) }}
        </summary>
        <ul>
          <li v-for="(edge, i) in result.skipped_edges" :key="i">
            <code>{{ JSON.stringify(edge) }}</code>
          </li>
        </ul>
      </details>
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import EmptyState from '@/components/ui/EmptyState.vue'
import { ref } from 'vue'
import { useImpactAnalysis } from '@/composables/analytics/useImpactAnalysis'

const nodeId = ref('')
const { loading, error, result, notIndexed, isPartial, callerCount, analyze } = useImpactAnalysis()

async function run(): Promise<void> {
  await analyze(nodeId.value)
}
</script>

<style scoped>
.impact-panel {
  padding: var(--spacing-md, 1rem) 0;
}

.section-hint {
  color: var(--text-secondary);
  margin-bottom: var(--spacing-md, 1rem);
}

.impact-form {
  display: flex;
  gap: var(--spacing-sm, 0.5rem);
  margin-bottom: var(--spacing-md, 1rem);
}

.impact-input {
  flex: 1;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  background: var(--color-bg);
  color: var(--text-primary);
  font-family: var(--font-mono, monospace);
}

.impact-error {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border: 1px solid var(--color-danger, #dc2626);
  border-radius: 6px;
  color: var(--color-danger, #dc2626);
}

/* Deliberately loud: this is the difference between a complete answer and a
   lower bound, and it is the one thing a reader must not skim past. */
.impact-partial {
  display: flex;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  margin-bottom: var(--spacing-md, 1rem);
  border-left: 4px solid var(--color-warning, #d97706);
  background: var(--color-bg-secondary);
  border-radius: 4px;
}

.impact-partial p {
  margin: 0.25rem 0 0;
  color: var(--text-secondary);
}

.impact-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--spacing-sm, 0.5rem);
  margin-bottom: var(--spacing-md, 1rem);
}

.impact-metric {
  padding: 0.75rem;
  border: 1px solid var(--border-default);
  border-radius: 6px;
  text-align: center;
}

.impact-metric.warn {
  border-color: var(--color-warning, #d97706);
}

.metric-value {
  display: block;
  font-size: 1.5rem;
  font-weight: 600;
}

.metric-label {
  display: block;
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.impact-list ul,
.impact-skipped ul {
  list-style: none;
  padding: 0;
  margin: 0.5rem 0 0;
  max-height: 320px;
  overflow-y: auto;
}

.impact-list li,
.impact-skipped li {
  padding: 0.25rem 0;
  border-bottom: 1px solid var(--border-default);
  word-break: break-all;
}

.impact-skipped {
  margin-top: var(--spacing-md, 1rem);
}

.impact-skipped summary {
  cursor: pointer;
  color: var(--text-secondary);
}
</style>
