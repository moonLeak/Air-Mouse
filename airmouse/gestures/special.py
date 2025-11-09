"""Special gesture recognisers for system-level controls.

This module centralises the recognition of non-primary gestures such as
closed-fist holds. Future gestures (wave, thumbs-up, etc.) can be added here.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from airmouse.utils import calculate_distance


@dataclass
class FistGestureConfig:
    """Configuration for fist/closed-hand detection."""

    hold_duration: float = 3.0
    distance_ratio_threshold: float = 0.28


class SpecialGestureRecognizer:
    """Recognise special gestures such as a sustained fist."""

    def __init__(self, fist_config: Optional[FistGestureConfig] = None) -> None:
        self.fist_config = fist_config or FistGestureConfig()
        self._fist_started_at: Optional[float] = None
        self._fist_active = False

    def update(self, hand_landmarks) -> Optional[str]:
        """Update recogniser state and return an action string when triggered."""

        if hand_landmarks is None:
            self._reset_fist_state()
            return None

        is_fist = self._is_fist_closed(hand_landmarks)
        now = time.time()

        if is_fist:
            if not self._fist_active:
                self._fist_active = True
                self._fist_started_at = now
            elif (
                self._fist_started_at is not None
                and now - self._fist_started_at >= self.fist_config.hold_duration
            ):
                self._reset_fist_state()
                return "fist_hold_exit"
        else:
            self._reset_fist_state()

        return None

    def _is_fist_closed(self, hand_landmarks) -> bool:
        wrist = hand_landmarks.landmark[0]
        middle_mcp = hand_landmarks.landmark[9]

        reference_distance = calculate_distance(wrist, middle_mcp)
        if reference_distance == 0:
            return False

        finger_tip_indices = [4, 8, 12, 16, 20]
        closed_count = 0

        for tip_index in finger_tip_indices:
            tip = hand_landmarks.landmark[tip_index]
            distance = calculate_distance(wrist, tip)
            ratio = distance / reference_distance
            if ratio <= self.fist_config.distance_ratio_threshold:
                closed_count += 1

        # Consider it a fist when most finger tips are close to the wrist.
        return closed_count >= 4

    def _reset_fist_state(self) -> None:
        self._fist_active = False
        self._fist_started_at = None

    def get_debug_state(self) -> dict[str, float | bool]:
        elapsed = 0.0
        if self._fist_active and self._fist_started_at is not None:
            elapsed = time.time() - self._fist_started_at
        return {
            "fist_active": self._fist_active,
            "fist_elapsed": elapsed,
            "fist_hold_duration": self.fist_config.hold_duration,
        }
