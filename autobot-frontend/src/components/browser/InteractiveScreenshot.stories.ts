// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

import type { Meta, StoryObj } from '@storybook/vue3';
import InteractiveScreenshot from './InteractiveScreenshot.vue';

// 1x1 transparent PNG for story demonstrations
const SAMPLE_SCREENSHOT =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==';

const SAMPLE_REGIONS = [
  {
    selector: '#main-nav',
    rect: { x: 0, y: 0, width: 200, height: 50 },
    label: 'Navigation',
  },
  {
    selector: '.hero-section',
    rect: { x: 0, y: 50, width: 1280, height: 400 },
    label: 'Hero',
  },
];

const meta = {
  title: 'Components/Browser/InteractiveScreenshot',
  component: InteractiveScreenshot,
  tags: ['autodocs'],
  argTypes: {
    screenshot: {
      control: 'text',
      description: 'Base64-encoded PNG screenshot data (without data URI prefix)',
    },
    loading: {
      control: 'boolean',
      description: 'Show loading overlay over the screenshot',
    },
    interactive: {
      control: 'boolean',
      description: 'Allow click/scroll/type interaction with the screenshot',
    },
    viewportWidth: {
      control: { type: 'number', min: 320, max: 3840, step: 10 },
      description: 'Width of the remote viewport in pixels',
    },
    viewportHeight: {
      control: { type: 'number', min: 240, max: 2160, step: 10 },
      description: 'Height of the remote viewport in pixels',
    },
    regions: {
      control: 'object',
      description: 'Array of PageRegion objects for region-marking mode',
    },
    markRegionsMode: {
      control: 'boolean',
      description: 'Activate region-marking overlay (requires regions + screenshot)',
    },
  },
} as Meta<typeof InteractiveScreenshot>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

/** No screenshot loaded — shows placeholder message */
export const Empty: Story = {
  args: {
    screenshot: null,
    loading: false,
    interactive: true,
    viewportWidth: 1280,
    viewportHeight: 720,
    regions: [],
    markRegionsMode: false,
  },
};

/** Screenshot is loading — spinner overlay shown on existing image */
export const Loading: Story = {
  args: {
    screenshot: SAMPLE_SCREENSHOT,
    loading: true,
    interactive: true,
    viewportWidth: 1280,
    viewportHeight: 720,
    regions: [],
    markRegionsMode: false,
  },
};

/** Screenshot loaded and interactive — crosshair cursor, scroll/type toolbar visible */
export const WithScreenshot: Story = {
  args: {
    screenshot: SAMPLE_SCREENSHOT,
    loading: false,
    interactive: true,
    viewportWidth: 1280,
    viewportHeight: 720,
    regions: [],
    markRegionsMode: false,
  },
};

/** Screenshot loaded but read-only — toolbar hidden, normal cursor */
export const ReadOnly: Story = {
  args: {
    screenshot: SAMPLE_SCREENSHOT,
    loading: false,
    interactive: false,
    viewportWidth: 1280,
    viewportHeight: 720,
    regions: [],
    markRegionsMode: false,
  },
};

/** Region-marking mode active with sample page regions (#5136) */
export const WithRegions: Story = {
  args: {
    screenshot: SAMPLE_SCREENSHOT,
    loading: false,
    interactive: true,
    viewportWidth: 1280,
    viewportHeight: 720,
    regions: SAMPLE_REGIONS,
    markRegionsMode: true,
  },
};
