<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025-2026 mrveiss -->
<!-- Author: mrveiss -->
<!--
  LlcBreadcrumb (GH#9628) — the LLC Portfolio → Program → Project trail. A thin wrapper over
  the kit's Breadcrumb (#17563): it supplies RouterLink and the translated landmark name, and
  keeps the LLC views' spacing under the trail.
-->
<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { Breadcrumb, type BreadcrumbItem } from '@autobot/ui'

export type { BreadcrumbItem }

defineProps<{
  items: BreadcrumbItem[]
}>()
</script>

<template>
  <Breadcrumb class="llc-breadcrumb" :items="items" :label="$t('common.breadcrumb')" :link-as="RouterLink" />
</template>

<style scoped>
.llc-breadcrumb {
  margin-bottom: var(--aui-space-4);
}
</style>
