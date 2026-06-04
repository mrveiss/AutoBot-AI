// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
import type { Meta, StoryObj } from '@storybook/vue3';
import ManPageManager from './ManPageManager.vue';

const meta = {
  title: 'Components/ManPage/ManPageManager',
  component: ManPageManager,
  tags: ['autodocs'],
  argTypes: {},
} as Meta<typeof ManPageManager>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

// ManPageManager is self-contained: it fetches its own data via composables on mount.
// Stories render the shell; real data requires a live backend.

export const Default: Story = {
  render: () => ({
    components: { ManPageManager },
    template: '<ManPageManager />',
  }),
};

export const WithStubSetup: Story = {
  name: 'Default (stub note)',
  render: () => ({
    components: { ManPageManager },
    template: `
      <div>
        <p style="color: var(--color-warning, #f39c12); margin-bottom: 8px; font-size: 0.85rem;">
          Note: ManPageManager fetches live data on mount. Connect to a running backend to see populated state.
        </p>
        <ManPageManager />
      </div>
    `,
  }),
};
