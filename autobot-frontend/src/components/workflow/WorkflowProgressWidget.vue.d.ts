import type { DefineComponent } from 'vue'

declare const WorkflowProgressWidget: DefineComponent<
  {
    workflowId?: string
  },
  {},
  unknown
>

export default WorkflowProgressWidget
