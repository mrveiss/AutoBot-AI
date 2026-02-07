import { z } from 'zod';

export const TOOL_NAME = "getNextTask";

export const TOOL_DESCRIPTION = `
Identifies and returns the next actionable task within a specified project.
A task is considered actionable if its status is 'todo' and all its dependencies (if any) have a status of 'done'.
If multiple tasks are ready, the one with the highest priority ('high' > 'medium' > 'low') is chosen.
If priorities are equal, the task created earliest is chosen.
Returns the full details of the next task, or null if no task is currently ready.
`;

// Zod schema for the parameters, matching FR-007 and getNextTaskTool.md spec
export const TOOL_PARAMS = z.object({
    project_id: z.string()
        .uuid("The project_id must be a valid UUID.")
        .describe("The unique identifier (UUID) of the project to find the next task for."), // Required, UUID format
});

// Define the expected type for arguments based on the Zod schema
export type GetNextTaskArgs = z.infer<typeof TOOL_PARAMS>;
