<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss | Author: mrveiss -->
<template>
  <!-- Mobile (≤390px): tabbed fallback -->
  <div v-if="isMobile" data-testid="canvas-tabbed-layout" class="flex flex-col h-full">
    <div class="flex border-b border-border-default" role="tablist">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        :class="['px-4 py-2 text-sm font-medium', activeTab === tab.id ? 'border-b-2 border-autobot-primary text-autobot-primary' : 'text-text-secondary']"
        :aria-selected="activeTab === tab.id"
        role="tab"
        @click="activeTab = tab.id"
      >
        {{ tab.label }}
        <span v-if="tab.id === 'canvas' && agentContentBadge > 0" class="ml-1 text-xs bg-autobot-primary text-white rounded-full px-1.5">{{ agentContentBadge }}</span>
      </button>
    </div>
    <div class="flex-1 overflow-hidden">
      <div v-show="activeTab === 'chat'" class="h-full" role="tabpanel"><slot name="chat" /></div>
      <div v-show="activeTab === 'canvas'" class="h-full" role="tabpanel"><slot name="canvas" /></div>
    </div>
  </div>

  <!-- Desktop: split panel -->
  <div
    v-else
    data-testid="canvas-split-layout"
    class="flex h-full overflow-hidden select-none"
    @mousemove="onGutterDrag"
    @mouseup="stopDrag"
    @mouseleave="stopDrag"
  >
    <!-- Chat panel -->
    <div
      data-testid="chat-panel"
      :class="['overflow-hidden transition-[width] duration-150', chatPanelClass]"
      :style="chatPanelStyle"
    >
      <slot name="chat" />
    </div>

    <!-- Gutter -->
    <div
      v-if="variant === 'split'"
      data-testid="gutter"
      :class="[
        'relative flex-shrink-0 cursor-col-resize',
        'bg-border-subtle hover:bg-autobot-primary/30 active:bg-autobot-primary/50 transition-colors',
        'flex items-center justify-center',
      ]"
      :style="{ width: `${gutterWidth}px` }"
      role="separator"
      aria-label="Resize panels"
      @mousedown.prevent="startDrag"
      @dblclick="cycleSnapPreset"
    >
      <div class="w-0.5 h-8 bg-border-default rounded opacity-60" aria-hidden="true" />
    </div>

    <!-- Canvas panel -->
    <div
      data-testid="canvas-panel"
      :class="['flex-1 overflow-hidden', canvasPanelClass]"
    >
      <slot name="canvas" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import type { CanvasLayoutVariant } from '@/constants/canvas'
import { CANVAS_GUTTER_HOT_ZONE_PX, CANVAS_MOBILE_BREAKPOINT_PX, CANVAS_SPLIT_DEFAULT } from '@/constants/canvas'

const props = withDefaults(defineProps<{
  variant: CanvasLayoutVariant
  agentContentBadge?: number
}>(), { agentContentBadge: 0 })

const emit = defineEmits<{
  'variant-changed': [variant: CanvasLayoutVariant]
}>()

const gutterWidth = CANVAS_GUTTER_HOT_ZONE_PX
const chatPercent = ref<number>(CANVAS_SPLIT_DEFAULT.chat)
const dragging = ref(false)
const dragStartX = ref(0)
const dragStartPercent = ref<number>(CANVAS_SPLIT_DEFAULT.chat)
const activeTab = ref<'chat' | 'canvas'>('chat')
const isMobile = ref(false)

const tabs = [
  { id: 'chat' as const, label: 'Chat' },
  { id: 'canvas' as const, label: 'Canvas' },
]

const SNAP_PRESETS: CanvasLayoutVariant[] = ['canvas-focus', 'chat-focus', 'full-canvas', 'split']
let snapIndex = 0

function cycleSnapPreset() {
  emit('variant-changed', SNAP_PRESETS[snapIndex % SNAP_PRESETS.length])
  snapIndex++
}

function startDrag(e: MouseEvent) {
  dragging.value = true
  dragStartX.value = e.clientX
  dragStartPercent.value = chatPercent.value
}

function onGutterDrag(e: MouseEvent) {
  if (!dragging.value) return
  const container = (e.currentTarget as HTMLElement)
  const containerWidth = container.offsetWidth
  if (containerWidth === 0) return
  const dx = e.clientX - dragStartX.value
  const dpct = (dx / containerWidth) * 100
  chatPercent.value = Math.max(10, Math.min(90, dragStartPercent.value + dpct))
}

function stopDrag() {
  dragging.value = false
}

const chatPanelStyle = computed(() =>
  props.variant === 'split' ? { width: `${chatPercent.value}%` } : {}
)

const chatPanelClass = computed(() => {
  if (props.variant === 'canvas-focus' || props.variant === 'full-canvas') return 'hidden'
  if (props.variant === 'chat-focus') return 'flex-1'
  return ''
})

const canvasPanelClass = computed(() => {
  if (props.variant === 'chat-focus') return 'hidden'
  return ''
})

function checkMobile() {
  isMobile.value = window.innerWidth <= CANVAS_MOBILE_BREAKPOINT_PX
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', checkMobile)
})
</script>
