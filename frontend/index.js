// frontend/index.js
import { openHistoryModal, openCtxWindowModal } from "./js/history.js";

// Define and assign missing functions to the window object
window.settingsModal = window.settingsModal || function () {
    alert('Settings modal functionality is not implemented yet.');
};

window.restart = window.restart || async function () {
    alert('Restart functionality is not implemented yet.');
};

window.loadChats = window.loadChats || async function () {
    alert('Load chats functionality is not implemented yet.');
};

window.saveChat = window.saveChat || async function () {
    alert('Save chat functionality is not implemented yet.');
};

window.newChat = window.newChat || async function () {
    alert('New chat functionality is not implemented yet.');
};

window.resetChat = window.resetChat || async function () {
    alert('Reset chat functionality is not implemented yet.');
};

window.loadKnowledge = window.loadKnowledge || async function () {
    alert('Load knowledge functionality is not implemented yet.');
};

window.openFiles = window.openFiles || async function () {
    alert('Open files functionality is not implemented yet.');
};

window.nudge = window.nudge || function () {
    alert('Nudge functionality is not implemented yet.');
};

window.toastFetchError = window.toastFetchError || function (message, error) {
    console.error(message, error);
    alert(`${message}: ${error.message || error}`);
};

window.sendJsonData = window.sendJsonData || async function (url, data) {
    try {
        const options = {
            headers: {
                'Content-Type': 'application/json',
            },
        };

        if (data === null || data === undefined) {
            options.method = 'GET';
        } else {
            options.method = 'POST';
            options.body = JSON.stringify(data);
        }

        const response = await fetch(url, options);
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP error! status: ${response.status}, message: ${errorText}`);
        }
        return response.json();
    } catch (error) {
        console.error('Error sending JSON data:', error);
        throw error;
    }
};

// Update openCtxWindowModal to handle 404 errors gracefully
window.openCtxWindowModal = async () => {
    try {
        const contextData = await fetch('/api/context');
        if (!contextData.ok) {
            throw new Error(`HTTP error! status: ${contextData.status}`);
        }
        const contextJson = await contextData.json();
        console.log('Context data loaded:', contextJson);

        if (window.genericModal) {
            window.genericModal.openModal({
                title: 'Context Window',
                content: JSON.stringify(contextJson, null, 2),
                isJson: true
            });
        } else {
            console.warn('No modal implementation found for displaying context.');
        }
    } catch (error) {
        console.error('Error loading context window modal:', error);
        alert('Failed to load context window. Please try again later.');
    }
};

// Define and export getContext
export function getContext() {
    return "No context available.";
}
