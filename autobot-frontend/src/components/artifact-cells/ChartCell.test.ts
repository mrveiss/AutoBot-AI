// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ChartCell from './ChartCell.vue'
import { createI18n } from 'vue-i18n'

// Mock vega-embed
vi.mock('vega-embed', () => ({
  default: {
    embed: vi.fn(async () => ({}))
  }
}))

// Setup i18n
const i18n = createI18n({
  legacy: false,
  locale: 'en',
  messages: {
    en: {
      charts: {
        cellPlaceholder: 'Chart',
        renderError: 'Chart rendering failed',
        viewData: 'View raw data',
        ariaLabel: 'Data visualization chart',
        defaultAriaLabel: 'Data visualization chart'
      },
      common: {
        retry: 'Retry'
      }
    }
  }
})

describe('ChartCell.vue', () => {
  const simpleChartSpec = {
    $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
    data: { values: [{ x: 1, y: 2 }] },
    mark: 'bar',
    encoding: { x: { field: 'x', type: 'quantitative' } }
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('rendering', () => {
    it('shows placeholder when richPayload is null', () => {
      const wrapper = mount(ChartCell, {
        props: { richPayload: null },
        global: {
          stubs: { i: true },
          plugins: [i18n]
        }
      })

      expect(wrapper.find('.chart-placeholder').exists()).toBe(true)
      expect(wrapper.find('.chart-container').exists()).toBe(false)
    })

    it('renders chart container when richPayload is provided', async () => {
      const wrapper = mount(ChartCell, {
        props: { richPayload: simpleChartSpec },
        global: {
          stubs: { i: true },
          plugins: [i18n]
        }
      })

      await wrapper.vm.$nextTick()
      expect(wrapper.find('.chart-container').exists()).toBe(true)
    })

    it('generates unique chart ID', () => {
      const wrapper1 = mount(ChartCell, {
        props: { richPayload: null },
        global: {
          stubs: { i: true },
          plugins: [i18n]
        }
      })

      const wrapper2 = mount(ChartCell, {
        props: { richPayload: null },
        global: {
          stubs: { i: true },
          plugins: [i18n]
        }
      })

      const id1 = wrapper1.vm.chartId
      const id2 = wrapper2.vm.chartId

      expect(id1).not.toBe(id2)
      expect(id1).toMatch(/^chart-/)
    })
  })

  describe('accessibility', () => {
    it('has proper aria-label on chart container', async () => {
      const wrapper = mount(ChartCell, {
        props: { richPayload: simpleChartSpec, title: 'Sales Chart' },
        global: {
          stubs: { i: true },
          plugins: [i18n]
        }
      })

      await wrapper.vm.$nextTick()
      const chartContainer = wrapper.find('[role="img"]')
      expect(chartContainer.exists()).toBe(true)
      expect(chartContainer.attributes('aria-label')).toBeTruthy()
    })

    it('shows accessible data table fallback', async () => {
      const wrapper = mount(ChartCell, {
        props: {
          richPayload: {
            ...simpleChartSpec,
            data: { values: [{ category: 'A', value: 10 }] }
          }
        },
        global: {
          stubs: { i: true },
          plugins: [i18n]
        }
      })

      await wrapper.vm.$nextTick()
      expect(wrapper.find('.chart-data-fallback').exists()).toBe(true)
      expect(wrapper.find('table').exists()).toBe(true)
    })
  })

  describe('data formatting', () => {
    it('extracts data from chart payload', () => {
      const wrapper = mount(ChartCell, {
        props: {
          richPayload: {
            data: [{ x: 1, y: 2 }, { x: 3, y: 4 }],
            mark: 'point'
          }
        },
        global: {
          stubs: { i: true },
          plugins: [i18n]
        }
      })

      const chartData = wrapper.vm.getChartData()
      expect(chartData['Data Points']).toBe(2)
      expect(chartData['Type']).toBe('point')
    })

    it('formats values correctly', () => {
      const wrapper = mount(ChartCell, {
        props: { richPayload: null },
        global: {
          stubs: { i: true },
          plugins: [i18n]
        }
      })

      expect(wrapper.vm.formatValue(null)).toBe('-')
      expect(wrapper.vm.formatValue(undefined)).toBe('-')
      expect(wrapper.vm.formatValue(123)).toBe('123')
      expect(wrapper.vm.formatValue('test')).toBe('test')
    })
  })

  describe('props', () => {
    it('respects renderer prop', () => {
      const wrapper = mount(ChartCell, {
        props: {
          richPayload: simpleChartSpec,
          renderer: 'svg'
        },
        global: {
          stubs: { i: true },
          plugins: [i18n]
        }
      })

      expect(wrapper.props('renderer')).toBe('svg')
    })

    it('respects title prop', () => {
      const wrapper = mount(ChartCell, {
        props: {
          richPayload: simpleChartSpec,
          title: 'My Chart'
        },
        global: {
          stubs: { i: true },
          plugins: [i18n]
        }
      })

      expect(wrapper.props('title')).toBe('My Chart')
    })
  })
})
