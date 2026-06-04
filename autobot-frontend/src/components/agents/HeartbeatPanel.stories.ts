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

/**
 * Visual preview of all four AgentStatus badge variants (GH#8732 / GH#6476 AC-8).
 * These badges appear in the Configuration card once data is loaded.
 * active → green, disabled → gray, paused → orange (with pause details), terminated → red.
 */
export const StatusBadgeVariants: Story = {
  render: () => ({
    template: `
      <div style="background: #0f172a; padding: 1.5rem; font-family: sans-serif; display: flex; flex-direction: column; gap: 1.5rem;">
        <div style="color: #94a3b8; font-size: 0.8rem; margin-bottom: 0.5rem;">AgentStatus badge variants (GH#6476 AC-8)</div>
        <div style="display: flex; gap: 0.75rem; flex-wrap: wrap; align-items: center;">
          <span style="background: rgba(16,185,129,0.2); color: #34d399; border-radius: 4px; font-size: 0.72rem; font-weight: 600; padding: 0.1rem 0.45rem; text-transform: uppercase;">active</span>
          <span style="background: rgba(100,116,139,0.2); color: #94a3b8; border-radius: 4px; font-size: 0.72rem; font-weight: 600; padding: 0.1rem 0.45rem; text-transform: uppercase;">disabled</span>
          <span style="background: rgba(249,115,22,0.2); color: #fb923c; border-radius: 4px; font-size: 0.72rem; font-weight: 600; padding: 0.1rem 0.45rem; text-transform: uppercase;">paused</span>
          <span style="background: rgba(239,68,68,0.2); color: #f87171; border-radius: 4px; font-size: 0.72rem; font-weight: 600; padding: 0.1rem 0.45rem; text-transform: uppercase;">terminated</span>
        </div>
        <div style="background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 1rem;">
          <div style="font-weight: 600; color: #e2e8f0; margin-bottom: 0.75rem;">Paused state — shows pause details</div>
          <div style="display: flex; flex-direction: column; gap: 0.4rem; font-size: 0.8rem;">
            <div style="display: flex; gap: 0.75rem;"><span style="width: 130px; color: #94a3b8;">Status</span><span style="background: rgba(249,115,22,0.2); color: #fb923c; border-radius: 4px; font-size: 0.72rem; font-weight: 600; padding: 0.1rem 0.45rem; text-transform: uppercase;">paused</span></div>
            <div style="display: flex; gap: 0.75rem;"><span style="width: 130px; color: #94a3b8;">Paused By</span><span style="font-family: monospace; color: #e2e8f0;">system:budget</span></div>
            <div style="display: flex; gap: 0.75rem;"><span style="width: 130px; color: #94a3b8;">Paused At</span><span style="color: #e2e8f0;">5/26/2026, 3:42:00 PM</span></div>
            <div style="display: flex; gap: 0.75rem;"><span style="width: 130px; color: #94a3b8;">Reason</span><span style="color: #e2e8f0;">Budget threshold exceeded (80%)</span></div>
          </div>
          <div style="border-top: 1px solid #334155; margin-top: 0.75rem; padding-top: 0.75rem; display: flex; gap: 0.5rem;">
            <button style="background: rgba(16,185,129,0.2); border: 1px solid rgba(16,185,129,0.5); border-radius: 4px; color: #34d399; font-size: 0.8rem; padding: 0.3rem 0.6rem; cursor: pointer;">Resume</button>
          </div>
        </div>
      </div>
    `,
  }),
};
