<!-- autobot-frontend/src/components/transcriber/ExportMenu.vue -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { ref } from 'vue'
import { useTranscriberApi } from '@/composables/transcriber/useTranscriberApi'
import { useFileDownload } from '@/composables/useFileDownload'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ExportMenu')
const props = defineProps<{ recordingId: number; filename: string }>()
const api = useTranscriberApi()
const { download } = useFileDownload()
const open = ref(false)
const exporting = ref(false)

const FORMATS = [
  { key: 'docx', label: 'Word Document (.docx)' },
  { key: 'pdf', label: 'PDF Document (.pdf)' },
  { key: 'srt', label: 'Subtitles (.srt)' },
  { key: 'vtt', label: 'WebVTT (.vtt)' },
] as const

async function doExport(format: 'docx' | 'pdf' | 'srt' | 'vtt') {
  open.value = false
  exporting.value = true
  try {
    const resp = await api.exportRecording(props.recordingId, format)
    const blob = await resp.blob()
    download(blob, `${props.filename}.${format}`)
  } catch (err) {
    logger.error('Export failed', err)
  } finally {
    exporting.value = false
  }
}
</script>

<template>
  <div class="export-menu" v-click-outside="() => (open = false)">
    <button class="btn btn-sm" @click="open = !open" :disabled="exporting">
      {{ exporting ? 'Exporting…' : 'Export ▾' }}
    </button>
    <div v-if="open" class="export-dropdown">
      <button
        v-for="fmt in FORMATS"
        :key="fmt.key"
        class="export-option"
        @click="doExport(fmt.key)"
      >{{ fmt.label }}</button>
    </div>
  </div>
</template>
