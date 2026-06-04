<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { ref } from 'vue'
import { useTranscriberApi } from '@/composables/transcriber/useTranscriberApi'
import type { Recording } from '@/composables/transcriber/useTranscriberApi'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('UploadModal')
const props = defineProps<{ projectId: number; open: boolean }>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'uploaded', r: Recording): void }>()
const api = useTranscriberApi()
const file = ref<File | null>(null)
const uploading = ref(false)
const dragover = ref(false)

const ACCEPT = '.wav,.mp3,.mp4,.m4a,.ogg,.flac,.webm'

function onDrop(e: DragEvent) {
  dragover.value = false
  const f = e.dataTransfer?.files[0]
  if (f) file.value = f
}

async function upload() {
  if (!file.value) return
  uploading.value = true
  try {
    const rec = await api.uploadRecording(props.projectId, file.value)
    emit('uploaded', rec)
    emit('close')
  } catch (err) {
    logger.error('Upload failed', err)
  } finally {
    uploading.value = false
    file.value = null
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="modal-overlay" @click.self="emit('close')">
      <div class="modal">
        <div class="modal-header">
          <h3>Upload Recording</h3>
          <button class="btn-icon" @click="emit('close')">✕</button>
        </div>
        <div
          class="drop-zone"
          :class="{ 'drop-zone-active': dragover }"
          @dragover.prevent="dragover = true"
          @dragleave="dragover = false"
          @drop.prevent="onDrop"
          @click="($refs.fileInput as HTMLInputElement).click()"
        >
          <input
            ref="fileInput"
            type="file"
            :accept="ACCEPT"
            class="hidden"
            @change="file = ($event.target as HTMLInputElement).files?.[0] ?? null"
          />
          <span v-if="file">{{ file.name }}</span>
          <span v-else>Drag audio file here or click to browse</span>
        </div>
        <div class="modal-footer">
          <button class="btn btn-primary" @click="upload" :disabled="!file || uploading">
            {{ uploading ? 'Uploading…' : 'Upload & Process' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
