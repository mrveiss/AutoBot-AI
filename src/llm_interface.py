import asyncio
import json
import os
import re

import aiohttp
import requests
from dotenv import load_dotenv

# Import configuration managers
from src.circuit_breaker import circuit_breaker_async
from src.config import config as global_config_manager
from src.prompt_manager import prompt_manager
from src.retry_mechanism import retry_network_operation
from src.utils.config_manager import config_manager
from src.utils.logging_manager import get_llm_logger

# Conditional torch import for environments without CUDA
try:
    import torch

    TORCH_AVAILABLE = True
except ImportError:
    print("Warning: PyTorch not available or CUDA libraries missing")
    TORCH_AVAILABLE = False
    torch = None

load_dotenv()

logger = get_llm_logger("llm")


class LocalLLM:
    async def generate(self, prompt):
        logger.info("Using local TinyLLaMA fallback.")
        await asyncio.sleep(0.1)
        return {
            "choices": [
                {"message": {"content": f"Local TinyLLaMA response to: {prompt}"}}
            ]
        }


local_llm = LocalLLM()


class MockPalm:
    class QuotaExceededError(Exception):
        pass

    async def get_quota_status(self):
        await asyncio.sleep(0.05)
        import random

        class MockQuotaStatus:
            def __init__(self, remaining_tokens):
                self.remaining_tokens = remaining_tokens

        mock_status = MockQuotaStatus(50000)
        if random.random() < 0.2:
            mock_status.remaining_tokens = 500
        return mock_status

    async def generate_text(self, **kwargs):
        await asyncio.sleep(0.1)
        import random

        if random.random() < 0.1:
            raise self.QuotaExceededError("Mock Quota Exceeded")
        return {
            "choices": [
                {
                    "message": {
                        "content": f"Google LLM response to: {kwargs.get('prompt')}"
                    }
                }
            ]
        }


palm = MockPalm()


class LLMInterface:
    def __init__(self):
        # Use centralized configuration with fallback to environment variables
        self.ollama_host = config_manager.get(
            "llm.ollama.base_url", "http://localhost:11434"
        )

        # Try config first, then environment variable
        self.openai_api_key = config_manager.get(
            "llm.openai.api_key", ""
        ) or config_manager.get("openai.api_key", "")

        self.ollama_models = global_config_manager.get_nested(
            "llm_config.ollama.models", {}
        )
        # Use unified configuration for LLM models
        unified_llm_config = global_config_manager.get_llm_config()
        selected_model = unified_llm_config.get("ollama", {}).get(
            "model", "deepseek-r1:14b"
        )
        self.orchestrator_llm_alias = unified_llm_config.get(
            "orchestrator_llm", f"ollama_{selected_model}"
        )
        self.task_llm_alias = unified_llm_config.get(
            "task_llm", f"ollama_{selected_model}"
        )

        self.orchestrator_llm_settings = global_config_manager.get_nested(
            "llm_config.orchestrator_llm_settings", {}
        )
        self.task_llm_settings = global_config_manager.get_nested(
            "llm_config.task_llm_settings", {}
        )

        self.hardware_priority = global_config_manager.get_nested(
            "hardware_acceleration.priority",
            ["openvino_npu", "openvino", "cuda", "cpu"],
        )

        # Use centralized prompt manager instead of direct file loading
        try:
            orchestrator_prompt_key = global_config_manager.get_nested(
                "prompts.orchestrator_key", "default.agent.system.main"
            )
            self.orchestrator_system_prompt = prompt_manager.get(
                orchestrator_prompt_key
            )
        except KeyError:
            # Fallback to legacy loading for backward compatibility
            logger.warning(
                "Orchestrator prompt not found in prompt manager, "
                "using legacy file loading"
            )
            self.orchestrator_system_prompt = self._load_composite_prompt(
                global_config_manager.get_nested(
                    "prompts.orchestrator", "prompts/default/agent.system.main.md"
                )
            )

        try:
            task_prompt_key = global_config_manager.get_nested(
                "prompts.task_key", "reflection.agent.system.main.role"
            )
            self.task_system_prompt = prompt_manager.get(task_prompt_key)
        except KeyError:
            # Fallback to legacy loading for backward compatibility
            logger.warning(
                "Task prompt not found in prompt manager, " "using legacy file loading"
            )
            self.task_system_prompt = self._load_composite_prompt(
                global_config_manager.get_nested(
                    "prompts.task", "prompts/reflection/agent.system.main.role.md"
                )
            )

        try:
            tool_interpreter_prompt_key = global_config_manager.get_nested(
                "prompts.tool_interpreter_key", "tool_interpreter_system_prompt"
            )
            self.tool_interpreter_system_prompt = prompt_manager.get(
                tool_interpreter_prompt_key
            )
        except KeyError:
            # Fallback to legacy loading for backward compatibility
            logger.warning(
                "Tool interpreter prompt not found in prompt manager, "
                "using legacy file loading"
            )
            self.tool_interpreter_system_prompt = self._load_prompt_from_file(
                global_config_manager.get_nested(
                    "prompts.tool_interpreter",
                    "prompts/tool_interpreter_system_prompt.txt",
                )
            )

    def _load_prompt_from_file(self, file_path: str) -> str:
        try:
            with open(file_path, "r") as f:
                return f.read().strip()
        except FileNotFoundError:
            logger.error(f"Prompt file not found: {file_path}")
            return ""
        except Exception as e:
            logger.error(f"Error loading prompt from {file_path}: {e}")
            return ""

    def _resolve_includes(self, content: str, base_path: str) -> str:
        def replace_include(match):
            included_file = match.group(1)
            included_path = os.path.join(base_path, included_file)
            if os.path.exists(included_path):
                with open(included_path, "r") as f:
                    included_content = f.read()
                return self._resolve_includes(
                    included_content, os.path.dirname(included_path)
                )
            else:
                logger.warning(f"Included file not found: {included_path}")
                return f"{{{{ INCLUDE_ERROR: {included_file} NOT FOUND }}}}"

        return re.sub(r"\{\{\s*include\s*\"(.*?)\"\s*\}\}", replace_include, content)

    def _load_composite_prompt(self, base_file_path: str) -> str:
        if not os.path.exists(base_file_path):
            logger.error(f"Base composite prompt file not found: {base_file_path}")
            return ""

        with open(base_file_path, "r") as f:
            initial_content = f.read()

        resolved_content = self._resolve_includes(
            initial_content, os.path.dirname(base_file_path)
        )
        return resolved_content.strip()

    async def check_ollama_connection(self) -> bool:
        logger.info(f"Attempting to connect to Ollama at {self.ollama_host}...")
        try:
            health_check_url = f"{self.ollama_host}/api/tags"

            # Use retry mechanism for network connection - Native async HTTP
            async def make_request():
                timeout = aiohttp.ClientTimeout(total=5)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(health_check_url) as response:
                        response.raise_for_status()
                        return await response.json()

            models_info = await retry_network_operation(make_request)
            available_ollama_models = {
                model["name"] for model in models_info.get("models", [])
            }

            all_configured_ollama_models = set()

            if self.orchestrator_llm_alias.startswith("ollama_"):
                base_alias = self.orchestrator_llm_alias.replace("ollama_", "")
                configured_model_name = self.ollama_models.get(base_alias, base_alias)
                all_configured_ollama_models.add(configured_model_name)

            if self.task_llm_alias.startswith("ollama_"):
                base_alias = self.task_llm_alias.replace("ollama_", "")
                configured_model_name = self.ollama_models.get(base_alias, base_alias)
                all_configured_ollama_models.add(configured_model_name)

            missing_models = [
                model
                for model in all_configured_ollama_models
                if model not in available_ollama_models
            ]

            if not missing_models:
                logger.info(
                    "✅ Ollama server is reachable and all configured models "
                    f"({', '.join(all_configured_ollama_models)}) are available."
                )
                return True
            else:
                models_missing = ", ".join(missing_models)
                models_available = ", ".join(available_ollama_models)
                logger.warning(
                    "⚠️ Ollama server is reachable, but the following "
                    f"configured models are not found: {models_missing}. "
                    f"Available models: {models_available}"
                )
                return False
        except requests.exceptions.ConnectionError:
            logger.error(
                f"❌ Failed to connect to Ollama server at {self.ollama_host}. "
                "Is it running?"
            )
            return False
        except requests.exceptions.Timeout:
            logger.error(
                f"❌ Ollama server at {self.ollama_host} timed out. "
                "It might be too busy or slow."
            )
            return False
        except requests.exceptions.RequestException as e:
            logger.error(
                "❌ An unexpected error occurred while checking "
                f"Ollama connection: {e}"
            )
            return False
        except Exception as e:
            logger.error(f"❌ An unexpected error occurred: {e}")
            return False

    def _detect_hardware(self):
        detected_hardware = []
        if TORCH_AVAILABLE and torch.cuda.is_available():
            detected_hardware.append("cuda")
        try:
            from openvino.runtime import Core

            core = Core()
            available_devices = core.available_devices
            logger.info(f"OpenVINO available devices: {available_devices}")

            if "CPU" in available_devices:
                detected_hardware.append("openvino_cpu")
            if "GPU" in available_devices:
                detected_hardware.append("openvino_gpu")

            npu_devices = [device for device in available_devices if "NPU" in device]
            if npu_devices:
                detected_hardware.append("openvino_npu")
                logger.info(f"OpenVINO NPU devices detected: {npu_devices}")

            gna_devices = [device for device in available_devices if "GNA" in device]
            if gna_devices:
                detected_hardware.append("openvino_gna")
                logger.info(f"OpenVINO GNA devices detected: {gna_devices}")

        except ImportError:
            logger.debug("OpenVINO not installed or configured")
            pass
        except Exception as e:
            logger.warning(f"Error detecting OpenVINO devices: {e}")

        try:
            import onnxruntime as rt

            if "CUDAExecutionProvider" in rt.get_available_providers():
                detected_hardware.append("onnxruntime_cuda")
            if "OpenVINOExecutionProvider" in rt.get_available_providers():
                detected_hardware.append("onnxruntime_openvino")
            if "CPUExecutionProvider" in rt.get_available_providers():
                detected_hardware.append("onnxruntime_cpu")
        except ImportError:
            pass

        detected_hardware.append("cpu")
        return detected_hardware

    def _select_backend(self):
        """Select the best available backend based on hardware detection and priority"""
        detected_hardware = self._detect_hardware()

        for preferred_backend in self.hardware_priority:
            backend = self._try_backend_selection(preferred_backend, detected_hardware)
            if backend:
                return backend

        return "cpu"  # Fallback

    def _try_backend_selection(
        self, preferred_backend: str, detected_hardware: set
    ) -> str:
        """Try to select a specific backend if hardware supports it"""
        if preferred_backend == "openvino_npu":
            return self._select_openvino_npu(detected_hardware)
        elif preferred_backend == "openvino":
            return self._select_openvino_variant(detected_hardware)
        elif preferred_backend == "cuda":
            return self._select_cuda(detected_hardware)
        elif preferred_backend == "onnxruntime":
            return self._select_onnxruntime(detected_hardware)
        elif preferred_backend == "cpu":
            return self._select_cpu(detected_hardware)
        return None

    def _select_openvino_npu(self, detected_hardware: set) -> str:
        """Select OpenVINO NPU if available"""
        if "openvino_npu" in detected_hardware:
            return "openvino_npu"
        return None

    def _select_openvino_variant(self, detected_hardware: set) -> str:
        """Select the best OpenVINO variant available"""
        openvino_options = ["openvino_npu", "openvino_gpu", "openvino_cpu"]

        for option in openvino_options:
            if option in detected_hardware:
                if option == "openvino_npu":
                    return "openvino_npu"
                elif option == "openvino_gpu":
                    return "openvino_gpu"
                elif option == "openvino_cpu":
                    return "openvino_cpu"
        return None

    def _select_cuda(self, detected_hardware: set) -> str:
        """Select CUDA if available"""
        if "cuda" in detected_hardware:
            return "cuda"
        return None

    def _select_onnxruntime(self, detected_hardware: set) -> str:
        """Select ONNX Runtime if any variant is available"""
        onnx_options = ["onnxruntime_cpu", "onnxruntime_cuda", "onnxruntime_openvino"]

        if any(option in detected_hardware for option in onnx_options):
            return "onnxruntime"
        return None

    def _select_cpu(self, detected_hardware: set) -> str:
        """Select CPU backend if available"""
        if "cpu" in detected_hardware:
            return "cpu"
        return None

    async def chat_completion(
        self, messages: list, llm_type: str = "orchestrator", **kwargs
    ):
        """
        Performs a chat completion using the specified LLM type.
        llm_type: "orchestrator" or "task"
        """
        if llm_type == "orchestrator":
            model_alias = self.orchestrator_llm_alias
            settings = self.orchestrator_llm_settings
            system_prompt_content = self.orchestrator_system_prompt
        elif llm_type == "task":
            model_alias = self.task_llm_alias
            settings = self.task_llm_settings
            system_prompt_content = self.task_system_prompt
        else:
            raise ValueError(
                f"Unsupported LLM type: {llm_type}. Must be 'orchestrator' or 'task'."
            )

        if model_alias.startswith("ollama_"):
            base_alias = model_alias.replace("ollama_", "")
            model_name = self.ollama_models.get(base_alias, base_alias)
        elif model_alias.startswith("openai_"):
            model_name = model_alias.replace("openai_", "")
        elif model_alias.startswith("transformers_"):
            model_name = model_alias.replace("transformers_", "")
        else:
            model_name = model_alias

        if system_prompt_content and not any(
            m.get("role") == "system" for m in messages
        ):
            messages.insert(0, {"role": "system", "content": system_prompt_content})

        llm_params = {"temperature": settings.get("temperature", 0.7), **kwargs}

        if llm_type == "orchestrator" and (
            model_alias.startswith("ollama_")
            or not any(
                model_alias.startswith(prefix)
                for prefix in ["ollama_", "openai_", "transformers_"]
            )
        ):
            llm_params["structured_output"] = True

        if model_alias.startswith("ollama_"):
            return await self._ollama_chat_completion(
                model_name, messages, **llm_params
            )
        elif model_alias.startswith("openai_"):
            return await self._openai_chat_completion(
                model_name, messages, **llm_params
            )
        elif model_alias.startswith("transformers_"):
            return await self._transformers_chat_completion(
                model_name, messages, **llm_params
            )
        else:
            # Default to Ollama for models without prefix (like dolphin-llama3:8b)
            logger.info(
                f"Model '{model_alias}' has no prefix, defaulting to Ollama provider"
            )
            return await self._ollama_chat_completion(
                model_name, messages, **llm_params
            )

    @circuit_breaker_async(
        "ollama_service", failure_threshold=3, recovery_timeout=30.0, timeout=120.0
    )
    async def _ollama_chat_completion(
        self,
        model: str,
        messages: list,
        temperature: float = 0.7,
        structured_output: bool = False,
        **kwargs,
    ):
        url = f"{self.ollama_host}/api/chat"
        headers = {"Content-Type": "application/json"}

        data = {
            "model": model,
            "messages": messages,
            "stream": False,
            "temperature": temperature,
            "format": "json" if structured_output else "",
        }
        if "device" in kwargs:
            device_value = kwargs.pop("device")
            if device_value.startswith("cuda"):
                data["options"] = {"num_gpu": device_value.split(":")[-1]}
            else:
                data["options"] = {"device": device_value}
        else:
            selected_backend = self._select_backend()
            if selected_backend == "openvino_npu":
                data["options"] = {"device": "NPU"}
            elif selected_backend == "openvino_gpu":
                data["options"] = {"device": "GPU"}
            elif selected_backend == "cuda":
                data["options"] = {"num_gpu": 1}
        data.update(kwargs)

        print(f"Ollama Request URL: {url}")
        print(f"Ollama Request Headers: {headers}")
        print(f"Ollama Request Data: {json.dumps(data, indent=2)}")
        logger.debug(f"Ollama Request URL: {url}")
        logger.debug(f"Ollama Request Headers: {headers}")
        logger.debug(f"Ollama Request Data: {json.dumps(data, indent=2)}")

        try:
            # Use retry mechanism for LLM API calls - PERFORMANCE FIX: Native async HTTP
            async def make_llm_request():
                timeout = aiohttp.ClientTimeout(total=600)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        url, headers=headers, json=data
                    ) as response:
                        response.raise_for_status()
                        response_text = await response.text()
                        response_json = await response.json()

                        print(f"Ollama Raw Response Status: {response.status}")
                        print(f"Ollama Raw Response Headers: {response.headers}")
                        print(f"Ollama Raw Response Text: {response_text}")
                        logger.debug(f"Ollama Raw Response Status: {response.status}")
                        logger.debug(f"Ollama Raw Response Headers: {response.headers}")
                        logger.debug(f"Ollama Raw Response Text: {response_text}")

                        return response_json

            return await retry_network_operation(make_llm_request)
        except aiohttp.ClientResponseError as e:
            error_msg = f"HTTP Error communicating with Ollama: {e.status}"
            print(f"{error_msg} - {e.message}")
            logger.error(f"{error_msg} - {e.message}")
            return None
        except aiohttp.ClientConnectorError as e:
            print(f"Connection Error communicating with Ollama: {e}")
            logger.error(f"Connection Error communicating with Ollama: {e}")
            return None
        except asyncio.TimeoutError as e:
            print(f"Timeout Error communicating with Ollama: {e}")
            logger.error(f"Timeout Error communicating with Ollama: {e}")
            return None
        except Exception as e:
            print(f"Generic Request Error communicating with Ollama: {e}")
            logger.error(f"Generic Request Error communicating with Ollama: {e}")
            return None
        except Exception as e:
            print("An unexpected error occurred during Ollama chat completion: " f"{e}")
            logger.error(
                f"An unexpected error occurred during Ollama chat completion: {e}"
            )
            return None

    @circuit_breaker_async(
        "openai_service", failure_threshold=2, recovery_timeout=60.0, timeout=120.0
    )
    async def _openai_chat_completion(
        self,
        model: str,
        messages: list,
        temperature: float = 0.7,
        structured_output: bool = False,
        **kwargs,
    ):
        if not self.openai_api_key:
            print(
                "OpenAI API key not found. "
                "Please set OPENAI_API_KEY in .env or config.yaml."
            )
            return None

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.openai_api_key}",
        }
        data = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "response_format": ({"type": "json_object"} if structured_output else None),
            **kwargs,
        }
        try:
            # Use retry mechanism for OpenAI API calls - Native async HTTP
            async def make_openai_request():
                timeout = aiohttp.ClientTimeout(total=600)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(
                        url, headers=headers, json=data
                    ) as response:
                        response.raise_for_status()
                        return await response.json()

            return await retry_network_operation(make_openai_request)
        except (
            aiohttp.ClientResponseError,
            aiohttp.ClientConnectorError,
            asyncio.TimeoutError,
        ) as e:
            print(f"Error communicating with OpenAI: {e}")
            return None

    async def _transformers_chat_completion(
        self,
        model_name: str,
        messages: list,
        temperature: float = 0.7,
        structured_output: bool = False,
        **kwargs,
    ):
        print(
            f"Transformers backend for {model_name} is a placeholder. "
            f"Not implemented yet. Temp: {temperature}, "
            f"Structured: {structured_output}"
        )
        await asyncio.sleep(0.1)
        return {
            "choices": [
                {"message": {"content": "Placeholder response from Transformers."}}
            ]
        }


async def safe_query(prompt, retries=2, initial_delay=1):
    for i in range(retries + 1):
        try:
            usage_info = await palm.get_quota_status()
            if usage_info.remaining_tokens < 1000:
                logger.warning("⚠️ Google LLM quota low, falling back to local model.")
                return await local_llm.generate(prompt)

            response = await palm.generate_text(prompt=prompt)
            logger.info("Successfully queried Google LLM.")
            return response

        except palm.QuotaExceededError:
            if i < retries:
                delay = initial_delay * (2**i)
                logger.warning(
                    f"❌ Quota exceeded on Google API. Retrying in {delay} "
                    f"seconds (attempt {i+1}/{retries})."
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "❌ Quota exceeded on Google API after multiple retries. "
                    "Using local fallback."
                )
                return await local_llm.generate(prompt)
        except Exception:
            if i < retries:
                delay = initial_delay * (2**i)
                logger.exception(
                    f"🔧 LLM query failed (attempt {i+1}/{retries}). "
                    f"Retrying in {delay} seconds..."
                )
                await asyncio.sleep(delay)
            else:
                logger.exception(
                    "🔧 LLM query failed after multiple retries. "
                    "Attempting local fallback."
                )
                return await local_llm.generate(prompt)
    return await local_llm.generate(prompt)
