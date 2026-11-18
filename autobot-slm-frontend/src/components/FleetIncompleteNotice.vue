<script setup lang="ts">
// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/** Renderless: mounts the shell-level "node list is not the whole fleet" notice (#21584). */
import { useFleetIncompleteNotice } from '@/composables/useFleetIncompleteNotice'

useFleetIncompleteNotice()
</script>

<template>
  <span hidden />
</template>
