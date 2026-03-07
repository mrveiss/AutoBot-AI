<template>
  <div class="about-view view-container-centered">
    <h1>{{ $t('views.about.title') }}</h1>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<style scoped>
/* View-specific styles - centered layout provided by .view-container-centered (Issue #548) */
</style>
