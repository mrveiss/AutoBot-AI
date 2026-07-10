// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * SchemaForm component tests
 * Issue #11522 - schema-driven config form
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, fireEvent, screen } from '@testing-library/vue'
import { createI18n } from 'vue-i18n'
import SchemaForm from '../SchemaForm.vue'

// ---- minimal i18n ----
const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    en: {
      components: {
        schemaForm: {
          requiredMark: 'required',
          selectPlaceholder: 'Select an option',
          removeTag: 'Remove tag',
          addTagPlaceholder: 'Press Enter to add',
          rawJsonFallback: 'Schema contains nested objects. Edit as raw JSON:',
          rawJsonLabel: 'Plugin configuration (JSON)',
          invalidJson: 'Invalid JSON — please fix before saving.',
        },
      },
    },
  },
})

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({
    warn: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    debug: vi.fn(),
  }),
}))

function mountSchemaForm(schema: object, modelValue: Record<string, unknown> = {}) {
  const modelRef = { value: modelValue }
  const result = render(SchemaForm, {
    props: {
      schema,
      modelValue,
    },
    global: {
      plugins: [i18n],
    },
  })
  return result
}

// ============================================================
describe('SchemaForm', () => {
  // ----------------------------------------------------------
  describe('string field', () => {
    it('renders a text input for type=string', () => {
      const { getByRole } = mountSchemaForm({
        type: 'object',
        properties: {
          host: { type: 'string', title: 'Host', description: 'Server host' },
        },
      })
      const input = getByRole('textbox', { name: /host/i })
      expect(input).toBeTruthy()
    })

    it('shows default value in text input', () => {
      const { getByRole } = mountSchemaForm(
        {
          type: 'object',
          properties: {
            name: { type: 'string', default: 'AutoBot', title: 'Name' },
          },
        },
        {},
      )
      const input = getByRole('textbox') as HTMLInputElement
      expect(input.value).toBe('AutoBot')
    })

    it('emits update:modelValue on text input change', async () => {
      const handlers: Array<Record<string, unknown>> = []
      const { getByRole, emitted } = render(SchemaForm, {
        props: {
          schema: {
            type: 'object',
            properties: { host: { type: 'string', title: 'Host' } },
          },
          modelValue: {},
        },
        global: { plugins: [i18n] },
      })
      const input = getByRole('textbox')
      await fireEvent.input(input, { target: { value: 'localhost' } })
      const emits = emitted()['update:modelValue'] as Array<[Record<string, unknown>]>
      expect(emits).toBeTruthy()
      expect(emits[emits.length - 1][0]).toEqual({ host: 'localhost' })
    })
  })

  // ----------------------------------------------------------
  describe('number / integer field', () => {
    it('renders a number input for type=number', () => {
      const { container } = mountSchemaForm({
        type: 'object',
        properties: {
          port: { type: 'number', title: 'Port' },
        },
      })
      const input = container.querySelector('input[type="number"]')
      expect(input).toBeTruthy()
    })

    it('renders a number input for type=integer', () => {
      const { container } = mountSchemaForm({
        type: 'object',
        properties: {
          count: { type: 'integer', title: 'Count' },
        },
      })
      const input = container.querySelector('input[type="number"]')
      expect(input).toBeTruthy()
    })

    it('emits numeric value on change', async () => {
      const { container, emitted } = render(SchemaForm, {
        props: {
          schema: { type: 'object', properties: { port: { type: 'integer', title: 'Port' } } },
          modelValue: {},
        },
        global: { plugins: [i18n] },
      })
      const input = container.querySelector('input[type="number"]') as HTMLInputElement
      await fireEvent.input(input, { target: { value: '8080' } })
      const emits = emitted()['update:modelValue'] as Array<[Record<string, unknown>]>
      expect(emits[emits.length - 1][0]).toEqual({ port: 8080 })
    })
  })

  // ----------------------------------------------------------
  describe('boolean field', () => {
    it('renders a checkbox for type=boolean', () => {
      const { container } = mountSchemaForm({
        type: 'object',
        properties: {
          enabled: { type: 'boolean', title: 'Enabled' },
        },
      })
      const checkbox = container.querySelector('input[type="checkbox"]')
      expect(checkbox).toBeTruthy()
    })

    it('reflects default=true in checkbox', () => {
      const { container } = mountSchemaForm({
        type: 'object',
        properties: {
          enabled: { type: 'boolean', default: true, title: 'Enabled' },
        },
      })
      const checkbox = container.querySelector('input[type="checkbox"]') as HTMLInputElement
      expect(checkbox.checked).toBe(true)
    })

    it('emits boolean value on toggle', async () => {
      const { container, emitted } = render(SchemaForm, {
        props: {
          schema: { type: 'object', properties: { enabled: { type: 'boolean', title: 'Enabled' } } },
          modelValue: { enabled: false },
        },
        global: { plugins: [i18n] },
      })
      const checkbox = container.querySelector('input[type="checkbox"]') as HTMLInputElement
      await fireEvent.change(checkbox, { target: { checked: true } })
      const emits = emitted()['update:modelValue'] as Array<[Record<string, unknown>]>
      expect(emits[emits.length - 1][0]).toEqual({ enabled: true })
    })
  })

  // ----------------------------------------------------------
  describe('enum / select field', () => {
    it('renders a select for enum', () => {
      const { container } = mountSchemaForm({
        type: 'object',
        properties: {
          mode: { enum: ['fast', 'slow'], title: 'Mode' },
        },
      })
      const select = container.querySelector('select')
      expect(select).toBeTruthy()
    })

    it('shows each enum value as an option', () => {
      const { container } = mountSchemaForm({
        type: 'object',
        properties: {
          mode: { enum: ['fast', 'slow', 'medium'], title: 'Mode' },
        },
      })
      const options = container.querySelectorAll('option')
      const values = Array.from(options).map((o) => o.value)
      expect(values).toContain('fast')
      expect(values).toContain('slow')
      expect(values).toContain('medium')
    })

    it('emits selected value on change', async () => {
      const { container, emitted } = render(SchemaForm, {
        props: {
          schema: { type: 'object', properties: { mode: { enum: ['fast', 'slow'], title: 'Mode' } } },
          modelValue: {},
        },
        global: { plugins: [i18n] },
      })
      const select = container.querySelector('select') as HTMLSelectElement
      await fireEvent.change(select, { target: { value: 'slow' } })
      const emits = emitted()['update:modelValue'] as Array<[Record<string, unknown>]>
      expect(emits[emits.length - 1][0]).toEqual({ mode: 'slow' })
    })
  })

  // ----------------------------------------------------------
  describe('enum typed values (B-1)', () => {
    it('emits the original numeric enum member, not its string form', async () => {
      const { container, emitted } = mountSchemaForm(
        {
          type: 'object',
          properties: { level: { type: 'integer', title: 'Level', enum: [1, 2, 3] } },
        },
        { level: 1 },
      )
      const select = container.querySelector('.field-select') as HTMLSelectElement
      await fireEvent.update(select, '2')
      const events = emitted()['update:modelValue']
      expect(events?.at(-1)?.[0]).toEqual({ level: 2 })
    })
  })

  // ----------------------------------------------------------
  describe('array (tag list) field', () => {
    it('renders tag list and add input for type=array', () => {
      const { container } = mountSchemaForm(
        {
          type: 'object',
          properties: {
            tags: { type: 'array', title: 'Tags' },
          },
        },
        { tags: ['alpha', 'beta'] },
      )
      expect(container.querySelector('.field-tags')).toBeTruthy()
    })

    it('emits update:modelValue with appended tag on enter', async () => {
      const { container, emitted } = mountSchemaForm(
        {
          type: 'object',
          properties: { tags: { type: 'array', title: 'Tags' } },
        },
        { tags: ['alpha'] },
      )
      const input = container.querySelector('.tags-input') as HTMLInputElement
      input.value = 'beta'
      await fireEvent.keyDown(input, { key: 'Enter' })
      const events = emitted()['update:modelValue']
      expect(events?.at(-1)?.[0]).toEqual({ tags: ['alpha', 'beta'] })
    })

    it('emits update:modelValue without the removed tag', async () => {
      const { container, emitted } = mountSchemaForm(
        {
          type: 'object',
          properties: { tags: { type: 'array', title: 'Tags' } },
        },
        { tags: ['alpha', 'beta'] },
      )
      const removeButtons = container.querySelectorAll('.tag-remove')
      await fireEvent.click(removeButtons[0])
      const events = emitted()['update:modelValue']
      expect(events?.at(-1)?.[0]).toEqual({ tags: ['beta'] })
    })

    it('coerces added tags to numbers when items.type is integer (B-1)', async () => {
      const { container, emitted } = mountSchemaForm(
        {
          type: 'object',
          properties: { ports: { type: 'array', title: 'Ports', items: { type: 'integer' } } },
        },
        { ports: [8080] },
      )
      const input = container.querySelector('.tags-input') as HTMLInputElement
      input.value = '9090'
      await fireEvent.keyDown(input, { key: 'Enter' })
      const events = emitted()['update:modelValue']
      expect(events?.at(-1)?.[0]).toEqual({ ports: [8080, 9090] })
    })

    it('shows existing tags from modelValue', () => {
      const { container } = mountSchemaForm(
        {
          type: 'object',
          properties: { tags: { type: 'array', title: 'Tags' } },
        },
        { tags: ['alpha', 'beta'] },
      )
      const tags = container.querySelectorAll('.tag')
      expect(tags.length).toBe(2)
    })
  })

  // ----------------------------------------------------------
  describe('required field marker', () => {
    it('shows required marker for required fields', () => {
      const { container } = mountSchemaForm({
        type: 'object',
        properties: { host: { type: 'string', title: 'Host' } },
        required: ['host'],
      })
      const mark = container.querySelector('.required-mark')
      expect(mark).toBeTruthy()
    })

    it('does not show required marker for optional fields', () => {
      const { container } = mountSchemaForm({
        type: 'object',
        properties: { host: { type: 'string', title: 'Host' } },
      })
      const mark = container.querySelector('.required-mark')
      expect(mark).toBeNull()
    })
  })

  // ----------------------------------------------------------
  describe('description (help text)', () => {
    it('renders field description when provided', () => {
      const { getByText } = mountSchemaForm({
        type: 'object',
        properties: {
          url: { type: 'string', title: 'URL', description: 'Base API URL' },
        },
      })
      expect(getByText('Base API URL')).toBeTruthy()
    })
  })

  // ----------------------------------------------------------
  describe('raw JSON fallback', () => {
    it('renders textarea fallback when schema has no renderable properties', () => {
      const { container } = mountSchemaForm({
        type: 'object',
        properties: {
          nested: { type: 'object', title: 'Nested' },
        },
      })
      const textarea = container.querySelector('textarea')
      expect(textarea).toBeTruthy()
    })

    it('renders textarea when schema has no properties', () => {
      const { container } = mountSchemaForm({
        type: 'object',
      })
      const textarea = container.querySelector('textarea')
      expect(textarea).toBeTruthy()
    })
  })
})
