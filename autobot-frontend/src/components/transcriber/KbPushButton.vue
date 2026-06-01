<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useTranscriberApi } from '@/composables/transcriber/useTranscriberApi'
import type { KbPushStatus } from '@/composables/transcriber/useTranscriberApi'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('KbPushButton')
const props = defineProps<{ recordingId: number }>()
const api = useTranscriberApi()

const status = ref<KbPushStatus | null>(null)
const pushing = ref(false)
const collectionId = ref('default')
const showInput = ref(false)

onMounted(async () => {
  status.value = await api.kbStatus(props.recordingId)
})

async function push() {
  pushing.value = true
  try {
    await api.kbPush(props.recordingId, collectionId.value)
    status.value = await api.kbStatus(props.recordingId)
    showInput.value = false
  } catch (err) {
    logger.error('KB push failed', err)
  } finally {
    pushing.value = false
  }
}
</script>

<template>
  <div class="kb-push">
    <div v-if="status?.pushed" class="kb-pushed-badge">
      ✅ In Knowledge Base
      <button class="btn-link btn-xs" @click="showInput = true">Re-index</button>
    </div>
    <div v-else>
      <button class="btn btn-sm btn-outline" @click="showInput = !showInput">Push to KB</button>
    </div>
    <div v-if="showInput" class="kb-push-form">
      <input v-model="collectionId" placeholder="Collection ID" class="input input-sm" />
      <button class="btn btn-sm btn-primary" @click="push" :disabled="pushing">
        {{ pushing ? 'Pushing…' : 'Confirm' }}
      </button>
    </div>
  </div>
</template>
