# AutoBot Project Map

This document provides a comprehensive overview of the AutoBot project's structure, detailing the purpose of each file and folder within the repository. It aims to facilitate navigation and understanding of the codebase for developers and contributors.

## Project Overview

AutoBot is an AI-driven application designed to automate tasks and provide intelligent responses through a web interface. It leverages machine learning models for natural language processing, a knowledge base for information retrieval, and a modular architecture for extensibility. The project is structured into backend and frontend components, with supporting scripts and configuration files.

## Root Directory Structure

- **.gitignore**: Specifies intentionally untracked files to ignore by Git, such as temporary files, virtual environments, and build artifacts.
- **check_ollama.py**: A utility script to check the availability and configuration of Ollama, a library for running large language models locally.
- **fix_static_paths.sh**: A shell script to fix or adjust paths for static files, likely used during deployment or build processes.
- **gui_design_prompt.txt**: Contains design prompts or guidelines for the graphical user interface, used for planning or generating UI components.
- **main.py**: The primary entry point for the AutoBot application, likely orchestrating the initialization of various components.
- **pyvenv.cfg**: Configuration file for the Python virtual environment, specifying settings like Python version and paths.
- **README.md**: The project's main documentation file, providing an overview, installation instructions, and usage guidelines.
- **requirements.txt**: Lists Python dependencies required for the project, used by `pip` to install necessary packages.
- **run_agent.sh**: A shell script to run the AutoBot application, starting both backend and frontend servers, and now including Redis startup if installed.
- **run_autobot.sh**: Another script to launch the AutoBot application, possibly with different configurations or for specific environments.
- **run_with_openvino.sh**: A script to run AutoBot with OpenVINO, an optimization toolkit for AI inference, likely for performance enhancement.
- **serve_previous_ui.sh**: A script to serve a previous version of the UI, useful for testing or rollback purposes.
- **setup_agent.sh**: A setup script to initialize the AutoBot environment, installing dependencies like Python, Node.js, Redis, and setting up virtual environments.
- **start_autobot.sh**: A script to start the AutoBot application, potentially a simplified or alternative launcher.
- **todo.md**: A markdown file listing tasks or features to be implemented, serving as a project roadmap or task tracker.

## Subdirectories

### autobot-vue/
This directory contains the frontend application built with Vue.js, a progressive JavaScript framework for building user interfaces.

- **.editorconfig**: Configuration for editor settings to maintain consistent coding styles across different editors.
- **.gitattributes**: Specifies attributes for Git, such as handling line endings or merge strategies for specific files.
- **.gitignore**: Ignores specific frontend-related files and directories from version control.
- **.prettierrc.json**: Configuration for Prettier, a code formatter, to enforce consistent code style in the frontend codebase.
- **cypress.config.ts**: Configuration for Cypress, an end-to-end testing framework for web applications.
- **env.d.ts**: TypeScript declaration file for environment variables used in the Vue application.
- **eslint.config.ts**: Configuration for ESLint, a static code analysis tool for identifying problematic patterns in JavaScript/TypeScript code.
- **fix_github_url.sh**: A script to fix or update GitHub URLs, possibly related to repository links or dependencies.
- **index.html**: The main HTML file for the Vue application, serving as the entry point for the frontend.
- **package-lock.json**: Locks the versions of npm dependencies to ensure consistent installations across environments.
- **package.json**: Defines the project's metadata, scripts, and dependencies for the Vue frontend.
- **README.md**: Documentation specific to the Vue frontend component of AutoBot.
- **tsconfig.app.json**, **tsconfig.json**, **tsconfig.node.json**, **tsconfig.vitest.json**: TypeScript configuration files for different parts of the project (app, general, node, and testing with Vitest).
- **vite.config.ts**: Configuration for Vite, a modern frontend tooling framework used for building and serving the Vue application.
- **vitest.config.ts**: Configuration for Vitest, a testing framework for Vite projects.

- **cypress/**: Contains Cypress testing setup and scripts.
  - **tsconfig.json**: TypeScript configuration for Cypress tests.
  - **e2e/**: End-to-end test files.
  - **fixtures/**: Test data fixtures for Cypress.
  - **support/**: Support files for Cypress testing.

- **public/**: Static assets for the frontend.
  - **favicon.ico**: Favicon for the web application.

- **src/**: Source code for the Vue frontend.
  - **App.vue**: The root Vue component of the application.
  - **main.ts**: Entry point for the Vue application, initializing the app.
  - **shims-vue.d.ts**: TypeScript shims for Vue files.
  - **assets/**: Static assets like images and styles.
  - **components/**: Reusable Vue components (e.g., `ChatInterface.vue`, `SettingsPanel.vue`).
  - **router/**: Routing configuration for the Vue app.
  - **stores/**: State management using Pinia or Vuex.
  - **views/**: Page-level Vue components.

### backend/
This directory houses the backend server code for AutoBot, built with FastAPI for API services.

- **main.py**: The main entry point for the FastAPI backend, defining API endpoints and server logic.

### bin/
Directory for executable scripts or binaries, potentially for tools or utilities used by AutoBot. Currently empty or not detailed in the file list.

### config/
Contains configuration files for the AutoBot application.

- **config.yaml.template**: A template for the main configuration file, defining settings like server host/port, logging, models, knowledge base paths, and Redis configuration.

### data/
Stores data files and databases used by AutoBot.

- **chat_history.json**: Stores conversational history for memory storage in JSON format.
- **reliability_stats.json**: Contains statistics or metrics related to system reliability.
- **chromadb/**: Directory for ChromaDB storage, where LLM vectors are persisted for the knowledge base.

### docs/
Documentation directory for the project, adhering to the user's custom instructions for maintaining canonical files.

- **decisions.md**: Records architectural choices, design tradeoffs, and justifications.
- **project.md**: Outlines project goals, scope, roadmap, and high-level features.
- **status.md**: Current status of tasks and project phases.
- **task_log.md**: Logs of completed tasks, results, outcomes, and LLM usage.
- **tasks.md**: Task board with statuses (TODO, IN PROGRESS, BLOCKED, DONE).

### frontend/
Contains an older or alternative frontend setup, possibly a static version or a different implementation.

- **index.css**, **index.js**: Core files for a static frontend.
- **admin_gui/**: Directory for an administrative GUI, specifics not detailed.
- **css/**: CSS styles for various frontend components (e.g., `file_browser.css`, `history.css`).
- **js/**: JavaScript files for frontend functionality (e.g., `file_browser.js`, `history.js`).
- **public/**: Static assets like icons and images for the frontend.
- **static/**: Compiled or static files served by the frontend, including JavaScript and CSS bundles.
- **templates/**: HTML templates or remnants, possibly for an older UI setup.

### logs/
Directory for log files generated by AutoBot, used for debugging and monitoring. Specific log files are not listed but are referenced in configuration.

### prompts/
Contains prompt templates used for interacting with language models or defining agent behavior.

- **orchestrator_system_prompt.txt**, **task_system_prompt.txt**, **tool_interpreter_system_prompt.txt**: System prompts for different components of AutoBot.
- **default/**: Default prompt templates for agent behavior, communication, and tools.
- **reflection/**: Prompts related to reflection or self-assessment by the AI.

### src/
Source code for the backend and core logic of AutoBot, written in Python.

- **chat_history_manager.py**: Manages conversational memory, currently using JSON, with a placeholder for Redis integration.
- **diagnostics.py**: Provides diagnostic tools or functions for system health checks.
- **event_manager.py**: Handles event-driven processes or notifications within AutoBot.
- **gui_controller.py**, **gui_controller_dummy.py**: Controls GUI interactions, with a dummy version for testing or fallback.
- **knowledge_base.py**: Implements the knowledge base, managing data storage with SQLite and vector storage with ChromaDB for semantic search.
- **llm_interface.py**: Interface to interact with large language models (LLMs).
- **orchestrator.py**: Coordinates various components of AutoBot for task execution.
- **security_layer.py**: Implements security features or protocols for the application.
- **system_info_collector.py**: Collects system information for diagnostics or optimization.
- **system_integration.py**: Handles integration with system-level functionalities.
- **tool_discovery.py**: Discovers or manages tools available to AutoBot.
- **voice_interface.py**: Manages voice input/output functionalities.
- **worker_node.py**: Defines worker processes or nodes for distributed tasks.

### tests/
Directory for test scripts to validate the functionality of AutoBot components.

- **test_tool_discovery.py**: Tests for the tool discovery module.

## Autogenerated Files and Folders

This section lists files and folders that are regenerated or automatically created during setup, build, or runtime processes. These should not be manually edited as they may be overwritten.

- **autobot-vue/dist/**: The build output directory for the Vue frontend, regenerated each time `npm run build` is executed. Contains compiled JavaScript, CSS, and HTML files.
- **autobot-vue/node_modules/**: Directory for npm dependencies, regenerated during `npm install`. It is ignored by Git and recreated as needed.
- **data/chromadb/**: Contains vector data for the knowledge base, regenerated or updated when new documents are added or embeddings are recalculated.
- **frontend/static/**: Contains compiled static files for an older frontend setup, regenerated during build processes or when copying from `autobot-vue/dist/`.
- **logs/**: Log files are autogenerated during runtime to capture application events and errors. Specific files within this directory are created dynamically.
- **.venv/** or virtual environment directories: If present, these are regenerated by `setup_agent.sh` when creating Python virtual environments.
