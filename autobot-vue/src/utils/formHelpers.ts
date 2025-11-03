/**
 * Form Helpers
 *
 * Utility functions for form state management and operations.
 * Provides reusable form reset, validation, and state manipulation.
 */

/**
 * Reset all fields in a reactive form object to default values
 *
 * @param form - Reactive form object (reactive or ref)
 * @param defaults - Optional default values to set (empty string if not provided)
 *
 * @example
 * const formData = reactive({ name: 'John', email: 'john@example.com', age: 25 })
 * resetFormFields(formData)
 * // Result: { name: '', email: '', age: '' }
 *
 * @example
 * const formData = reactive({ name: 'John', category: 'Tech', tags: 'vue,ts' })
 * resetFormFields(formData, { category: 'General' })
 * // Result: { name: '', category: 'General', tags: '' }
 */
export function resetFormFields<T extends Record<string, any>>(
  form: T,
  defaults: Partial<T> = {}
): void {
  ;(Object.keys(form) as Array<keyof T>).forEach((key) => {
    const defaultValue = defaults[key]

    if (defaultValue !== undefined) {
      form[key] = defaultValue as T[keyof T]
    } else {
      // Auto-detect default based on current type
      const currentValue = form[key]

      if (typeof currentValue === 'string') {
        form[key] = '' as T[keyof T]
      } else if (typeof currentValue === 'number') {
        form[key] = 0 as T[keyof T]
      } else if (typeof currentValue === 'boolean') {
        form[key] = false as T[keyof T]
      } else if (Array.isArray(currentValue)) {
        form[key] = [] as T[keyof T]
      } else if (currentValue === null || currentValue === undefined) {
        form[key] = '' as T[keyof T]
      } else {
        form[key] = '' as T[keyof T]
      }
    }
  })
}

/**
 * Check if all required fields in a form are filled
 *
 * @param form - Form object to validate
 * @param requiredFields - Array of field names that are required
 * @returns True if all required fields have values
 *
 * @example
 * const formData = { name: 'John', email: '', age: 25 }
 * hasRequiredFields(formData, ['name', 'email'])
 * // Returns: false (email is empty)
 */
export function hasRequiredFields<T extends Record<string, any>>(
  form: T,
  requiredFields: (keyof T)[]
): boolean {
  return requiredFields.every((field) => {
    const value = form[field]

    if (value === null || value === undefined) {
      return false
    }

    if (typeof value === 'string') {
      return value.trim().length > 0
    }

    if (Array.isArray(value)) {
      return value.length > 0
    }

    return true
  })
}

/**
 * Get list of empty required fields
 *
 * @param form - Form object to check
 * @param requiredFields - Array of field names that are required
 * @returns Array of empty field names
 *
 * @example
 * const formData = { name: 'John', email: '', age: 0 }
 * getEmptyFields(formData, ['name', 'email', 'age'])
 * // Returns: ['email', 'age']
 */
export function getEmptyFields<T extends Record<string, any>>(
  form: T,
  requiredFields: (keyof T)[]
): (keyof T)[] {
  return requiredFields.filter((field) => {
    const value = form[field]

    if (value === null || value === undefined) {
      return true
    }

    if (typeof value === 'string') {
      return value.trim().length === 0
    }

    if (typeof value === 'number') {
      return value === 0
    }

    if (Array.isArray(value)) {
      return value.length === 0
    }

    return false
  })
}

/**
 * Clone form data (deep copy)
 *
 * @param form - Form object to clone
 * @returns Deep copy of form data
 *
 * @example
 * const original = { name: 'John', tags: ['vue', 'ts'] }
 * const copy = cloneFormData(original)
 * copy.tags.push('js')
 * // original.tags remains ['vue', 'ts']
 */
export function cloneFormData<T extends Record<string, any>>(form: T): T {
  return JSON.parse(JSON.stringify(form))
}

/**
 * Check if form has been modified from initial state
 *
 * @param currentForm - Current form state
 * @param initialForm - Initial form state to compare against
 * @returns True if form has been modified
 *
 * @example
 * const initial = { name: 'John', email: 'john@example.com' }
 * const current = { name: 'John Doe', email: 'john@example.com' }
 * isFormModified(current, initial)
 * // Returns: true
 */
export function isFormModified<T extends Record<string, any>>(
  currentForm: T,
  initialForm: T
): boolean {
  return JSON.stringify(currentForm) !== JSON.stringify(initialForm)
}

/**
 * Trim all string fields in a form
 *
 * @param form - Form object with string fields
 *
 * @example
 * const formData = { name: '  John  ', email: ' john@example.com ' }
 * trimFormFields(formData)
 * // Result: { name: 'John', email: 'john@example.com' }
 */
export function trimFormFields<T extends Record<string, any>>(form: T): void {
  ;(Object.keys(form) as Array<keyof T>).forEach((key) => {
    if (typeof form[key] === 'string') {
      form[key] = (form[key] as string).trim() as T[keyof T]
    }
  })
}
