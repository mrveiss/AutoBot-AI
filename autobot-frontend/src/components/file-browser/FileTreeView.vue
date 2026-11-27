<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- The Files tab folder tree on the kit and tokens (#22349); a node is a real button, so it is keyboard-reachable. -->
<template>
  <div class="tree-panel">
    <div class="tree-header">
      <h3><Icon name="folder" /> {{ $t('fileBrowser.treeView.title') }}</h3>
      <div class="tree-controls">
        <BaseButton variant="ghost" size="sm" :aria-label="$t('fileBrowser.treeView.expandAll')" data-testid="tree-expand-all" @click="$emit('expand-all')">
          <Icon name="expand-alt" />
        </BaseButton>
        <BaseButton variant="ghost" size="sm" :aria-label="$t('fileBrowser.treeView.collapseAll')" data-testid="tree-collapse-all" @click="$emit('collapse-all')">
          <Icon name="compress-alt" />
        </BaseButton>
      </div>
    </div>

    <div class="tree-content">
      <div
        v-for="{ item, depth } in rows"
        :key="item.path"
        class="tree-node"
        :class="{ expanded: item.expanded, selected: selectedPath === item.path }"
      >
        <BaseButton
          variant="ghost"
          size="sm"
          class="tree-node-content"
          :style="{ paddingInlineStart: (depth * 20) + 'px' }"
          :aria-expanded="item.is_dir ? !!item.expanded : undefined"
          :aria-current="selectedPath === item.path ? 'true' : undefined"
          data-testid="tree-node"
          @click="$emit('toggle-node', item)"
        >
          <Icon v-if="item.is_dir" :name="item.expanded ? 'chevron-down' : 'chevron-right'" class="tree-toggle" />
          <Icon :name="iconFor(item)" class="tree-icon" :class="item.is_dir ? 'tree-icon--dir' : ''" />
          <span class="tree-label">{{ item.name }}</span>
        </BaseButton>
      </div>

      <EmptyState v-if="directoryTree.length === 0" compact :description="$t('fileBrowser.treeView.noStructure')">
        <template #icon><Icon name="folder-open" size="xl" /></template>
      </EmptyState>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import Icon, { type IconName } from '@/components/ui/Icon.vue'
import { BaseButton, EmptyState } from '@autobot/ui'
import { getFileIconName } from '@/utils/iconMappings'

// #9724: aligned with FileBrowserTreeNode (useFileBrowser) — is_dir/level
// are optional in the backend payload and nodes carry nested children.
interface TreeItem {
  name: string
  path: string
  is_dir?: boolean
  level?: number
  expanded?: boolean
  children?: TreeItem[]
}

interface Props {
  directoryTree: TreeItem[]
  selectedPath: string
}

interface Emits {
  (e: 'toggle-node', item: TreeItem): void
  (e: 'expand-all'): void
  (e: 'collapse-all'): void
}

const props = defineProps<Props>()
defineEmits<Emits>()

interface TreeRow { item: TreeItem; depth: number }

// An expanded folder shows its nested children (the tree endpoint returns them nested); a flat list that already
// carries `level` keeps it. Collapsed folders hide their children, so `aria-expanded` always matches what is visible.
function flatten(nodes: TreeItem[], depth: number, out: TreeRow[]): TreeRow[] {
  for (const item of nodes) {
    out.push({ item, depth: item.level ?? depth })
    if (item.expanded && item.children) flatten(item.children, depth + 1, out)
  }
  return out
}
const rows = computed(() => flatten(props.directoryTree, 0, []))

// Icon mapping centralized in @/utils/iconMappings; an open folder shows the open-folder icon.
const iconFor = (item: TreeItem): IconName =>
  item.is_dir && item.expanded ? 'folder-open' : getFileIconName(item.name, item.is_dir)
</script>

<style scoped>
.tree-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--aui-color-surface-raised);
  border: 1px solid var(--aui-color-border);
  border-radius: var(--aui-radius-lg);
}
.tree-header {
  display: flex;
  flex-shrink: 0;
  justify-content: space-between;
  align-items: center;
  padding: var(--aui-space-4);
  border-bottom: 1px solid var(--aui-color-border);
  background: var(--aui-color-surface-sunken);
}
.tree-header h3 {
  display: flex;
  align-items: center;
  gap: var(--aui-space-2);
  font-size: var(--aui-text-lg);
  font-weight: var(--aui-font-weight-semibold);
  color: var(--aui-color-text);
}
.tree-controls {
  display: flex;
  gap: var(--aui-space-1);
}
.tree-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: var(--aui-space-2);
}
.tree-node {
  user-select: none;
}
.tree-node :deep(.tree-node-content) {
  width: 100%;
  justify-content: flex-start;
  gap: var(--aui-space-2);
}
.tree-node.selected :deep(.tree-node-content) {
  background: var(--aui-color-surface-sunken);
  box-shadow: inset 2px 0 0 var(--aui-color-primary);
  color: var(--aui-color-text);
}
.tree-toggle {
  color: var(--aui-color-text-muted);
}
.tree-icon--dir {
  color: var(--aui-color-primary);
}
/* BaseButton wraps the slot in its label span: make that span shrinkable so the label can truncate */
.tree-node :deep(.tree-node-content .aui-btn__label) {
  display: flex;
  flex: 1;
  align-items: center;
  gap: var(--aui-space-2);
  min-width: 0;
}
.tree-label {
  flex: 1;
  min-width: 0;
  font-size: var(--aui-text-sm);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: start;
}
</style>
