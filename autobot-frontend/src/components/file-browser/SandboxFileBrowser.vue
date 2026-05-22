<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<template>
  <div class="sandbox-file-browser">
    <div class="sbfb-header">
      <h3 class="sbfb-title">
        <Icon name="folder-open" />
        Sandbox Files
      </h3>
      <button
        class="btn-action-secondary btn-sm"
        :disabled="loading"
        :aria-label="loading ? 'Loading…' : 'Refresh sandbox files'"
        @click="refresh"
      >
        <i :class="['fas', loading ? 'fa-spinner fa-spin' : 'fa-sync-alt']"></i>
        Refresh
      </button>
    </div>

    <div v-if="error" class="sbfb-error" role="alert">
      <Icon name="exclamation-circle" />
      <span>{{ error }}</span>
      <button class="btn-dismiss" :aria-label="'Dismiss error'" @click="clearError">
        <Icon name="times" />
      </button>
    </div>

    <!-- Stats banner -->
    <div v-if="stats" class="sbfb-stats">
      <span class="stat-item" title="Total files">
        <Icon name="file" /> {{ stats.total_files }} files
      </span>
      <span class="stat-item" title="Total directories">
        <Icon name="folder" /> {{ stats.total_directories }} dirs
      </span>
      <span class="stat-item" title="Total size">
        <Icon name="database" /> {{ stats.total_size_mb.toFixed(2) }} MB
      </span>
      <span class="stat-item" title="Max file size">
        <Icon name="cube" /> max {{ stats.max_file_size_mb }} MB
      </span>
    </div>

    <!-- File tree -->
    <div class="sbfb-tree" role="tree" aria-label="Sandbox file tree">
      <div v-if="loading && tree.length === 0" class="sbfb-loading">
        <Icon name="spinner" class="animate-spin" /> Loading…
      </div>

      <div v-else-if="tree.length === 0 && !loading" class="sbfb-empty">
        <Icon name="folder-open" />
        <span>Sandbox is empty</span>
      </div>

      <SandboxTreeNode
        v-for="node in tree"
        :key="node.path"
        :node="node"
        :depth="0"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { onMounted } from 'vue'
import { useFileSandbox } from '@/composables/useFileSandbox'
import SandboxTreeNode from './SandboxTreeNode.vue'

const { tree, stats, loading, error, getTree, getStats, clearError } = useFileSandbox()

async function refresh(): Promise<void> {
  await Promise.all([getTree(), getStats()])
}

onMounted(refresh)
</script>

<style scoped>
.sandbox-file-browser {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  padding: 1rem;
  background: var(--bg-secondary, #1a1a2e);
  border-radius: 0.5rem;
  border: 1px solid var(--border-color, rgba(255, 255, 255, 0.1));
}

.sbfb-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sbfb-title {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 600;
  color: var(--text-primary, #e0e0e0);
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.sbfb-error {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  background: rgba(239, 68, 68, 0.15);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 0.375rem;
  color: #fca5a5;
  font-size: 0.85rem;
}

.sbfb-error .btn-dismiss {
  margin-left: auto;
  background: none;
  border: none;
  cursor: pointer;
  color: #fca5a5;
  padding: 0;
  line-height: 1;
}

.sbfb-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem 1rem;
  padding: 0.5rem 0.75rem;
  background: var(--bg-tertiary, rgba(255, 255, 255, 0.04));
  border-radius: 0.375rem;
}

.stat-item {
  font-size: 0.8rem;
  color: var(--text-secondary, rgba(255, 255, 255, 0.6));
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.sbfb-tree {
  min-height: 4rem;
}

.sbfb-loading,
.sbfb-empty {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: var(--text-secondary, rgba(255, 255, 255, 0.4));
  font-size: 0.875rem;
  padding: 1rem 0.5rem;
  justify-content: center;
}

.btn-sm {
  font-size: 0.8rem;
  padding: 0.25rem 0.6rem;
}
</style>
