# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
VNC Human-like Behavior Helpers
Issue #74 - Area 5: Automation Features

Provides functions to add realistic human-like behavior to desktop automation:
- Random offsets for mouse clicks
- Variable typing speeds
- Curved mouse movements
- Realistic pauses and delays
"""

import math
import random
from typing import Tuple


def humanize_click_position(x: int, y: int, radius: int = 5) -> Tuple[int, int]:
    """
    Add random offset to click coordinates to mimic human imprecision.

    Args:
        x: Original X coordinate
        y: Original Y coordinate
        radius: Maximum offset in pixels (default: 5)

    Returns:
        Tuple of (humanized_x, humanized_y) with random offset applied
    """
    offset_x = random.randint(-radius, radius)
    offset_y = random.randint(-radius, radius)
    return (max(0, x + offset_x), max(0, y + offset_y))


def humanize_typing_speed() -> float:
    """
    Generate realistic delay between keypresses (in seconds).

    Returns:
        Random delay between 0.05s and 0.15s (typical human typing speed)
    """
    return random.uniform(0.05, 0.15)


def humanize_action_delay() -> float:
    """
    Generate realistic delay before starting an action (in seconds).

    Returns:
        Random delay between 0.1s and 0.3s (human reaction time)
    """
    return random.uniform(0.1, 0.3)


def humanize_mouse_movement_delay() -> float:
    """
    Generate realistic delay during mouse movement (in seconds).

    Returns:
        Random delay between 0.01s and 0.03s for smooth movement
    """
    return random.uniform(0.01, 0.03)


def simulate_mouse_curve(
    x1: int, y1: int, x2: int, y2: int, steps: int = 10
) -> list[Tuple[int, int]]:
    """
    Generate intermediate points for realistic curved mouse movement.

    Instead of instant teleport or straight line, generates a slightly curved
    path with random deviation to simulate natural mouse movement.

    Args:
        x1: Start X coordinate
        y1: Start Y coordinate
        x2: End X coordinate
        y2: End Y coordinate
        steps: Number of intermediate points (default: 10)

    Returns:
        List of (x, y) tuples forming a curved path from start to end
    """
    points = []

    # Calculate distance to adjust step count for longer movements
    distance = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
    adjusted_steps = max(5, min(20, int(distance / 50)))  # 5-20 steps based on distance

    for i in range(adjusted_steps + 1):
        # Linear interpolation
        t = i / adjusted_steps
        x = int(x1 + (x2 - x1) * t)
        y = int(y1 + (y2 - y1) * t)

        # Add slight curve/wobble for realism (perpendicular offset)
        if i > 0 and i < adjusted_steps:
            # Calculate perpendicular direction
            dx = x2 - x1
            dy = y2 - y1
            length = math.sqrt(dx * dx + dy * dy)

            if length > 0:
                # Perpendicular vector
                perp_x = -dy / length
                perp_y = dx / length

                # Sine wave for smooth curve
                curve_amount = math.sin(t * math.pi) * random.uniform(2, 8)

                x += int(perp_x * curve_amount)
                y += int(perp_y * curve_amount)

        points.append((max(0, x), max(0, y)))

    return points


def humanize_key_press_timing() -> Tuple[float, float]:
    """
    Generate realistic key press and release timing (in seconds).

    Returns:
        Tuple of (press_duration, release_delay)
        - press_duration: How long the key is held down (0.05-0.12s)
        - release_delay: Delay before next action (0.03-0.08s)
    """
    press_duration = random.uniform(0.05, 0.12)
    release_delay = random.uniform(0.03, 0.08)
    return (press_duration, release_delay)


def should_add_human_pause() -> bool:
    """
    Randomly decide if a human-like pause should be added.

    Humans don't type or act continuously - they pause to think or look at the screen.

    Returns:
        True if a pause should be added (20% chance), False otherwise
    """
    return random.random() < 0.2


def humanize_pause_duration() -> float:
    """
    Generate realistic pause duration when human stops to think (in seconds).

    Returns:
        Random pause between 0.5s and 2.0s
    """
    return random.uniform(0.5, 2.0)
