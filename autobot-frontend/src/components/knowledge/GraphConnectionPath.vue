<template>
  <div class="graph-connection-path">
    <!-- Header -->
    <div class="path-header">
      <h4><Icon name="sitemap" /> {{ $t('knowledge.graphPath.title') }}</h4>
      <p class="header-description">{{ $t('knowledge.graphPath.description') }}</p>
    </div>

    <!-- Query Section -->
    <div class="path-section">
      <div class="endpoints-row">
        <div class="form-group">
          <label for="path-from">
            <Icon name="play-circle" /> {{ $t('knowledge.graphPath.fromEntity') }}
          </label>
          <input
            id="path-from"
            v-model="fromEntity"
            type="text"
            :placeholder="$t('knowledge.graphPath.fromEntityPlaceholder')"
            :disabled="isFindingPath"
            @keyup.enter="executeFindPath"
          />
        </div>

        <button
          class="swap-btn"
          type="button"
          :disabled="isFindingPath"
          :title="$t('knowledge.graphPath.swap')"
          :aria-label="$t('knowledge.graphPath.swap')"
          @click="swapEndpoints"
        >
          <Icon name="exchange-alt" />
        </button>

        <div class="form-group">
          <label for="path-to">
            <Icon name="flag" /> {{ $t('knowledge.graphPath.toEntity') }}
          </label>
          <input
            id="path-to"
            v-model="toEntity"
            type="text"
            :placeholder="$t('knowledge.graphPath.toEntityPlaceholder')"
            :disabled="isFindingPath"
            @keyup.enter="executeFindPath"
          />
        </div>
      </div>

      <div class="options-row">
        <div class="form-group compact">
          <label for="path-direction">
            <Icon name="exchange-alt" /> {{ $t('knowledge.graphPath.direction') }}
          </label>
          <select id="path-direction" v-model="direction" :disabled="isFindingPath">
            <option value="both">{{ $t('knowledge.graphPath.directionBoth') }}</option>
            <option value="outgoing">{{ $t('knowledge.graphPath.directionOutgoing') }}</option>
            <option value="incoming">{{ $t('knowledge.graphPath.directionIncoming') }}</option>
          </select>
          <span class="label-hint">{{ $t('knowledge.graphPath.directionHint') }}</span>
        </div>

        <div class="form-group compact">
          <label for="path-max-depth">
            <Icon name="layer-group" /> {{ $t('knowledge.graphPath.maxDepth') }}
          </label>
          <select id="path-max-depth" v-model.number="maxDepth" :disabled="isFindingPath">
            <option v-for="depth in DEPTH_OPTIONS" :key="depth" :value="depth">
              {{ $t('knowledge.graphPath.hops', { count: depth }) }}
            </option>
          </select>
        </div>

        <div class="form-group compact">
          <label for="path-relation">
            <Icon name="filter" /> {{ $t('knowledge.graphPath.relation') }}
            <span class="label-hint">{{ $t('knowledge.graphPath.relationHint') }}</span>
          </label>
          <input
            id="path-relation"
            v-model="relation"
            type="text"
            :placeholder="$t('knowledge.graphPath.relationPlaceholder')"
            :disabled="isFindingPath"
          />
        </div>
      </div>

      <div class="path-actions">
        <button
          class="action-btn primary"
          :disabled="isFindingPath || !canSubmit"
          @click="executeFindPath"
        >
          <Icon v-if="isFindingPath" name="spinner" class="animate-spin" />
          <Icon v-else name="search" />
          {{ isFindingPath ? $t('knowledge.graphPath.searching') : $t('knowledge.graphPath.findPath') }}
        </button>
      </div>
    </div>

    <!-- Result Section -->
    <div v-if="pathResult" class="result-section">
      <!-- Found: render the chain -->
      <template v-if="pathResult.found">
        <div class="result-header">
          <h5>
            <Icon name="link" />
            {{ $t('knowledge.graphPath.connectedIn', { count: pathResult.hops }) }}
          </h5>
          <span v-if="pathResult.traversal_time !== undefined" class="metric-badge">
            <Icon name="clock" />
            {{ pathResult.traversal_time.toFixed(3) }}s
          </span>
        </div>

        <!-- A zero-hop path means both names resolved to the same entity. -->
        <p v-if="pathResult.hops === 0" class="same-entity-note">
          <Icon name="exclamation-circle" />
          {{ $t('knowledge.graphPath.sameEntity', { name: resolvedFromName }) }}
        </p>

        <ol v-else class="path-chain">
          <li class="chain-node start">
            <Icon name="play-circle" />
            <span class="node-name">{{ resolvedFromName }}</span>
            <span v-if="pathResult.from_entity?.type" class="node-type">
              {{ pathResult.from_entity.type }}
            </span>
          </li>

          <template v-for="(hop, index) in pathResult.path" :key="hop.edge_id ?? index">
            <li class="chain-edge" :class="hop.direction">
              <Icon :name="hop.direction === 'incoming' ? 'arrow-left' : 'arrow-right'" />
              <span class="edge-relation">{{ hop.relation || $t('knowledge.graphPath.unnamedRelation') }}</span>
              <span class="edge-direction">
                {{ hop.direction === 'incoming'
                  ? $t('knowledge.graphPath.crossedBackwards')
                  : $t('knowledge.graphPath.crossedForwards') }}
              </span>
            </li>
            <li class="chain-node" :class="{ end: index === pathResult.path.length - 1 }">
              <Icon :name="index === pathResult.path.length - 1 ? 'flag' : 'circle'" />
              <span class="node-name">{{ hop.node?.name || hop.node?.id }}</span>
              <span v-if="hop.node?.type" class="node-type">{{ hop.node.type }}</span>
            </li>
          </template>
        </ol>
      </template>

      <!-- Not found: the two cases must not read the same -->
      <div v-else class="empty-result" :class="pathResult.reason ?? 'no_path'">
        <template v-if="pathResult.reason === 'entity_not_found'">
          <Icon name="question-circle" />
          <p>{{ $t('knowledge.graphPath.entityNotFound') }}</p>
          <ul class="missing-list">
            <li v-for="name in pathResult.missing_entities" :key="name">{{ name }}</li>
          </ul>
          <p class="hint">{{ $t('knowledge.graphPath.entityNotFoundHint') }}</p>
        </template>
        <template v-else>
          <Icon name="unlink" />
          <p>{{ $t('knowledge.graphPath.noPathFound') }}</p>
          <p class="hint">{{ $t('knowledge.graphPath.noPathHint') }}</p>
        </template>
      </div>
    </div>

    <!-- Error Notification -->
    <div v-if="errorMessage" class="error-notification" role="alert">
      <Icon name="exclamation-circle" />
      <span>{{ errorMessage }}</span>
      <button class="close-btn" @click="errorMessage = ''">
        <Icon name="times" />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * GraphConnectionPath - shortest relationship path between two entities
 *
 * @description Answers "how are these two things connected". The Graph-RAG
 * query tab expands a neighbourhood ("what relates to X"); this walks the
 * memory graph from one named entity to another and renders the chain of
 * relations that links them.
 *
 * Each hop shows the direction it was crossed: with the default undirected
 * search a link may be traversed against the way it was stored, and hiding that
 * would misrepresent the relationship.
 *
 * @see Issue #13474 - wire PropertyGraph.shortest_path to a production caller
 *
 * @author mrveiss
 * @copyright (c) 2025 mrveiss
 */

// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import Icon from '@/components/ui/Icon.vue'
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  useKnowledgeGraphRAG,
  type GraphPathDirection,
} from '@/composables/knowledge/useKnowledgeGraphRAG'

const { t } = useI18n()

// ============================================================================
// Constants
// ============================================================================

/** Matches the backend's ge=1, le=10 bound on max_depth (#13474). */
const DEPTH_OPTIONS = [2, 3, 4, 6, 8, 10] as const

// ============================================================================
// Composable
// ============================================================================

const { pathResult, isFindingPath, errorMessage, findPath } = useKnowledgeGraphRAG()

// ============================================================================
// Local UI state
// ============================================================================

const fromEntity = ref('')
const toEntity = ref('')
const relation = ref('')
const maxDepth = ref(6)
const direction = ref<GraphPathDirection>('both')

// ============================================================================
// Computed
// ============================================================================

const canSubmit = computed(() => fromEntity.value.trim() !== '' && toEntity.value.trim() !== '')

/**
 * Prefer the name the backend actually resolved over what was typed — name
 * lookup is a search, so the match may differ from the input and the user needs
 * to see which entity was used.
 */
const resolvedFromName = computed(
  () => pathResult.value?.from_entity?.name || fromEntity.value.trim(),
)

// ============================================================================
// Methods
// ============================================================================

function swapEndpoints(): void {
  const previousFrom = fromEntity.value
  fromEntity.value = toEntity.value
  toEntity.value = previousFrom
}

async function executeFindPath(): Promise<void> {
  if (!canSubmit.value) {
    errorMessage.value = t('knowledge.graphPath.errorEnterBoth')
    return
  }

  try {
    await findPath({
      from_entity: fromEntity.value.trim(),
      to_entity: toEntity.value.trim(),
      relation: relation.value.trim() || null,
      max_depth: maxDepth.value,
      direction: direction.value,
    })
  } catch (error) {
    // findPath rejects on transport/server failure (a "not connected" answer
    // resolves normally). Without this the rejection would be unhandled and the
    // user would see the button stop spinning with nothing explaining why.
    errorMessage.value = error instanceof Error ? error.message : String(error)
  }
}
</script>

<style scoped>
/* Issue #13474: connection-path styles — design tokens only, no literals. */
.graph-connection-path {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.path-header h4 {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: var(--spacing-0);
}

.path-header h4 i {
  color: var(--color-primary);
}

.header-description {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  margin-top: var(--spacing-sm);
}

.path-section {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
  border: 1px solid var(--border-subtle);
}

.endpoints-row {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: end;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-md);
}

.form-group {
  margin-bottom: var(--spacing-0);
}

.form-group label {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
  margin-bottom: var(--spacing-sm);
}

.form-group label i {
  color: var(--text-tertiary);
}

.label-hint {
  font-weight: var(--font-normal);
  color: var(--text-tertiary);
  font-size: var(--text-xs);
}

.form-group input,
.form-group select {
  width: 100%;
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  background: var(--bg-input);
  color: var(--text-primary);
  transition: border-color var(--duration-200);
}

.form-group input:focus,
.form-group select:focus {
  outline: none;
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.form-group input:focus-visible,
.form-group select:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.form-group input:disabled,
.form-group select:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.swap-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-sm);
  margin-bottom: var(--spacing-xs);
  border: 1px solid var(--border-default);
  background: var(--bg-card);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--duration-200);
}

.swap-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--color-primary);
}

.swap-btn:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.swap-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.options-row {
  display: grid;
  grid-template-columns: 1fr 1fr 2fr;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-md);
}

.path-actions {
  display: flex;
  justify-content: flex-end;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-lg);
  border: 1px solid var(--border-default);
  background: var(--bg-card);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
  cursor: pointer;
  transition: all var(--duration-200);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-btn.primary {
  background: var(--color-primary);
  color: white;
  border-color: transparent;
}

.action-btn.primary:hover:not(:disabled) {
  box-shadow: var(--shadow-primary);
}

.result-section {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
  border: 1px solid var(--border-subtle);
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-md);
  padding-bottom: var(--spacing-md);
  border-bottom: 1px solid var(--border-subtle);
}

.result-header h5 {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: var(--spacing-0);
}

.metric-badge {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-xs) var(--spacing-sm);
  background: var(--bg-secondary);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.same-entity-note {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: var(--spacing-0);
}

.path-chain {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
  list-style: none;
  padding: var(--spacing-0);
  margin: var(--spacing-0);
}

.chain-node {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--bg-secondary);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
}

.chain-node.start i,
.chain-node.end i {
  color: var(--color-primary);
}

.node-name {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.node-type {
  padding: 2px var(--spacing-sm);
  background: var(--bg-tertiary);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.chain-edge {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-xs) var(--spacing-lg);
  font-size: var(--text-xs);
  color: var(--text-secondary);
}

.chain-edge i {
  color: var(--color-primary);
}

.chain-edge.incoming i {
  color: var(--color-warning);
}

.edge-relation {
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.edge-direction {
  color: var(--text-tertiary);
}

.empty-result {
  text-align: center;
  padding: var(--spacing-xl);
  color: var(--text-secondary);
}

.empty-result i {
  font-size: 2rem;
  margin-bottom: var(--spacing-md);
  color: var(--text-tertiary);
}

.empty-result p {
  margin: var(--spacing-0);
}

.empty-result .hint {
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  margin-top: var(--spacing-sm);
}

.missing-list {
  list-style: none;
  padding: var(--spacing-0);
  margin: var(--spacing-sm) var(--spacing-0);
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
  justify-content: center;
}

.missing-list li {
  padding: var(--spacing-xs) var(--spacing-sm);
  background: var(--color-warning-bg);
  color: var(--color-warning);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
}

.error-notification {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  border-left: 4px solid var(--color-error);
  border-radius: var(--radius-md);
  color: var(--color-error-text);
}

.error-notification span {
  flex: 1;
  font-size: var(--text-sm);
}

.close-btn {
  background: none;
  border: none;
  padding: var(--spacing-xs);
  cursor: pointer;
  color: var(--text-secondary);
  opacity: 0.7;
  transition: opacity var(--duration-200);
}

.close-btn:hover {
  opacity: 1;
}

@media (max-width: 768px) {
  .endpoints-row,
  .options-row {
    grid-template-columns: 1fr;
  }

  .swap-btn {
    justify-self: center;
  }

  .result-header {
    flex-direction: column;
    align-items: flex-start;
    gap: var(--spacing-sm);
  }
}
</style>
