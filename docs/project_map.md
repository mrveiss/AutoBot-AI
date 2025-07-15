# AutoBot Project Map

This document provides a comprehensive overview of the AutoBot project's structure, detailing the purpose of each file and folder within the repository. It aims to facilitate navigation and understanding of the codebase for developers and contributors.

## Project Overview

AutoBot is an AI-driven application designed to automate tasks and provide intelligent responses through a web interface. It leverages machine learning models for natural language processing, a knowledge base for information retrieval, and a modular architecture for extensibility. The project is structured into backend and frontend components, with supporting scripts and configuration files.

## Root Directory Structure

- **.gitignore**: Specifies intentionally untracked files to ignore by Git, such as temporary files, virtual environments, and build artifacts.
- **CLAUDE.md**: Documentation specific to the Claude model.
- **README.md**: The project's main documentation file, providing an overview, installation instructions, and usage guidelines.
- **autobot-vue/**: Contains the frontend application built with Vue.js.
- **backend/**: Contains the backend server code for AutoBot, built with FastAPI.
- **bin/**: Contains executable files and scripts, including the Python virtual environment.
- **check_ollama.py**: A utility script to check the availability and configuration of Ollama.
- **config/**: Contains configuration files for the AutoBot application.
- **data/**: Stores data files and databases used by AutoBot.
- **docs/**: Contains documentation for the project.
- **frontend/**: Contains an older or alternative frontend setup.
- **prompts/**: Contains prompt templates used for interacting with language models.
- **pyvenv.cfg**: Configuration file for the Python virtual environment.
- **requirements.txt**: Lists Python dependencies required for the project.
- **run_agent.sh**: A shell script to run the AutoBot application.
- **scripts/**: Contains miscellaneous scripts.
- **setup_agent.sh**: A setup script to initialize the AutoBot environment.
- **src/**: Contains the source code for the backend and core logic of AutoBot.
- **static/**: Contains static files for the web server.
- **tests/**: Contains test scripts.
- **todo.md**: A markdown file listing tasks or features to be implemented.

## Subdirectories

### `autobot-vue/`

This directory contains the frontend application built with Vue.js, a progressive JavaScript framework for building user interfaces.

- **README.md**: Documentation specific to the Vue frontend component.
- **cypress/**: Contains Cypress end-to-end testing setup and scripts.
- **cypress.config.ts**: Configuration for Cypress.
- **env.d.ts**: TypeScript declaration file for environment variables.
- **eslint.config.ts**: Configuration for ESLint.
- **fix_github_url.sh**: A script to fix or update GitHub URLs.
- **index.html**: The main HTML file for the Vue application.
- **package-lock.json**: Locks the versions of npm dependencies.
- **package.json**: Defines the project's metadata, scripts, and dependencies for the Vue frontend.
- **public/**: Static assets for the frontend.
- **src/**: Source code for the Vue frontend.
- **tsconfig.app.json**, **tsconfig.json**, **tsconfig.node.json**, **tsconfig.vitest.json**: TypeScript configuration files.
- **vite.config.ts**: Configuration for Vite.
- **vitest.config.ts**: Configuration for Vitest.

### `backend/`

This directory houses the backend server code for AutoBot, built with FastAPI for API services.

- **main.py**: The main entry point for the FastAPI backend, defining API endpoints and server logic.
- **config/**: Contains backend-specific configuration.

### `bin/`

This directory contains the Python virtual environment and executable scripts.

### `config/`

Contains configuration files for the AutoBot application.

- **config.yaml.template**: A template for the main configuration file.
- **settings.json**: User-defined settings that override the default configuration.

### `data/`

Stores data files and databases used by AutoBot.

- **chat_history.json**: Stores conversational history.
- **reliability_stats.json**: Contains statistics or metrics related to system reliability.

### `docs/`

Documentation directory for the project.

- **decisions.md**: Records architectural choices and design tradeoffs.
- **external_apps/**: Documentation for external applications.
- **process_map.md**: A Mermaid sequence diagram illustrating the project's process flow.
- **project.md**: Outlines project goals, scope, roadmap, and high-level features.
- **project_map.md**: This file.
- **status.md**: Current status of tasks and project phases.
- **suggested_improvements.md**: A document outlining potential improvements for the project.
- **task_log.md**: Logs of completed tasks, results, and outcomes.
- **tasks.md**: A task board with statuses (TODO, IN PROGRESS, BLOCKED, DONE).
- **todo.md**: A list of tasks to be implemented.

### `frontend/`

Contains an older or alternative frontend setup.

### `prompts/`

Contains prompt templates used for interacting with language models or defining agent behavior.

- **default/**: Default prompt templates.
- **orchestrator_system_prompt.txt**: System prompt for the orchestrator.
- **reflection/**: Prompts related to reflection or self-assessment by the AI.
- **task_system_prompt.txt**: System prompt for the task execution agent.
- **tool_interpreter_system_prompt.txt**: System prompt for the tool interpreter.

### `scripts/`

Contains miscellaneous scripts.

- **setup_openvino.sh**: A script to set up OpenVINO.

### `src/`

Source code for the backend and core logic of AutoBot, written in Python.

- **chat_history_manager.py**: Manages conversational memory.
- **diagnostics.py**: Provides diagnostic tools or functions for system health checks.
- **event_manager.py**: Handles event-driven processes or notifications.
- **gui_controller.py**, **gui_controller_dummy.py**: Controls GUI interactions.
- **knowledge_base.py**: Implements the knowledge base, managing data storage and retrieval.
- **langchain_agent_orchestrator.py**: An alternative orchestrator based on LangChain.
- **llm_interface.py**: Interface to interact with large language models (LLMs).
- **memory_manager.py**: Manages the agent's memory.
- **orchestrator.py**: Coordinates various components of AutoBot for task execution.
- **security_layer.py**: Implements security features or protocols.
- **system_info_collector.py**: Collects system information.
- **system_integration.py**: Handles integration with system-level functionalities.
- **tool_discovery.py**: Discovers or manages tools available to AutoBot.
- **voice_interface.py**: Manages voice input/output functionalities.
- **worker_node.py**: Defines worker processes or nodes for distributed tasks.

### `static/`

Contains static files for the web server.

### `tests/`

Directory for test scripts to validate the functionality of AutoBot components.

- **test_tool_discovery.py**: Tests for the tool discovery module.
