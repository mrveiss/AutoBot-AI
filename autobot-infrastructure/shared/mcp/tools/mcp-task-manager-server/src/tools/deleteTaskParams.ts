import { z } from 'zod';

export const TOOL_NAME = "deleteTask";

export const TOOL_DESCRIPTION = `
Deletes one or more tasks within a specified project.
Requires the project ID and an array of task IDs to delete.
Note: Deleting a task also deletes its subtasks and dependency links due to database cascade rules.
Returns the count of successfully deleted tasks.
`;

// Zod schema for the parameters, matching FR-012
export const TOOL_PARAMS = z.object({
    project_id: z.string()
        .uuid("The project_id must be a valid UUID.")
        .describe("The unique identifier (UUID) of the project containing the tasks to delete. This project must exist."), // Required, UUID format

    task_ids: z.array(
            z.string()
                .uuid("Each task ID must be a valid UUID.")
                .describe("A unique identifier (UUID) of a task to delete.")
        )
        .min(1, "At least one task ID must be provided.")
        .max(100, "Cannot delete more than 100 tasks per call.")
        .describe("An array of task IDs (UUIDs, 1-100) to be deleted from the specified project."), // Required, array of UUID strings, limits

});

// Define the expected type for arguments based on the Zod schema
export type DeleteTaskArgs = z.infer<typeof TOOL_PARAMS>;
