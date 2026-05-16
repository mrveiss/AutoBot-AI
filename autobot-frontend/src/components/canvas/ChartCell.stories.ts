import type { Meta, StoryObj } from '@storybook/vue3'
import type { TopLevelSpec } from 'vega-lite'
import ChartCell from './ChartCell.vue'
import type { ChartPayload } from '@/types/canvas'

const meta: Meta<typeof ChartCell> = {
  title: 'Canvas/ChartCell',
  component: ChartCell,
  parameters: {
    layout: 'padded',
  },
  argTypes: {
    richPayload: { control: 'object' },
  },
}

export default meta
type Story = StoryObj<typeof ChartCell>

// Sample Vega-Lite spec
const barChartSpec: TopLevelSpec = {
  $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
  title: 'Simple Bar Chart',
  data: {
    values: [
      { category: 'A', value: 28 },
      { category: 'B', value: 55 },
      { category: 'C', value: 43 },
      { category: 'D', value: 91 },
      { category: 'E', value: 81 },
      { category: 'F', value: 53 },
      { category: 'G', value: 19 },
      { category: 'H', value: 87 },
    ],
  },
  mark: 'bar',
  encoding: {
    x: { field: 'category', type: 'nominal', axis: { labelAngle: 0 } },
    y: { field: 'value', type: 'quantitative' },
    color: { field: 'category', type: 'nominal', legend: null },
  },
}

export const Default: Story = {
  args: {
    richPayload: {
      payloadType: 'vega-lite',
      specVersion: '5',
      spec: barChartSpec,
      executable: false,
    } as ChartPayload,
  },
}

export const LineChart: Story = {
  args: {
    richPayload: {
      payloadType: 'vega-lite',
      specVersion: '5',
      spec: {
        $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
        title: 'Line Chart Over Time',
        data: {
          values: [
            { date: '2026-01-01', value: 10 },
            { date: '2026-02-01', value: 25 },
            { date: '2026-03-01', value: 35 },
            { date: '2026-04-01', value: 28 },
            { date: '2026-05-01', value: 45 },
          ],
        },
        mark: 'line',
        encoding: {
          x: { field: 'date', type: 'temporal', title: 'Date' },
          y: { field: 'value', type: 'quantitative', title: 'Value' },
          tooltip: [
            { field: 'date', type: 'temporal' },
            { field: 'value', type: 'quantitative' },
          ],
        },
      } as TopLevelSpec,
      executable: false,
    } as ChartPayload,
  },
}

export const Empty: Story = {
  args: {
    richPayload: null,
  },
}

export const ScatterPlot: Story = {
  args: {
    richPayload: {
      payloadType: 'vega-lite',
      specVersion: '5',
      spec: {
        $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
        title: 'Scatter Plot',
        data: {
          values: [
            { x: 10, y: 28, category: 'A' },
            { x: 15, y: 35, category: 'B' },
            { x: 20, y: 42, category: 'A' },
            { x: 25, y: 55, category: 'B' },
            { x: 30, y: 48, category: 'A' },
            { x: 35, y: 62, category: 'B' },
          ],
        },
        mark: 'point',
        encoding: {
          x: { field: 'x', type: 'quantitative' },
          y: { field: 'y', type: 'quantitative' },
          color: { field: 'category', type: 'nominal' },
          size: { value: 100 },
        },
      } as TopLevelSpec,
      executable: false,
    } as ChartPayload,
  },
}
