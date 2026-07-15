<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss | Author: mrveiss -->
<template>
  <div class="flex flex-col h-full overflow-hidden">
    <canvas-tool-palette
      :save-status="autoSave.status.value"
      :last-saved-at="autoSave.lastSavedAt.value"
      @export="showExport = true"
      @retry-save="$emit('retry-save')"
    />

    <canvas-conflict-banner
      :conflict="store.conflict"
      @resume="onConflictResume"
      @dismiss="store.resolveConflict()"
    />

    <!-- Non-blocking agent-working banner -->
    <canvas-edge-states
      v-if="agentWorking && !store.isEmpty"
      state="agent-working"
    />

    <!-- Full-panel edge states (empty / load-error) -->
    <canvas-edge-states
      v-if="store.isEmpty || loadError"
      :state="loadError ? 'load-error' : 'empty'"
      @add-cell="store.addCell('user')"
      @retry="$emit('retry-load')"
    />

    <!-- Cell list -->
    <div
      v-else
      class="flex-1 overflow-y-auto p-4"
      role="list"
      aria-label="Canvas cells"
      data-testid="canvas-cells-list"
    >
      <canvas-cell
        v-for="cell in store.cells"
        :key="cell.id"
        :cell="cell"
        :data-testid="`canvas-cell-${cell.id}`"
        :data-owner="cell.owner"
        role="listitem"
        @accept="onAccept(cell.id)"
        @edit="onEdit(cell.id)"
        @discard="store.deleteCell(cell.id)"
        @cancel="onCancelStream(cell.id)"
        @keep="onKeepError(cell.id)"
        @retry="$emit('retry-stream', cell.id)"
        @conflict-click="onConflictClick(cell)"
      >
        <template #toolbar>
          <canvas-cell-toolbar
            :cell-id="cell.id"
            @move="store.moveCell(cell.id, $event)"
            @duplicate="store.duplicateCell(cell.id)"
            @copy="copyCell(cell)"
            @delete="store.deleteCell(cell.id)"
          />
        </template>
      </canvas-cell>
    </div>

    <canvas-export-sheet
      :open="showExport"
      @close="showExport = false"
      @export="onExport"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useCanvasStore } from '@/stores/useCanvasStore'
import type { CanvasCell as CellType } from '@/types/canvas'
import type { useCanvasAutoSave } from '@/composables/useCanvasAutoSave'
import CanvasCell from './CanvasCell.vue'
import CanvasCellToolbar from './CanvasCellToolbar.vue'
import CanvasToolPalette from './CanvasToolPalette.vue'
import CanvasConflictBanner from './CanvasConflictBanner.vue'
import CanvasEdgeStates from './CanvasEdgeStates.vue'
import CanvasExportSheet from './CanvasExportSheet.vue'

defineProps<{
  canvasId: string
  autoSave: ReturnType<typeof useCanvasAutoSave>
  loadError?: boolean
}>()

defineEmits<{
  'retry-load': []
  'retry-stream': [cellId: string]
  'retry-save': []
}>()

const store = useCanvasStore()
const showExport = ref(false)

const agentWorking = computed(() =>
  store.cells.some(c => c.owner === 'agent' && c.streamState === 'skeleton')
)

function onAccept(cellId: string) {
  const cell = store.cells.find(c => c.id === cellId)
  if (cell) cell.owner = 'user'
}

function onEdit(cellId: string) {
  const cell = store.cells.find(c => c.id === cellId)
  if (cell) { cell.owner = 'user'; cell.streamState = 'complete' }
  store.setFocusedCell(cellId)
}

function onCancelStream(cellId: string) {
  const cell = store.cells.find(c => c.id === cellId)
  if (cell) cell.streamState = 'complete'
}

function onKeepError(cellId: string) {
  const cell = store.cells.find(c => c.id === cellId)
  if (cell) { cell.owner = 'user'; cell.streamState = 'complete' }
}

function onConflictClick(cell: CellType) {
  store.triggerConflict(cell.id, cell.seq)
}

function onConflictResume() {
  store.addCell('agent')
  store.resolveConflict()
}

function copyCell(cell: CellType) {
  navigator.clipboard.writeText(cell.content).catch(() => {})
}

function onExport(format: string, types: string[]) {
  const cells = store.cells.filter(c => types.includes(c.contentType))
  const content = cells.map(c => c.content).join('\n\n---\n\n')
  const mimeMap: Record<string, string> = {
    markdown: 'text/markdown',
    html: 'text/html',
    json: 'application/json',
    pdf: 'text/plain',
  }
  const extMap: Record<string, string> = { markdown: 'md', html: 'html', json: 'json', pdf: 'txt' }
  const blob = new Blob([format === 'json' ? JSON.stringify(cells, null, 2) : content], {
    type: mimeMap[format] ?? 'text/plain',
  })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `canvas.${extMap[format] ?? 'txt'}`
  a.click()
  URL.revokeObjectURL(a.href)
}
</script>
