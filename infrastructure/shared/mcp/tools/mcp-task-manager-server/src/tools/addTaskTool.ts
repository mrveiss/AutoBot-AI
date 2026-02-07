import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js"; // Correct path for McpServer
import { McpError, ErrorCode } from "@modelcontextprotocol/sdk/types.js"; // Correct path for Error types
import { TOOL_NAME, TOOL_DESCRIPTION, TOOL_PARAMS, AddTaskArgs } from "./addTaskParams.js";
import { TaskService } from "../services/TaskService.js"; // Assuming TaskService is exported via services/index.js
import { logger } from '../utils/logger.js';
import { NotFoundError, ValidationError } from "../utils/errors.js"; // Import custom errors

/**
 * Registers the addTask tool with the MCP server.
 *
 * @param server - The McpServer instance.
 * @param taskService - An instance of the TaskService.
 */
export const addTaskTool = (server: McpServer, taskService: TaskService): void => {

    // Define the asynchronous function that handles the actual tool logic
    const processRequest = async (args: AddTaskArgs) => {
        logger.info(`[${TOOL_NAME}] Received request with args:`, args);
        try {
            // Call the service method to add the task
            // The Zod schema handles basic type/format/length validation
            const newTask = await taskService.addTask({
                project_id: args.project_id,
                description: args.description,
                dependencies: args.dependencies, // Pass optional fields
                priority: args.priority,
                status: args.status,
            });

            // Format the successful response according to MCP standards
            // Return the full details of the created task as per spec FR-FS-011
            logger.info(`[${TOOL_NAME}] Task added successfully: ${newTask.task_id}`);
            return {
                content: [{
                    type: "text" as const,
                    text: JSON.stringify(newTask) // Return the full task object
                }]
            };
        } catch (error: unknown) {
            // Handle potential errors from the service layer
            logger.error(`[${TOOL_NAME}] Error processing request:`, error);

            if (error instanceof NotFoundError) {
                // Specific error if the project wasn't found - map to InvalidParams as project_id is invalid
                throw new McpError(ErrorCode.InvalidParams, error.message);
            } else if (error instanceof ValidationError) {
                // Specific error for validation issues within the service (e.g., dependency check if implemented)
                throw new McpError(ErrorCode.InvalidParams, error.message);
            } else {
                // Generic internal error for database issues or unexpected problems
                const message = error instanceof Error ? error.message : 'An unknown error occurred while adding the task.';
                throw new McpError(ErrorCode.InternalError, message);
            }
        }
    };

    // Register the tool with the server, passing the shape of the Zod object
    server.tool(TOOL_NAME, TOOL_DESCRIPTION, TOOL_PARAMS.shape, processRequest);

    logger.info(`[${TOOL_NAME}] Tool registered successfully.`);
};
