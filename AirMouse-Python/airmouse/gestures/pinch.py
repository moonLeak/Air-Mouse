from __future__ import annotations

import time
from collections import deque
from typing import Any, Deque, Dict, Optional

import numpy as np


class PinchClickGesture:
    """Detect thumb-index pinch for left click/drag interactions."""

    def __init__(
        self,
        window_size: int = 5,
        stability_duration: float = 0.2,
        threshold_margin: float = 0.15,
        low_speed_threshold: float = 200.0,
        freeze_thresholds_during_hold: bool = False,
    ) -> None:
        self.window_size = window_size
        self.stability_duration = stability_duration
        self.threshold_margin = threshold_margin
        self.low_speed_threshold = low_speed_threshold
        self.freeze_thresholds_during_hold = freeze_thresholds_during_hold

        self.is_holding = False
        self.is_pitching = False
        self.click_return_level: Optional[float] = None
        self.release_return_level_up: Optional[float] = None
        self.release_return_level_low: Optional[float] = None
        self.release_return_level: Optional[float] = None
        self.start_time: Optional[float] = None

        self.normalized_distance_window: Deque[float] = deque(maxlen=window_size)
        self.dynamic_line_history: Deque[float] = deque(maxlen=300)
        self.dynamic_threshold_low_history: Deque[float] = deque(maxlen=300)
        self.dynamic_threshold_high_history: Deque[float] = deque(maxlen=300)
        self.normalized_history: Deque[float] = deque(maxlen=300)
        self._last_debug_state: Dict[str, Any] = {
            "stage": "init",
            "action": None,
            "is_holding": self.is_holding,
            "is_pitching": self.is_pitching,
            "elapsed": None,
        }

    def _record_debug(self, *, stage: str, action: Optional[str], elapsed: Optional[float]) -> None:
        self._last_debug_state = {
            "stage": stage,
            "action": action,
            "is_holding": self.is_holding,
            "is_pitching": self.is_pitching,
            "elapsed": elapsed,
        }

    def get_debug_state(self) -> Dict[str, Any]:
        return dict(self._last_debug_state)

    def update(self, normalized_distance: float, hand_speed: float) -> Optional[str]:
        # Optionally freeze dynamic thresholds while holding (pre-pitch)
        if not (self.freeze_thresholds_during_hold and self.is_holding and not self.is_pitching):
            self.normalized_distance_window.append(normalized_distance)

        if len(self.normalized_distance_window) < self.window_size:
            self._record_debug(stage="warmup", action=None, elapsed=None)
            return None

        dynamic_line = float(np.median(list(self.normalized_distance_window)))
        dynamic_threshold_low = dynamic_line - self.threshold_margin
        dynamic_threshold_high = dynamic_line + self.threshold_margin

        self.dynamic_line_history.append(dynamic_line)
        self.dynamic_threshold_low_history.append(dynamic_threshold_low)
        self.dynamic_threshold_high_history.append(dynamic_threshold_high)
        self.normalized_history.append(normalized_distance)

        action: Optional[str] = None
        stage = "hold_check"

        if not self.is_holding:
            if normalized_distance < dynamic_threshold_low:
                self.is_holding = True
                stage = "enter_hold"
                self.start_time = time.time()
                self.click_return_level = dynamic_threshold_low
                self.release_return_level_up = dynamic_line
            else:
                stage = "await_hold"
            self._record_debug(stage=stage, action=None, elapsed=None)
            return None

        elapsed = time.time() - (self.start_time or time.time())
        stage = "holding"

        if not self.is_pitching:
            if elapsed <= self.stability_duration and normalized_distance > (self.click_return_level or 0):
                self.is_holding = False
                action = "click"
                stage = "click"
            elif elapsed > self.stability_duration:
                self.is_pitching = True
                self.release_return_level_low = dynamic_line
                if self.release_return_level_up is not None:
                    self.release_return_level = self.release_return_level_low + (
                        (self.release_return_level_up - self.release_return_level_low) / 4.0
                    )
                action = "pitch"
                stage = "pitch"
            else:
                stage = "holding"
        else:
            release_condition = (
                normalized_distance > dynamic_threshold_high
                or (
                    self.release_return_level is not None
                    and dynamic_line > self.release_return_level
                )
            )
            if release_condition:
                if hand_speed > self.low_speed_threshold:
                    stage = "skip_release_speed"
                else:
                    self.is_holding = False
                    self.is_pitching = False
                    action = "release"
                    stage = "release"
            else:
                stage = "holding"
        self._record_debug(stage=stage, action=action, elapsed=elapsed)
        return action

    def reset(self) -> None:
        self.is_holding = False
        self.is_pitching = False
        self.click_return_level = None
        self.release_return_level_up = None
        self.release_return_level_low = None
        self.release_return_level = None
        self.start_time = None
        self.normalized_distance_window.clear()
        self.dynamic_line_history.clear()
        self.dynamic_threshold_low_history.clear()
        self.dynamic_threshold_high_history.clear()
        self.normalized_history.clear()
        self._record_debug(stage="reset", action=None, elapsed=None)
