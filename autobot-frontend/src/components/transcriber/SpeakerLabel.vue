<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { ref } from 'vue'
import type { Speaker } from '@/composables/transcriber/useTranscriberApi'
import { useTranscriberApi } from '@/composables/transcriber/useTranscriberApi'
import { useTranscriberStore } from '@/stores/transcriber/useTranscriberStore'

const props = defineProps<{ speaker: Speaker }>()
const api = useTranscriberApi()
const store = useTranscriberStore()
const editing = ref(false)
const name = ref(props.speaker.display_name)

async function save() {
  editing.value = false
  if (name.value === props.speaker.display_name) return
  await api.updateSpeaker(props.speaker.id, name.value)
  store.updateSpeakerName(props.speaker.id, name.value)
}
</script>

<template>
  <span class="speaker-label">
    <input
      v-if="editing"
      v-model="name"
      class="speaker-edit-input"
      @blur="save"
      @keydown.enter.prevent="save"
      @keydown.escape="editing = false"
      autofocus
    />
    <span v-else class="speaker-chip" @dblclick="editing = true" :title="'Double-click to rename'">
      {{ speaker.display_name }}
    </span>
  </span>
</template>
