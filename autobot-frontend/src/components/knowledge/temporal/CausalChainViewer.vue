<!-- AutoBot - Knowledge Graph Pipeline (Issue #759) -->
<template>
  <div class="causal-chain-viewer">
    <div class="chain-header">
      <h4><i class="fas fa-code-branch"></i> Causal Chain</h4>
      <p class="header-description">
        Trace the chain of causally linked events
      </p>
    </div>

    <!-- Controls -->
    <div class="chain-controls">
      <div class="control-group">
        <label for="max-depth">
          Max Depth: <strong>{{ maxDepth }}</strong>
        </label>
        <input
          id="max-depth"
          v-model.number="maxDepth"
          type="range"
          min="1"
          max="10"
          step="1"
          class="range-input"
        />
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      <span>Tracing causal chain...</span>
    </div>

    <!-- Chain Display -->
    <div v-else-if="chainEvents.length > 0" class="chain-container">
      <div
        v-for="(event, index) in chainEvents"
        :key="event.id"
        class="chain-node"
      >
        <!-- Connection Arrow -->
        <div v-if="index > 0" class="chain-arrow">
          <div class="arrow-line" />
          <i class="fas fa-chevron-down arrow-head"></i>
        </div>

        <!-- Event Card -->
        <div
          class="chain-event-card"
          :class="{ root: index === 0 }"
        >
          <div class="card-top">
            <span
              class="depth-badge"
              :style="{ backgroundColor: getDepthColor(index) }"
            >
              {{ index === 0 ? 'Root' : `Depth ${index}` }}
            </span>
            <span class="event-time">
              {{ event.timestamp
                ? new Date(event.timestamp).toLocaleDateString()
                : event.temporal_expression ?? ''
              }}
            </span>
          </div>

          <h5 class="event-name">{{ event.name }}</h5>

          <p v-if="event.description" class="event-desc">
            {{ event.description }}
          </p>

          <div
            v-if="event.participants.length > 0"
            class="event-participants"
          >
            <span
              v-for="p in event.participants"
              :key="p"
              class="participant-badge"
            >
              {{ p }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Empty -->
    <div v-else class="empty-state">
      <i class="fas fa-code-branch"></i>
      <p>No causal chain found for this event</p>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref, onMounted, watch } from 'vue'
import type { TemporalEvent } from '@/composables/useKnowledgeGraph'
import { useKnowledgeGraph } from '@/composables/useKnowledgeGraph'
const props = defineProps<{
  eventId: string
  initialEvents?: TemporalEvent[]
}>()

const { getTimeline, loading } = useKnowledgeGraph()

const maxDepth = ref(5)
const chainEvents = ref<TemporalEvent[]>([])

function getDepthColor(depth: number): string {
  const colors = [
    'rgba(59, 130, 246, 0.9)',
    'rgba(99, 102, 241, 0.9)',
    'rgba(139, 92, 246, 0.9)',
    'rgba(168, 85, 247, 0.9)',
    'rgba(192, 75, 238, 0.9)',
    'rgba(217, 70, 239, 0.9)',
    'rgba(236, 72, 153, 0.9)',
    'rgba(244, 63, 94, 0.9)',
    'rgba(249, 115, 22, 0.9)',
    'rgba(234, 179, 8, 0.9)',
  ]
  return colors[depth % colors.length]
}

async function loadChain(): Promise<void> {
  if (props.initialEvents && props.initialEvents.length > 0) {
    chainEvents.value = props.initialEvents.slice(0, maxDepth.value)
    return
  }

  // Use the entity name from the event to get timeline
  // In a full implementation, this would follow causal_links
  const events = await getTimeline(props.eventId)
  chainEvents.value = events.slice(0, maxDepth.value)
}

onMounted(loadChain)

watch(maxDepth, loadChain)
watch(() => props.eventId, loadChain)
</script>

<style scoped>
.causal-chain-viewer {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
  padding: var(--spacing-lg);
}

.chain-header h4 {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: 0;
}

.chain-header h4 i {
  color: var(--color-primary);
}

.header-description {
  color: var(--text-secondary);
  font-size: var(--text-sm);
  margin-top: var(--spacing-xs);
}

/* Controls */
.chain-controls {
  display: flex;
  gap: var(--spacing-lg);
  flex-wrap: wrap;
}

.control-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.control-group label {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--text-primary);
}

.range-input {
  accent-color: var(--color-primary);
  min-width: 150px;
}

/* States */
.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-2xl);
  color: var(--text-tertiary);
  gap: var(--spacing-md);
}

.loading-state i,
.empty-state i {
  font-size: var(--text-2xl);
}

/* Chain */
.chain-container {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.chain-node {
  width: 100%;
  max-width: 500px;
}

.chain-arrow {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--spacing-xs) 0;
}

.arrow-line {
  width: 2px;
  height: 20px;
  background: var(--border-default);
}

.arrow-head {
  color: var(--text-tertiary);
  font-size: var(--text-xs);
}

/* Event Card */
.chain-event-card {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--spacing-md);
}

.chain-event-card.root {
  border-color: var(--color-primary);
  border-width: 2px;
}

.card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-xs);
}

.depth-badge {
  font-size: var(--text-xs);
  padding: 2px var(--spacing-sm);
  border-radius: var(--radius-full);
  color: white;
}

.event-time {
  font-size: var(--text-xs);
  color: var(--text-tertiary);
}

.event-name {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin: 0 0 var(--spacing-xs) 0;
}

.event-desc {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.5;
}

.event-participants {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
  margin-top: var(--spacing-sm);
}

.participant-badge {
  font-size: var(--text-xs);
  padding: 2px var(--spacing-sm);
  background: var(--bg-secondary);
  border-radius: var(--radius-full);
  color: var(--text-secondary);
}

@media (max-width: 768px) {
  .chain-controls {
    flex-direction: column;
  }
}
</style>
