<!--
  Copyright 2025-2026 mrveiss
  SPDX-License-Identifier: Apache-2.0

  KnowledgeUpload — "Knowledge · Manage · Upload" (#747, #18244): three ways to give the knowledge
  base a source (typed text, a URL, files), one shared progress bar and one success / error banner.
  The accepted file types are the shared constant the server list is checked against (#17528).
-->
<template>
  <div class="knowledge-upload flex flex-col gap-4">
    <p class="m-0 text-[var(--muted)]">{{ $t('knowledge.upload.description') }}</p>

    <div class="grid grid-cols-[repeat(auto-fit,minmax(22rem,1fr))] items-start gap-4">
      <KnowledgeUploadText :feedback="feedback" />
      <KnowledgeUploadUrl :feedback="feedback" />
      <KnowledgeUploadFiles :feedback="feedback" :accept="KNOWLEDGE_UPLOAD_ACCEPT" />
    </div>

    <BaseCard v-if="feedback.progress.show" :title="feedback.progress.title">
      <BaseProgress :value="feedback.progress.percentage" :label="$t('knowledge.upload.overallProgress')" />
      <p class="mb-0 mt-2 text-[var(--text)]">{{ feedback.progress.percentage }}% - {{ feedback.progress.status }}</p>
    </BaseCard>

    <BaseAlert v-if="feedback.successMessage.value" variant="success" :message="feedback.successMessage.value" />
    <BaseAlert v-if="feedback.errorMessage.value" variant="error" :message="feedback.errorMessage.value ?? ''" />
  </div>
</template>

<script setup lang="ts">
import { BaseAlert, BaseCard, BaseProgress } from '@autobot/ui'
import { KNOWLEDGE_UPLOAD_ACCEPT } from '@/constants/knowledgeUpload'
import { useKnowledgeUploadFeedback } from '@/composables/knowledge/useKnowledgeUploadFeedback'
import KnowledgeUploadText from './upload/KnowledgeUploadText.vue'
import KnowledgeUploadUrl from './upload/KnowledgeUploadUrl.vue'
import KnowledgeUploadFiles from './upload/KnowledgeUploadFiles.vue'

const feedback = useKnowledgeUploadFeedback()
</script>
