# Quick Start: Uploading Knowledge and Asking Questions

This guide takes about five minutes. By the end, you will have uploaded a
document to AutoBot's knowledge base and asked a question that uses it.

## What is the Knowledge Base?

The knowledge base is where AutoBot stores documents, notes, and other
information. When you ask a question in the chat, AutoBot can search the
knowledge base to give you an informed answer -- even if the information is not
something the AI model was originally trained on.

## Step 1 -- Open the Knowledge Base

1. Click **Knowledge Base** in the navigation bar (or go to `/knowledge`).
2. The Knowledge Base view opens with a sidebar on the left showing sections:
   **Search**, **Research**, **Categories**, **Knowledge Graph**, **Manage**,
   **Verification**, **Connectors**, **Statistics**, and **Maintenance**.

<!-- Screenshot: Knowledge Base main view with sidebar -->

## Step 2 -- Upload a Document

1. In the sidebar, click **Manage** (under the "Manage" heading).
2. On the Manage Knowledge page, look for the **Upload** or **Add Entry**
   button.
3. Click it and select a file from your computer. Supported formats typically
   include PDF, TXT, Markdown, and common document types.
4. Fill in any optional fields such as a title, category, or tags to help you
   find the document later.
5. Click **Save** or **Upload** to add the document.

<!-- Screenshot: Knowledge upload form -->

AutoBot will process the document in the background. Processing usually takes
a few seconds for small files and up to a minute for larger ones.

## Step 3 -- Search Your Knowledge

1. In the sidebar, click **Search**.
2. Type a keyword or question related to your uploaded document. For example,
   if you uploaded a company policy document, try "What is the vacation
   policy?"
3. Press **Enter** or click the search button.
4. Results will appear, showing relevant passages from your documents.

<!-- Screenshot: Knowledge search results -->

## Step 4 -- Ask AutoBot About Your Knowledge

1. Go back to the **AI Assistant** (`/chat`).
2. Type a question that relates to the document you just uploaded. For
   example:

   ```
   Based on my uploaded documents, what are the key budget figures for Q3?
   ```

3. AutoBot will search the knowledge base automatically and include relevant
   information in its response. You may see **citations** indicating which
   document the information came from.

## Step 5 -- Browse by Category

1. In the Knowledge Base sidebar, click **Categories**.
2. Documents are organized by category. Click a category to see all documents
   within it.
3. Click any document to read its content or edit its metadata.

## Tips

- **Tags and categories** make it easier to find documents later. Take a
  moment to add them when uploading.
- **Verification queue** (`/knowledge/health?tab=verification`) lets you review and
  confirm the accuracy of imported content before it is used in answers.
- **Connectors** (`/knowledge/connectors`) allow you to import data from
  external sources automatically.
- The **Knowledge Graph** (`/knowledge/graph`) provides a visual map of how
  your documents and topics relate to each other.

## Next Steps

- [Knowledge Management Guide](guides/knowledge-management.md) -- full guide
  to all knowledge features.
- [Chat Interface Guide](guides/chat-interface.md) -- learn how to get the
  most out of conversations.
