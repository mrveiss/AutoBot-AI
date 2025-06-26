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

## Project Structure

*   `main.py`: Main FastAPI application, defines API endpoints.
*   `src/`: Contains core Python modules.
    *   `orchestrator.py`: Manages task planning and dispatch.
    *   `llm_interface.py`: Handles communication with various LLM backends.
    *   `knowledge_base.py`: Manages RAG, document processing, and fact storage.
    *   `diagnostics.py`: Provides system monitoring and failure analysis.
    *   `event_manager.py`: Centralized event bus for inter-module communication.
    *   `worker_node.py`: Executes tasks dispatched by the orchestrator.
    *   `gui_controller.py`: Provides functions for GUI automation (mouse, keyboard, OCR, window management).
*   `config/`: Configuration files.
    *   `config.yaml.template`: Template for `config.yaml`.
    *   `config.yaml`: Your active configuration (created from template by `setup_agent.sh`).
*   `frontend/`: Web-based user interface.
    *   `index.html`: Main HTML file.
    *   `css/style.css`: CSS styles.
    *   `js/main.js`: Frontend JavaScript logic.
    *   `vendor/noVNC/`: noVNC client library (downloaded by `setup_agent.sh`).
*   `data/`: Persistent data storage (e.g., knowledge base SQLite DB, ChromaDB embeddings).
*   `requirements.txt`: Python dependencies.
*   `setup_agent.sh`: Script for initial project setup.
*   `run_agent.sh`: Script to run the AutoBot agent.
*   `run_with_openvino.sh`: Example script to activate the OpenVINO environment (if created).

## Contributing

Contributions are welcome! Please feel free to open issues or submit pull requests.

## License

[Specify your license here, e.g., MIT License]
