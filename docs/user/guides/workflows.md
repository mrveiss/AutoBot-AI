# Workflows Guide

Workflows let you automate sequences of tasks so they run without manual
intervention. This guide explains how to create, run, and monitor workflows
in AutoBot.

## What is a Workflow?

A workflow is a series of steps that AutoBot performs in order. Each step can
be an AI task, a data operation, a notification, or any other action. For
example, a workflow might:

1. Check a website for new data every hour.
2. Summarize the new data using AI.
3. Save the summary to the knowledge base.
4. Send a notification that the summary is ready.

Once you set up a workflow, it runs automatically on the schedule you define.

## Accessing Workflows

Click **Workflow Automation** in the navigation bar, or navigate to
`/automation`. The sidebar on the left provides access to:

- **Overview** -- a dashboard showing all your workflows and their statuses.
- **Visual Builder** -- a drag-and-drop editor for creating workflows.
- **Templates** -- pre-built workflow patterns you can start from.
- **Browser Automation** -- control browser workers for web-based tasks.

<!-- Screenshot: Workflow Automation view with sidebar -->

## Creating a Workflow

### Using a Template

1. Click **Templates** in the sidebar.
2. Browse the available templates. Each one shows a description and the
   steps it includes.
3. Click a template to preview it.
4. Click **Use Template** (or similar) to create a new workflow based on it.
5. Customize the steps to match your needs, then save.

### Using the Visual Builder

1. Click **Visual Builder** in the sidebar.
2. The canvas opens with a blank workspace.
3. **Add a step:** Drag a block from the palette on the side, or click the
   **Add Step** button.
4. **Configure each step:** Click a block on the canvas to open its settings.
   Fill in the required fields (for example, the URL for a web request, or the
   prompt for an AI task).
5. **Connect steps:** Drag a line from one block's output to another block's
   input to define the order.
6. **Save:** Click **Save** to store the workflow.

<!-- Screenshot: Visual Builder canvas with connected blocks -->

### Step Types

Common step types include:

| Step Type | Description |
|-----------|-------------|
| AI Task | Send a prompt to an AI agent and use its response |
| Web Request | Fetch data from a URL |
| Knowledge Query | Search or update the knowledge base |
| Notification | Send an alert via email, webhook, or in-app message |
| Condition | Branch the workflow based on a yes/no check |
| Delay | Wait for a specified time before continuing |

## Running a Workflow

1. Open the workflow you want to run from the **Overview** page.
2. Click **Run** (or **Execute**) to start it immediately.
3. The workflow status will change to **Running**.
4. Each step shows its status as it completes: **Pending**, **Running**,
   **Completed**, or **Failed**.

### Scheduling a Workflow

To run a workflow on a recurring schedule:

1. Open the workflow's settings.
2. Look for the **Schedule** section.
3. Choose the frequency (for example, every hour, daily, or weekly).
4. Save. The workflow will run automatically at the times you configured.

## Monitoring Workflows

The **Overview** page shows all workflows and their current status:

| Status | Meaning |
|--------|---------|
| Idle | Not currently running |
| Running | Executing steps right now |
| Completed | Finished successfully |
| Failed | One or more steps encountered an error |

Click a workflow to see detailed logs for each step, including input, output,
and any error messages.

<!-- Screenshot: Workflow overview with status indicators -->

## Browser Automation

AutoBot can control a web browser to automate tasks on websites. Access this
feature at `/automation/browser-automation`.

1. Open **Browser Automation** in the sidebar.
2. Configure a browser session: provide the target URL and any login
   credentials if needed.
3. Define actions such as clicking buttons, filling forms, or extracting data.
4. Run the session. AutoBot will execute the actions in a real browser and
   return the results.

<!-- Screenshot: Browser Automation session view -->

## Approval Gates

Some workflows include an **approval gate** -- a step that pauses the workflow
and asks you (or another user) to approve before continuing. When a workflow
reaches an approval gate:

1. You receive a notification.
2. Open the workflow to review what has happened so far.
3. Click **Approve** to continue or **Reject** to stop the workflow.

## Tips

- Start with a template and modify it rather than building from scratch.
- Use the **Condition** step to handle different outcomes (for example, only
  send a notification if new data was found).
- Check the Overview page regularly to catch failed workflows early.
- Use descriptive names for your workflows so they are easy to find later.

## Related Guides

- [Working with Agents](working-with-agents.md) -- agents power many workflow
  steps
- [Knowledge Management](knowledge-management.md) -- workflows can read from
  and write to the knowledge base
- [Chat Interface](chat-interface.md) -- you can trigger workflows from the
  chat
