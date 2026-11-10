<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Author: mrveiss -->
<!--
  More readable facts remain past this page (#20945): the server hands back the scan cursor it stopped at,
  so every fact the caller may read is reachable however deep the listing is.
-->
<template>
  <div class="error-notification" role="status">
    <span>{{ $t('knowledge.graph.moreFactsAvailable') }}</span>
    <button class="btn-link" @click="emit('more')">{{ $t('knowledge.graph.loadMoreFacts') }}</button>
  </div>
</template>

<script setup lang="ts">
const emit = defineEmits<{ (e: 'more'): void }>()
</script>
