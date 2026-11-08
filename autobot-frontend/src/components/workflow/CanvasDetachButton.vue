<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Author: mrveiss -->
<!--
  The "x" control on an org-process node and on each role chip of an org-tool node (#14549, #14597).
  It only announces the click; the mutation is OrgChart.vue's job, reached by the canvas's event. The
  caller puts `.stop` on its listener so the click does not also select the node.
-->
<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'

defineProps<{
  /** Which node kind it sits on; sets the class and test id the tests key on. */
  kind: 'process' | 'tool'
  /** The accessible name: a bare "x" would not say what it detaches. */
  label: string
}>()
</script>

<template>
  <button
    type="button"
    class="cursor-pointer rounded border-0 bg-transparent p-1 leading-none text-autobot-text-secondary hover:bg-autobot-bg-secondary hover:text-autobot-error focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-autobot-primary"
    :class="[`${kind}-detach-btn`, kind === 'process' ? 'ms-auto' : '']"
    :data-testid="`${kind}-detach-btn`"
    :aria-label="label"
  >
    <Icon name="times" />
  </button>
</template>
