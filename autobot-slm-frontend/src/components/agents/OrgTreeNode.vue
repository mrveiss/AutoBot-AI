<script setup lang="ts">
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Recursive Org Tree Node (#1780)
 *
 * Renders a single node in the org tree and recursively renders
 * its children at increasing indent levels.
 */

interface OrgNode {
  agent_id: string
  name: string
  org_role: string
  title: string | null
  capabilities: string | null
  direct_reports_count: number
  children: OrgNode[]
}

defineProps<{
  node: OrgNode
  depth: number
  selectedId: string | null
}>()

const emit = defineEmits<{
  select: [node: OrgNode]
}>()

function roleBadgeClass(role: string): string {
  const map: Record<string, string> = {
    manager: 'badge-purple',
    coordinator: 'badge-blue',
    specialist: 'badge-green',
    worker: 'badge-gray',
  }
  return map[role] || 'badge-gray'
}
</script>

<template>
  <li
    :class="{ selected: selectedId === node.agent_id }"
    :style="{ paddingLeft: `${12 + depth * 24}px` }"
    @click.stop="emit('select', node)"
  >
    <span :class="['role-badge', roleBadgeClass(node.org_role)]">{{
      node.org_role
    }}</span>
    <span class="node-name">{{ node.name }}</span>
    <span v-if="node.direct_reports_count" class="reports-count"
      >{{ $t('agents.orgTreeNode.value0Reports', { value0: node.direct_reports_count }) }}</span
    >
  </li>
  <OrgTreeNode
    v-for="child in node.children"
    :key="child.agent_id"
    :node="child"
    :depth="depth + 1"
    :selected-id="selectedId"
    @select="emit('select', $event)"
  />
</template>

<style scoped>
li {
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 2px;
  list-style: none;
}
li:hover { background: var(--bg-tertiary); }
li.selected { background: var(--color-primary-bg); }
.node-name { font-weight: 500; color: var(--text-primary); }
.reports-count { font-size: 11px; color: var(--text-secondary); margin-left: auto; }
.role-badge { font-size: 10px; padding: 2px 8px; border-radius: 4px; font-weight: 600; text-transform: uppercase; }
.badge-purple { background: color-mix(in srgb, var(--chart-5) 10%, transparent); color: var(--chart-5); }
.badge-blue { background: var(--info-bg); color: var(--info-fg); }
.badge-green { background: var(--color-success-bg); color: var(--color-success-hover); }
.badge-gray { background: var(--bg-tertiary); color: var(--muted); }
</style>
