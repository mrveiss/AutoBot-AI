// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import type { Meta, StoryObj } from '@storybook/vue3';
import PhaseProgressionIndicator from './PhaseProgressionIndicator.vue';

const meta = {
  title: 'Components/Workflow/PhaseProgressionIndicator',
  component: PhaseProgressionIndicator,
  tags: ['autodocs'],
  argTypes: {},
} as Meta<typeof PhaseProgressionIndicator>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

// PhaseProgressionIndicator fetches its own data on demand via the
// /api/validation-dashboard/report endpoint. Stories render the idle
// (ready) state; clicking the "Load Data" button triggers the fetch.

export const ReadyState: Story = {
  render: () => ({
    components: { PhaseProgressionIndicator },
    template: '<PhaseProgressionIndicator />',
  }),
};

export const ContainerWidth: Story = {
  render: () => ({
    components: { PhaseProgressionIndicator },
    template: `
      <div style="max-width: 800px; margin: 0 auto;">
        <PhaseProgressionIndicator />
      </div>
    `,
  }),
};

export const NarrowViewport: Story = {
  render: () => ({
    components: { PhaseProgressionIndicator },
    template: '<PhaseProgressionIndicator />',
  }),
  parameters: {
    viewport: { defaultViewport: 'mobile1' },
  },
};
