<!--
AutoBot - AI-Powered Automation Platform
Copyright (c) 2025 mrveiss
Author: mrveiss

LanguageSwitcher.vue - Globe icon language switcher for nav bar
-->

<template>
  <div class="language-switcher" :class="{ 'language-switcher--mobile': mobile }">
    <!-- Desktop: icon button that opens dropdown -->
    <template v-if="!mobile">
      <button
        ref="triggerRef"
        @click="toggleDropdown"
        class="lang-trigger"
        :aria-label="t('nav.switchLanguage')"
        :aria-expanded="open"
        aria-haspopup="listbox"
      >
        <Icon name="globe" />
      </button>

      <Transition name="lang-dropdown">
        <ul
          v-if="open"
          ref="dropdownRef"
          role="listbox"
          class="lang-dropdown"
          :aria-label="t('nav.switchLanguage')"
        >
          <li
            v-for="lang in languages"
            :key="lang.code"
            role="option"
            :aria-selected="lang.code === currentLanguage"
            class="lang-option"
            :class="{ 'lang-option--active': lang.code === currentLanguage }"
            @click="select(lang.code)"
          >
            <Icon name="check" class="lang-option__check" v-if="lang.code === currentLanguage"
              
              aria-hidden="true" />
            <span class="lang-option__name">{{ lang.name }}</span>
          </li>
        </ul>
      </Transition>
    </template>

    <!-- Mobile: inline row with select -->
    <template v-else>
      <div class="lang-mobile-row">
        <Icon name="globe" class="lang-mobile-icon" />
        <select
          :value="currentLanguage"
          @change="select(($event.target as HTMLSelectElement).value)"
          class="lang-mobile-select"
          :aria-label="t('nav.switchLanguage')"
        >
          <option
            v-for="lang in languages"
            :key="lang.code"
            :value="lang.code"
          >
            {{ lang.name }}
          </option>
        </select>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import Icon from '@/components/ui/Icon.vue'
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePreferences } from '@/composables/usePreferences'
import { useAvailableLanguages } from '@/composables/useAvailableLanguages'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('LanguageSwitcher')

defineProps<{ mobile?: boolean }>()

const { t } = useI18n()
const { language, setLanguage } = usePreferences()
const { languages } = useAvailableLanguages()

const open = ref(false)
const triggerRef = ref<HTMLElement | null>(null)
const dropdownRef = ref<HTMLElement | null>(null)

const currentLanguage = computed(() => language.value)

function toggleDropdown() {
  open.value = !open.value
}

async function select(code: string) {
  open.value = false
  if (code === currentLanguage.value) return
  try {
    await setLanguage(code)
  } catch (err) {
    logger.error('Failed to switch language', err)
  }
}

function handleOutsideClick(event: MouseEvent) {
  const target = event.target as Node
  if (
    triggerRef.value && !triggerRef.value.contains(target) &&
    dropdownRef.value && !dropdownRef.value.contains(target)
  ) {
    open.value = false
  }
}

onMounted(() => document.addEventListener('click', handleOutsideClick))
onUnmounted(() => document.removeEventListener('click', handleOutsideClick))
</script>

<style scoped>
.language-switcher {
  position: relative;
}

/* Theme-aware: the hardcoded white icon was invisible on the light-mode
   navbar (light-on-light). Use text/bg tokens so it works in both themes. */
.lang-trigger {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  background-color: transparent;
  color: var(--text-secondary);
  font-size: var(--text-lg);
  transition: all var(--duration-200) var(--ease-out);
  cursor: pointer;
}

.lang-trigger:hover {
  background-color: var(--bg-tertiary);
  color: var(--text-primary);
  transform: scale(1.05);
}

.lang-trigger:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.lang-dropdown {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  min-width: 160px;
  background: var(--bg-secondary);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  z-index: var(--z-popover);
  padding: var(--spacing-xs) 0;
  list-style: none;
  margin: var(--spacing-0);
}

.lang-option {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  cursor: pointer;
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  transition: background var(--duration-150);
}

.lang-option:hover {
  background: var(--bg-tertiary);
}

.lang-option--active {
  color: var(--color-primary);
  font-weight: 600;
}

.lang-option__check {
  font-size: var(--font-size-xs);
  color: var(--color-primary);
  width: 12px;
}

.lang-option__name {
  flex: 1;
}

/* Mobile row */
.lang-mobile-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  color: var(--text-primary);
}

.lang-mobile-icon {
  width: 16px;
  text-align: center;
}

.lang-mobile-select {
  flex: 1;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  cursor: pointer;
  appearance: none;
}

.lang-mobile-select:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
  border-radius: var(--radius-sm);
}

/* Dropdown transition */
.lang-dropdown-enter-active,
.lang-dropdown-leave-active {
  transition: opacity var(--duration-150) var(--ease-out), transform var(--duration-150) var(--ease-out);
}

.lang-dropdown-enter-from,
.lang-dropdown-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
</style>
