<template>
  <div class="about-view view-container px-6 py-8 max-w-3xl mx-auto">
    <!-- Header -->
    <div class="mb-8">
      <div class="flex items-center gap-3 mb-2">
        <div class="w-10 h-10 bg-autobot-primary rounded-lg flex items-center justify-center shrink-0">
          <span class="text-white font-bold text-lg font-mono">AB</span>
        </div>
        <h1 class="text-2xl font-bold text-autobot-text-primary">{{ $t('views.about.title') }}</h1>
      </div>
      <p class="text-autobot-text-secondary text-base">{{ $t('views.about.tagline') }}</p>
    </div>

    <!-- Description -->
    <section class="mb-8">
      <h2 class="text-base font-semibold text-autobot-text-primary mb-2">
        {{ $t('views.about.descriptionHeading') }}
      </h2>
      <p class="text-autobot-text-secondary leading-relaxed">{{ $t('views.about.description') }}</p>
    </section>

    <!-- Capabilities -->
    <section class="mb-8">
      <h2 class="text-base font-semibold text-autobot-text-primary mb-3">
        {{ $t('views.about.capabilitiesHeading') }}
      </h2>
      <ul class="space-y-2">
        <li
          v-for="n in 5"
          :key="n"
          class="flex items-start gap-2 text-autobot-text-secondary"
        >
          <svg class="w-4 h-4 mt-0.5 shrink-0 text-autobot-primary" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
            <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd" />
          </svg>
          <span>{{ $t(`views.about.capability${n}`) }}</span>
        </li>
      </ul>
    </section>

    <!-- Meta -->
    <section class="border-t border-autobot-border pt-6">
      <dl class="grid grid-cols-2 gap-x-8 gap-y-3 max-w-xs text-sm">
        <dt class="text-autobot-text-muted font-medium uppercase tracking-wide text-xs">{{ $t('views.about.versionLabel') }}</dt>
        <dd class="text-autobot-text-primary font-mono">{{ appVersion }}</dd>
        <dt class="text-autobot-text-muted font-medium uppercase tracking-wide text-xs">{{ $t('views.about.authorLabel') }}</dt>
        <dd class="text-autobot-text-primary">{{ $t('views.about.authorName') }}</dd>
        <dt class="text-autobot-text-muted font-medium uppercase tracking-wide text-xs">{{ $t('views.about.licenseLabel') }}</dt>
        <dd class="text-autobot-text-primary">{{ $t('views.about.licenseValue') }}</dd>
      </dl>
    </section>
  </div>
</template>

<script setup lang="ts">

// Read version from Vite's env injection (set in vite.config.ts via define)
// Falls back to '—' if not injected
const appVersion = import.meta.env.VITE_APP_VERSION ?? '—'
</script>

<style scoped>
/* view-container provides scroll and height constraints (Issue #548) */
</style>
