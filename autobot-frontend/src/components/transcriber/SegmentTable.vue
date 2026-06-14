<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import type { Segment, Speaker } from '@/composables/transcriber/useTranscriberApi'
import { useTranscriberApi } from '@/composables/transcriber/useTranscriberApi'
import { useInlineEdit } from '@/composables/useInlineEdit'
import { useTranscriberStore } from '@/stores/transcriber/useTranscriberStore'

const props = defineProps<{ segments: Segment[]; speakers: Speaker[]; currentTime?: number }>()
const emit = defineEmits<{ (e: 'seek', seconds: number): void }>()

const api = useTranscriberApi()
const store = useTranscriberStore()
const { editingId, editText, startEdit, saveEdit } = useInlineEdit<Segment>(
  (seg) => seg.text,
  async (seg, value) => {
    await api.updateSegment(seg.id, value)
    store.updateSegmentText(seg.id, value)
  }
)

function fmt(s: number) {
  const m = Math.floor(s / 60), sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

function speakerName(speakerId: number | null) {
  return store.speakerName(speakerId)
}

function isActive(seg: Segment) {
  const t = props.currentTime ?? 0
  return t >= seg.start_time && t < seg.end_time
}
</script>

<template>
  <div class="segment-table">
    <div
      v-for="seg in segments"
      :key="seg.id"
      class="segment-row"
      :class="{ 'segment-active': isActive(seg), 'segment-edited': seg.is_edited }"
    >
      <span class="segment-speaker">{{ speakerName(seg.speaker_id) }}</span>
      <button class="segment-time btn-link" @click="emit('seek', seg.start_time)">
        {{ fmt(seg.start_time) }}
      </button>
      <div class="segment-text-cell">
        <textarea
          v-if="editingId === seg.id"
          v-model="editText"
          class="segment-edit-input"
          rows="2"
          @blur="saveEdit(seg)"
          @keydown.enter.exact.prevent="saveEdit(seg)"
          @keydown.escape="editingId = null"
          autofocus
        />
        <span
          v-else
          class="segment-text"
          @dblclick="startEdit(seg)"
          :title="'Double-click to edit'"
        >{{ seg.text }}</span>
      </div>
    </div>
  </div>
</template>
