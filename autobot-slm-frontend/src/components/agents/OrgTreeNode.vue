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
li:hover { background: #f3f4f6; }
li.selected { background: #e0e7ff; }
.node-name { font-weight: 500; color: var(--text-primary, #1a1a2e); }
.reports-count { font-size: 11px; color: var(--text-secondary, #6b7280); margin-left: auto; }
.role-badge { font-size: 10px; padding: 2px 8px; border-radius: 4px; font-weight: 600; text-transform: uppercase; }
.badge-purple { background: #ede9fe; color: #7c3aed; }
.badge-blue { background: #dbeafe; color: #2563eb; }
.badge-green { background: #d1fae5; color: #059669; }
.badge-gray { background: #f3f4f6; color: #6b7280; }
</style>
