# useFormValidation Composable - Migration Examples

This document demonstrates how to migrate existing forms to use the centralized `useFormValidation.ts` composable.

---

## Table of Contents

1. [LoginForm.vue Migration](#loginformvue-migration)
2. [BackendSettings.vue Migration](#backendsettingsvue-migration)
3. [KnowledgeUpload.vue Migration](#knowledgeuploadvue-migration)
4. [NPUWorkersSettings.vue Migration](#npuworkerssettingsvue-migration)
5. [Quick Reference](#quick-reference)

---

## LoginForm.vue Migration

### ❌ BEFORE (Lines 94-169)

```vue
<script setup lang="ts">
import { ref, computed, reactive } from 'vue'

const credentials = reactive({
  username: '',
  password: ''
})

const validationErrors = reactive({
  username: '',
  password: ''
})

// Computed properties
const isFormValid = computed(() => {
  return credentials.username.length >= 2 &&
         credentials.password.length >= 1 &&
         !validationErrors.username &&
         !validationErrors.password
})

// Validation functions
function validateUsername() {
  validationErrors.username = ''

  if (!credentials.username) {
    validationErrors.username = 'Username is required'
    return false
  }

  if (credentials.username.length < 2) {
    validationErrors.username = 'Username must be at least 2 characters'
    return false
  }

  if (credentials.username.length > 50) {
    validationErrors.username = 'Username is too long'
    return false
  }

  const validPattern = /^[a-zA-Z0-9_\-.]+$/
  if (!validPattern.test(credentials.username)) {
    validationErrors.username = 'Username contains invalid characters'
    return false
  }

  return true
}

function validatePassword() {
  validationErrors.password = ''

  if (!credentials.password) {
    validationErrors.password = 'Password is required'
    return false
  }

  if (credentials.password.length > 128) {
    validationErrors.password = 'Password is too long'
    return false
  }

  return true
}

async function handleLogin() {
  const isUsernameValid = validateUsername()
  const isPasswordValid = validatePassword()

  if (!isUsernameValid || !isPasswordValid) {
    return
  }

  // ... API call logic
}
</script>

<template>
  <input
    v-model="credentials.username"
    :class="{ 'error': validationErrors.username }"
  />
  <div v-if="validationErrors.username">
    {{ validationErrors.username }}
  </div>

  <input
    v-model="credentials.password"
    :class="{ 'error': validationErrors.password }"
  />
  <div v-if="validationErrors.password">
    {{ validationErrors.password }}
  </div>

  <button :disabled="!isFormValid" @click="handleLogin">
    Sign In
  </button>
</template>
```

**Lines to Remove**: ~75 lines (validation functions, reactive objects, computed properties)

### ✅ AFTER

```vue
<script setup lang="ts">
import { useFormValidation } from '@/composables/useFormValidation'

const { fields, errors, isValid, validate, touch, reset } = useFormValidation({
  username: {
    value: '',
    rules: [
      { rule: 'required', message: 'Username is required' },
      { rule: 'minLength', value: 2, message: 'Username must be at least 2 characters' },
      { rule: 'maxLength', value: 50, message: 'Username is too long' },
      { rule: 'pattern', value: /^[a-zA-Z0-9_\-.]+$/, message: 'Username contains invalid characters' }
    ],
    validateOnBlur: true
  },
  password: {
    value: '',
    rules: [
      { rule: 'required', message: 'Password is required' },
      { rule: 'maxLength', value: 128, message: 'Password is too long' }
    ],
    validateOnBlur: true
  }
})

async function handleLogin() {
  const isFormValid = await validate()

  if (!isFormValid) {
    return
  }

  // ... API call logic using fields.username.value, fields.password.value

  // Clear form on success
  reset()
}
</script>

<template>
  <input
    v-model="fields.username.value"
    :class="{ 'error': errors.username.value }"
    @blur="touch('username')"
  />
  <div v-if="errors.username.value">
    {{ errors.username.value }}
  </div>

  <input
    v-model="fields.password.value"
    :class="{ 'error': errors.password.value }"
    @blur="touch('password')"
  />
  <div v-if="errors.password.value">
    {{ errors.password.value }}
  </div>

  <button :disabled="!isValid" @click="handleLogin">
    Sign In
  </button>
</template>
```

**Savings**: 75 lines → 35 lines = **40 lines saved (-53%)**

**Benefits**:
- Declarative validation rules
- Built-in validators (no manual if/else chains)
- Automatic error message management
- Touch state tracking
- One-line form reset

---

## BackendSettings.vue Migration

### ❌ BEFORE (Lines 804-912)

```vue
<script setup lang="ts">
const validationErrors = reactive({})
const validationSuccess = reactive({})

const handleChange = (key: string, value: any) => {
  delete validationErrors[key]

  const validation = validateSetting(key, value)

  if (!validation.valid) {
    validationErrors[key] = validation.error
  }
}

const validateSetting = (key: string, value: any) => {
  switch (key) {
    case 'api_endpoint':
    case 'ollama_endpoint':
    case 'lmstudio_endpoint':
      if (!value || !value.startsWith('http')) {
        return { valid: false, error: 'Must be a valid HTTP URL' }
      }
      break

    case 'server_host':
      if (!value || value.trim() === '') {
        return { valid: false, error: 'Server host cannot be empty' }
      }
      break

    case 'server_port':
      const port = Number(value)
      if (isNaN(port) || port < 1 || port > 65535) {
        return { valid: false, error: 'Must be a valid port (1-65535)' }
      }
      break

    case 'openai_api_key':
    case 'anthropic_api_key':
      if (value && value.length < 10) {
        return { valid: false, error: 'API key appears to be invalid' }
      }
      break
  }

  return { valid: true }
}

const validatePath = async (pathKey: string) => {
  // Complex async validation logic...
}
</script>

<template>
  <input
    v-model="settings.api_endpoint"
    :class="{ 'validation-error': validationErrors.api_endpoint }"
    @input="handleChange('api_endpoint', settings.api_endpoint)"
  />
  <div v-if="validationErrors.api_endpoint" class="validation-message error">
    {{ validationErrors.api_endpoint }}
  </div>

  <input
    v-model="settings.server_port"
    :class="{ 'validation-error': validationErrors.server_port }"
    @input="handleChange('server_port', settings.server_port)"
  />
  <div v-if="validationErrors.server_port" class="validation-message error">
    {{ validationErrors.server_port }}
  </div>
</template>
```

**Lines to Remove**: ~108 lines (validation logic, error handling, switch statements)

### ✅ AFTER

```vue
<script setup lang="ts">
import { useFormValidation } from '@/composables/useFormValidation'

const { fields, errors, isValid, validateField, touch } = useFormValidation({
  api_endpoint: {
    value: settings.api_endpoint || '',
    rules: [
      { rule: 'required', message: 'API endpoint is required' },
      { rule: 'url', message: 'Must be a valid HTTP URL' }
    ],
    validateOnChange: true,
    debounce: 500
  },
  server_host: {
    value: settings.server_host || '',
    rules: [
      { rule: 'required', message: 'Server host cannot be empty' }
    ]
  },
  server_port: {
    value: settings.server_port || 8001,
    rules: [
      { rule: 'required', message: 'Port is required' },
      { rule: 'number', message: 'Must be a valid number' },
      { rule: 'min', value: 1, message: 'Port must be at least 1' },
      { rule: 'max', value: 65535, message: 'Port cannot exceed 65535' }
    ]
  },
  openai_api_key: {
    value: settings.openai_api_key || '',
    rules: [
      { rule: 'minLength', value: 10, message: 'API key appears to be invalid' }
    ]
  },
  anthropic_api_key: {
    value: settings.anthropic_api_key || '',
    rules: [
      { rule: 'minLength', value: 10, message: 'API key appears to be invalid' }
    ]
  },
  chat_data_dir: {
    value: settings.chat_data_dir || '',
    rules: [
      {
        rule: 'custom',
        message: 'Invalid path',
        validator: async (path) => {
          // Async path validation
          const response = await ApiClient.post('/api/validate-path', { path })
          const result = await response.json()
          return result.valid || result.error
        }
      }
    ]
  }
})
</script>

<template>
  <input
    v-model="fields.api_endpoint.value"
    :class="{ 'validation-error': errors.api_endpoint.value }"
    @blur="touch('api_endpoint')"
  />
  <div v-if="errors.api_endpoint.value" class="validation-message error">
    {{ errors.api_endpoint.value }}
  </div>

  <input
    v-model="fields.server_port.value"
    :class="{ 'validation-error': errors.server_port.value }"
    @blur="touch('server_port')"
  />
  <div v-if="errors.server_port.value" class="validation-message error">
    {{ errors.server_port.value }}
  </div>
</template>
```

**Savings**: 108 lines → 50 lines = **58 lines saved (-54%)**

**Benefits**:
- No manual switch statements
- Declarative rule configuration
- Debounced validation built-in
- Async validators for path checking
- Automatic error clearing

---

## KnowledgeUpload.vue Migration

### ❌ BEFORE

```vue
<script setup lang="ts">
const textEntry = reactive({
  title: '',
  content: '',
  category: '',
  tagsInput: ''
})

const urlEntry = reactive({
  url: '',
  category: '',
  tagsInput: ''
})

function isValidUrl(url: string): boolean {
  try {
    new URL(url)
    return true
  } catch {
    return false
  }
}

async function addTextEntry() {
  if (!textEntry.content.trim()) {
    alert('Content is required')
    return
  }

  // ... API call
}

async function importFromUrl() {
  if (!isValidUrl(urlEntry.url)) {
    alert('Invalid URL')
    return
  }

  // ... API call
}
</script>

<template>
  <textarea
    v-model="textEntry.content"
    required
  ></textarea>
  <button
    :disabled="!textEntry.content.trim() || isSubmitting"
    @click="addTextEntry"
  >
    Add to Knowledge Base
  </button>

  <input
    v-model="urlEntry.url"
    type="url"
  />
  <button
    :disabled="!isValidUrl(urlEntry.url) || isSubmitting"
    @click="importFromUrl"
  >
    Import Content
  </button>
</template>
```

### ✅ AFTER

```vue
<script setup lang="ts">
import { useFormValidation } from '@/composables/useFormValidation'

const {
  fields: textFields,
  errors: textErrors,
  isValid: textValid,
  validate: validateText,
  reset: resetText
} = useFormValidation({
  title: {
    value: '',
    rules: [
      { rule: 'maxLength', value: 100, message: 'Title is too long' }
    ]
  },
  content: {
    value: '',
    rules: [
      { rule: 'required', message: 'Content is required' },
      { rule: 'minLength', value: 10, message: 'Content must be at least 10 characters' }
    ]
  },
  category: { value: '' },
  tags: { value: '' }
})

const {
  fields: urlFields,
  errors: urlErrors,
  isValid: urlValid,
  validate: validateUrl,
  reset: resetUrl
} = useFormValidation({
  url: {
    value: '',
    rules: [
      { rule: 'required', message: 'URL is required' },
      { rule: 'url', message: 'Invalid URL format' }
    ],
    validateOnChange: true,
    debounce: 300
  },
  category: { value: '' },
  tags: { value: '' }
})

async function addTextEntry() {
  const valid = await validateText()
  if (!valid) return

  // ... API call with textFields.content.value

  resetText()
}

async function importFromUrl() {
  const valid = await validateUrl()
  if (!valid) return

  // ... API call with urlFields.url.value

  resetUrl()
}
</script>

<template>
  <textarea
    v-model="textFields.content.value"
    :class="{ error: textErrors.content.value }"
  ></textarea>
  <div v-if="textErrors.content.value" class="error-message">
    {{ textErrors.content.value }}
  </div>
  <button
    :disabled="!textValid || isSubmitting"
    @click="addTextEntry"
  >
    Add to Knowledge Base
  </button>

  <input
    v-model="urlFields.url.value"
    :class="{ error: urlErrors.url.value }"
  />
  <div v-if="urlErrors.url.value" class="error-message">
    {{ urlErrors.url.value }}
  </div>
  <button
    :disabled="!urlValid || isSubmitting"
    @click="importFromUrl"
  >
    Import Content
  </button>
</template>
```

**Savings**: ~35 lines → ~50 lines = Net increase, but with much better validation
**Benefits**: Real-time URL validation, debounced input, proper error messages

---

## NPUWorkersSettings.vue Migration

### ❌ BEFORE (Lines 526-661)

```vue
<script setup lang="ts">
const validateIPAddress = (ip: string): boolean => {
  const ipPattern = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/
  return ipPattern.test(ip)
}

const validatePort = (port: number): boolean => {
  return port >= 1 && port <= 65535
}

const addWorker = async () => {
  if (!validateIPAddress(workerForm.value.ip_address)) {
    alert('Invalid IP address format')
    return
  }

  if (!validatePort(workerForm.value.port)) {
    alert('Port must be between 1 and 65535')
    return
  }

  if (!workerForm.value.name.trim()) {
    alert('Worker name is required')
    return
  }

  // ... API call
}
</script>
```

### ✅ AFTER

```vue
<script setup lang="ts">
import { useFormValidation } from '@/composables/useFormValidation'

const { fields, errors, isValid, validate, reset } = useFormValidation({
  name: {
    value: '',
    rules: [
      { rule: 'required', message: 'Worker name is required' },
      { rule: 'minLength', value: 2, message: 'Name must be at least 2 characters' },
      { rule: 'maxLength', value: 50, message: 'Name is too long' }
    ]
  },
  ip_address: {
    value: '',
    rules: [
      { rule: 'required', message: 'IP address is required' },
      {
        rule: 'pattern',
        value: /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/,
        message: 'Invalid IP address format'
      }
    ],
    validateOnBlur: true
  },
  port: {
    value: 8081,
    rules: [
      { rule: 'required', message: 'Port is required' },
      { rule: 'number', message: 'Must be a valid number' },
      { rule: 'min', value: 1, message: 'Port must be at least 1' },
      { rule: 'max', value: 65535, message: 'Port cannot exceed 65535' }
    ]
  },
  capabilities: {
    value: [],
    rules: [
      { rule: 'required', message: 'At least one capability is required' }
    ]
  }
})

const addWorker = async () => {
  const valid = await validate()
  if (!valid) return

  // ... API call using fields.name.value, fields.ip_address.value, etc.

  reset()
}
</script>

<template>
  <input
    v-model="fields.name.value"
    :class="{ error: errors.name.value }"
    @blur="touch('name')"
  />
  <div v-if="errors.name.value" class="error-message">
    {{ errors.name.value }}
  </div>

  <input
    v-model="fields.ip_address.value"
    :class="{ error: errors.ip_address.value }"
    @blur="touch('ip_address')"
  />
  <div v-if="errors.ip_address.value" class="error-message">
    {{ errors.ip_address.value }}
  </div>

  <input
    v-model="fields.port.value"
    type="number"
    :class="{ error: errors.port.value }"
    @blur="touch('port')"
  />
  <div v-if="errors.port.value" class="error-message">
    {{ errors.port.value }}
  </div>

  <button :disabled="!isValid" @click="addWorker">
    Add Worker
  </button>
</template>
```

**Savings**: ~135 lines → ~70 lines = **65 lines saved (-48%)**

---

## Quick Reference

### Common Validation Patterns

#### Pattern 1: Required Field

```vue
<!-- BEFORE -->
<script>
if (!username) {
  error = 'Username is required'
}
</script>

<!-- AFTER -->
<script>
const { fields, errors } = useFormValidation({
  username: {
    value: '',
    rules: [{ rule: 'required' }]
  }
})
</script>
```

#### Pattern 2: Length Validation

```vue
<!-- BEFORE -->
<script>
if (password.length < 8) {
  error = 'Password must be at least 8 characters'
}
if (password.length > 128) {
  error = 'Password is too long'
}
</script>

<!-- AFTER -->
<script>
const { fields, errors } = useFormValidation({
  password: {
    value: '',
    rules: [
      { rule: 'minLength', value: 8 },
      { rule: 'maxLength', value: 128 }
    ]
  }
})
</script>
```

#### Pattern 3: Pattern Validation (IP, Email, etc.)

```vue
<!-- BEFORE -->
<script>
const ipPattern = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/
if (!ipPattern.test(ip)) {
  error = 'Invalid IP address'
}
</script>

<!-- AFTER -->
<script>
const { fields, errors } = useFormValidation({
  ip: {
    value: '',
    rules: [
      { rule: 'pattern', value: /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/ }
    ]
  }
})
</script>
```

#### Pattern 4: Number Range

```vue
<!-- BEFORE -->
<script>
const port = Number(portInput)
if (isNaN(port) || port < 1 || port > 65535) {
  error = 'Invalid port number'
}
</script>

<!-- AFTER -->
<script>
const { fields, errors } = useFormValidation({
  port: {
    value: 8001,
    rules: [
      { rule: 'number' },
      { rule: 'min', value: 1 },
      { rule: 'max', value: 65535 }
    ]
  }
})
</script>
```

#### Pattern 5: Email Validation

```vue
<!-- BEFORE -->
<script>
const emailPattern = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
if (!emailPattern.test(email)) {
  error = 'Invalid email address'
}
</script>

<!-- AFTER -->
<script>
const { fields, errors } = useFormValidation({
  email: {
    value: '',
    rules: [{ rule: 'email' }]
  }
})
</script>
```

#### Pattern 6: URL Validation

```vue
<!-- BEFORE -->
<script>
function isValidUrl(url) {
  try {
    new URL(url)
    return true
  } catch {
    return false
  }
}

if (!isValidUrl(endpoint)) {
  error = 'Invalid URL'
}
</script>

<!-- AFTER -->
<script>
const { fields, errors } = useFormValidation({
  endpoint: {
    value: '',
    rules: [{ rule: 'url' }]
  }
})
</script>
```

#### Pattern 7: Custom Async Validation

```vue
<!-- BEFORE -->
<script>
async function validateUsername(username) {
  const response = await fetch(`/api/check-username?username=${username}`)
  const result = await response.json()
  if (!result.available) {
    error = 'Username is already taken'
    return false
  }
  return true
}
</script>

<!-- AFTER -->
<script>
const { fields, errors } = useFormValidation({
  username: {
    value: '',
    rules: [
      { rule: 'required' },
      {
        rule: 'custom',
        message: 'Username is already taken',
        validator: async (value) => {
          const response = await fetch(`/api/check-username?username=${value}`)
          const result = await response.json()
          return result.available || 'Username is already taken'
        }
      }
    ],
    debounce: 500 // Debounce API calls
  }
})
</script>
```

#### Pattern 8: Cross-Field Validation

```vue
<!-- AFTER -->
<script>
const { fields, errors } = useFormValidation({
  password: {
    value: '',
    rules: [
      { rule: 'required' },
      { rule: 'minLength', value: 8 }
    ]
  },
  confirmPassword: {
    value: '',
    rules: [
      { rule: 'required' },
      {
        rule: 'custom',
        message: 'Passwords do not match',
        validator: (value, allFields) => {
          return value === allFields.password || 'Passwords do not match'
        }
      }
    ]
  }
})
</script>
```

---

## Migration Checklist

For each form with validation:

- [ ] Import `useFormValidation` from `@/composables/useFormValidation`
- [ ] Replace reactive validation objects with `useFormValidation` config
- [ ] Map validation functions to declarative rules
- [ ] Update template to use `fields.fieldName.value` and `errors.fieldName.value`
- [ ] Add `@blur="touch('fieldName')"` for blur validation
- [ ] Replace manual `isFormValid` computed with `isValid` from composable
- [ ] Use `validate()` before form submission
- [ ] Use `reset()` after successful submission
- [ ] Test validation with edge cases
- [ ] Remove old validation code

---

## Statistics

**Estimated Savings Across All Forms:**

| Component | Lines Before | Lines After | Saved |
|-----------|--------------|-------------|-------|
| LoginForm.vue | 75 | 35 | 40 (-53%) |
| BackendSettings.vue | 108 | 50 | 58 (-54%) |
| NPUWorkersSettings.vue | 135 | 70 | 65 (-48%) |
| UserManagementSettings.vue | ~80 | 45 | 35 (-44%) |
| ChatSettings.vue | ~60 | 35 | 25 (-42%) |
| SecretsManager.vue | ~55 | 30 | 25 (-45%) |
| KnowledgeUpload.vue | ~35 | 40 | -5 (but better validation) |
| AddHostModal.vue | ~50 | 30 | 20 (-40%) |
| ... (5+ more forms) | ~180 | 100 | 80 (-44%) |
| **TOTAL** | **~778** | **~435** | **~343 (-44%)** |

**Total Estimated Savings: 343 lines of duplicate validation code eliminated**

---

## Advanced Features

### Debounced Validation

```typescript
const { fields, errors } = useFormValidation({
  search: {
    value: '',
    rules: [{ rule: 'minLength', value: 3 }],
    validateOnChange: true,
    debounce: 500 // Wait 500ms after typing stops
  }
})
```

### Touch State Tracking

```typescript
const { touched, touch, touchAll } = useFormValidation(config)

// Mark field as touched on blur
@blur="touch('username')"

// Mark all fields as touched on submit attempt
const handleSubmit = () => {
  touchAll()
  if (!isValid) return
  // ... submit
}
```

### Dirty State Tracking

```typescript
const { dirty, isDirty } = useFormValidation(config)

// Check if form has unsaved changes
if (isDirty.value) {
  confirm('You have unsaved changes. Are you sure you want to leave?')
}
```

### Manual Error Setting

```typescript
const { setFieldError, clearFieldError, clearErrors } = useFormValidation(config)

// Set server-side validation errors
try {
  await submitForm()
} catch (error) {
  if (error.field) {
    setFieldError(error.field, error.message)
  }
}

// Clear errors programmatically
clearFieldError('username')
clearErrors()
```

---

## TypeScript Support

Full TypeScript support with type-safe field access:

```typescript
import type { UseFormValidationReturn, FieldConfig } from '@/composables/useFormValidation'

const config: Record<string, FieldConfig> = {
  username: {
    value: '',
    rules: [
      { rule: 'required' },
      { rule: 'minLength', value: 3 }
    ]
  }
}

const validation: UseFormValidationReturn = useFormValidation(config)
```

---

## Next Steps

1. ✅ **Created**: `useFormValidation.ts` composable
2. ✅ **Created**: Migration examples document
3. 📋 **Next**: Create comprehensive unit tests
4. 📋 **Then**: Migrate 2-3 forms as proof-of-concept
5. 📋 **Finally**: Migrate remaining forms systematically

---

**Created**: 2025-10-27
**Author**: AutoBot Frontend Refactoring Initiative
**Part of**: Priority 2 - Medium Impact Composables/Utilities
