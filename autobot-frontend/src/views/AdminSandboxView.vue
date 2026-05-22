<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<!-- Author: mrveiss -->
<!--
  AdminSandboxView — code-execution sandbox file inspector.
  Wires useFileSandbox() into a UI panel (GH#7773 wire-in requirement).
-->
<template>
  <div class="admin-sandbox-view view-container">
    <div class="page-header">
      <div class="page-header-content">
        <h2 class="page-title">Sandbox Inspector</h2>
        <p class="page-subtitle">Browse and inspect files in the code-execution sandbox</p>
      </div>
    </div>

    <SandboxFileBrowser />
  </div>
</template>

<script setup lang="ts">
import SandboxFileBrowser from '@/components/file-browser/SandboxFileBrowser.vue'
</script>

<style scoped>
.admin-sandbox-view {
  padding: 1.5rem;
}
</style>
