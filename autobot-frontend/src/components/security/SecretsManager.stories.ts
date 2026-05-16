import type { Meta, StoryObj } from '@storybook/vue3';
import SecretsManager from './SecretsManager.vue';

const meta = {
  title: 'Components/Security/SecretsManager',
  component: SecretsManager,
  argTypes: {},
} as Meta<typeof SecretsManager>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
type Story = StoryObj<any>;

export const Default: Story = {
  render: () => ({
    components: { SecretsManager },
    template: '<SecretsManager />',
  }),
};

export const FullWidth: Story = {
  render: () => ({
    components: { SecretsManager },
    template: `
      <div style="width: 100%; min-height: 600px;">
        <SecretsManager />
      </div>
    `,
  }),
};

export const InPanel: Story = {
  render: () => ({
    components: { SecretsManager },
    template: `
      <div style="max-width: 1200px; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden;">
        <SecretsManager />
      </div>
    `,
  }),
};
