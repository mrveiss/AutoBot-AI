<template>
  <PopoutChromiumBrowser 
    :session-id="browserSessionId"
    :initial-url="'about:blank'"
    :chat-context="false"
    class="h-full"
  />
</template>

<script setup>
import { ref } from 'vue'
import PopoutChromiumBrowser from './PopoutChromiumBrowser.vue'

// Generate a unique session ID for this browser instance
const browserSessionId = ref(`tools-browser-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`)
</script>

<style scoped>
/* Browser fills the full height */
</style>