<template>
  <keep-alive>
    <router-view class="h-full" />
  </keep-alive>
</template>

<script setup lang="ts">
// Issue #4356: Wrap router-view in keep-alive to preserve ChatInterface state
// and avoid full remount when navigating away and back to /chat.
//
// Issue #6615: explicit class="h-full" on the inner router-view. The outer
// route in App.vue declares `<router-view class="h-full">`, but classes do
// not pass cleanly through `<keep-alive>` to the nested router-view, so the
// rendered ChatInterface root would not get its viewport-height constraint —
// breaking sidebar/input pinning and message-area scroll.
</script>
