import asyncio
import os
import sys

# Add the parent directory of src to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

from llm_interface import LLMInterface

async def check_ollama_status():
    llm_interface = LLMInterface()
    print("Checking Ollama connection and model availability...")
    connected = await llm_interface.check_ollama_connection()
    if connected:
        print(f"Ollama is connected.")
        print(f"Configured Orchestrator LLM: {llm_interface.orchestrator_llm_alias}")
        print(f"Configured Task LLM: {llm_interface.task_llm_alias}")
    else:
        print("Ollama connection failed or configured models not found. Please ensure Ollama is running and the required models are pulled.")

if __name__ == "__main__":
    asyncio.run(check_ollama_status())
