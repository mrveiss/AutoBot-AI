import { z } from 'zod';

export const TOOL_NAME = "createProject";

export const TOOL_DESCRIPTION = `
Creates a new, empty project entry in the Task Management Server database.
This tool is used by clients (e.g., AI agents) to initiate a new workspace for tasks.
It returns the unique identifier (UUID) assigned to the newly created project.
An optional name can be provided; otherwise, a default name including a timestamp will be generated.
`;

// Define the shape of the parameters for the server.tool method
export const TOOL_PARAMS = {
    projectName: z.string()
        .max(255, "Project name cannot exceed 255 characters.") // Max length constraint
        .optional() // Optional parameter
        .describe("Optional human-readable name for the new project (max 255 chars). If omitted, a default name like 'New Project [timestamp]' will be used."), // Detailed description
};

// Create a Zod schema object from the shape for validation and type inference
const toolParamsSchema = z.object(TOOL_PARAMS);

// Define the expected type for arguments based on the Zod schema
export type CreateProjectArgs = z.infer<typeof toolParamsSchema>;
