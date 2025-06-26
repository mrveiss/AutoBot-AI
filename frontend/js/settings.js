window.settingsModal = {
    settingsData: {},
    resolvePromise: null,

    async openModal() {
        try {
            const rawSettings = await sendJsonData("/api/settings", null);
            this.settingsData = this.transformSettingsToSections(rawSettings);

            const modalContent = this.renderSettingsContent(this.settingsData);

            return new Promise(resolve => {
                this.resolvePromise = resolve;
                window.genericModal.openModal({
                    title: this.settingsData.title,
                    content: modalContent,
                    buttons: this.settingsData.buttons.map(button => ({
                        id: button.id,
                        text: button.title,
                        classes: button.classes,
                        onClick: () => this.handleButton(button.id)
                    })),
                    onClose: () => this.handleCancel()
                });
            });

        } catch (e) {
            window.toastFetchError("Error getting settings", e);
            return Promise.resolve({ status: 'error', data: null });
        }
    },

    transformSettingsToSections(rawSettings) {
        const sections = [];
        const generalFields = [];

        const llmConfigSection = {
            'id': 'llm_config',
            'title': 'LLM Configuration',
            'description': 'Settings for Language Model interactions.',
            'fields': [],
            'sub_sections': []
        };

        for (const key in rawSettings) {
            if (key === 'llm_config') {
                const llmRaw = rawSettings[key];

                // Orchestrator LLM Section
                const orchestratorFields = [];
                orchestratorFields.push({
                    'id': 'llm_config.default_llm',
                    'title': 'Orchestrator Model',
                    'value': llmRaw.default_llm,
                    'type': 'text',
                    'classes': '', 'readonly': false, 'description': 'The LLM used for orchestration tasks.'
                });
                for (const fieldKey in llmRaw.orchestrator_llm_settings) {
                    let fieldType = 'text';
                    if (typeof llmRaw.orchestrator_llm_settings[fieldKey] === 'boolean') fieldType = 'switch';
                    else if (typeof llmRaw.orchestrator_llm_settings[fieldKey] === 'number') fieldType = 'number';
                    orchestratorFields.push({
                        'id': `llm_config.orchestrator_llm_settings.${fieldKey}`,
                        'title': fieldKey.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' '),
                        'value': llmRaw.orchestrator_llm_settings[fieldKey],
                        'type': fieldType,
                        'classes': '', 'readonly': false, 'description': ''
                    });
                }
                llmConfigSection.sub_sections.push({
                    'id': 'llm_config_orchestrator',
                    'title': 'Orchestrator LLM',
                    'description': 'Settings for the Orchestrator LLM.',
                    'fields': orchestratorFields,
                });

                // Task LLM Section
                const taskFields = [];
                taskFields.push({
                    'id': 'llm_config.task_llm',
                    'title': 'Task Model',
                    'value': llmRaw.task_llm,
                    'type': 'text',
                    'classes': '', 'readonly': false, 'description': 'The LLM used for specific task execution.'
                });
                for (const fieldKey in llmRaw.task_llm_settings) {
                    let fieldType = 'text';
                    if (typeof llmRaw.task_llm_settings[fieldKey] === 'boolean') fieldType = 'switch';
                    else if (typeof llmRaw.task_llm_settings[fieldKey] === 'number') fieldType = 'number';
                    taskFields.push({
                        'id': `llm_config.task_llm_settings.${fieldKey}`,
                        'title': fieldKey.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' '),
                        'value': llmRaw.task_llm_settings[fieldKey],
                        'type': fieldType,
                        'classes': '', 'readonly': false, 'description': ''
                    });
                }
                llmConfigSection.sub_sections.push({
                    'id': 'llm_config_task',
                    'title': 'Task LLM',
                    'description': 'Settings for the Task LLM.',
                    'fields': taskFields,
                });

                // LLM Provider Settings (Ollama, OpenAI, Transformers)
                const llmProviders = ['ollama', 'openai', 'transformers'];
                llmProviders.forEach(providerKey => {
                    if (llmRaw[providerKey]) {
                        const providerFields = [];
                        for (const fieldKey in llmRaw[providerKey]) {
                            let fieldType = 'text';
                            if (typeof llmRaw[providerKey][fieldKey] === 'boolean') fieldType = 'switch';
                            else if (typeof llmRaw[providerKey][fieldKey] === 'number') fieldType = 'number';
                            else if (typeof llmRaw[providerKey][fieldKey] === 'string' && (fieldKey.includes('api_key') || fieldKey.includes('password'))) fieldType = 'password';

                            let fieldValue = llmRaw[providerKey][fieldKey];
                            if (typeof llmRaw[providerKey][fieldKey] === 'object' && llmRaw[providerKey][fieldKey] !== null) {
                                fieldValue = JSON.stringify(llmRaw[providerKey][fieldKey]);
                            }

                            providerFields.push({
                                'id': `llm_config.${providerKey}.${fieldKey}`,
                                'title': fieldKey.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' '),
                                'value': fieldValue,
                                'type': fieldType,
                                'classes': '', 'readonly': false, 'description': ''
                            });
                        }
                        llmConfigSection.sub_sections.push({
                            'id': `llm_config_${providerKey}`,
                            'title': providerKey.charAt(0).toUpperCase() + providerKey.slice(1) + ' Settings',
                            'description': `Configuration for the ${providerKey} LLM provider.`,
                            'fields': providerFields,
                        });
                    }
                });

                sections.push(llmConfigSection);

            } else if (typeof rawSettings[key] === 'object' && rawSettings[key] !== null && !Array.isArray(rawSettings[key])) {
                const categoryFields = [];
                for (const fieldKey in rawSettings[key]) {
                    let fieldType = 'text';
                    if (typeof rawSettings[key][fieldKey] === 'boolean') fieldType = 'switch';
                    else if (typeof rawSettings[key][fieldKey] === 'number') fieldType = 'number';
                    else if (typeof rawSettings[key][fieldKey] === 'string' && (fieldKey.includes('password') || fieldKey.includes('api_key'))) fieldType = 'password';

                    let categoryFieldValue = rawSettings[key][fieldKey];
                    if (typeof rawSettings[key][fieldKey] === 'object' && rawSettings[key][fieldKey] !== null) {
                        categoryFieldValue = JSON.stringify(rawSettings[key][fieldKey]);
                    }

                    categoryFields.push({
                        'id': `${key}.${fieldKey}`,
                        'title': fieldKey.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' '),
                        'value': categoryFieldValue,
                        'type': fieldType,
                        'classes': '',
                        'readonly': false,
                        'description': '',
                    });
                }
                sections.push({
                    'id': key,
                    'title': key.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' '),
                    'description': '',
                    'fields': categoryFields,
                });
            } else {
                let fieldType = 'text';
                if (typeof rawSettings[key] === 'boolean') fieldType = 'switch';
                else if (typeof rawSettings[key] === 'number') fieldType = 'number';
                else if (typeof rawSettings[key] === 'string' && (key.includes('password') || key.includes('api_key'))) fieldType = 'password';

                let fieldValue = rawSettings[key];
                if (Array.isArray(rawSettings[key])) {
                    fieldValue = JSON.stringify(rawSettings[key]);
                }

                generalFields.push({
                    'id': key,
                    'title': key.split('_').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' '),
                    'value': fieldValue,
                    'type': fieldType,
                    'classes': '',
                    'readonly': false,
                    'description': '',
                });
            }
        }

        if (generalFields.length > 0) {
            sections.unshift({
                'id': 'general',
                'title': 'General',
                'description': 'General application settings.',
                'fields': generalFields,
            });
        }

        return {
            "title": "Settings",
            "buttons": [
                {
                    "id": "save",
                    "title": "Save",
                    "classes": "btn btn-ok"
                },
                {
                    "id": "cancel",
                    "title": "Cancel",
                    "type": "secondary",
                    "classes": "btn btn-cancel"
                }
            ],
            "sections": sections
        };
    },

    renderSettingsContent(settings) {
        const container = document.createElement('div');
        container.className = 'settings-container';

        settings.sections.forEach(section => {
            const sectionDiv = document.createElement('div');
            sectionDiv.className = 'settings-section';
            sectionDiv.innerHTML = `<h3>${section.title}</h3><p>${section.description}</p>`;

            const fieldsDiv = document.createElement('div');
            fieldsDiv.className = 'settings-fields';

            section.fields.forEach(field => {
                fieldsDiv.appendChild(this.createFieldElement(field));
            });

            section.sub_sections?.forEach(subSection => {
                const subSectionDiv = document.createElement('div');
                subSectionDiv.className = 'settings-sub-section';
                subSectionDiv.innerHTML = `<h4>${subSection.title}</h4><p>${subSection.description}</p>`;

                const subFieldsDiv = document.createElement('div');
                subFieldsDiv.className = 'settings-fields';
                subSection.fields.forEach(field => {
                    subFieldsDiv.appendChild(this.createFieldElement(field));
                });
                subSectionDiv.appendChild(subFieldsDiv);
                fieldsDiv.appendChild(subSectionDiv);
            });

            sectionDiv.appendChild(fieldsDiv);
            container.appendChild(sectionDiv);
        });

        return container.innerHTML;
    },

    createFieldElement(field) {
        const fieldDiv = document.createElement('div');
        fieldDiv.className = 'settings-field';
        fieldDiv.dataset.fieldId = field.id;

        const label = document.createElement('label');
        label.htmlFor = field.id;
        label.textContent = field.title;
        fieldDiv.appendChild(label);

        let inputElement;
        switch (field.type) {
            case 'text':
            case 'number':
            case 'password':
                inputElement = document.createElement('input');
                inputElement.type = field.type;
                inputElement.id = field.id;
                inputElement.value = field.value;
                inputElement.readOnly = field.readonly;
                inputElement.className = field.classes;
                inputElement.addEventListener('input', (e) => this.updateFieldValue(field.id, e.target.value));
                break;
            case 'switch':
                inputElement = document.createElement('input');
                inputElement.type = 'checkbox';
                inputElement.id = field.id;
                inputElement.checked = field.value;
                inputElement.readOnly = field.readonly;
                inputElement.className = field.classes;
                inputElement.addEventListener('change', (e) => this.updateFieldValue(field.id, e.target.checked));
                break;
            default:
                inputElement = document.createElement('span');
                inputElement.textContent = field.value;
                break;
        }
        fieldDiv.appendChild(inputElement);

        if (field.description) {
            const description = document.createElement('p');
            description.className = 'field-description';
            description.textContent = field.description;
            fieldDiv.appendChild(description);
        }

        return fieldDiv;
    },

    updateFieldValue(fieldId, value) {
        const parts = fieldId.split('.');
        let currentLevel = this.settingsData;
        for (let i = 0; i < parts.length; i++) {
            if (i === parts.length - 1) {
                // Handle type conversion for numbers and booleans
                if (typeof currentLevel[parts[i]] === 'number') {
                    currentLevel[parts[i]] = parseFloat(value);
                } else if (typeof currentLevel[parts[i]] === 'boolean') {
                    currentLevel[parts[i]] = value; // value is already boolean from checkbox
                } else {
                    currentLevel[parts[i]] = value;
                }
            } else {
                if (!currentLevel[parts[i]]) {
                    currentLevel[parts[i]] = {};
                }
                currentLevel = currentLevel[parts[i]];
            }
        }
    },

    async handleButton(buttonId) {
        if (buttonId === 'save') {
            try {
                // The settingsData object is already updated by updateFieldValue
                const settingsToSave = this.extractSettingsToSave(this.settingsData);
                const resp = await window.sendJsonData("/api/settings", settingsToSave);
                document.dispatchEvent(new CustomEvent('settings-updated', { detail: resp.settings }));
                this.resolvePromise({
                    status: 'saved',
                    data: resp.settings
                });
            } catch (e) {
                window.toastFetchError("Error saving settings", e);
                this.resolvePromise({ status: 'error', data: null });
            }
        } else if (buttonId === 'cancel') {
            this.handleCancel();
        }
        window.genericModal.closeModal();
    },

    extractSettingsToSave(settings) {
        const settingsToSave = {};

        settings.sections.forEach(section => {
            if (section.id === 'general') {
                section.fields.forEach(field => {
                    // Use the value from the settingsData object, which is kept updated
                    settingsToSave[field.id] = this.getNestedValue(settings, field.id);
                });
            } else if (section.id === 'llm_config') {
                settingsToSave.llm_config = {};
                // Process fields directly under llm_config (like default_llm, task_llm)
                section.fields.forEach(field => {
                    const parts = field.id.split('.');
                    if (parts.length === 2 && parts[0] === 'llm_config') {
                        settingsToSave.llm_config[parts[1]] = this.getNestedValue(settings, field.id);
                    }
                });

                // Process sub_sections (orchestrator_llm_settings, task_llm_settings, providers)
                section.sub_sections.forEach(subSection => {
                    subSection.fields.forEach(field => {
                        const parts = field.id.split('.');
                        let currentLevel = settingsToSave;
                        for (let i = 0; i < parts.length; i++) {
                            if (i === parts.length - 1) {
                                currentLevel[parts[i]] = this.getNestedValue(settings, field.id);
                            } else {
                                if (!currentLevel[parts[i]]) {
                                    currentLevel[parts[i]] = {};
                                }
                                currentLevel = currentLevel[parts[i]];
                            }
                        }
                    });
                });
            } else {
                settingsToSave[section.id] = {};
                section.fields.forEach(field => {
                    const key = field.id.split('.')[1];
                    settingsToSave[section.id][key] = this.getNestedValue(settings, field.id);
                });
            }
        });
        return settingsToSave;
    },

    getNestedValue(obj, path) {
        const parts = path.split('.');
        let current = obj;
        for (let i = 0; i < parts.length; i++) {
            if (current === undefined || current === null) {
                return undefined;
            }
            current = current[parts[i]];
        }
        return current;
    },

    handleCancel() {
        this.resolvePromise({
            status: 'cancelled',
            data: null
        });
        window.genericModal.closeModal();
    },

    handleFieldButton(field) {
        console.log(`Button clicked: ${field.action}`);
    }
};
