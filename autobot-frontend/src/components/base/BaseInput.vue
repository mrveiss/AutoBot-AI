<template>
  <div class="base-input-wrapper" :class="wrapperClasses">
    <!-- Label -->
    <label
      v-if="label"
      :for="inputId"
      class="input-label"
      :class="{ 'label-required': required }"
    >
      {{ label }}
      <span v-if="required" class="label-asterisk">*</span>
    </label>

    <!-- Input Container -->
    <div class="input-container" :class="containerClasses">
      <!-- Prefix Icon Slot -->
      <div v-if="$slots.prefix" class="input-prefix">
        <slot name="prefix"></slot>
      </div>

      <!-- Input Element -->
      <input
        :id="inputId"
        ref="inputRef"
        :type="type"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :readonly="readonly"
        :required="required"
        :autocomplete="autocomplete"
        :class="inputClasses"
        @input="handleInput"
        @focus="handleFocus"
        @blur="handleBlur"
        @keydown="handleKeydown"
      />

      <!-- Suffix Icon Slot -->
      <div v-if="$slots.suffix || clearable" class="input-suffix">
        <button
          v-if="clearable && modelValue"
          type="button"
          class="clear-button"
          @click="handleClear"
          aria-label="Clear input"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
          </svg>
        </button>
        <slot name="suffix"></slot>
      </div>
    </div>

    <!-- Helper Text / Error Message -->
    <div v-if="helperText || error" class="input-feedback">
      <p v-if="error" class="error-text">{{ error }}</p>
      <p v-else-if="helperText" class="helper-text">{{ helperText }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

interface Props {
  modelValue?: string | number
  type?: 'text' | 'email' | 'password' | 'number' | 'tel' | 'url' | 'search'
  label?: string
  placeholder?: string
  helperText?: string
  error?: string
  size?: 'sm' | 'md' | 'lg'
  disabled?: boolean
  readonly?: boolean
  required?: boolean
  clearable?: boolean
  autocomplete?: string
  id?: string
}

const props = withDefaults(defineProps<Props>(), {
  type: 'text',
  size: 'md',
  disabled: false,
  readonly: false,
  required: false,
  clearable: false
})

const emit = defineEmits<{
  'update:modelValue': [value: string | number]
  focus: [event: FocusEvent]
  blur: [event: FocusEvent]
  keydown: [event: KeyboardEvent]
  clear: []
}>()

const inputRef = ref<HTMLInputElement>()
const isFocused = ref(false)

const inputId = computed(() => props.id || `input-${Math.random().toString(36).substr(2, 9)}`)

const wrapperClasses = computed(() => [
  `input-size-${props.size}`,
  {
    'input-disabled': props.disabled,
    'input-error': props.error,
    'input-focused': isFocused.value
  }
])

const containerClasses = computed(() => ({
  'container-focused': isFocused.value,
  'container-error': props.error,
  'container-disabled': props.disabled
}))

const inputClasses = computed(() => 'base-input')

const handleInput = (event: Event) => {
  const target = event.target as HTMLInputElement
  emit('update:modelValue', props.type === 'number' ? Number(target.value) : target.value)
}

const handleFocus = (event: FocusEvent) => {
  isFocused.value = true
  emit('focus', event)
}

const handleBlur = (event: FocusEvent) => {
  isFocused.value = false
  emit('blur', event)
}

const handleKeydown = (event: KeyboardEvent) => {
  emit('keydown', event)
}

const handleClear = () => {
  emit('update:modelValue', '')
  emit('clear')
  inputRef.value?.focus()
}

// Expose focus method
defineExpose({
  focus: () => inputRef.value?.focus(),
  blur: () => inputRef.value?.blur()
})
</script>

<style scoped>
/* Issue #901: Technical Precision Input Design */

.base-input-wrapper {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* Label */
.input-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 4px;
  font-family: var(--font-sans);
}

.label-asterisk {
  color: var(--color-error);
  margin-left: 2px;
}

/* Input Container */
.input-container {
  position: relative;
  display: flex;
  align-items: center;
  background-color: var(--bg-input);
  border: 1px solid var(--border-default);
  border-radius: 2px;
  transition: all 150ms cubic-bezier(0.4, 0, 0.2, 1);
}

.container-focused {
  border-color: var(--color-info);
  box-shadow: 0 0 0 3px var(--color-info-bg);
}

.container-error {
  border-color: var(--color-error);
}

.container-error.container-focused {
  box-shadow: 0 0 0 3px var(--color-error-bg);
}

.container-disabled {
  background-color: var(--bg-secondary);
  cursor: not-allowed;
  opacity: 0.6;
}

/* Input Element */
.base-input {
  flex: 1;
  width: 100%;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-primary);
  font-size: 14px;
  font-family: var(--font-sans);
  transition: color 150ms ease;
}

.base-input::placeholder {
  color: var(--text-muted);
}

.base-input:disabled {
  cursor: not-allowed;
  color: var(--text-muted);
}

/* Size Variants */
.input-size-sm .input-container {
  height: 32px;
  padding: 0 8px;
}

.input-size-sm .base-input {
  font-size: 13px;
}

.input-size-md .input-container {
  height: 40px;
  padding: 0 12px;
}

.input-size-md .base-input {
  font-size: 14px;
}

.input-size-lg .input-container {
  height: 48px;
  padding: 0 16px;
}

.input-size-lg .base-input {
  font-size: 16px;
}

/* Prefix/Suffix */
.input-prefix,
.input-suffix {
  display: flex;
  align-items: center;
  color: var(--text-muted);
}

.input-prefix {
  margin-right: 8px;
}

.input-suffix {
  margin-left: 8px;
  gap: 4px;
}

.clear-button {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px;
  background: transparent;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  border-radius: 2px;
  transition: all 150ms ease;
}

.clear-button:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}

/* Feedback Text */
.input-feedback {
  min-height: 18px;
}

.helper-text {
  font-size: 12px;
  color: var(--text-muted);
  margin: 0;
  font-family: var(--font-sans);
}

.error-text {
  font-size: 12px;
  color: var(--color-error);
  margin: 0;
  font-family: var(--font-sans);
  font-weight: 500;
}

/* Number input - hide spinners for cleaner look */
.base-input[type="number"]::-webkit-inner-spin-button,
.base-input[type="number"]::-webkit-outer-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

.base-input[type="number"] {
  -moz-appearance: textfield;
  font-family: var(--font-numeric);
}

/* Autofill styling */
.base-input:-webkit-autofill,
.base-input:-webkit-autofill:hover,
.base-input:-webkit-autofill:focus {
  -webkit-text-fill-color: var(--text-primary);
  -webkit-box-shadow: 0 0 0 1000px var(--bg-input) inset;
  transition: background-color 5000s ease-in-out 0s;
}
</style>
