<template>
  <div class="p-6 max-w-7xl mx-auto">
    <div class="audit-log-container">
      <SecretAuditLog />
    </div>
  </div>
</template>

<script setup lang="ts">
import SecretAuditLog from '@/components/secrets/SecretAuditLog.vue'
</script>

<style scoped>
/* #16429: SecretAuditLog.vue is `h-full flex flex-col` and needs a bounded
   ancestor height to render its scroll region -- this page has no h-full
   chain from App.vue (unlike the LLC board layout), so a concrete height is
   the simplest correct fix rather than routing this page into that chain. */
.audit-log-container {
  height: 600px;
}
</style>
