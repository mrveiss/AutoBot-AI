window.fileBrowserModal = {
    browser: {
        title: "File Browser",
        currentPath: "",
        entries: [],
        parentPath: "",
        sortBy: "name",
        sortDirection: "asc",
    },
    history: [],
    resolvePromise: null,

    async openModal(path) {
        this.history = [];
        if (path) this.browser.currentPath = path;
        else if (!this.browser.currentPath) this.browser.currentPath = "$WORK_DIR";

        await this.fetchFiles(this.browser.currentPath);

        return new Promise(resolve => {
            this.resolvePromise = resolve;
            this.renderAndOpenModal();
        });
    },

    renderAndOpenModal() {
        const modalContent = this.renderFileBrowserContent();
        window.genericModal.openModal({
            title: this.browser.title,
            content: modalContent,
            buttons: [
                {
                    id: "upload",
                    text: "Upload",
                    classes: "btn btn-upload",
                    onClick: () => document.getElementById('fileUploadInput').click()
                },
                {
                    id: "close",
                    text: "Close",
                    classes: "btn btn-cancel",
                    onClick: () => this.handleClose()
                }
            ],
            onClose: () => this.handleClose()
        });
        this.addEventListeners();
    },

    renderFileBrowserContent() {
        const container = document.createElement('div');
        container.className = 'file-browser-container';

        const pathDisplay = document.createElement('div');
        pathDisplay.className = 'file-browser-path';
        pathDisplay.innerHTML = `Current Path: <span>${this.browser.currentPath}</span>`;
        container.appendChild(pathDisplay);

        const controls = document.createElement('div');
        controls.className = 'file-browser-controls';

        const uploadInput = document.createElement('input');
        uploadInput.type = 'file';
        uploadInput.id = 'fileUploadInput';
        uploadInput.multiple = true;
        uploadInput.style.display = 'none';
        uploadInput.addEventListener('change', (e) => this.handleFileUpload(e));
        controls.appendChild(uploadInput);

        const navButtons = document.createElement('div');
        navButtons.className = 'file-browser-nav-buttons';

        const upButton = document.createElement('button');
        upButton.className = 'btn btn-secondary';
        upButton.textContent = 'Up';
        upButton.onclick = () => this.navigateUp();
        navButtons.appendChild(upButton);

        const backButton = document.createElement('button');
        backButton.className = 'btn btn-secondary';
        backButton.textContent = 'Back';
        backButton.onclick = () => this.navigateBack();
        navButtons.appendChild(backButton);

        controls.appendChild(navButtons);
        container.appendChild(controls);

        const table = document.createElement('table');
        table.className = 'file-browser-table';
        table.innerHTML = `
            <thead>
                <tr>
                    <th data-sort="name">Name</th>
                    <th data-sort="size">Size</th>
                    <th data-sort="date">Modified</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody></tbody>
        `;
        container.appendChild(table);

        this.updateFileEntriesTable(table.querySelector('tbody'));

        return container.innerHTML;
    },

    updateFileEntriesTable(tbody) {
        tbody.innerHTML = '';
        const sortedEntries = this.sortFiles(this.browser.entries);
        sortedEntries.forEach(entry => {
            tbody.appendChild(this.createFileEntryElement(entry));
        });
    },

    addEventListeners() {
        const modalEl = document.getElementById('genericModal');
        if (modalEl) {
            const nameHeader = modalEl.querySelector('th[data-sort="name"]');
            const sizeHeader = modalEl.querySelector('th[data-sort="size"]');
            const dateHeader = modalEl.querySelector('th[data-sort="date"]');

            if (nameHeader) nameHeader.onclick = () => { this.toggleSort('name'); this.renderAndOpenModal(); };
            if (sizeHeader) sizeHeader.onclick = () => { this.toggleSort('size'); this.renderAndOpenModal(); };
            if (dateHeader) dateHeader.onclick = () => { this.toggleSort('date'); this.renderAndOpenModal(); };
        }
    },

    createFileEntryElement(entry) {
        const tr = document.createElement('tr');
        tr.className = entry.is_dir ? 'folder-entry' : 'file-entry';

        const nameTd = document.createElement('td');
        const nameLink = document.createElement('a');
        nameLink.href = '#';
        nameLink.textContent = entry.name;
        nameLink.onclick = (e) => {
            e.preventDefault();
            if (entry.is_dir) {
                this.navigateToFolder(entry.path);
            } else {
                this.downloadFile(entry);
            }
        };
        nameTd.appendChild(nameLink);
        tr.appendChild(nameTd);

        const sizeTd = document.createElement('td');
        sizeTd.textContent = entry.is_dir ? '-' : this.formatFileSize(entry.size);
        tr.appendChild(sizeTd);

        const dateTd = document.createElement('td');
        dateTd.textContent = this.formatDate(entry.modified);
        tr.appendChild(dateTd);

        const actionsTd = document.createElement('td');
        const deleteButton = document.createElement('button');
        deleteButton.className = 'btn btn-danger btn-sm';
        deleteButton.textContent = 'Delete';
        deleteButton.onclick = () => this.deleteFile(entry);
        actionsTd.appendChild(deleteButton);
        tr.appendChild(actionsTd);

        return tr;
    },

    isArchive(filename) {
        const archiveExts = ["zip", "tar", "gz", "rar", "7z"];
        const ext = filename.split(".").pop().toLowerCase();
        return archiveExts.includes(ext);
    },

    async fetchFiles(path = "") {
        // this.isLoading = true; // No longer needed as genericModal handles loading state
        try {
            const response = await fetch(
                `/get_work_dir_files?path=${encodeURIComponent(path)}`
            );

            if (response.ok) {
                const data = await response.json();
                this.browser.entries = data.data.entries;
                this.browser.currentPath = data.data.current_path;
                this.browser.parentPath = data.data.parent_path;
            } else {
                console.error("Error fetching files:", await response.text());
                this.browser.entries = [];
            }
        } catch (error) {
            window.toastFetchError("Error fetching files", error);
            this.browser.entries = [];
        } finally {
            // this.isLoading = false; // No longer needed
        }
    },

    async navigateToFolder(path) {
        if (this.browser.currentPath !== path) {
            this.history.push(this.browser.currentPath);
        }
        await this.fetchFiles(path);
        this.renderAndOpenModal(); // Re-render modal content with new files
    },

    async navigateUp() {
        if (this.browser.parentPath !== "") {
            this.history.push(this.browser.currentPath);
            await this.fetchFiles(this.browser.parentPath);
            this.renderAndOpenModal(); // Re-render modal content
        }
    },

    async navigateBack() {
        if (this.history.length > 0) {
            const previousPath = this.history.pop();
            await this.fetchFiles(previousPath);
            this.renderAndOpenModal(); // Re-render modal content
        }
    },

    sortFiles(entries) {
        return [...entries].sort((a, b) => {
            if (a.is_dir !== b.is_dir) {
                return a.is_dir ? -1 : 1;
            }

            const direction = this.browser.sortDirection === "asc" ? 1 : -1;
            switch (this.browser.sortBy) {
                case "name":
                    return direction * a.name.localeCompare(b.name);
                case "size":
                    return direction * (a.size - b.size);
                case "date":
                    return direction * (new Date(a.modified) - new Date(b.modified));
                default:
                    return 0;
            }
        });
    },

    toggleSort(column) {
        if (this.browser.sortBy === column) {
            this.browser.sortDirection =
                this.browser.sortDirection === "asc" ? "desc" : "asc";
        } else {
            this.browser.sortBy = column;
            this.browser.sortDirection = "asc";
        }
    },

    async deleteFile(file) {
        if (!confirm(`Are you sure you want to delete ${file.name}?`)) {
            return;
        }

        try {
            const response = await fetch("/delete_work_dir_file", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({
                    path: file.path,
                    currentPath: this.browser.currentPath,
                }),
            });

            if (response.ok) {
                const data = await response.json();
                this.browser.entries = this.browser.entries.filter(
                    (entry) => entry.path !== file.path
                );
                alert("File deleted successfully.");
                this.renderAndOpenModal(); // Re-render to reflect deletion
            } else {
                alert(`Error deleting file: ${await response.text()}`);
            }
        } catch (error) {
            window.toastFetchError("Error deleting file", error);
            alert("Error deleting file");
        }
    },

    async handleFileUpload(event) {
        try {
            const files = event.target.files;
            if (!files.length) return;

            const formData = new FormData();
            formData.append("path", this.browser.currentPath);

            for (let i = 0; i < files.length; i++) {
                const ext = files[i].name.split(".").pop().toLowerCase();
                if (!["zip", "tar", "gz", "rar", "7z"].includes(ext)) {
                    if (files[i].size > 100 * 1024 * 1024) {
                        alert(
                            `File ${files[i].name} exceeds the maximum allowed size of 100MB.`
                        );
                        continue;
                    }
                }
                formData.append("files[]", files[i]);
            }

            const response = await fetch("/upload_work_dir_files", {
                method: "POST",
                body: formData,
            });

            if (response.ok) {
                const data = await response.json();
                this.browser.entries = data.data.entries; // Refresh all entries
                this.browser.currentPath = data.data.current_path;
                this.browser.parentPath = data.data.parent_path;

                if (data.failed && data.failed.length > 0) {
                    const failedFiles = data.failed
                        .map((file) => `${file.name}: ${file.error}`)
                        .join("\n");
                    alert(`Some files failed to upload:\n${failedFiles}`);
                }
                this.renderAndOpenModal(); // Re-render to reflect upload
            } else {
                alert(data.message);
            }
        } catch (error) {
            window.toastFetchError("Error uploading files", error);
            alert("Error uploading files");
        }
    },

    async downloadFile(file) {
        try {
            const downloadUrl = `/download_work_dir_file?path=${encodeURIComponent(
                file.path
            )}`;

            const response = await fetch(downloadUrl);

            if (!response.ok) {
                throw new Error("Network response was not ok");
            }

            const blob = await response.blob();

            const link = document.createElement("a");
            link.href = window.URL.createObjectURL(blob);
            link.download = file.name;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            window.URL.revokeObjectURL(link.href);
        } catch (error) {
            window.toastFetchError("Error downloading file", error);
            alert("Error downloading file");
        }
    },

    formatFileSize(size) {
        if (size === 0) return "0 Bytes";
        const k = 1024;
        const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
        const i = Math.floor(Math.log(size) / Math.log(k));
        return parseFloat((size / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
    },

    formatDate(dateString) {
        const options = {
            year: "numeric",
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        };
        return new Date(dateString).toLocaleDateString(undefined, options);
    },

    handleClose() {
        window.genericModal.closeModal();
        if (this.resolvePromise) {
            this.resolvePromise({ status: 'closed' });
            this.resolvePromise = null;
        }
    },
};

window.openFileLink = async function (path) {
    try {
        const resp = await window.sendJsonData("/file_info", { path });
        if (!resp.exists) {
            window.toast("File does not exist.", "error");
            return;
        }

        if (resp.is_dir) {
            window.fileBrowserModal.openModal(resp.abs_path);
        } else {
            window.fileBrowserModal.downloadFile({
                path: resp.abs_path,
                name: resp.file_name,
            });
        }
    } catch (e) {
        window.toastFetchError("Error opening file", e);
    }
};
