<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!--
  KnowledgeUploadTab: the upload manager's tab. The upload form for everyone; for an admin also the
  abandoned chunked uploads to review and free (#20905).
-->
<template>
  <div>
    <KnowledgeUpload />
    <AbandonedUploadsPanel v-if="isAdmin" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import KnowledgeUpload from './KnowledgeUpload.vue'
import AbandonedUploadsPanel from './AbandonedUploadsPanel.vue'
import { useUserStore } from '@/stores/useUserStore'

const userStore = useUserStore()
const isAdmin = computed(() => userStore.isAdmin)
</script>
