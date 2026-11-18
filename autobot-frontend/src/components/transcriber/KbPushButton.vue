<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useTranscriberApi } from '@/composables/transcriber/useTranscriberApi'
import { useKbStatus } from '@/composables/transcriber/useKbStatus'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('KbPushButton')
const { t } = useI18n()
const props = defineProps<{ recordingId: number }>()
const api = useTranscriberApi()
const { status, refresh } = useKbStatus(props.recordingId)

const pushing = ref(false)
const collectionId = ref('default')
const showInput = ref(false)
// #17535: the push failure was logged and nothing else. The form closed on
// success and stayed open on failure, which is the only difference a user
// could see -- so a failed push and a slow one looked the same. Surfaced
// rather than filed separately, since it is four lines in a file this change
// already rewrites.
const pushError = ref('')

onMounted(async () => {
  await refresh()
})

async function push() {
  pushing.value = true
  pushError.value = ''
  try {
    // #17533: the push can succeed at storing and fail at routing. The route answers
    // `partial` for exactly that, and this discarded the response -- so a transcript
    // that never joined the named collection closed the form like a clean success.
    // The collection is UUID-keyed and this field is free text, so `partial` was the
    // normal outcome, not an edge case.
    // `status` is top-level: transcriber/routes/kb.py returns a plain dict and
    // ApiClient.post returns the parsed body, not an envelope. Reading result.data
    // here type-checks as `any` in some shapes and is simply always undefined at
    // runtime -- a check that never fires and a bug that looks fixed.
    const result = await api.kbPush(props.recordingId, collectionId.value)
    await refresh()
    if (result?.status === 'partial') {
      pushError.value = t('transcriber.kbPush.collectionNotJoined')
      return
    }
    showInput.value = false
  } catch (err) {
    logger.error('KB push failed', err)
    pushError.value = t('transcriber.kbPush.pushFailed')
  } finally {
    pushing.value = false
  }
}
</script>

<template>
  <div class="kb-push">
    <div v-if="status?.pushed" class="kb-pushed-badge">
      <!-- #17535: the tick stays markup rather than joining the string, so
           eleven translators are not each carrying an emoji. -->
      <span aria-hidden="true">✅</span>
      {{ t('transcriber.kbPush.inKnowledgeBase') }}
      <button class="btn-link btn-xs" @click="showInput = true">
        {{ t('transcriber.kbPush.reindex') }}
      </button>
    </div>
    <div v-else>
      <button class="btn btn-sm btn-outline" @click="showInput = !showInput">
        {{ t('transcriber.kbPush.push') }}
      </button>
    </div>
    <div v-if="showInput" class="kb-push-form">
      <input
        v-model="collectionId"
        :placeholder="t('transcriber.kbPush.collectionIdPlaceholder')"
        class="input input-sm"
      />
      <button class="btn btn-sm btn-primary" @click="push" :disabled="pushing">
        {{ pushing ? t('transcriber.kbPush.pushing') : t('transcriber.kbPush.confirm') }}
      </button>
      <p v-if="pushError" class="field-error-msg" role="alert">{{ pushError }}</p>
    </div>
  </div>
</template>
