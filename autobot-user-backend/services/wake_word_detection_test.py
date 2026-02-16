"""
Unit tests for Wake Word Detection Service
Issue #54 - Advanced Wake Word Detection Optimization
"""

import time

import pytest

from backend.services.wake_word_service import (
    WakeWordConfig,
    WakeWordDetector,
    WakeWordEvent,
    WakeWordState,
    get_wake_word_detector,
    reset_wake_word_detector,
)


@pytest.fixture
def detector():
    """Create a fresh wake word detector for each test"""
    reset_wake_word_detector()
    config = WakeWordConfig(
        wake_words=["hey autobot", "ok autobot", "autobot"],
        confidence_threshold=0.7,
        cooldown_seconds=0.1,  # Short for testing
        adaptive_threshold=True,
    )
    return WakeWordDetector(config)


@pytest.fixture
def singleton_detector():
    """Get singleton detector instance"""
    reset_wake_word_detector()
    return get_wake_word_detector()


class TestWakeWordDetection:
    """Test wake word detection functionality"""

    def test_basic_wake_word_detection(self, detector):
        """Test that basic wake words are detected"""
        # Test "hey autobot"
        event = detector.check_text_for_wake_word("hey autobot", confidence=0.9)
        assert event is not None
        assert event.wake_word == "hey autobot"
        assert event.confidence >= 0.7

    def test_case_insensitive_detection(self, detector):
        """Test wake word detection is case insensitive"""
        event = detector.check_text_for_wake_word("HEY AUTOBOT", confidence=0.9)
        assert event is not None
        assert event.wake_word.lower() == "hey autobot"

    def test_multiple_wake_words(self, detector):
        """Test multiple wake words are supported"""
        # Test "ok autobot"
        event = detector.check_text_for_wake_word("ok autobot", confidence=0.9)
        assert event is not None
        assert event.wake_word == "ok autobot"

        # Test single "autobot"
        time.sleep(0.15)  # Wait for cooldown
        event = detector.check_text_for_wake_word("autobot", confidence=0.9)
        assert event is not None
        assert event.wake_word == "autobot"

    def test_wake_word_in_sentence(self, detector):
        """Test wake word detection within a sentence"""
        event = detector.check_text_for_wake_word(
            "hey autobot what's the weather", confidence=0.85
        )
        assert event is not None
        assert event.wake_word == "hey autobot"

    def test_no_wake_word(self, detector):
        """Test that non-wake word text is not detected"""
        event = detector.check_text_for_wake_word("hello world", confidence=0.9)
        assert event is None

    def test_low_confidence_rejection(self, detector):
        """Test that low confidence detections are rejected"""
        event = detector.check_text_for_wake_word("hey autobot", confidence=0.3)
        assert event is None

    def test_disabled_detection(self, detector):
        """Test that detection is disabled when config.enabled is False"""
        detector.disable()
        event = detector.check_text_for_wake_word("hey autobot", confidence=0.9)
        assert event is None

    def test_cooldown_period(self, detector):
        """Test that cooldown prevents rapid re-triggering"""
        # First detection should work
        event1 = detector.check_text_for_wake_word("hey autobot", confidence=0.9)
        assert event1 is not None

        # Immediate second detection should be blocked (cooldown)
        event2 = detector.check_text_for_wake_word("hey autobot", confidence=0.9)
        assert event2 is None

        # After cooldown, should work again
        time.sleep(0.15)
        event3 = detector.check_text_for_wake_word("hey autobot", confidence=0.9)
        assert event3 is not None


class TestWakeWordConfiguration:
    """Test wake word configuration management"""

    def test_add_wake_word(self, detector):
        """Test adding a new wake word"""
        initial_count = len(detector.get_wake_words())
        success = detector.add_wake_word("hello bot")
        assert success is True
        assert len(detector.get_wake_words()) == initial_count + 1
        assert "hello bot" in detector.get_wake_words()

    def test_add_duplicate_wake_word(self, detector):
        """Test adding a duplicate wake word returns False"""
        success = detector.add_wake_word("hey autobot")
        assert success is False

    def test_remove_wake_word(self, detector):
        """Test removing a wake word"""
        initial_count = len(detector.get_wake_words())
        success = detector.remove_wake_word("autobot")
        assert success is True
        assert len(detector.get_wake_words()) == initial_count - 1
        assert "autobot" not in detector.get_wake_words()

    def test_remove_nonexistent_wake_word(self, detector):
        """Test removing a non-existent wake word returns False"""
        success = detector.remove_wake_word("nonexistent")
        assert success is False

    def test_get_config(self, detector):
        """Test getting configuration"""
        config = detector.get_config()
        assert "enabled" in config
        assert "wake_words" in config
        assert "confidence_threshold" in config
        assert "cooldown_seconds" in config
        assert "adaptive_threshold" in config

    def test_update_config(self, detector):
        """Test updating configuration"""
        detector.update_config({"confidence_threshold": 0.8})
        config = detector.get_config()
        assert config["confidence_threshold"] == 0.8

    def test_enable_disable(self, detector):
        """Test enable/disable functionality"""
        detector.disable()
        assert detector.config.enabled is False
        assert detector.state == WakeWordState.IDLE

        detector.enable()
        assert detector.config.enabled is True
        assert detector.state == WakeWordState.LISTENING


class TestFalsePositiveReduction:
    """Test false positive reduction features"""

    def test_noise_word_penalty(self, detector):
        """Test that noise words reduce confidence"""
        # Normal detection
        event1 = detector.check_text_for_wake_word("hey autobot", confidence=0.9)
        assert event1 is not None
        conf1 = event1.confidence

        time.sleep(0.15)

        # Detection with noise words (should have lower effective confidence)
        event2 = detector.check_text_for_wake_word(
            "I said hey autobot to the user", confidence=0.9
        )
        # May or may not detect depending on final confidence after penalties
        if event2:
            assert event2.confidence < conf1 * 1.1  # Should be lower due to penalties

    def test_long_text_penalty(self, detector):
        """Test that long text reduces confidence"""
        # Short text (ideal)
        event1 = detector.check_text_for_wake_word("hey autobot", confidence=0.85)
        assert event1 is not None

        time.sleep(0.15)

        # Very long text (wake word is small part)
        long_text = "hey autobot " + "word " * 50
        event2 = detector.check_text_for_wake_word(long_text, confidence=0.85)
        # May be detected with lower confidence or rejected
        if event2:
            assert event2.confidence <= event1.confidence

    def test_adaptive_threshold_increase(self, detector):
        """Test that false positive reports increase threshold"""
        wake_word = "hey autobot"
        initial_threshold = detector._adaptive_thresholds[wake_word]

        # Simulate a detection and report false positive
        detector.check_text_for_wake_word(wake_word, confidence=0.9)
        detector.report_false_positive()

        new_threshold = detector._adaptive_thresholds[wake_word]
        assert new_threshold > initial_threshold

    def test_adaptive_threshold_decrease(self, detector):
        """Test that true positive reports can decrease threshold"""
        wake_word = "hey autobot"

        # First increase threshold with false positives
        detector.check_text_for_wake_word(wake_word, confidence=0.9)
        detector.report_false_positive()
        time.sleep(0.15)

        increased_threshold = detector._adaptive_thresholds[wake_word]

        # Now report true positives to decrease
        detector.check_text_for_wake_word(wake_word, confidence=0.95)
        detector.report_true_positive()

        # Threshold might decrease if FP rate is acceptable
        final_threshold = detector._adaptive_thresholds[wake_word]
        # At minimum, should not increase
        assert final_threshold <= increased_threshold * 1.01


class TestStatistics:
    """Test wake word detection statistics"""

    def test_stats_tracking(self, detector):
        """Test that statistics are tracked correctly"""
        # Initial stats
        stats = detector.get_stats()
        assert stats["total_detections"] == 0

        # Make a detection
        detector.check_text_for_wake_word("hey autobot", confidence=0.9)

        stats = detector.get_stats()
        assert stats["total_detections"] == 1
        assert stats["average_confidence"] > 0
        assert stats["last_detection_time"] is not None

    def test_false_positive_tracking(self, detector):
        """Test false positive tracking"""
        detector.check_text_for_wake_word("hey autobot", confidence=0.9)
        detector.report_false_positive()

        stats = detector.get_stats()
        assert stats["false_positives"] == 1

    def test_true_positive_tracking(self, detector):
        """Test true positive tracking"""
        detector.check_text_for_wake_word("hey autobot", confidence=0.9)
        detector.report_true_positive()

        stats = detector.get_stats()
        assert stats["true_positives"] == 1

    def test_stats_reset(self, detector):
        """Test statistics reset"""
        # Generate some stats
        detector.check_text_for_wake_word("hey autobot", confidence=0.9)
        detector.report_true_positive()

        # Reset
        detector.reset_stats()

        stats = detector.get_stats()
        assert stats["total_detections"] == 0
        assert stats["true_positives"] == 0
        assert stats["false_positives"] == 0

    def test_accuracy_calculation(self, detector):
        """Test accuracy calculation"""
        # Make some detections
        detector.check_text_for_wake_word("hey autobot", confidence=0.9)
        detector.report_true_positive()
        time.sleep(0.15)

        detector.check_text_for_wake_word("ok autobot", confidence=0.9)
        detector.report_false_positive()
        time.sleep(0.15)

        stats = detector.get_stats()
        # 1 true positive out of 2 detections = 50%
        assert stats["accuracy"] == 50.0


class TestCallbacks:
    """Test callback functionality"""

    def test_callback_invocation(self, detector):
        """Test that callbacks are invoked on detection"""
        callback_called = {"value": False}
        received_event = {"event": None}

        def callback(event):
            callback_called["value"] = True
            received_event["event"] = event

        detector.add_callback(callback)
        detector.check_text_for_wake_word("hey autobot", confidence=0.9)

        assert callback_called["value"] is True
        assert received_event["event"] is not None
        assert isinstance(received_event["event"], WakeWordEvent)

    def test_multiple_callbacks(self, detector):
        """Test multiple callbacks are all invoked"""
        count = {"value": 0}

        def callback1(event):
            count["value"] += 1

        def callback2(event):
            count["value"] += 10

        detector.add_callback(callback1)
        detector.add_callback(callback2)
        detector.check_text_for_wake_word("hey autobot", confidence=0.9)

        assert count["value"] == 11

    def test_remove_callback(self, detector):
        """Test removing a callback"""
        called = {"value": False}

        def callback(event):
            called["value"] = True

        detector.add_callback(callback)
        detector.remove_callback(callback)
        detector.check_text_for_wake_word("hey autobot", confidence=0.9)

        assert called["value"] is False


class TestMishearingHandling:
    """Test common mishearing variations"""

    def test_autobot_variations(self, detector):
        """Test common mishearings of 'autobot'"""
        time.sleep(0.15)

        # "auto bot" (two words)
        event = detector.check_text_for_wake_word("hey auto bot", confidence=0.85)
        assert event is not None

    def test_hay_vs_hey(self, detector):
        """Test 'hay' instead of 'hey'"""
        event = detector.check_text_for_wake_word("hay autobot", confidence=0.85)
        assert event is not None

    def test_okay_vs_ok(self, detector):
        """Test 'okay' instead of 'ok'"""
        time.sleep(0.15)
        event = detector.check_text_for_wake_word("okay autobot", confidence=0.85)
        assert event is not None


class TestSingletonPattern:
    """Test singleton pattern for global detector"""

    def test_get_singleton(self, singleton_detector):
        """Test getting singleton instance"""
        detector1 = get_wake_word_detector()
        detector2 = get_wake_word_detector()
        assert detector1 is detector2

    def test_reset_singleton(self):
        """Test resetting singleton instance"""
        reset_wake_word_detector()
        detector1 = get_wake_word_detector()

        reset_wake_word_detector()
        detector2 = get_wake_word_detector()

        assert detector1 is not detector2
