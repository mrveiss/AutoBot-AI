<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->

<script setup lang="ts">
/** #10200: people whose SLM copy the main app could not update. They may keep access until it can. */
import { onMounted, ref } from 'vue'
import { createAutobotBackendClient } from '@/composables/useAutobotApi'
import { createLogger } from '@/utils/debugUtils'
import { BaseAlert } from '@autobot/ui'

const logger = createLogger('PersonPushFailuresAlert')
const usernames = ref<string[]>([])

onMounted(async () => {
  try {
    const client = createAutobotBackendClient()
    const response: { failures: { username: string }[] } = await client.get('/admin/person-links/push-failures')
    usernames.value = response.failures.map((failure) => failure.username)
  } catch (err) {
    // With the main app down this page already works from the SLM's copy, and nothing can be pushed.
    logger.warn('Could not read push failures', err)
  }
})
</script>

<template>
  <BaseAlert
    v-if="usernames.length"
    variant="error"
    :message="$t('settings.admin.userManagementSettings.personPushFailed', { names: usernames.join(', ') })"
  />
</template>
