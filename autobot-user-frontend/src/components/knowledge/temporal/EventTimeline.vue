<!-- AutoBot - Knowledge Graph Pipeline (Issue #759) -->
<template>
  <div class="event-timeline">
    <div class="timeline-header">
      <h4><i class="fas fa-stream"></i> Event Timeline</h4>
      <span v-if="events.length > 0" class="event-count">
        {{ events.length }} events
      </span>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading-state">
      <i class="fas fa-spinner fa-spin"></i>
      <span>Loading timeline...</span>
    </div>

    <!-- Empty -->
    <div v-else-if="events.length === 0" class="empty-state">
      <i class="fas fa-calendar-times"></i>
      <p>No events to display</p>
      <p class="empty-hint">
        Use the filter panel to search for events
      </p>
    </div>

    <!-- Timeline -->
    <div v-else class="timeline-container">
      <div class="timeline-line" />

      <div
        v-for="(event, index) in events"
        :key="event.id"
        class="timeline-item"
      >
        <!-- Date Marker -->
        <div
          v-if="shouldShowDateMarker(index)"
          class="date-marker"
        >
          <span>{{ formatDateMarker(event) }}</span>
        </div>

        <!-- Event Card -->
        <div class="timeline-dot-container">
          <div
            class="timeline-dot"
            :style="{ backgroundColor: getEventColor(event.event_type) }"
          >
            <i :class="getEventIcon(event.event_type)"></i>
          </div>
        </div>

        <div
          class="timeline-card"
          :class="{ expanded: expandedEvent === event.id }"
          @click="toggleExpand(event.id)"
        >
          <div class="card-header">
            <span
              class="event-type-badge"
              :style="{
                backgroundColor: getEventColor(event.event_type),
                color: 'white',
              }"
            >
              {{ event.event_type }}
            </span>
            <span class="event-time">
              {{ formatTimestamp(event) }}
            </span>
          </div>

          <h5 class="event-name">{{ event.name }}</h5>

          <p
            v-if="event.description"
            class="event-description"
          >
            {{ event.description }}
          </p>

          <!-- Participants -->
          <div
            v-if="event.participants.length > 0"
            class="event-participants"
          >
            <span
              v-for="participant in event.participants"
              :key="participant"
              class="participant-badge"
            >
              {{ participant }}
            </span>
          </div>

          <!-- Expanded Content -->
          <div
            v-if="expandedEvent === event.id"
            class="expanded-content"
          >
            <div
              v-if="event.causal_links.length > 0"
              class="causal-links"
            >
              <span class="links-label">Causal Links:</span>
              <span
                v-for="link in event.causal_links"
                :key="link"
                class="link-badge"
              >
                {{ link }}
              </span>
            </div>
            <div class="event-entity">
              <span class="entity-label">Entity:</span>
              <span>{{ event.entity_name }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { ref } from 'vue'
import type { TemporalEvent } from '@/composables/useKnowledgeGraph'

defineProps<{
  events: TemporalEvent[]
  loading: boolean
}>()

const expandedEvent = ref<string | null>(null)

const eventColorMap: Record<string, string> = {
  action: 'rgba(59, 130, 246, 0.9)',
  decision: 'rgba(168, 85, 247, 0.9)',
  change: 'rgba(249, 115, 22, 0.9)',
  milestone: 'rgba(34, 197, 94, 0.9)',
  occurrence: 'rgba(107, 114, 128, 0.9)',
}

const eventIconMap: Record<string, string> = {
  action: 'fas fa-bolt',
  decision: 'fas fa-gavel',
  change: 'fas fa-exchange-alt',
  milestone: 'fas fa-flag',
  occurrence: 'fas fa-circle',
}

function getEventColor(type: string): string {
  return eventColorMap[type.toLowerCase()] ?? eventColorMap.occurrence
}

function getEventIcon(type: string): string {
  return eventIconMap[type.toLowerCase()] ?? eventIconMap.occurrence
}

function formatTimestamp(event: TemporalEvent): string {
  if (event.timestamp) {
    const date = new Date(event.timestamp)
    return date.toLocaleString()
  }
  return event.temporal_expression ?? 'Unknown time'
}

function formatDateMarker(event: TemporalEvent): string {
  if (event.timestamp) {
    const date = new Date(event.timestamp)
    return date.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    })
  }
  return event.temporal_expression ?? ''
}

function shouldShowDateMarker(index: number): boolean {
  // Show date marker for first event and when date changes
  return index === 0
}

function toggleExpand(eventId: string): void {
  expandedEvent.value = expandedEvent.value === eventId
    ? null
    : eventId
}
</script>

<style scoped>
.event-timeline {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.timeline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.timeline-header h4 {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: 0;
}

.timeline-header h4 i {
  color: var(--color-primary);
}

.event-count {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  background: var(--bg-secondary);
  padding: var(--spacing-xs) var(--spacing-sm);
  border-radius: var(--radius-full);
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
  gap: var(--spacing-sm);
}

.loading-state i,
.empty-state i {
  font-size: var(--text-2xl);
}

.empty-hint {
  font-size: var(--text-sm);
}

/* Timeline */
.timeline-container {
  position: relative;
  padding-left: 40px;
}

.timeline-line {
  position: absolute;
  left: 15px;
  top: 0;
  bottom: 0;
  width: 2px;
  background: var(--border-default);
}

.timeline-item {
  position: relative;
  margin-bottom: var(--spacing-md);
}

.date-marker {
  margin-bottom: var(--spacing-sm);
  margin-left: -40px;
  padding-left: 40px;
}

.date-marker span {
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.timeline-dot-container {
  position: absolute;
  left: -40px;
  top: var(--spacing-sm);
  width: 30px;
  display: flex;
  justify-content: center;
}

.timeline-dot {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1;
}

.timeline-dot i {
  color: white;
  font-size: 10px;
}

/* Event Card */
.timeline-card {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--spacing-md);
  cursor: pointer;
  transition: all var(--duration-200);
}

.timeline-card:hover {
  border-color: var(--border-strong);
}

.timeline-card.expanded {
  border-color: var(--color-primary);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--spacing-xs);
}

.event-type-badge {
  font-size: var(--text-xs);
  padding: 2px var(--spacing-sm);
  border-radius: var(--radius-full);
  text-transform: capitalize;
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

.event-description {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.5;
}

/* Participants */
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

/* Expanded */
.expanded-content {
  margin-top: var(--spacing-sm);
  padding-top: var(--spacing-sm);
  border-top: 1px solid var(--border-subtle);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.causal-links {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
}

.links-label,
.entity-label {
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--text-secondary);
}

.link-badge {
  font-size: var(--text-xs);
  padding: 2px var(--spacing-sm);
  background: rgba(244, 63, 94, 0.1);
  color: rgba(244, 63, 94, 0.9);
  border-radius: var(--radius-full);
}

.event-entity {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-size: var(--text-sm);
  color: var(--text-primary);
}

@media (max-width: 768px) {
  .timeline-container {
    padding-left: 32px;
  }

  .timeline-line {
    left: 11px;
  }

  .timeline-dot-container {
    left: -32px;
  }

  .timeline-dot {
    width: 22px;
    height: 22px;
  }

  .timeline-dot i {
    font-size: 8px;
  }
}
</style>
