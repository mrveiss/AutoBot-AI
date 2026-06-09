// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3'
import ChartCell from './ChartCell.vue'

const meta = {
  title: 'Components/Artifact Cells/ChartCell',
  component: ChartCell,
  tags: ['autodocs'],
  argTypes: {
    richPayload: {
      control: 'object',
      description: 'Vega-Lite specification object'
    },
    title: {
      control: 'text',
      description: 'Chart title for accessibility'
    },
    height: {
      control: 'text',
      description: 'Chart height (CSS)'
    },
    width: {
      control: 'text',
      description: 'Chart width (CSS)'
    },
    renderer: {
      control: { type: 'radio', options: ['canvas', 'svg'] },
      description: 'Vega-Lite renderer type'
    }
  }
} satisfies Meta<typeof ChartCell>

export default meta
type Story = StoryObj<typeof meta>

// Simple bar chart
const simpleBarChart = {
  $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
  title: 'Sales by Category',
  description: 'A simple bar chart showing sales data',
  data: {
    values: [
      { category: 'A', sales: 28 },
      { category: 'B', sales: 55 },
      { category: 'C', sales: 43 },
      { category: 'D', sales: 91 },
      { category: 'E', sales: 81 }
    ]
  },
  mark: 'bar',
  encoding: {
    x: { field: 'category', type: 'nominal' },
    y: { field: 'sales', type: 'quantitative' }
  }
}

// Line chart with animation
const lineChart = {
  $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
  description: 'A line chart showing trends over time',
  data: {
    values: [
      { date: '2024-01', value: 10 },
      { date: '2024-02', value: 20 },
      { date: '2024-03', value: 15 },
      { date: '2024-04', value: 30 },
      { date: '2024-05', value: 25 }
    ]
  },
  mark: 'line',
  encoding: {
    x: { field: 'date', type: 'temporal' },
    y: { field: 'value', type: 'quantitative' }
  },
  config: {
    mark: { animationDuration: 500 }
  }
}

// Scatter plot
const scatterPlot = {
  $schema: 'https://vega.github.io/schema/vega-lite/v5.json',
  description: 'A scatter plot with color encoding',
  data: {
    values: [
      { x: 10, y: 20, category: 'A' },
      { x: 20, y: 40, category: 'B' },
      { x: 30, y: 35, category: 'A' },
      { x: 40, y: 50, category: 'B' },
      { x: 50, y: 45, category: 'A' }
    ]
  },
  mark: 'point',
  encoding: {
    x: { field: 'x', type: 'quantitative' },
    y: { field: 'y', type: 'quantitative' },
    color: { field: 'category', type: 'nominal' },
    size: { value: 100 }
  }
}

// Invalid spec for error state
const invalidSpec = {
  mark: 'invalid-mark-type',
  data: []
}

export const Default: Story = {
  args: {
    richPayload: simpleBarChart,
    title: 'Sales Data'
  }
}

export const WithLineChart: Story = {
  args: {
    richPayload: lineChart,
    title: 'Trend Over Time'
  }
}

export const WithScatterPlot: Story = {
  args: {
    richPayload: scatterPlot,
    title: 'Correlation Analysis'
  }
}

export const Empty: Story = {
  args: {
    richPayload: null,
    title: 'Empty Chart'
  }
}

export const WithError: Story = {
  args: {
    richPayload: invalidSpec as any,
    title: 'Error State Chart'
  }
}

export const SVGRenderer: Story = {
  args: {
    richPayload: simpleBarChart,
    title: 'SVG Rendered Chart',
    renderer: 'svg'
  }
}

export const CustomHeight: Story = {
  args: {
    richPayload: lineChart,
    title: 'Tall Chart',
    height: 500
  }
}

export const NoAnimation: Story = {
  args: {
    richPayload: {
      ...lineChart,
      config: {
        mark: { animationDuration: 0 }
      }
    },
    title: 'No Animation Chart'
  }
}
