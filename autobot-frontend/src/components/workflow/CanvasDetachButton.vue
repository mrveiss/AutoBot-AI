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
  /** Which node kind it sits on; sets the class and test id the tests and stylesheet key on. */
  kind: 'process' | 'tool'
  /** The accessible name: a bare "x" would not say what it detaches. */
  label: string
}>()
</script>

<template>
  <button
    type="button"
    class="canvas-detach-btn"
    :class="`${kind}-detach-btn`"
    :data-testid="`${kind}-detach-btn`"
    :aria-label="label"
  >
    <Icon name="times" />
  </button>
</template>

<style scoped>
.canvas-detach-btn {
  padding: var(--spacing-1);
  background: transparent;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: var(--radius-default);
  line-height: 1;
}
.process-detach-btn {
  margin-inline-start: auto;
}
.canvas-detach-btn:hover {
  color: var(--color-error);
  background: var(--bg-hover);
}
.canvas-detach-btn:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}
</style>
