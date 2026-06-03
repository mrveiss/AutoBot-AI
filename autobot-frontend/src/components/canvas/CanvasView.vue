<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss | Author: mrveiss -->
<template>
  <div
    class="flex flex-col h-full outline-none"
    tabindex="-1"
    @keydown="onKeydown"
  >
    <canvas-split-layout
      :variant="layoutVariant"
      :agent-content-badge="agentCellCount"
      @variant-changed="layoutVariant = $event"
    >
      <template #chat>
        <slot name="chat">
          <div class="flex items-center justify-center h-full text-text-secondary text-sm p-4">
            Chat panel — connect to chat interface via slot
          </div>
        </slot>
      </template>
      <template #canvas>
        <canvas-panel
          :canvas-id="canvasId"
          :auto-save="autoSave"
          :load-error="loadError"
          @retry-load="loadCanvas"
          @retry-stream="$emit('retry-stream', $event)"
          @retry-save="triggerRetrySave"
        />
      </template>
    </canvas-split-layout>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useCanvasStore } from '@/stores/useCanvasStore'
import { useCanvasAutoSave } from '@/composables/useCanvasAutoSave'
import { useCanvasWebSocket } from '@/composables/useCanvasWebSocket'
import { useApiClient } from '@/plugins/api'
import CanvasSplitLayout from './CanvasSplitLayout.vue'
import CanvasPanel from './CanvasPanel.vue'
import type { CanvasLayoutVariant } from '@/constants/canvas'
import type { CanvasDocument } from '@/types/canvas'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('CanvasView')

const props = defineProps<{ canvasId: string }>()

const emit = defineEmits<{
  'retry-stream': [cellId: string]
  'focus-chat': []
}>()

const store = useCanvasStore()
const layoutVariant = ref<CanvasLayoutVariant>('split')
const loadError = ref(false)
const api = useApiClient()

async function saveCanvas(canvasId: string, cells: unknown[]) {
  await api.put(`/api/canvas/${canvasId}`, { cells })
}

const autoSave = useCanvasAutoSave(saveCanvas)
useCanvasWebSocket(props.canvasId)

async function loadCanvas() {
  loadError.value = false
  try {
    const doc = await api.get<CanvasDocument>(`/api/canvas/${props.canvasId}`)
    store.setCanvas(doc)
  } catch (err) {
    logger.error('Failed to load canvas', err)
    loadError.value = true
  }
}

function triggerRetrySave() {
  if (store.canvasId) store.isDirty = true
}

onMounted(loadCanvas)

const agentCellCount = computed(() =>
  store.cells.filter(c => c.owner === 'agent' && c.streamState === 'complete').length
)

function onKeydown(e: KeyboardEvent) {
  const meta = e.metaKey || e.ctrlKey
  const focused = store.focusedCellId

  if (meta && !e.shiftKey && e.key === 'z') {
    e.preventDefault()
    store.undo()
    return
  }
  if (meta && e.shiftKey && e.key === 'Z') {
    e.preventDefault()
    store.redo()
    return
  }
  if (meta && e.shiftKey && e.key === 'E') {
    e.preventDefault()
    // Export is triggered via toolbar emit; this shortcut fires the palette's export button
    return
  }
  if (meta && e.key === 'l') {
    e.preventDefault()
    emit('focus-chat')
    return
  }
  if (focused) {
    const cell = store.cells.find(c => c.id === focused)
    if (cell?.owner === 'agent' && cell.streamState === 'complete') {
      if (e.altKey && e.key === 'Enter') {
        e.preventDefault()
        cell.owner = 'user'
        return
      }
      if (e.key === 'Escape') {
        e.preventDefault()
        store.deleteCell(focused)
        return
      }
    }
    if (meta && e.key === 'ArrowUp') {
      e.preventDefault()
      store.moveCell(focused, 'up')
      return
    }
    if (meta && e.key === 'ArrowDown') {
      e.preventDefault()
      store.moveCell(focused, 'down')
      return
    }
  }
}
</script>
