window.fullScreenInputModal = {
    inputText: '',
    wordWrap: true,
    undoStack: [],
    redoStack: [],
    maxStackSize: 100,
    lastSavedState: '',
    resolvePromise: null,

    async openModal() {
        const chatInput = document.getElementById('chat-input');
        this.inputText = chatInput.value;
        this.lastSavedState = this.inputText;
        this.undoStack = [];
        this.redoStack = [];

        const modalContent = this.renderModalContent();

        return new Promise(resolve => {
            this.resolvePromise = resolve;
            window.genericModal.openModal({
                title: "Full Screen Input",
                content: modalContent,
                buttons: [
                    {
                        id: "save",
                        text: "Save",
                        classes: "btn btn-ok",
                        onClick: () => this.handleSave()
                    },
                    {
                        id: "cancel",
                        text: "Cancel",
                        classes: "btn btn-cancel",
                        onClick: () => this.handleCancel()
                    }
                ],
                onClose: () => this.handleCancel()
            });
            this.addEventListeners();
        });
    },

    renderModalContent() {
        const container = document.createElement('div');
        container.className = 'full-screen-input-container';

        const textarea = document.createElement('textarea');
        textarea.id = 'full-screen-input';
        textarea.className = 'full-screen-textarea';
        textarea.value = this.inputText;
        textarea.style.whiteSpace = this.wordWrap ? 'pre-wrap' : 'pre';
        textarea.addEventListener('input', (e) => {
            this.inputText = e.target.value;
            this.updateHistory();
        });
        container.appendChild(textarea);

        const controls = document.createElement('div');
        controls.className = 'full-screen-controls';

        const undoButton = document.createElement('button');
        undoButton.className = 'btn btn-secondary';
        undoButton.textContent = 'Undo';
        undoButton.onclick = () => this.undo();
        controls.appendChild(undoButton);

        const redoButton = document.createElement('button');
        redoButton.className = 'btn btn-secondary';
        redoButton.textContent = 'Redo';
        redoButton.onclick = () => this.redo();
        controls.appendChild(redoButton);

        const clearButton = document.createElement('button');
        clearButton.className = 'btn btn-secondary';
        clearButton.textContent = 'Clear';
        clearButton.onclick = () => this.clearText();
        controls.appendChild(clearButton);

        const wrapButton = document.createElement('button');
        wrapButton.className = 'btn btn-secondary';
        wrapButton.textContent = `Word Wrap: ${this.wordWrap ? 'On' : 'Off'}`;
        wrapButton.onclick = () => this.toggleWrap();
        controls.appendChild(wrapButton);

        container.appendChild(controls);
        return container.innerHTML;
    },

    addEventListeners() {
        setTimeout(() => {
            const fullScreenInput = document.getElementById('full-screen-input');
            if (fullScreenInput) {
                fullScreenInput.focus();
                fullScreenInput.setSelectionRange(this.inputText.length, this.inputText.length);
            }
        }, 100);
    },

    updateHistory() {
        if (this.lastSavedState === this.inputText) return;

        this.undoStack.push(this.lastSavedState);
        if (this.undoStack.length > this.maxStackSize) {
            this.undoStack.shift();
        }
        this.redoStack = [];
        this.lastSavedState = this.inputText;
        this.updateControlStates();
    },

    undo() {
        if (!this.canUndo) return;

        this.redoStack.push(this.inputText);
        this.inputText = this.undoStack.pop();
        this.lastSavedState = this.inputText;
        document.getElementById('full-screen-input').value = this.inputText;
        this.updateControlStates();
    },

    redo() {
        if (!this.canRedo) return;

        this.undoStack.push(this.inputText);
        this.inputText = this.redoStack.pop();
        this.lastSavedState = this.inputText;
        document.getElementById('full-screen-input').value = this.inputText;
        this.updateControlStates();
    },

    clearText() {
        if (this.inputText) {
            this.updateHistory();
            this.inputText = '';
            this.lastSavedState = '';
            document.getElementById('full-screen-input').value = this.inputText;
            this.updateControlStates();
        }
    },

    toggleWrap() {
        this.wordWrap = !this.wordWrap;
        const textarea = document.getElementById('full-screen-input');
        if (textarea) {
            textarea.style.whiteSpace = this.wordWrap ? 'pre-wrap' : 'pre';
        }
        this.updateControlStates();
    },

    updateControlStates() {
        const modalEl = document.getElementById('genericModal');
        if (modalEl) {
            const undoButton = modalEl.querySelector('.full-screen-controls button:nth-child(1)');
            const redoButton = modalEl.querySelector('.full-screen-controls button:nth-child(2)');
            const wrapButton = modalEl.querySelector('.full-screen-controls button:nth-child(4)');

            if (undoButton) undoButton.disabled = !this.canUndo;
            if (redoButton) redoButton.disabled = !this.canRedo;
            if (wrapButton) wrapButton.textContent = `Word Wrap: ${this.wordWrap ? 'On' : 'Off'}`;
        }
    },

    get canUndo() {
        return this.undoStack.length > 0;
    },

    get canRedo() {
        return this.redoStack.length > 0;
    },

    handleSave() {
        const chatInput = document.getElementById('chat-input');
        chatInput.value = this.inputText;
        chatInput.dispatchEvent(new Event('input'));
        window.genericModal.closeModal();
        if (this.resolvePromise) {
            this.resolvePromise({ status: 'saved', data: this.inputText });
            this.resolvePromise = null;
        }
    },

    handleCancel() {
        window.genericModal.closeModal();
        if (this.resolvePromise) {
            this.resolvePromise({ status: 'cancelled', data: null });
            this.resolvePromise = null;
        }
    }
};

window.genericModal = {
    modalElement: null,
    titleElement: null,
    contentElement: null,
    buttonsContainer: null,
    closeButton: null,
    onCloseCallback: null,

    init() {
        this.modalElement = document.getElementById('genericModal');
        this.titleElement = this.modalElement.querySelector('.modal-title');
        this.contentElement = this.modalElement.querySelector('.modal-content-viewer');
        this.buttonsContainer = this.modalElement.querySelector('.modal-buttons');
        this.closeButton = this.modalElement.querySelector('.modal-close-button');

        if (this.closeButton) {
            this.closeButton.onclick = () => this.closeModal();
        }
    },

    openModal({ title, content, buttons = [], onClose = null, contentClasses = [] }) {
        if (!this.modalElement) this.init();

        this.titleElement.textContent = title;
        this.contentElement.innerHTML = ''; // Clear previous content
        if (typeof content === 'string') {
            this.contentElement.innerHTML = content;
        } else if (content instanceof HTMLElement) {
            this.contentElement.appendChild(content);
        }

        this.contentElement.className = 'modal-content-viewer'; // Reset classes
        this.contentElement.classList.add(...contentClasses);

        this.buttonsContainer.innerHTML = ''; // Clear previous buttons
        buttons.forEach(buttonConfig => {
            const button = document.createElement('button');
            button.id = buttonConfig.id;
            button.textContent = buttonConfig.text;
            button.className = buttonConfig.classes || 'btn';
            button.onclick = buttonConfig.onClick;
            this.buttonsContainer.appendChild(button);
        });

        this.onCloseCallback = onClose;
        this.modalElement.classList.add('open');
    },

    closeModal() {
        if (!this.modalElement) return;
        this.modalElement.classList.remove('open');
        if (this.onCloseCallback) {
            this.onCloseCallback();
            this.onCloseCallback = null;
        }
    }
};

// Initialize the genericModal when the DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.genericModal.init();
});
