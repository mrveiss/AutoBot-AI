import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { McpError, ErrorCode } from "@modelcontextprotocol/sdk/types.js";
import { TOOL_NAME, TOOL_DESCRIPTION, TOOL_PARAMS, ListTasksArgs } from "./listTasksParams.js";
import { TaskService } from "../services/TaskService.js";
import { logger } from '../utils/logger.js';
import { NotFoundError } from "../utils/errors.js";

/**
 * Registers the listTasks tool with the MCP server.
 *
 * @param server - The McpServer instance.
 * @param taskService - An instance of the TaskService.
 */
export const listTasksTool = (server: McpServer, taskService: TaskService): void => {

    const processRequest = async (args: ListTasksArgs) => {
        logger.info(`[${TOOL_NAME}] Received request with args:`, args);
        try {
            // Call the service method to list tasks
            const tasks = await taskService.listTasks({
                project_id: args.project_id,
                status: args.status,
                include_subtasks: args.include_subtasks,
            });

            // Format the successful response
            logger.info(`[${TOOL_NAME}] Found ${tasks.length} tasks for project ${args.project_id}`);
            return {
                content: [{
                    type: "text" as const,
                    text: JSON.stringify(tasks) // Return the array of task objects
                }]
            };
        } catch (error: unknown) {
            // Handle potential errors
            logger.error(`[${TOOL_NAME}] Error processing request:`, error);

            if (error instanceof NotFoundError) {
                // Specific error if the project wasn't found
                throw new McpError(ErrorCode.InvalidParams, error.message); // Map NotFound to InvalidParams for project_id
            } else {
                // Generic internal error
                const message = error instanceof Error ? error.message : 'An unknown error occurred while listing tasks.';
                throw new McpError(ErrorCode.InternalError, message);
            }
        }
    };

    // Register the tool with the server
    server.tool(TOOL_NAME, TOOL_DESCRIPTION, TOOL_PARAMS.shape, processRequest);

    logger.info(`[${TOOL_NAME}] Tool registered successfully.`);
};
