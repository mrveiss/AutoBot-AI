<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<template>
  <div class="collections-list">
    <!-- #19725: most collections on a node can be empty, which read as "lots of empty facts". -->
    <label v-if="emptyCount > 0">
      <input v-model="showEmpty" type="checkbox" />
      {{ $t('knowledge.chromaExplorer.includeEmpty', { count: emptyCount }) }}
    </label>
    <button
      v-for="collection in visible"
      :key="collection.name"
      class="collection-item"
      :class="{ active: selectedName === collection.name }"
      @click="emit('select', collection)"
    >
      <div class="collection-info">
        <span class="collection-name">{{ collection.name }}</span>
        <span class="collection-count">{{ $t('knowledge.chromaExplorer.documentCount', { count: collection.count }) }}</span>
      </div>
      <svg fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
      </svg>
    </button>
  </div>
</template>

<script setup lang="ts" generic="T extends { name: string; count: number }">
import { computed, ref } from 'vue'

const props = defineProps<{ collections: T[]; selectedName?: string }>()
const emit = defineEmits<{ (e: 'select', collection: T): void }>()

const showEmpty = ref(false)
const emptyCount = computed(() => props.collections.filter((c) => c.count === 0).length)
const visible = computed(() => (showEmpty.value ? props.collections : props.collections.filter((c) => c.count > 0)))
</script>

<style scoped>
.collections-list {
  flex: 1;
  overflow-y: auto;
  padding: var(--spacing-2);
}

.collection-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: var(--spacing-3);
  background: transparent;
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  cursor: pointer;
  text-align: left;
  transition: all var(--duration-150) ease;
  margin-bottom: var(--spacing-1);
}

.collection-item:hover {
  background: var(--bg-tertiary);
  border-color: var(--border-default);
}

.collection-item.active {
  background: var(--color-info-bg);
  border-color: var(--color-info);
  color: var(--color-info);
}

.collection-info {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
  flex: 1;
}

.collection-name {
  font-size: var(--text-sm);
  font-weight: 500;
}

.collection-count {
  font-size: var(--text-xs);
  opacity: 0.7;
}

.collection-item svg {
  width: var(--spacing-4);
  height: var(--spacing-4);
  flex-shrink: 0;
}
</style>
