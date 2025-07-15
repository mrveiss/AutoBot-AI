# AutoBot Agent

AutoBot is an autonomous agent designed to interact with a computer's GUI and execute tasks. It leverages LLMs for planning, a knowledge base for context, and various tools for system interaction, including GUI automation, shell command execution, and real-time diagnostics.

## Features

*   **LLM-Powered Task Planning:** Breaks down high-level goals into actionable steps.
*   **Knowledge Base (RAG):** Integrates relevant context from documents and facts to inform decision-making.
*   **GUI Automation:** Interacts with the desktop environment by typing, clicking elements (via image recognition), reading text (OCR), and managing windows.
*   **Shell Command Execution:** Executes commands directly on the system.
*   **Real-time Diagnostics:** Monitors task failures, analyzes causes, and suggests fixes, with optional user permission.
*   **System Monitoring UI:** A web-based control panel to monitor CPU, RAM, and GPU/VRAM usage in real-time.
*   **Flexible LLM Backends:** Supports Ollama, OpenAI, and a placeholder for local Hugging Face Transformers models.
*   **Hardware Acceleration:** Configurable priority for OpenVINO, CUDA, ONNX Runtime, and CPU.

## Installation

This project is designed to run locally without Docker, leveraging Python virtual environments.

### Prerequisites

*   **Python 3.10 or higher:** Python 3.10 is recommended for the main environment. Python 3.11+ is required for OpenVINO support.
*   **pip:** Python package installer.
*   **Git:** For cloning the repository.
*   **VNC Server (Optional, for GUI control):** `x11vnc` or `TigerVNC` is required for the live computer window feature.
    *   **Ubuntu/Debian:** `sudo apt update && sudo apt install x11vnc`
    *   **Fedora:** `sudo dnf install tigervnc-server`
*   **Tesseract OCR (Optional, for GUI text recognition):** Required for the `read_text_from_region` GUI action.
    *   **Ubuntu/Debian:** `sudo apt update && sudo apt install tesseract-ocr`
    *   **Fedora:** `sudo dnf install tesseract`
    *   **macOS:** `brew install tesseract`

### Steps

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-repo/autobot.git
    cd autobot
    ```

2.  **Run the setup script:**
    This script will create Python virtual environments, install dependencies, and download necessary frontend assets (noVNC).

    ```bash
    chmod +x setup_agent.sh
    ./setup_agent.sh
    ```
    *   The script will create a main virtual environment named `AutoBot/` and an optional `venvs/openvino_env/` if Python 3.11+ is detected.
    *   It will also copy `config/config.yaml.template` to `config/config.yaml` if `config.yaml` does not already exist.

3.  **Configure your LLM (Optional but Recommended):**
    Edit `config/config.yaml` to configure your preferred LLM.
    *   **Ollama:** Ensure Ollama is running and you have pulled the desired models (e.g., `ollama pull tinyllama`).
    *   **OpenAI:** Add your `OPENAI_API_KEY` to `config/config.yaml` or set it as an environment variable.

    Example `config/config.yaml` snippet for Ollama:
    ```yaml
    llm_config:
      default_llm: "ollama_tinyllama"
      ollama:
        host: "http://localhost:11434"
        models:
          tinyllama: "tinyllama"
    ```

## Running the Agent

1.  **Activate the main virtual environment:**
    ```bash
    source bin/activate
    ```

2.  **Start the AutoBot agent:**
    This script will start the backend FastAPI server, a simple frontend HTTP server, and optionally the VNC server and websockify.

    ```bash
    chmod +x run_agent.sh
    ./run_agent.sh
    ```

3.  **Access the Control Panel:**
    Open your web browser and navigate to `http://localhost:5174/` for the Vue.js frontend interface.

## Usage

*   **Control Panel:** Use the web interface to submit goals, execute commands, upload files, and monitor system resources.
*   **VNC Viewer:** If VNC is enabled in `config.yaml`, you can connect to the VNC server (default port 5900) using a VNC client with the password configured in `config.yaml`. The web interface also provides a live view via noVNC.

## Architecture

The AutoBot project is composed of a Vue.js frontend and a Python backend. The backend is a FastAPI application that uses a modular architecture to separate concerns. The core components are:

*   **Frontend (`autobot-vue/`)**: A Vue.js application that provides the user interface for interacting with the agent.
*   **Backend (`backend/`)**: A FastAPI application that exposes a REST API for the frontend to consume.
*   **Orchestrator (`src/orchestrator.py`)**: The brain of the agent. It takes a high-level goal from the user and breaks it down into a series of tasks.
*   **LLM Interface (`src/llm_interface.py`)**: A unified interface for interacting with different LLM backends.
*   **Knowledge Base (`src/knowledge_base.py`)**: Manages the agent's long-term memory using LlamaIndex and Redis.
*   **Worker Node (`src/worker_node.py`)**: Executes tasks dispatched by the orchestrator, such as running system commands or performing GUI automation.

For a more detailed overview of the project's architecture, please see the following documents:

*   **[Project Map](docs/project_map.md)**: A comprehensive overview of the project's structure.
*   **[Process Map](docs/process_map.md)**: A sequence diagram that illustrates the flow of a user request through the system.
*   **[Suggested Improvements](docs/suggested_improvements.md)**: A list of potential improvements for the project.

## Contributing

Contributions are welcome! Please feel free to open issues or submit pull requests.

## License

[Specify your license here, e.g., MIT License]
