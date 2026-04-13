import type { Meta, StoryObj } from '@storybook/vue3';

const meta = {
  title: 'Introduction/Welcome',
  tags: ['autodocs'],
  parameters: {
    layout: 'centered',
  },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const Overview: Story = {
  render: () => ({
    template: `
      <div class="max-w-4xl mx-auto p-8 space-y-8">
        <div>
          <h1 class="text-4xl font-bold mb-2">AutoBot Component Library</h1>
          <p class="text-lg text-gray-600">Vue 3 design system documentation and interactive component showcase</p>
        </div>

        <div class="space-y-6">
          <section>
            <h2 class="text-2xl font-bold mb-4">Base Components</h2>
            <div class="grid grid-cols-2 gap-4">
              <a href="?path=/docs/components-base-basebutton--docs" class="p-4 border rounded-lg hover:bg-gray-50">
                <h3 class="font-semibold">BaseButton</h3>
                <p class="text-sm text-gray-600">Interactive button component with variants and states</p>
              </a>
              <a href="?path=/docs/components-base-baseinput--docs" class="p-4 border rounded-lg hover:bg-gray-50">
                <h3 class="font-semibold">BaseInput</h3>
                <p class="text-sm text-gray-600">Form input component with validation and helpers</p>
              </a>
              <a href="?path=/docs/components-base-basecard--docs" class="p-4 border rounded-lg hover:bg-gray-50">
                <h3 class="font-semibold">BaseCard</h3>
                <p class="text-sm text-gray-600">Card container with multiple styling variants</p>
              </a>
              <a href="?path=/docs/components-base-basebadge--docs" class="p-4 border rounded-lg hover:bg-gray-50">
                <h3 class="font-semibold">BaseBadge</h3>
                <p class="text-sm text-gray-600">Badge component for labels and status indicators</p>
              </a>
              <a href="?path=/docs/components-base-basetable--docs" class="p-4 border rounded-lg hover:bg-gray-50">
                <h3 class="font-semibold">BaseTable</h3>
                <p class="text-sm text-gray-600">Data table component with sorting and filtering</p>
              </a>
              <a href="?path=/docs/components-base-basepanel--docs" class="p-4 border rounded-lg hover:bg-gray-50">
                <h3 class="font-semibold">BasePanel</h3>
                <p class="text-sm text-gray-600">Collapsible panel component for organizing content</p>
              </a>
            </div>
          </section>

          <section>
            <h2 class="text-2xl font-bold mb-4">Common Components</h2>
            <div class="grid grid-cols-2 gap-4">
              <a href="?path=/docs/components-common-errorboundary--docs" class="p-4 border rounded-lg hover:bg-gray-50">
                <h3 class="font-semibold">ErrorBoundary</h3>
                <p class="text-sm text-gray-600">Error handling and recovery component</p>
              </a>
              <a href="?path=/docs/components-common-permissiondenied--docs" class="p-4 border rounded-lg hover:bg-gray-50">
                <h3 class="font-semibold">PermissionDenied</h3>
                <p class="text-sm text-gray-600">Permission access denied display</p>
              </a>
            </div>
          </section>

          <section>
            <h2 class="text-2xl font-bold mb-4">Feature Components</h2>
            <div class="grid grid-cols-2 gap-4">
              <a href="?path=/docs/components-chat-chatheader--docs" class="p-4 border rounded-lg hover:bg-gray-50">
                <h3 class="font-semibold">ChatHeader</h3>
                <p class="text-sm text-gray-600">Header component for chat interface</p>
              </a>
              <a href="?path=/docs/components-auth-loginform--docs" class="p-4 border rounded-lg hover:bg-gray-50">
                <h3 class="font-semibold">LoginForm</h3>
                <p class="text-sm text-gray-600">User authentication form</p>
              </a>
            </div>
          </section>

          <section class="bg-blue-50 p-6 rounded-lg">
            <h3 class="text-xl font-bold mb-2">Usage Guide</h3>
            <ul class="space-y-2 text-sm text-gray-700">
              <li>• Click on any component to view its documentation and interactive examples</li>
              <li>• Use the "Docs" tab to read component API documentation</li>
              <li>• Use the "Canvas" tab to interact with component controls</li>
              <li>• Check "Controls" panel to modify props and see live updates</li>
            </ul>
          </section>

          <section class="bg-green-50 p-6 rounded-lg">
            <h3 class="text-xl font-bold mb-2">For Developers</h3>
            <p class="text-sm text-gray-700 mb-3">Component stories are located alongside component files:</p>
            <code class="block bg-white p-3 rounded text-xs text-gray-800 border border-gray-200">
              src/components/base/BaseButton.stories.ts<br/>
              src/components/chat/ChatHeader.stories.ts<br/>
              src/components/auth/LoginForm.stories.ts
            </code>
          </section>
        </div>
      </div>
    `,
  }),
};
