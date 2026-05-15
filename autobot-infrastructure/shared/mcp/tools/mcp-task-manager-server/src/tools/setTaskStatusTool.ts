import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { McpError, ErrorCode } from "@modelcontextprotocol/sdk/types.js";
import { TOOL_NAME, TOOL_DESCRIPTION, TOOL_PARAMS, SetTaskStatusArgs } from "./setTaskStatusParams.js";
import { TaskService } from "../services/TaskService.js";
import { logger } from '../utils/logger.js';
import { NotFoundError } from "../utils/errors.js";

/**
 * Registers the setTaskStatus tool with the MCP server.
 *
 * @param server - The McpServer instance.
 * @param taskService - An instance of the TaskService.
 */
export const setTaskStatusTool = (server: McpServer, taskService: TaskService): void => {

    const processRequest = async (args: SetTaskStatusArgs) => {
        logger.info(`[${TOOL_NAME}] Received request with args:`, args);
        try {
            // Call the service method to update the status
            const updatedCount = await taskService.setTaskStatus(
                args.project_id,
                args.task_ids,
                args.status
            );

            // Format the successful response
            const responsePayload = { success: true, updated_count: updatedCount };
            logger.info(`[${TOOL_NAME}] Updated status for ${updatedCount} tasks in project ${args.project_id}`);
            return {
                content: [{
                    type: "text" as const,
                    text: JSON.stringify(responsePayload)
                }]
            };
        } catch (error: unknown) {
            // Handle potential errors
            logger.error(`[${TOOL_NAME}] Error processing request:`, error);

            if (error instanceof NotFoundError) {
                // Specific error if the project or any task wasn't found
                // Map to InvalidParams as the provided ID(s) are invalid
                throw new McpError(ErrorCode.InvalidParams, error.message);
            } else {
                // Generic internal error
                const message = error instanceof Error ? error.message : 'An unknown error occurred while setting task status.';
                throw new McpError(ErrorCode.InternalError, message);
            }
        }
    };

    // Register the tool with the server
    server.tool(TOOL_NAME, TOOL_DESCRIPTION, TOOL_PARAMS.shape, processRequest);

    logger.info(`[${TOOL_NAME}] Tool registered successfully.`);
};
