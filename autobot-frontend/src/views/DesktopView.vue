<template>
  <div class="desktop-view view-container-full">
    <DesktopAccessDenied v-if="!canUseDesktop" />
    <DesktopInterface v-else />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import DesktopInterface from '@/components/desktop/DesktopInterface.vue'
import DesktopAccessDenied from '@/components/desktop/DesktopAccessDenied.vue'
import { usePermissions } from '@/composables/usePermissions'

// #17370: the desktop socket refuses a caller without `mcp.desktop.control`
// (#17054/#17369). Gated through `holdsPermission` -- the role table, no
// administrative override -- so this agrees with the socket on every role,
// including superadmin, whose table entry is empty and whom the socket
// refuses while `hasPermission` would return true.
//
// Not the boundary. The socket is. This is so a refused caller reads an
// explanation instead of a viewer that never connects.
//
// `/desktop` redirects to `/chat` (router/index.ts:905), so this view is
// unreachable by URL today. Gated anyway: an unreachable mounted viewer is
// unfinished work, and the redirect is one line away from being removed.
const { holdsPermission } = usePermissions()
const canUseDesktop = computed(() => holdsPermission('mcp.desktop.control'))
</script>

<style scoped>
@reference "../assets/tailwind.css";
/* View-specific styles - layout provided by .view-container-full (Issue #548) */
.desktop-view {
  @apply bg-autobot-bg-secondary;
}
</style>
