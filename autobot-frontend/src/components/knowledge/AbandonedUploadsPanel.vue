<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!--
  AbandonedUploadsPanel (#20905): chunked uploads that expired unfinished still take up disk.
  An admin reviews the list and frees one; the server records the decision before removing anything.
-->
<template>
  <BaseCard
    :title="t('knowledge.abandonedUploads.title')"
    :subtitle="t('knowledge.abandonedUploads.description')"
    data-testid="abandoned-uploads"
  >
    <BaseAlert v-if="loadFailed" variant="warning" :message="t('knowledge.abandonedUploads.loadFailed')" />
    <p v-else-if="!loaded">{{ t('admin.cleanup.loading') }}</p>
    <p v-else-if="uploads.length === 0">{{ t('knowledge.abandonedUploads.none') }}</p>
    <ul v-else class="list-none p-0">
      <li class="flex items-center gap-3 py-1" v-for="u in uploads" :key="u.upload_id" :data-testid="`abandoned-${u.upload_id}`">
        <span>{{ u.filename }}</span>
        <span>{{ t('knowledge.abandonedUploads.progress', { received: formatFileSize(u.received), total: formatFileSize(u.total_size) }) }}</span>
        <BaseButton size="sm" :disabled="busyId !== ''" @click="free(u.upload_id)">
          {{ t('knowledge.abandonedUploads.free') }}
        </BaseButton>
      </li>
    </ul>
    <BaseAlert v-if="error" variant="error" :message="error" />
  </BaseCard>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BaseAlert, BaseButton, BaseCard, formatFileSize } from '@autobot/ui'
import { createLogger } from '@/utils/debugUtils'
import { useConfirmDialog } from '@/composables/useConfirmDialog'
import { useExpiredUploads } from '@/composables/knowledge/useExpiredUploads'

const { t } = useI18n()
const logger = createLogger('AbandonedUploadsPanel')
const { uploads, loaded, loadFailed, load, remove } = useExpiredUploads()
const { confirm } = useConfirmDialog()

const busyId = ref('')
const error = ref('')

async function free(uploadId: string): Promise<void> {
  const ok = await confirm({ title: t('common.confirm'), message: t('knowledge.abandonedUploads.confirm') })
  if (!ok) return
  busyId.value = uploadId
  error.value = ''
  try {
    await remove(uploadId)
  } catch (err) {
    error.value = t('knowledge.abandonedUploads.freeFailed')
    logger.error('Could not free the abandoned upload', uploadId, err)
  } finally {
    busyId.value = ''
  }
}

onMounted(() => void load())
</script>
