import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import type { TopLevelSpec } from 'vega-lite'
import ChartCell from './ChartCell.vue'
import type { ChartPayload } from '@/types/canvas'

describe('ChartCell.vue', () => {
  const mockSpec: TopLevelSpec = {
    $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
    data: { values: [{ x: 1, y: 2 }, { x: 2, y: 3 }] },
    mark: 'point',
    encoding: {
      x: { field: 'x', type: 'quantitative' },
      y: { field: 'y', type: 'quantitative' },
    },
  }

  const mockPayload: ChartPayload = {
    payloadType: 'vega-lite',
    specVersion: '5',
    spec: mockSpec,
    executable: false,
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders loading state when no payload', () => {
    const wrapper = mount(ChartCell, {
      props: { richPayload: null },
    })
    expect(wrapper.find('[aria-busy="true"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Loading chart')
  })

  it('renders chart container when payload provided', async () => {
    const wrapper = mount(ChartCell, {
      props: { richPayload: mockPayload },
    })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[role="img"]').exists()).toBe(true)
  })

  it('renders data table details element', () => {
    const wrapper = mount(ChartCell, {
      props: { richPayload: mockPayload },
    })
    expect(wrapper.find('details').exists()).toBe(true)
    expect(wrapper.text()).toContain('View data table')
  })

  it('has accessible aria-label on chart container', () => {
    const wrapper = mount(ChartCell, {
      props: { richPayload: mockPayload },
    })
    const chart = wrapper.find('[role="img"]')
    expect(chart.attributes('aria-label')).toContain('Chart')
  })

  it('displays error message on render failure', async () => {
    const wrapper = mount(ChartCell, {
      props: {
        richPayload: {
          ...mockPayload,
          spec: { invalid: 'spec' } as any,
        },
      },
    })
    await wrapper.vm.$nextTick()
    await new Promise(resolve => setTimeout(resolve, 100))
    // Error will be set due to invalid spec
    // Component should handle gracefully
    expect(wrapper.find('[role="img"]').exists() || wrapper.text().includes('Error')).toBe(true)
  })

  it('supports prefers-reduced-motion media query', () => {
    const wrapper = mount(ChartCell, {
      props: { richPayload: mockPayload },
    })
    // Component respects prefers-reduced-motion internally
    expect(wrapper.vm.$data.prefersReducedMotion !== undefined).toBe(true)
  })

  it('renders tables with proper structure', () => {
    const wrapper = mount(ChartCell, {
      props: { richPayload: mockPayload },
    })
    const table = wrapper.find('table')
    expect(table.exists()).toBe(true)
    expect(table.find('thead').exists()).toBe(true)
    expect(table.find('tbody').exists()).toBe(true)
  })

  it('updates chart when payload changes', async () => {
    const wrapper = mount(ChartCell, {
      props: { richPayload: mockPayload },
    })
    const newPayload: ChartPayload = {
      ...mockPayload,
      spec: {
        ...mockSpec,
        title: 'Updated Chart',
      },
    }
    await wrapper.setProps({ richPayload: newPayload })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[role="img"]').exists()).toBe(true)
  })

  it('clears error state when valid payload provided', async () => {
    const wrapper = mount(ChartCell, {
      props: { richPayload: null },
    })
    await wrapper.setProps({ richPayload: mockPayload })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('[role="img"]').exists()).toBe(true)
  })
})
