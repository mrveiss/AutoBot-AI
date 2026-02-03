#!/bin/bash

# AutoBot Agent MCP Tools Update Script
# Updates all remaining agents with complete MCP tool access and collaboration patterns

# Define the complete MCP tools list
MCP_TOOLS="mcp__memory__create_entities, mcp__memory__create_relations, mcp__memory__add_observations, mcp__memory__delete_entities, mcp__memory__delete_observations, mcp__memory__delete_relations, mcp__memory__read_graph, mcp__memory__search_nodes, mcp__memory__open_nodes, mcp__filesystem__read_text_file, mcp__filesystem__read_media_file, mcp__filesystem__read_multiple_files, mcp__filesystem__write_file, mcp__filesystem__edit_file, mcp__filesystem__create_directory, mcp__filesystem__list_directory, mcp__filesystem__list_directory_with_sizes, mcp__filesystem__directory_tree, mcp__filesystem__move_file, mcp__filesystem__search_files, mcp__filesystem__get_file_info, mcp__filesystem__list_allowed_directories, mcp__sequential-thinking__sequentialthinking, mcp__structured-thinking__chain_of_thought, mcp__shrimp-task-manager__plan_task, mcp__shrimp-task-manager__analyze_task, mcp__shrimp-task-manager__reflect_task, mcp__shrimp-task-manager__split_tasks, mcp__shrimp-task-manager__list_tasks, mcp__shrimp-task-manager__execute_task, mcp__shrimp-task-manager__verify_task, mcp__shrimp-task-manager__delete_task, mcp__shrimp-task-manager__update_task, mcp__shrimp-task-manager__query_task, mcp__shrimp-task-manager__get_task_detail, mcp__shrimp-task-manager__process_thought, mcp__context7__resolve-library-id, mcp__context7__get-library-docs, mcp__ide__getDiagnostics, mcp__ide__executeCode"

# List of agents that need basic MCP tools (no browser/mobile testing)
BASIC_AGENTS=(
    "database-engineer-md.md"
    "documentation-engineer-md.md"
    "performance-engineer-md.md"
    "multimodal-engineer-md.md"
    "project-manager-md.md"
    "project-task-planner.md"
    "prd-writer.md"
    "content-writer.md"
    "senior-backend-engineer.md"
    "systems-architect.md"
    "code-refactorer.md"
    "code-skeptic.md"
    "frontend-designer.md"
)

# Browser automation tools for testing-related agents
BROWSER_TOOLS="mcp__puppeteer__puppeteer_navigate, mcp__puppeteer__puppeteer_screenshot, mcp__puppeteer__puppeteer_click, mcp__puppeteer__puppeteer_fill, mcp__puppeteer__puppeteer_select, mcp__puppeteer__puppeteer_hover, mcp__puppeteer__puppeteer_evaluate, mcp__playwright-advanced__playwright_navigate, mcp__playwright-advanced__playwright_screenshot, mcp__playwright-advanced__playwright_click, mcp__playwright-advanced__playwright_fill, mcp__playwright-advanced__playwright_select, mcp__playwright-advanced__playwright_hover, mcp__playwright-advanced__playwright_upload_file, mcp__playwright-advanced__playwright_evaluate, mcp__playwright-advanced__playwright_console_logs, mcp__playwright-advanced__playwright_close, mcp__playwright-advanced__playwright_get, mcp__playwright-advanced__playwright_post"

# List of agents that need browser automation tools
BROWSER_AGENTS=(
    "testing-engineer-md.md"
)

# Mobile testing tools
MOBILE_TOOLS="mcp__mobile-simulator__mobile_use_default_device, mcp__mobile-simulator__mobile_list_available_devices, mcp__mobile-simulator__mobile_use_device, mcp__mobile-simulator__mobile_list_apps, mcp__mobile-simulator__mobile_launch_app, mcp__mobile-simulator__mobile_terminate_app, mcp__mobile-simulator__mobile_get_screen_size, mcp__mobile-simulator__mobile_click_on_screen_at_coordinates, mcp__mobile-simulator__mobile_long_press_on_screen_at_coordinates, mcp__mobile-simulator__mobile_list_elements_on_screen, mcp__mobile-simulator__mobile_press_button, mcp__mobile-simulator__mobile_open_url, mcp__mobile-simulator__swipe_on_screen, mcp__mobile-simulator__mobile_type_keys, mcp__mobile-simulator__mobile_save_screenshot, mcp__mobile-simulator__mobile_take_screenshot, mcp__mobile-simulator__mobile_set_orientation, mcp__mobile-simulator__mobile_get_orientation"

# Function to update basic agents
update_basic_agent() {
    local agent_file=$1
    echo "Updating basic agent: $agent_file"
    
    # Read current tools line and replace with enhanced version
    if grep -q "tools:" "$agent_file"; then
        # Extract current basic tools and add MCP tools
        current_tools=$(grep "tools:" "$agent_file" | sed 's/tools: //')
        
        # Check if MCP tools already exist
        if [[ ! "$current_tools" == *"mcp__memory"* ]]; then
            new_tools="$current_tools, $MCP_TOOLS"
            sed -i "s|tools: .*|tools: $new_tools|" "$agent_file"
            echo "  - Added MCP tools to $agent_file"
        else
            echo "  - MCP tools already present in $agent_file"
        fi
    fi
}

# Function to update browser agents
update_browser_agent() {
    local agent_file=$1
    echo "Updating browser agent: $agent_file"
    
    if grep -q "tools:" "$agent_file"; then
        current_tools=$(grep "tools:" "$agent_file" | sed 's/tools: //')
        
        if [[ ! "$current_tools" == *"mcp__puppeteer"* ]]; then
            new_tools="$current_tools, $MCP_TOOLS, $BROWSER_TOOLS, $MOBILE_TOOLS"
            sed -i "s|tools: .*|tools: $new_tools|" "$agent_file"
            echo "  - Added MCP, browser, and mobile tools to $agent_file"
        else
            echo "  - Advanced tools already present in $agent_file"
        fi
    fi
}

# Update basic agents
for agent in "${BASIC_AGENTS[@]}"; do
    if [[ -f "$agent" ]]; then
        update_basic_agent "$agent"
    else
        echo "Warning: $agent not found"
    fi
done

# Update browser agents
for agent in "${BROWSER_AGENTS[@]}"; do
    if [[ -f "$agent" ]]; then
        update_browser_agent "$agent"
    else
        echo "Warning: $agent not found"
    fi
done

echo "Agent MCP tools update complete!"
echo ""
echo "Summary of updates:"
echo "- Basic agents: Added memory, filesystem, thinking, task management, context7, and IDE tools"
echo "- Browser agents: Added all basic tools plus browser automation and mobile testing"
echo ""
echo "Next steps:"
echo "1. Add collaboration sections to all agents"
echo "2. Verify tool access is working correctly"
echo "3. Test agent interactions and memory sharing"