import type { Meta } from '@storybook/vue3';
import HeartbeatPanel from './HeartbeatPanel.vue';

const meta = {
  title: 'Components/Agents/HeartbeatPanel',
  component: HeartbeatPanel,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component:
          'Heartbeat monitoring panel for a single agent. Self-contained — enter an agent ID ' +
          'and click Load to fetch config, run history, and wakeup queue from the AutoBot backend ' +
          '(/api/heartbeat). Subscribes to live heartbeat_run_started / heartbeat_run_completed ' +
          'events via SSE. Requires a running AutoBot backend; in Storybook the panel renders in ' +
          'its empty/idle state until an agent ID is supplied.',
      },
    },
  },
} as Meta<typeof HeartbeatPanel>;

export default meta;
// #7273: relaxed to StoryObj<any> for render-only stories that don't match component props
 
type Story = { render?: () => unknown; decorators?: unknown[]; parameters?: unknown };

/** Default idle state — panel is empty, waiting for an agent ID to be entered. */
export const Default: Story = {
  render: () => ({
    components: { HeartbeatPanel },
    template: '<HeartbeatPanel />',
  }),
};

/** Panel inside a realistic page-content container with padding and dark background. */
export const InPageContext: Story = {
  render: () => ({
    components: { HeartbeatPanel },
    template: `
      <div style="background: #0f172a; padding: 1.5rem; min-height: 400px;">
        <HeartbeatPanel />
      </div>
    `,
  }),
};

/** Panel in a narrow column — tests responsive layout of header and config grid. */
export const NarrowColumn: Story = {
  render: () => ({
    components: { HeartbeatPanel },
    template: `
      <div style="max-width: 480px; background: #0f172a; padding: 1rem;">
        <HeartbeatPanel />
      </div>
    `,
  }),
};
