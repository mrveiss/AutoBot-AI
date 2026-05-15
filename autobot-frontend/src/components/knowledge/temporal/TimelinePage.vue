<!-- AutoBot - Knowledge Graph Pipeline (Issue #759) -->
<template>
  <div class="timeline-page">
    <div class="timeline-layout">
      <!-- Filter Sidebar -->
      <aside class="filter-sidebar">
        <TemporalFilter @filter-change="handleFilterChange" />
      </aside>

      <!-- Timeline Content -->
      <div class="timeline-main">
        <EventTimeline
          :events="events"
          :loading="loading"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

import { onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useKnowledgeGraph } from '@/composables/useKnowledgeGraph'
import TemporalFilter from './TemporalFilter.vue'
import EventTimeline from './EventTimeline.vue'

const route = useRoute()
const {
  events,
  searchEvents,
  getTimeline,
  loading,
} = useKnowledgeGraph()

interface FilterParams {
  start_date?: string
  end_date?: string
  event_types?: string[]
  entity_name?: string
}

async function handleFilterChange(filters: FilterParams): Promise<void> {
  await searchEvents({
    start_date: filters.start_date,
    end_date: filters.end_date,
    event_types: filters.event_types,
    entity_name: filters.entity_name,
  })
}

onMounted(async () => {
  // If navigated with entity query param, load that entity's timeline
  const entityName = route.query.entity as string | undefined
  if (entityName) {
    const timeline = await getTimeline(entityName)
    events.value = timeline
  } else {
    // Load recent events by default
    await searchEvents({})
  }
})
</script>

<style scoped>
.timeline-page {
  height: 100%;
  overflow: hidden;
}

.timeline-layout {
  display: flex;
  height: 100%;
  gap: var(--spacing-md);
  padding: var(--spacing-lg);
}

.filter-sidebar {
  width: 280px;
  min-width: 280px;
  overflow-y: auto;
}

.timeline-main {
  flex: 1;
  overflow-y: auto;
  min-width: 0;
}

@media (max-width: 768px) {
  .timeline-layout {
    flex-direction: column;
  }

  .filter-sidebar {
    width: 100%;
    min-width: 100%;
  }
}
</style>
