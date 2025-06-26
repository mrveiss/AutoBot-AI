import { getContext } from "../index.js";

async function renderEditorModalContent(data, type = "json") {
    const container = document.createElement('div');
    container.id = 'json-viewer-container';
    container.style.width = '100%';
    container.style.height = '100%';
    container.style.minHeight = '400px'; // Ensure it has a height for Ace Editor

    // Ace Editor initialization needs to happen after the element is in the DOM
    setTimeout(() => {
        const editor = ace.edit("json-viewer-container");
        const dark = localStorage.getItem('darkMode');
        if (dark !== "false") {
            editor.setTheme("ace/theme/github_dark");
        } else {
            editor.setTheme("ace/theme/tomorrow");
        }
        editor.session.setMode("ace/mode/" + type);
        editor.setValue(data);
        editor.clearSelection();
        editor.setReadOnly(true);
    }, 0);

    return container;
}

export async function openHistoryModal() {
    try {
        const hist = await window.sendJsonData("/api/chat/history", null);
        const data = hist.history;
        const size = hist.tokens;
        const title = `History ~${size} tokens`;
        const description = "Conversation history visible to the LLM. History is compressed to fit into the context window over time.";
        const content = await renderEditorModalContent(data, "markdown");

        window.genericModal.openModal({
            title: title,
            content: content,
            buttons: [{
                id: "close",
                text: "Close",
                classes: "btn btn-cancel",
                onClick: () => window.genericModal.closeModal()
            }],
            contentClasses: ["history-viewer"]
        });

    } catch (e) {
        window.toastFetchError("Error fetching history", e);
    }
}

export async function openCtxWindowModal() {
    try {
        const win = await window.sendJsonData("/ctx_window_get", { context: getContext() });
        const data = win.content;
        const size = win.tokens;
        const title = `Context window ~${size} tokens`;
        const description = "Data passed to the LLM during last interaction. Contains system message, conversation history and RAG.";
        const content = await renderEditorModalContent(data, "markdown");

        window.genericModal.openModal({
            title: title,
            content: content,
            buttons: [{
                id: "close",
                text: "Close",
                classes: "btn btn-cancel",
                onClick: () => window.genericModal.closeModal()
            }],
            contentClasses: ["history-viewer"]
        });

    } catch (e) {
        window.toastFetchError("Error fetching context", e);
    }
}

window.openHistoryModal = openHistoryModal;
window.openCtxWindowModal = openCtxWindowModal;
