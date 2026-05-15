import { z } from 'zod';

export const TOOL_NAME = "expandTask";

export const TOOL_DESCRIPTION = `
Breaks down a specified parent task into multiple subtasks based on provided descriptions.
Requires the project ID, the parent task ID, and an array of descriptions for the new subtasks.
Optionally allows forcing the replacement of existing subtasks using the 'force' flag.
Returns the updated parent task details, including the newly created subtasks.
`;

// Zod schema for the parameters, matching FR-006 and expandTaskTool.md spec
export const TOOL_PARAMS = z.object({
    project_id: z.string()
        .uuid("The project_id must be a valid UUID.")
        .describe("The unique identifier (UUID) of the project containing the parent task."), // Required, UUID format

    task_id: z.string()
        // Add .uuid() if task IDs are also UUIDs
        .min(1, "Parent task ID cannot be empty.")
        .describe("The unique identifier of the parent task to be expanded."), // Required, string (or UUID)

    subtask_descriptions: z.array(
            z.string()
                .min(1, "Subtask description cannot be empty.")
                .max(512, "Subtask description cannot exceed 512 characters.")
                .describe("A textual description for one of the new subtasks (1-512 characters).")
        )
        .min(1, "At least one subtask description must be provided.")
        .max(20, "Cannot create more than 20 subtasks per call.")
        .describe("An array of descriptions (1-20) for the new subtasks to be created under the parent task."), // Required, array of strings, limits

    force: z.boolean()
        .optional()
        .default(false)
        .describe("Optional flag (default false). If true, any existing subtasks of the parent task will be deleted before creating the new ones. If false and subtasks exist, the operation will fail."), // Optional, boolean, default
});

// Define the expected type for arguments based on the Zod schema
export type ExpandTaskArgs = z.infer<typeof TOOL_PARAMS>;
