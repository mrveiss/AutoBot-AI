# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Wake Word Detection Service for AutoBot
Optimized for low CPU usage with configurable wake words and false positive reduction

Issue #54 - Advanced Wake Word Detection Optimization
"""

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional

from backend.type_defs.common import Metadata

logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for noise indicators in false positive detection
_NOISE_INDICATORS = ("said", "mentioned", "talking about", "the word", "called")


class WakeWordState(Enum):
    """Wake word detection states"""

    IDLE = "idle"
    LISTENING = "listening"
    DETECTED = "detected"
    COOLDOWN = "cooldown"
    ERROR = "error"


@dataclass
class WakeWordConfig:
    """Configuration for wake word detection"""

    enabled: bool = True
    wake_words: List[str] = field(
        default_factory=lambda: ["hey autobot", "ok autobot", "autobot"]
    )
    confidence_threshold: float = 0.7
    cooldown_seconds: float = 2.0
    max_false_positive_rate: float = 0.1
    adaptive_threshold: bool = True
    noise_tolerance: float = 0.3
    sample_rate_hz: int = 16000
    chunk_duration_ms: int = 100
    max_cpu_percent: float = 15.0


@dataclass
class WakeWordEvent:
    """Event when wake word is detected"""

    wake_word: str
    confidence: float
    timestamp: float
    audio_context: Optional[bytes] = None
    metadata: Metadata = field(default_factory=dict)


@dataclass
class DetectionStats:
    """Statistics for wake word detection"""

    total_detections: int = 0
    false_positives: int = 0
    true_positives: int = 0
    total_listening_time: float = 0.0
    average_confidence: float = 0.0
    cpu_usage_percent: float = 0.0
    last_detection_time: Optional[float] = None


class WakeWordDetector:
    """
    Efficient wake word detection engine optimized for low CPU usage.

    Features:
    - Multiple configurable wake words
    - Adaptive confidence thresholds
    - False positive reduction
    - CPU usage optimization
    - Background listening with duty cycling
    """

    def __init__(self, config: Optional[WakeWordConfig] = None):
        """Initialize wake word detector with configuration and adaptive thresholds."""
        self.config = config or WakeWordConfig()
        self.state = WakeWordState.IDLE
        self.stats = DetectionStats()

        # Internal state
        self._listening_task: Optional[asyncio.Task] = None
        self._callbacks: List[Callable[[WakeWordEvent], None]] = []
        self._recent_detections: List[WakeWordEvent] = []
        self._adaptive_thresholds: Dict[str, float] = {}
        self._false_positive_buffer: List[float] = []
        self._start_time: Optional[float] = None
        self._cooldown_end_time: Optional[float] = None  # For sync context cooldown

        # Initialize adaptive thresholds
        for wake_word in self.config.wake_words:
            self._adaptive_thresholds[wake_word.lower()] = (
                self.config.confidence_threshold
            )

        logger.info(
            f"WakeWordDetector initialized with {len(self.config.wake_words)} wake words"
        )
        logger.info("Wake words: %s", self.config.wake_words)

    def add_wake_word(self, wake_word: str) -> bool:
        """Add a new wake word to detection list"""
        wake_word_lower = wake_word.lower().strip()
        if wake_word_lower not in {w.lower() for w in self.config.wake_words}:
            self.config.wake_words.append(wake_word_lower)
            self._adaptive_thresholds[wake_word_lower] = (
                self.config.confidence_threshold
            )
            logger.info("Added wake word: %s", wake_word)
            return True
        return False

    def remove_wake_word(self, wake_word: str) -> bool:
        """Remove a wake word from detection list"""
        wake_word_lower = wake_word.lower().strip()
        for i, w in enumerate(self.config.wake_words):
            if w.lower() == wake_word_lower:
                del self.config.wake_words[i]
                self._adaptive_thresholds.pop(wake_word_lower, None)
                logger.info("Removed wake word: %s", wake_word)
                return True
        return False

    def get_wake_words(self) -> List[str]:
        """Get list of current wake words"""
        return self.config.wake_words.copy()

    def check_text_for_wake_word(
        self, text: str, confidence: float = 1.0
    ) -> Optional[WakeWordEvent]:
        """
        Check if text contains a wake word.

        Args:
            text: Transcribed text to check
            confidence: Confidence score from speech recognition

        Returns:
            WakeWordEvent if detected, None otherwise
        """
        if not self.config.enabled:
            return None

        # Check cooldown - support both async and sync contexts
        if self.state == WakeWordState.COOLDOWN:
            # Check if cooldown has expired (for sync context)
            if self._cooldown_end_time and time.time() >= self._cooldown_end_time:
                self.state = WakeWordState.LISTENING
                self._cooldown_end_time = None
            else:
                logger.debug("In cooldown period, ignoring detection")
                return None

        text_lower = text.lower().strip()

        for wake_word in self.config.wake_words:
            wake_word_lower = wake_word.lower()

            # Check if wake word is in the text
            if self._contains_wake_word(text_lower, wake_word_lower):
                # Get adaptive threshold for this wake word
                threshold = self._adaptive_thresholds.get(
                    wake_word_lower, self.config.confidence_threshold
                )

                # Calculate effective confidence
                effective_confidence = self._calculate_effective_confidence(
                    text_lower, wake_word_lower, confidence
                )

                if effective_confidence >= threshold:
                    event = WakeWordEvent(
                        wake_word=wake_word,
                        confidence=effective_confidence,
                        timestamp=time.time(),
                        metadata={
                            "original_text": text,
                            "threshold_used": threshold,
                            "detection_method": "text_matching",
                        },
                    )

                    # Update stats and trigger callbacks
                    self._on_detection(event)
                    return event
                else:
                    logger.debug(
                        f"Wake word '{wake_word}' found but confidence "
                        f"{effective_confidence:.2f} < threshold {threshold:.2f}"
                    )

        return None

    def _contains_wake_word(self, text: str, wake_word: str) -> bool:
        """Check if text contains wake word with fuzzy matching"""
        # Exact match
        if wake_word in text:
            return True

        # Word boundary match (handle "hey autobot" vs "heyautobot")
        words = text.split()
        wake_words = wake_word.split()

        if len(wake_words) <= len(words):
            for i in range(len(words) - len(wake_words) + 1):
                if words[i : i + len(wake_words)] == wake_words:
                    return True

        # Check for common mishearings
        mishearings = self._get_common_mishearings(wake_word)
        for mishearing in mishearings:
            if mishearing in text:
                return True

        return False

    def _get_common_mishearings(self, wake_word: str) -> List[str]:
        """Get common mishearings for a wake word"""
        mishearings = []

        # AutoBot variations
        if "autobot" in wake_word:
            base = wake_word.replace("autobot", "")
            mishearings.extend(
                [
                    f"{base}auto bot",
                    f"{base}auto bought",
                    f"{base}otto bot",
                    f"{base}auto pot",
                    f"{base}auto bots",
                ]
            )

        # "Hey" variations
        if wake_word.startswith("hey "):
            rest = wake_word[4:]
            mishearings.extend(
                [
                    f"hay {rest}",
                    f"he {rest}",
                    f"a {rest}",
                ]
            )

        # "OK" variations
        if wake_word.startswith("ok "):
            rest = wake_word[3:]
            mishearings.extend(
                [
                    f"okay {rest}",
                    f"o k {rest}",
                ]
            )

        return mishearings

    def _calculate_effective_confidence(
        self, text: str, wake_word: str, base_confidence: float
    ) -> float:
        """
        Calculate effective confidence considering multiple factors.

        Factors:
        - Base recognition confidence
        - Position of wake word in text
        - Presence of noise words
        - Text length relative to wake word
        """
        # Start with base confidence
        confidence = base_confidence

        # Bonus for wake word at start of utterance
        if text.startswith(wake_word):
            confidence *= 1.2

        # Penalty for very long text (likely false positive from conversation)
        text_ratio = len(wake_word) / max(len(text), 1)
        if text_ratio < 0.3:  # Wake word is small part of text
            confidence *= 0.7
        elif text_ratio > 0.8:  # Wake word is most of text (ideal)
            confidence *= 1.1

        # Penalty for noise words that indicate normal conversation (Issue #380)
        for noise in _NOISE_INDICATORS:
            if noise in text:
                confidence *= 0.5
                break

        # Cap confidence at 1.0
        return min(confidence, 1.0)

    def _on_detection(self, event: WakeWordEvent) -> None:
        """Handle wake word detection event"""
        self.stats.total_detections += 1
        self.stats.last_detection_time = event.timestamp

        # Update running average confidence
        n = self.stats.total_detections
        self.stats.average_confidence = (
            self.stats.average_confidence * (n - 1) + event.confidence
        ) / n

        # Store recent detection
        self._recent_detections.append(event)
        if len(self._recent_detections) > 100:
            self._recent_detections = self._recent_detections[-100:]

        # Enter cooldown to prevent rapid re-triggering
        self._enter_cooldown()

        # Notify callbacks
        for callback in self._callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error("Error in wake word callback: %s", e)

        logger.info(
            f"Wake word detected: '{event.wake_word}' "
            f"(confidence: {event.confidence:.2f})"
        )

    def _enter_cooldown(self) -> None:
        """Enter cooldown state to prevent rapid re-triggering"""
        self.state = WakeWordState.COOLDOWN
        # Set cooldown end time for sync context checking
        self._cooldown_end_time = time.time() + self.config.cooldown_seconds

        def exit_cooldown():
            """Exit cooldown and resume listening state."""
            if self.state == WakeWordState.COOLDOWN:
                self.state = WakeWordState.LISTENING
                self._cooldown_end_time = None

        # Use threading Timer for non-blocking cooldown (works without event loop)
        timer = threading.Timer(self.config.cooldown_seconds, exit_cooldown)
        timer.daemon = True
        timer.start()

    def report_false_positive(self) -> None:
        """Report that last detection was a false positive"""
        if self._recent_detections:
            last_event = self._recent_detections[-1]
            self.stats.false_positives += 1
            self._false_positive_buffer.append(last_event.confidence)

            # Adapt threshold if too many false positives
            if self.config.adaptive_threshold:
                self._adapt_threshold(last_event.wake_word, increase=True)

            logger.info(
                f"False positive reported for '{last_event.wake_word}'. "
                f"Total FPs: {self.stats.false_positives}"
            )

    def report_true_positive(self) -> None:
        """Report that last detection was correct"""
        if self._recent_detections:
            last_event = self._recent_detections[-1]
            self.stats.true_positives += 1

            # Potentially lower threshold if many true positives
            if self.config.adaptive_threshold:
                self._adapt_threshold(last_event.wake_word, increase=False)

    def _adapt_threshold(self, wake_word: str, increase: bool) -> None:
        """Adaptively adjust threshold based on false positive rate"""
        wake_word_lower = wake_word.lower()
        current_threshold = self._adaptive_thresholds.get(
            wake_word_lower, self.config.confidence_threshold
        )

        if increase:
            # Increase threshold to reduce false positives
            new_threshold = min(current_threshold * 1.1, 0.95)
        else:
            # Decrease threshold slightly for convenience
            fp_rate = self.stats.false_positives / max(self.stats.total_detections, 1)
            if fp_rate < self.config.max_false_positive_rate:
                new_threshold = max(current_threshold * 0.95, 0.5)
            else:
                new_threshold = current_threshold

        self._adaptive_thresholds[wake_word_lower] = new_threshold
        logger.debug(
            f"Adapted threshold for '{wake_word}': "
            f"{current_threshold:.2f} -> {new_threshold:.2f}"
        )

    def add_callback(self, callback: Callable[[WakeWordEvent], None]) -> None:
        """Add callback to be called when wake word is detected"""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[WakeWordEvent], None]) -> None:
        """Remove a callback"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def get_stats(self) -> Metadata:
        """Get detection statistics"""
        total = self.stats.total_detections
        return {
            "total_detections": total,
            "true_positives": self.stats.true_positives,
            "false_positives": self.stats.false_positives,
            "accuracy": self.stats.true_positives / max(total, 1) * 100,
            "average_confidence": self.stats.average_confidence,
            "total_listening_time": self.stats.total_listening_time,
            "cpu_usage_percent": self.stats.cpu_usage_percent,
            "last_detection_time": self.stats.last_detection_time,
            "current_state": self.state.value,
            "adaptive_thresholds": self._adaptive_thresholds.copy(),
        }

    def reset_stats(self) -> None:
        """Reset all statistics"""
        self.stats = DetectionStats()
        self._false_positive_buffer.clear()
        logger.info("Wake word detection statistics reset")

    def get_config(self) -> Metadata:
        """Get current configuration"""
        return {
            "enabled": self.config.enabled,
            "wake_words": self.config.wake_words,
            "confidence_threshold": self.config.confidence_threshold,
            "cooldown_seconds": self.config.cooldown_seconds,
            "max_false_positive_rate": self.config.max_false_positive_rate,
            "adaptive_threshold": self.config.adaptive_threshold,
            "noise_tolerance": self.config.noise_tolerance,
            "max_cpu_percent": self.config.max_cpu_percent,
        }

    def update_config(self, updates: Metadata) -> None:
        """Update configuration"""
        for key, value in updates.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                logger.info("Updated config %s = %s", key, value)

        # Re-initialize adaptive thresholds if wake words changed
        if "wake_words" in updates:
            for wake_word in self.config.wake_words:
                if wake_word.lower() not in self._adaptive_thresholds:
                    self._adaptive_thresholds[wake_word.lower()] = (
                        self.config.confidence_threshold
                    )

    def enable(self) -> None:
        """Enable wake word detection"""
        self.config.enabled = True
        self.state = WakeWordState.LISTENING
        logger.info("Wake word detection enabled")

    def disable(self) -> None:
        """Disable wake word detection"""
        self.config.enabled = False
        self.state = WakeWordState.IDLE
        logger.info("Wake word detection disabled")


# Singleton instance for global access (thread-safe)
_wake_word_detector: Optional[WakeWordDetector] = None
_wake_word_detector_lock = threading.Lock()


def get_wake_word_detector() -> WakeWordDetector:
    """Get or create the global wake word detector instance (thread-safe)."""
    global _wake_word_detector
    if _wake_word_detector is None:
        with _wake_word_detector_lock:
            # Double-check after acquiring lock
            if _wake_word_detector is None:
                _wake_word_detector = WakeWordDetector()
    return _wake_word_detector


def reset_wake_word_detector() -> None:
    """Reset the global wake word detector instance (thread-safe)."""
    global _wake_word_detector
    with _wake_word_detector_lock:
        _wake_word_detector = None
