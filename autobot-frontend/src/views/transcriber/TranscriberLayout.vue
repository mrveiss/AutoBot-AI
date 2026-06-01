<!-- AutoBot - AI-Powered Automation Platform -->
<!-- Copyright (c) 2025 mrveiss -->
<script setup lang="ts">
import { useRouter } from 'vue-router'
const router = useRouter()
</script>

<template>
  <div class="transcriber-layout">
    <aside class="transcriber-sidebar">
      <RouterLink :to="{ name: 'transcriber-projects' }" class="sidebar-link">
        Projects
      </RouterLink>
    </aside>
    <main class="transcriber-content">
      <RouterView />
    </main>
  </div>
</template>
