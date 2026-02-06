/**
 * Unit Tests for useFormValidation.ts
 *
 * Test coverage for centralized form validation composable.
 * Target: 100% code coverage
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { useFormValidation, quickValidate, validators } from '../useFormValidation'

describe('useFormValidation composable', () => {
  // ========================================
  // Basic Functionality Tests
  // ========================================

  describe('basic functionality', () => {
    it('should initialize with field values', () => {
      const { fields } = useFormValidation({
        username: { value: 'test' },
        email: { value: 'test@example.com' }
      })

      expect(fields.username.value).toBe('test')
      expect(fields.email.value).toBe('test@example.com')
    })

    it('should initialize with empty errors', () => {
      const { errors } = useFormValidation({
        username: { value: '' }
      })

      expect(errors.username.value).toBe('')
    })

    it('should initialize with untouched state', () => {
      const { touched } = useFormValidation({
        username: { value: '' }
      })

      expect(touched.username.value).toBe(false)
    })

    it('should initialize with not dirty state', () => {
      const { dirty } = useFormValidation({
        username: { value: 'test' }
      })

      expect(dirty.username.value).toBe(false)
    })

    it('should mark field as dirty when value changes', async () => {
      const { fields, dirty } = useFormValidation({
        username: { value: 'test' }
      })

      fields.username.value = 'newvalue'
      await new Promise(resolve => setTimeout(resolve, 0))

      expect(dirty.username.value).toBe(true)
    })
  })

  // ========================================
  // Built-in Validators Tests
  // ========================================

  describe('required validator', () => {
    it('should fail for empty string', async () => {
      const { fields, errors, validateField } = useFormValidation({
        username: {
          value: '',
          rules: [{ rule: 'required' }]
        }
      })

      await validateField('username')
      expect(errors.username.value).toBeTruthy()
    })

    it('should fail for null', async () => {
      const { fields, errors, validateField } = useFormValidation({
        username: {
          value: null,
          rules: [{ rule: 'required' }]
        }
      })

      await validateField('username')
      expect(errors.username.value).toBeTruthy()
    })

    it('should fail for empty array', async () => {
      const { fields, errors, validateField } = useFormValidation({
        items: {
          value: [],
          rules: [{ rule: 'required' }]
        }
      })

      await validateField('items')
      expect(errors.items.value).toBeTruthy()
    })

    it('should pass for non-empty value', async () => {
      const { fields, errors, validateField } = useFormValidation({
        username: {
          value: 'test',
          rules: [{ rule: 'required' }]
        }
      })

      await validateField('username')
      expect(errors.username.value).toBe('')
    })

    it('should use custom message', async () => {
      const { errors, validateField } = useFormValidation({
        username: {
          value: '',
          rules: [{ rule: 'required', message: 'Username is mandatory' }]
        }
      })

      await validateField('username')
      expect(errors.username.value).toBe('Username is mandatory')
    })
  })

  describe('minLength validator', () => {
    it('should fail for string shorter than minimum', async () => {
      const { errors, validateField } = useFormValidation({
        password: {
          value: 'ab',
          rules: [{ rule: 'minLength', value: 8 }]
        }
      })

      await validateField('password')
      expect(errors.password.value).toContain('at least 8')
    })

    it('should pass for string equal to minimum', async () => {
      const { errors, validateField } = useFormValidation({
        password: {
          value: '12345678',
          rules: [{ rule: 'minLength', value: 8 }]
        }
      })

      await validateField('password')
      expect(errors.password.value).toBe('')
    })

    it('should pass for empty value (use required for that)', async () => {
      const { errors, validateField } = useFormValidation({
        password: {
          value: '',
          rules: [{ rule: 'minLength', value: 8 }]
        }
      })

      await validateField('password')
      expect(errors.password.value).toBe('')
    })
  })

  describe('maxLength validator', () => {
    it('should fail for string longer than maximum', async () => {
      const { errors, validateField } = useFormValidation({
        username: {
          value: 'a'.repeat(51),
          rules: [{ rule: 'maxLength', value: 50 }]
        }
      })

      await validateField('username')
      expect(errors.username.value).toContain('at most 50')
    })

    it('should pass for string equal to maximum', async () => {
      const { errors, validateField } = useFormValidation({
        username: {
          value: 'a'.repeat(50),
          rules: [{ rule: 'maxLength', value: 50 }]
        }
      })

      await validateField('username')
      expect(errors.username.value).toBe('')
    })
  })

  describe('min validator', () => {
    it('should fail for number below minimum', async () => {
      const { errors, validateField } = useFormValidation({
        age: {
          value: 17,
          rules: [{ rule: 'min', value: 18 }]
        }
      })

      await validateField('age')
      expect(errors.age.value).toContain('at least 18')
    })

    it('should pass for number equal to minimum', async () => {
      const { errors, validateField } = useFormValidation({
        age: {
          value: 18,
          rules: [{ rule: 'min', value: 18 }]
        }
      })

      await validateField('age')
      expect(errors.age.value).toBe('')
    })

    it('should handle zero correctly', async () => {
      const { errors, validateField } = useFormValidation({
        count: {
          value: 0,
          rules: [{ rule: 'min', value: 0 }]
        }
      })

      await validateField('count')
      expect(errors.count.value).toBe('')
    })
  })

  describe('max validator', () => {
    it('should fail for number above maximum', async () => {
      const { errors, validateField } = useFormValidation({
        port: {
          value: 70000,
          rules: [{ rule: 'max', value: 65535 }]
        }
      })

      await validateField('port')
      expect(errors.port.value).toContain('at most 65535')
    })

    it('should pass for number equal to maximum', async () => {
      const { errors, validateField } = useFormValidation({
        port: {
          value: 65535,
          rules: [{ rule: 'max', value: 65535 }]
        }
      })

      await validateField('port')
      expect(errors.port.value).toBe('')
    })
  })

  describe('pattern validator', () => {
    it('should fail for non-matching pattern', async () => {
      const { errors, validateField } = useFormValidation({
        username: {
          value: 'test@user',
          rules: [{ rule: 'pattern', value: /^[a-zA-Z0-9_-]+$/ }]
        }
      })

      await validateField('username')
      expect(errors.username.value).toBeTruthy()
    })

    it('should pass for matching pattern', async () => {
      const { errors, validateField } = useFormValidation({
        username: {
          value: 'test_user-123',
          rules: [{ rule: 'pattern', value: /^[a-zA-Z0-9_-]+$/ }]
        }
      })

      await validateField('username')
      expect(errors.username.value).toBe('')
    })
  })

  describe('email validator', () => {
    it('should pass for valid email', async () => {
      const { errors, validateField } = useFormValidation({
        email: {
          value: 'test@example.com',
          rules: [{ rule: 'email' }]
        }
      })

      await validateField('email')
      expect(errors.email.value).toBe('')
    })

    it('should fail for invalid email', async () => {
      const { errors, validateField } = useFormValidation({
        email: {
          value: 'notanemail',
          rules: [{ rule: 'email' }]
        }
      })

      await validateField('email')
      expect(errors.email.value).toContain('email')
    })

    it('should pass for empty value', async () => {
      const { errors, validateField } = useFormValidation({
        email: {
          value: '',
          rules: [{ rule: 'email' }]
        }
      })

      await validateField('email')
      expect(errors.email.value).toBe('')
    })
  })

  describe('url validator', () => {
    it('should pass for valid HTTP URL', async () => {
      const { errors, validateField } = useFormValidation({
        website: {
          value: 'http://example.com',
          rules: [{ rule: 'url' }]
        }
      })

      await validateField('website')
      expect(errors.website.value).toBe('')
    })

    it('should pass for valid HTTPS URL', async () => {
      const { errors, validateField } = useFormValidation({
        website: {
          value: 'https://example.com',
          rules: [{ rule: 'url' }]
        }
      })

      await validateField('website')
      expect(errors.website.value).toBe('')
    })

    it('should fail for invalid URL', async () => {
      const { errors, validateField } = useFormValidation({
        website: {
          value: 'not-a-url',
          rules: [{ rule: 'url' }]
        }
      })

      await validateField('website')
      expect(errors.website.value).toContain('URL')
    })
  })

  describe('number validator', () => {
    it('should pass for valid number', async () => {
      const { errors, validateField } = useFormValidation({
        amount: {
          value: '123.45',
          rules: [{ rule: 'number' }]
        }
      })

      await validateField('amount')
      expect(errors.amount.value).toBe('')
    })

    it('should fail for non-number', async () => {
      const { errors, validateField } = useFormValidation({
        amount: {
          value: 'abc',
          rules: [{ rule: 'number' }]
        }
      })

      await validateField('amount')
      expect(errors.amount.value).toContain('number')
    })
  })

  describe('integer validator', () => {
    it('should pass for integer', async () => {
      const { errors, validateField } = useFormValidation({
        count: {
          value: '42',
          rules: [{ rule: 'integer' }]
        }
      })

      await validateField('count')
      expect(errors.count.value).toBe('')
    })

    it('should fail for decimal', async () => {
      const { errors, validateField } = useFormValidation({
        count: {
          value: '42.5',
          rules: [{ rule: 'integer' }]
        }
      })

      await validateField('count')
      expect(errors.count.value).toContain('whole number')
    })
  })

  describe('alpha validator', () => {
    it('should pass for letters only', async () => {
      const { errors, validateField } = useFormValidation({
        name: {
          value: 'JohnDoe',
          rules: [{ rule: 'alpha' }]
        }
      })

      await validateField('name')
      expect(errors.name.value).toBe('')
    })

    it('should fail for alphanumeric', async () => {
      const { errors, validateField } = useFormValidation({
        name: {
          value: 'John123',
          rules: [{ rule: 'alpha' }]
        }
      })

      await validateField('name')
      expect(errors.name.value).toContain('letters')
    })
  })

  describe('alphanumeric validator', () => {
    it('should pass for letters and numbers', async () => {
      const { errors, validateField } = useFormValidation({
        code: {
          value: 'ABC123',
          rules: [{ rule: 'alphanumeric' }]
        }
      })

      await validateField('code')
      expect(errors.code.value).toBe('')
    })

    it('should fail for special characters', async () => {
      const { errors, validateField } = useFormValidation({
        code: {
          value: 'ABC-123',
          rules: [{ rule: 'alphanumeric' }]
        }
      })

      await validateField('code')
      expect(errors.code.value).toContain('letters and numbers')
    })
  })

  // ========================================
  // Custom Validator Tests
  // ========================================

  describe('custom validator', () => {
    it('should call custom validator', async () => {
      const customValidator = vi.fn(() => true)

      const { validateField } = useFormValidation({
        field: {
          value: 'test',
          rules: [{
            rule: 'custom',
            validator: customValidator
          }]
        }
      })

      await validateField('field')
      expect(customValidator).toHaveBeenCalledWith('test', { field: 'test' })
    })

    it('should pass when custom validator returns true', async () => {
      const { errors, validateField } = useFormValidation({
        field: {
          value: 'test',
          rules: [{
            rule: 'custom',
            validator: () => true
          }]
        }
      })

      await validateField('field')
      expect(errors.field.value).toBe('')
    })

    it('should fail when custom validator returns false', async () => {
      const { errors, validateField } = useFormValidation({
        field: {
          value: 'test',
          rules: [{
            rule: 'custom',
            message: 'Custom validation failed',
            validator: () => false
          }]
        }
      })

      await validateField('field')
      expect(errors.field.value).toBe('Custom validation failed')
    })

    it('should use error message from custom validator', async () => {
      const { errors, validateField } = useFormValidation({
        field: {
          value: 'test',
          rules: [{
            rule: 'custom',
            validator: () => 'This is wrong'
          }]
        }
      })

      await validateField('field')
      expect(errors.field.value).toBe('This is wrong')
    })

    it('should support async custom validator', async () => {
      const { errors, validateField } = useFormValidation({
        username: {
          value: 'taken',
          rules: [{
            rule: 'custom',
            validator: async (value) => {
              await new Promise(resolve => setTimeout(resolve, 10))
              return value !== 'taken' || 'Username is taken'
            }
          }]
        }
      })

      await validateField('username')
      expect(errors.username.value).toBe('Username is taken')
    })
  })

  // ========================================
  // Cross-Field Validation Tests
  // ========================================

  describe('cross-field validation', () => {
    it('should pass all field values to custom validator', async () => {
      const customValidator = vi.fn(() => true)

      const { validateField } = useFormValidation({
        password: { value: 'pass123' },
        confirmPassword: {
          value: 'pass123',
          rules: [{
            rule: 'custom',
            validator: customValidator
          }]
        }
      })

      await validateField('confirmPassword')
      expect(customValidator).toHaveBeenCalledWith('pass123', {
        password: 'pass123',
        confirmPassword: 'pass123'
      })
    })

    it('should validate password confirmation', async () => {
      const { errors, validateField } = useFormValidation({
        password: { value: 'pass123' },
        confirmPassword: {
          value: 'different',
          rules: [{
            rule: 'custom',
            message: 'Passwords do not match',
            validator: (value, allFields) => value === allFields.password
          }]
        }
      })

      await validateField('confirmPassword')
      expect(errors.confirmPassword.value).toBe('Passwords do not match')
    })
  })

  // ========================================
  // Form-Level Validation Tests
  // ========================================

  describe('form-level validation', () => {
    it('should validate all fields', async () => {
      const { fields, validate } = useFormValidation({
        username: {
          value: '',
          rules: [{ rule: 'required' }]
        },
        email: {
          value: 'invalid',
          rules: [{ rule: 'email' }]
        }
      })

      const isValid = await validate()
      expect(isValid).toBe(false)
    })

    it('should return true when all fields valid', async () => {
      const { validate } = useFormValidation({
        username: {
          value: 'test',
          rules: [{ rule: 'required' }]
        },
        email: {
          value: 'test@example.com',
          rules: [{ rule: 'email' }]
        }
      })

      const isValid = await validate()
      expect(isValid).toBe(true)
    })

    it('should update isValid computed property', async () => {
      const { isValid, validate } = useFormValidation({
        username: {
          value: '',
          rules: [{ rule: 'required' }]
        }
      })

      expect(isValid.value).toBe(true) // Initially no errors

      await validate()
      expect(isValid.value).toBe(false) // After validation, error present
    })
  })

  // ========================================
  // Touch State Tests
  // ========================================

  describe('touch state', () => {
    it('should mark field as touched', () => {
      const { touched, touch } = useFormValidation({
        username: { value: '' }
      })

      expect(touched.username.value).toBe(false)

      touch('username')
      expect(touched.username.value).toBe(true)
    })

    it('should mark all fields as touched', () => {
      const { touched, touchAll } = useFormValidation({
        username: { value: '' },
        email: { value: '' }
      })

      touchAll()
      expect(touched.username.value).toBe(true)
      expect(touched.email.value).toBe(true)
    })

    it('should update isTouched computed', () => {
      const { isTouched, touch } = useFormValidation({
        username: { value: '' }
      })

      expect(isTouched.value).toBe(false)

      touch('username')
      expect(isTouched.value).toBe(true)
    })

    it('should validate on touch if validateOnBlur is true', async () => {
      const { errors, touch } = useFormValidation({
        username: {
          value: '',
          rules: [{ rule: 'required' }],
          validateOnBlur: true
        }
      })

      touch('username')
      await new Promise(resolve => setTimeout(resolve, 0))

      expect(errors.username.value).toBeTruthy()
    })

    it('should not validate on touch if validateOnBlur is false', async () => {
      const { errors, touch } = useFormValidation({
        username: {
          value: '',
          rules: [{ rule: 'required' }],
          validateOnBlur: false
        }
      })

      touch('username')
      await new Promise(resolve => setTimeout(resolve, 0))

      expect(errors.username.value).toBe('')
    })
  })

  // ========================================
  // Dirty State Tests
  // ========================================

  describe('dirty state', () => {
    it('should mark field as dirty when value changes', async () => {
      const { fields, dirty } = useFormValidation({
        username: { value: 'initial' }
      })

      fields.username.value = 'changed'
      await new Promise(resolve => setTimeout(resolve, 0))

      expect(dirty.username.value).toBe(true)
    })

    it('should not mark field as dirty if value unchanged', async () => {
      const { fields, dirty } = useFormValidation({
        username: { value: 'test' }
      })

      fields.username.value = 'test'
      await new Promise(resolve => setTimeout(resolve, 0))

      expect(dirty.username.value).toBe(false)
    })

    it('should update isDirty computed', async () => {
      const { fields, isDirty } = useFormValidation({
        username: { value: 'test' }
      })

      expect(isDirty.value).toBe(false)

      fields.username.value = 'changed'
      await new Promise(resolve => setTimeout(resolve, 0))

      expect(isDirty.value).toBe(true)
    })
  })

  // ========================================
  // Reset Functionality Tests
  // ========================================

  describe('reset functionality', () => {
    it('should reset single field to initial value', () => {
      const { fields, resetField } = useFormValidation({
        username: { value: 'initial' }
      })

      fields.username.value = 'changed'
      resetField('username')

      expect(fields.username.value).toBe('initial')
    })

    it('should reset all fields', () => {
      const { fields, reset } = useFormValidation({
        username: { value: 'user' },
        email: { value: 'email@test.com' }
      })

      fields.username.value = 'changed'
      fields.email.value = 'new@test.com'

      reset()

      expect(fields.username.value).toBe('user')
      expect(fields.email.value).toBe('email@test.com')
    })

    it('should clear errors on reset', () => {
      const { errors, setFieldError, resetField } = useFormValidation({
        username: { value: '' }
      })

      setFieldError('username', 'Error')
      expect(errors.username.value).toBe('Error')

      resetField('username')
      expect(errors.username.value).toBe('')
    })

    it('should reset touched state', () => {
      const { touched, touch, resetField } = useFormValidation({
        username: { value: '' }
      })

      touch('username')
      expect(touched.username.value).toBe(true)

      resetField('username')
      expect(touched.username.value).toBe(false)
    })

    it('should reset dirty state', async () => {
      const { fields, dirty, resetField } = useFormValidation({
        username: { value: 'test' }
      })

      fields.username.value = 'changed'
      await new Promise(resolve => setTimeout(resolve, 0))
      expect(dirty.username.value).toBe(true)

      resetField('username')
      expect(dirty.username.value).toBe(false)
    })
  })

  // ========================================
  // Programmatic Control Tests
  // ========================================

  describe('programmatic control', () => {
    it('should set field value programmatically', () => {
      const { fields, setFieldValue } = useFormValidation({
        username: { value: '' }
      })

      setFieldValue('username', 'newvalue')
      expect(fields.username.value).toBe('newvalue')
    })

    it('should set field error programmatically', () => {
      const { errors, setFieldError } = useFormValidation({
        username: { value: '' }
      })

      setFieldError('username', 'Custom error')
      expect(errors.username.value).toBe('Custom error')
    })

    it('should clear field error', () => {
      const { errors, setFieldError, clearFieldError } = useFormValidation({
        username: { value: '' }
      })

      setFieldError('username', 'Error')
      clearFieldError('username')

      expect(errors.username.value).toBe('')
    })

    it('should clear all errors', () => {
      const { errors, setFieldError, clearErrors } = useFormValidation({
        username: { value: '' },
        email: { value: '' }
      })

      setFieldError('username', 'Error 1')
      setFieldError('email', 'Error 2')

      clearErrors()

      expect(errors.username.value).toBe('')
      expect(errors.email.value).toBe('')
    })
  })

  // ========================================
  // Quick Validate Helper Tests
  // ========================================

  describe('quickValidate helper', () => {
    it('should return empty string for valid value', async () => {
      const error = await quickValidate('test@example.com', [
        { rule: 'required' },
        { rule: 'email' }
      ])

      expect(error).toBe('')
    })

    it('should return error message for invalid value', async () => {
      const error = await quickValidate('', [
        { rule: 'required', message: 'Required' }
      ])

      expect(error).toBe('Required')
    })

    it('should support custom validators', async () => {
      const error = await quickValidate('test', [
        {
          rule: 'custom',
          message: 'Must be admin',
          validator: (value) => value === 'admin'
        }
      ])

      expect(error).toBe('Must be admin')
    })
  })

  // ========================================
  // Edge Case Tests
  // ========================================

  describe('edge cases', () => {
    it('should handle field without rules', async () => {
      const { validateField } = useFormValidation({
        username: { value: 'test' }
      })

      const isValid = await validateField('username')
      expect(isValid).toBe(true)
    })

    it('should handle empty rules array', async () => {
      const { validateField } = useFormValidation({
        username: { value: 'test', rules: [] }
      })

      const isValid = await validateField('username')
      expect(isValid).toBe(true)
    })

    it('should handle unknown rule gracefully', async () => {
      const consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

      const { validateField } = useFormValidation({
        username: {
          value: 'test',
          rules: [{ rule: 'unknown' as any }]
        }
      })

      await validateField('username')
      expect(consoleWarnSpy).toHaveBeenCalled()

      consoleWarnSpy.mockRestore()
    })

    it('should validate fields in parallel', async () => {
      const { validate } = useFormValidation({
        field1: {
          value: '',
          rules: [{ rule: 'required' }]
        },
        field2: {
          value: '',
          rules: [{ rule: 'required' }]
        }
      })

      const startTime = Date.now()
      await validate()
      const duration = Date.now() - startTime

      // Should complete quickly (parallel execution)
      expect(duration).toBeLessThan(50)
    })

    it('should stop validation on first error for field', async () => {
      const secondValidator = vi.fn(() => false)

      const { validateField } = useFormValidation({
        username: {
          value: '',
          rules: [
            { rule: 'required' },
            { rule: 'custom', validator: secondValidator }
          ]
        }
      })

      await validateField('username')

      // Second validator should not be called because first failed
      expect(secondValidator).not.toHaveBeenCalled()
    })

    it('should handle multiple validation rules in sequence', async () => {
      const { errors, validateField } = useFormValidation({
        password: {
          value: 'ab',
          rules: [
            { rule: 'required' },
            { rule: 'minLength', value: 8, message: 'Too short' },
            { rule: 'pattern', value: /[A-Z]/, message: 'Needs uppercase' }
          ]
        }
      })

      await validateField('password')

      // Should fail on first failing rule (minLength)
      expect(errors.password.value).toBe('Too short')
    })
  })
})
