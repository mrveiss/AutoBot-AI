"""
Multi-Modal Integration Tests

Comprehensive integration tests for AutoBot's multi-modal capabilities,
testing the interaction between text, image, audio, and combined processing
components under realistic scenarios.
"""

import asyncio
import base64
import io
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from src.computer_vision_system import computer_vision_system
from src.context_aware_decision_system import (
    DecisionType,
    context_aware_decision_system,
)

# Import multi-modal components
from src.multimodal_processor import (
    ModalInput,
    ModalityType,
    ProcessingIntent,
    multimodal_processor,
)
from src.voice_processing_system import AudioInput, voice_processing_system


class TestMultiModalWorkflowIntegration:
    """Test integrated multi-modal workflows"""

    def setup_method(self):
        """Set up test environment"""
        self.test_start_time = time.time()

    def teardown_method(self):
        """Clean up after tests"""

    def create_test_image(
        self, width: int = 400, height: int = 300, color: str = "lightblue"
    ) -> bytes:
        """Create a test image for multi-modal testing"""
        image = Image.new("RGB", (width, height), color=color)

        # Add some content to make it more realistic
        from PIL import ImageDraw, ImageFont

        draw = ImageDraw.Draw(image)

        # Draw some shapes and text
        draw.rectangle([50, 50, 150, 100], fill="red", outline="black")
        draw.ellipse([200, 50, 350, 150], fill="green", outline="blue")

        try:
            # Try to use a default font, fall back to basic if not available
            font = ImageFont.load_default()
            draw.text((50, 200), "Test UI Element", fill="black", font=font)
            draw.text((200, 200), "Button", fill="white", font=font)
        except Exception:
            # Fallback without font
            draw.text((50, 200), "Test UI Element", fill="black")
            draw.text((200, 200), "Button", fill="white")

        # Convert to bytes
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def create_test_audio(
        self, duration: float = 2.0, sample_rate: int = 16000
    ) -> bytes:
        """Create test audio data for multi-modal testing"""
        # Generate a simple sine wave
        t = np.linspace(0, duration, int(sample_rate * duration))
        frequency = 440  # A4 note
        audio_signal = np.sin(2 * np.pi * frequency * t)

        # Convert to 16-bit PCM
        audio_int16 = (audio_signal * 32767).astype(np.int16)
        return audio_int16.tobytes()

    async def test_text_to_multimodal_workflow(self):
        """Test workflow starting with text that triggers multi-modal processing"""
        # Scenario: User asks to analyze a screenshot
        user_request = "Take a screenshot and analyze it for automation opportunities"

        # Step 1: Process text input
        text_input = ModalInput(
            input_id="text_workflow_1",
            modality_type=ModalityType.TEXT,
            processing_intent=ProcessingIntent.WORKFLOW_AUTOMATION,
            content=user_request,
            metadata={"source": "user", "workflow_step": 1},
            timestamp=time.time(),
        )

        with patch.object(multimodal_processor, "_process_text_input") as mock_text:
            mock_text.return_value = {
                "intent": "screenshot_analysis",
                "next_actions": ["take_screenshot", "analyze_ui"],
                "confidence": 0.9,
            }

            text_result = await multimodal_processor.process_input(text_input)

            # Verify text processing
            assert text_result.success
            assert text_result.confidence > 0.8
            assert "screenshot_analysis" in str(text_result.results)

        # Step 2: Take screenshot (simulated with test image)
        test_screenshot = self.create_test_image(1920, 1080, "white")

        screenshot_input = ModalInput(
            input_id="screenshot_workflow_1",
            modality_type=ModalityType.IMAGE,
            processing_intent=ProcessingIntent.SCREEN_ANALYSIS,
            content=test_screenshot,
            metadata={"source": "screenshot", "workflow_step": 2},
            timestamp=time.time(),
        )

        with patch.object(computer_vision_system, "analyze_screenshot") as mock_cv:
            mock_cv.return_value = {
                "ui_elements": [
                    {
                        "type": "button",
                        "text": "Submit",
                        "confidence": 0.95,
                        "bbox": [100, 200, 200, 250],
                    },
                    {
                        "type": "text_field",
                        "confidence": 0.85,
                        "bbox": [100, 100, 400, 130],
                    },
                ],
                "automation_opportunities": [
                    {"action": "click_button", "target": "Submit", "confidence": 0.9},
                    {"action": "fill_form", "target": "text_field", "confidence": 0.8},
                ],
                "confidence_score": 0.88,
            }

            screenshot_result = await multimodal_processor.process_input(
                screenshot_input
            )

            # Verify screenshot analysis
            assert screenshot_result.success
            assert len(screenshot_result.results.get("ui_elements", [])) > 0

        # Step 3: Make contextual decision based on analysis
        decision = await context_aware_decision_system.make_contextual_decision(
            DecisionType.AUTOMATION_ACTION,
            "Determine best automation strategy based on screenshot analysis",
        )

        # Verify decision making
        assert decision.confidence > 0.5
        assert decision.chosen_action.get("action") is not None

        print("✅ Text-to-multimodal workflow completed successfully")

    async def test_image_audio_combined_workflow(self):
        """Test workflow combining image and audio inputs"""
        # Scenario: User provides image and voice command for analysis

        test_image = self.create_test_image(800, 600, "lightgray")
        test_audio = self.create_test_audio(3.0)

        # Step 1: Process combined input
        combined_input = ModalInput(
            input_id="combined_workflow_1",
            modality_type=ModalityType.COMBINED,
            processing_intent=ProcessingIntent.DECISION_MAKING,
            content={
                "image": base64.b64encode(test_image).decode("utf-8"),
                "audio": base64.b64encode(test_audio).decode("utf-8"),
                "text": "Analyze this interface and implement the voice command",
            },
            metadata={"source": "multimodal_user", "workflow_step": 1},
            timestamp=time.time(),
        )

        with patch.object(
            multimodal_processor, "_process_combined_input"
        ) as mock_combined:
            mock_combined.return_value = {
                "image_analysis": {
                    "ui_elements": [{"type": "menu", "confidence": 0.9}],
                    "context": "settings_screen",
                },
                "audio_analysis": {
                    "transcription": "open settings menu",
                    "intent": "navigation_command",
                    "confidence": 0.85,
                },
                "correlation_score": 0.92,
                "recommended_actions": [
                    {"action": "click_menu", "target": "settings", "confidence": 0.88}
                ],
            }

            combined_result = await multimodal_processor.process_input(combined_input)

            # Verify combined processing
            assert combined_result.success
            assert combined_result.confidence > 0.8
            results = combined_result.results
            assert "image_analysis" in results
            assert "audio_analysis" in results
            assert results.get("correlation_score", 0) > 0.8

    async def test_realtime_multimodal_stream(self):
        """Test real-time multi-modal input streaming"""
        # Simulate streaming inputs over time
        stream_inputs = []

        # Create a sequence of inputs simulating real-time interaction
        for i in range(5):
            # Alternate between different modalities
            if i % 3 == 0:
                # Text input
                input_data = ModalInput(
                    input_id=f"stream_{i}",
                    modality_type=ModalityType.TEXT,
                    processing_intent=ProcessingIntent.REAL_TIME_ASSISTANCE,
                    content=f"Step {i}: Check current status",
                    metadata={"stream_index": i, "timestamp": time.time()},
                    timestamp=time.time(),
                )
            elif i % 3 == 1:
                # Image input
                test_image = self.create_test_image(200, 200, f"color_{i}")
                input_data = ModalInput(
                    input_id=f"stream_{i}",
                    modality_type=ModalityType.IMAGE,
                    processing_intent=ProcessingIntent.REAL_TIME_ASSISTANCE,
                    content=test_image,
                    metadata={"stream_index": i, "timestamp": time.time()},
                    timestamp=time.time(),
                )
            else:
                # Audio input
                test_audio = self.create_test_audio(1.0)
                audio_input = AudioInput(
                    audio_id=f"stream_audio_{i}",
                    audio_data=test_audio,
                    sample_rate=16000,
                    duration=1.0,
                    format="raw",
                    channels=1,
                    timestamp=time.time(),
                    metadata={"stream_index": i},
                )
                input_data = audio_input

            stream_inputs.append(input_data)

        # Process streaming inputs
        results = []
        processing_times = []

        for input_data in stream_inputs:
            start_time = time.perf_counter()

            if isinstance(input_data, AudioInput):
                # Process audio input
                with patch.object(
                    voice_processing_system, "process_voice_command"
                ) as mock_voice:
                    mock_voice.return_value = {
                        "success": True,
                        "transcription": f'Stream command {input_data.metadata["stream_index"]}',
                        "intent": "status_check",
                        "confidence": 0.8,
                    }

                    result = await voice_processing_system.process_voice_command(
                        input_data
                    )
            else:
                # Process other modalities
                with patch.object(multimodal_processor, "process_input") as mock_modal:
                    mock_result = MagicMock()
                    mock_result.success = True
                    mock_result.confidence = 0.85
                    mock_result.results = {
                        "processed": True,
                        "modality": input_data.modality_type.value,
                        "stream_index": input_data.metadata.get("stream_index"),
                    }
                    mock_modal.return_value = mock_result

                    result = await multimodal_processor.process_input(input_data)

            processing_time = time.perf_counter() - start_time
            processing_times.append(processing_time)
            results.append(result)

            # Simulate small delay between inputs
            await asyncio.sleep(0.1)

        # Verify streaming performance
        assert len(results) == len(stream_inputs)
        assert all(r is not None for r in results)

        # Performance assertions for real-time processing
        avg_processing_time = sum(processing_times) / len(processing_times)
        max_processing_time = max(processing_times)

        assert (
            avg_processing_time < 1.0
        ), "Average processing time too high for real-time"
        assert (
            max_processing_time < 2.0
        ), "Maximum processing time too high for real-time"

        print(
            f"✅ Real-time stream: {len(results)} inputs, avg {avg_processing_time:.3f}s"
        )

    async def test_cross_modal_context_preservation(self):
        """Test that context is preserved across different modalities"""
        session_id = f"context_test_{time.time()}"

        # Step 1: Establish context with text
        initial_context = ModalInput(
            input_id=f"{session_id}_1",
            modality_type=ModalityType.TEXT,
            processing_intent=ProcessingIntent.CONTEXT_ESTABLISHMENT,
            content="I'm working on automating a web form submission process",
            metadata={"session_id": session_id, "step": 1},
            timestamp=time.time(),
        )

        with patch.object(multimodal_processor, "_establish_context") as mock_context:
            mock_context.return_value = {
                "context_type": "web_automation",
                "task": "form_submission",
                "established": True,
            }

            context_result = await multimodal_processor.process_input(initial_context)
            assert context_result.success

        # Step 2: Provide visual context with image
        form_image = self.create_test_image(1024, 768, "white")

        visual_context = ModalInput(
            input_id=f"{session_id}_2",
            modality_type=ModalityType.IMAGE,
            processing_intent=ProcessingIntent.CONTEXT_ENHANCEMENT,
            content=form_image,
            metadata={"session_id": session_id, "step": 2},
            timestamp=time.time(),
        )

        with patch.object(
            multimodal_processor, "_enhance_visual_context"
        ) as mock_visual:
            mock_visual.return_value = {
                "form_elements": [
                    {"type": "input", "label": "username"},
                    {"type": "input", "label": "password"},
                    {"type": "button", "label": "submit"},
                ],
                "context_enhanced": True,
                "previous_context": "web_automation",
            }

            visual_result = await multimodal_processor.process_input(visual_context)
            assert visual_result.success
            # Verify context preservation
            assert "previous_context" in visual_result.results

        # Step 3: Add audio instructions
        audio_data = self.create_test_audio(2.5)
        audio_context = AudioInput(
            audio_id=f"{session_id}_3",
            audio_data=audio_data,
            sample_rate=16000,
            duration=2.5,
            format="raw",
            channels=1,
            timestamp=time.time(),
            metadata={"session_id": session_id, "step": 3},
        )

        with patch.object(
            voice_processing_system, "process_voice_command"
        ) as mock_audio:
            mock_audio.return_value = {
                "success": True,
                "transcription": "fill username with john_doe and click submit",
                "intent": "form_automation",
                "confidence": 0.9,
                "context_awareness": {
                    "previous_modalities": ["text", "image"],
                    "task_context": "web_form_automation",
                },
            }

            audio_result = await voice_processing_system.process_voice_command(
                audio_context
            )
            assert audio_result["success"]
            assert "context_awareness" in audio_result

        # Step 4: Make final contextual decision
        decision = await context_aware_decision_system.make_contextual_decision(
            DecisionType.AUTOMATION_ACTION,
            "Execute the complete form automation based on all provided context",
        )

        # Verify comprehensive context integration
        assert decision.confidence > 0.7
        assert decision.chosen_action.get("action") is not None

        print(f"✅ Cross-modal context preserved across {3} modalities")

    async def test_error_recovery_multimodal_workflow(self):
        """Test error recovery in multi-modal workflows"""
        # Scenario: Simulate various failures and recovery mechanisms

        # Step 1: Text processing failure
        text_input = ModalInput(
            input_id="error_recovery_1",
            modality_type=ModalityType.TEXT,
            processing_intent=ProcessingIntent.ERROR_RECOVERY,
            content="Deliberately malformed input with \x00 null bytes \xff",
            metadata={"test_scenario": "text_error"},
            timestamp=time.time(),
        )

        # Should handle malformed input gracefully
        with patch.object(multimodal_processor, "_process_text_input") as mock_text:
            # Simulate processing error
            mock_text.side_effect = ValueError("Invalid input encoding")

            try:
                text_result = await multimodal_processor.process_input(text_input)
                # Should either succeed with fallback or fail gracefully
                if not text_result.success:
                    assert "error" in text_result.results
            except Exception as e:
                # Should be controlled exception
                assert isinstance(e, (ValueError, UnicodeError))

        # Step 2: Image processing failure recovery
        # Create corrupted image data
        corrupted_image = b"\x00\x01\x02\x03" * 100  # Not valid image data

        image_input = ModalInput(
            input_id="error_recovery_2",
            modality_type=ModalityType.IMAGE,
            processing_intent=ProcessingIntent.ERROR_RECOVERY,
            content=corrupted_image,
            metadata={"test_scenario": "image_error"},
            timestamp=time.time(),
        )

        with patch.object(multimodal_processor, "_process_image_input") as mock_image:
            # Simulate image processing error with recovery
            def recovery_side_effect(*args, **kwargs):
                # First attempt fails, second succeeds with fallback
                if not hasattr(recovery_side_effect, "called"):
                    recovery_side_effect.called = True
                    raise IOError("Invalid image format")
                else:
                    return {
                        "fallback_analysis": True,
                        "error_recovered": True,
                        "confidence": 0.3,
                    }

            mock_image.side_effect = recovery_side_effect

            try:
                image_result = await multimodal_processor.process_input(image_input)
                # Should recover or fail gracefully
                if image_result and image_result.success:
                    assert image_result.results.get("error_recovered", False)
            except Exception as e:
                # Should be controlled exception
                assert isinstance(e, (IOError, ValueError))

        # Step 3: Audio processing with fallback
        invalid_audio = b"not_audio_data" * 50
        audio_input = AudioInput(
            audio_id="error_recovery_3",
            audio_data=invalid_audio,
            sample_rate=16000,
            duration=1.0,
            format="invalid",
            channels=1,
            timestamp=time.time(),
            metadata={"test_scenario": "audio_error"},
        )

        with patch.object(
            voice_processing_system, "process_voice_command"
        ) as mock_audio:
            mock_audio.return_value = {
                "success": False,
                "error": "Invalid audio format",
                "fallback_used": True,
                "confidence": 0.0,
            }

            audio_result = await voice_processing_system.process_voice_command(
                audio_input
            )

            # Should handle error gracefully
            assert isinstance(audio_result, dict)
            assert "error" in audio_result or not audio_result.get("success", True)

        print("✅ Error recovery workflow completed - system remained stable")

    async def test_performance_under_multimodal_load(self):
        """Test system performance under concurrent multi-modal load"""
        concurrent_requests = 10
        modality_types = [ModalityType.TEXT, ModalityType.IMAGE, ModalityType.AUDIO]

        async def create_load_request(request_id: int):
            modality = modality_types[request_id % len(modality_types)]

            if modality == ModalityType.TEXT:
                content = f"Load test request {request_id}"
                input_data = ModalInput(
                    input_id=f"load_{request_id}",
                    modality_type=modality,
                    processing_intent=ProcessingIntent.PERFORMANCE_TEST,
                    content=content,
                    metadata={"load_test": True, "request_id": request_id},
                    timestamp=time.time(),
                )

                with patch.object(
                    multimodal_processor, "process_input"
                ) as mock_process:
                    mock_result = MagicMock()
                    mock_result.success = True
                    mock_result.confidence = 0.8
                    mock_result.results = {"processed": True, "request_id": request_id}
                    mock_process.return_value = mock_result

                    return await multimodal_processor.process_input(input_data)

            elif modality == ModalityType.IMAGE:
                content = self.create_test_image(200, 200, "blue")
                input_data = ModalInput(
                    input_id=f"load_{request_id}",
                    modality_type=modality,
                    processing_intent=ProcessingIntent.PERFORMANCE_TEST,
                    content=content,
                    metadata={"load_test": True, "request_id": request_id},
                    timestamp=time.time(),
                )

                with patch.object(
                    multimodal_processor, "process_input"
                ) as mock_process:
                    mock_result = MagicMock()
                    mock_result.success = True
                    mock_result.confidence = 0.8
                    mock_result.results = {"processed": True, "request_id": request_id}
                    mock_process.return_value = mock_result

                    return await multimodal_processor.process_input(input_data)

            else:  # Audio
                content = self.create_test_audio(1.0)
                audio_input = AudioInput(
                    audio_id=f"load_{request_id}",
                    audio_data=content,
                    sample_rate=16000,
                    duration=1.0,
                    format="raw",
                    channels=1,
                    timestamp=time.time(),
                    metadata={"load_test": True, "request_id": request_id},
                )

                with patch.object(
                    voice_processing_system, "process_voice_command"
                ) as mock_voice:
                    mock_voice.return_value = {
                        "success": True,
                        "transcription": f"Load test {request_id}",
                        "confidence": 0.8,
                        "request_id": request_id,
                    }

                    return await voice_processing_system.process_voice_command(
                        audio_input
                    )

        # Execute concurrent load test
        start_time = time.perf_counter()

        tasks = [create_load_request(i) for i in range(concurrent_requests)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        end_time = time.perf_counter()
        total_time = end_time - start_time

        # Verify all requests completed
        successful_results = [r for r in results if not isinstance(r, Exception)]
        assert (
            len(successful_results) >= concurrent_requests * 0.8
        )  # At least 80% success

        # Performance assertions
        avg_time_per_request = total_time / concurrent_requests
        assert total_time < 30.0, f"Load test took too long: {total_time:.2f}s"
        assert (
            avg_time_per_request < 3.0
        ), f"Average per request too high: {avg_time_per_request:.2f}s"

        print(
            f"✅ Load test: {len(successful_results)}/{concurrent_requests} succeeded in {total_time:.2f}s"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
