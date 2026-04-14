<template>
  <keep-alive>
    <router-view />
  </keep-alive>
</template>

<script setup lang="ts">
// Issue #4356: Wrap router-view in keep-alive to preserve ChatInterface state
// and avoid full remount when navigating away and back to /chat
</script>
