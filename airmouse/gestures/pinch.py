from __future__ import annotations

import time
from collections import deque
from typing import Deque, Optional

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
        testing_output: bool = False,
    ) -> None:
        self.window_size = window_size
        self.stability_duration = stability_duration
        self.threshold_margin = threshold_margin
        self.low_speed_threshold = low_speed_threshold
        self.freeze_thresholds_during_hold = freeze_thresholds_during_hold
        self.testing_output = testing_output

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

    def _debug_state(
        self,
        *,
        stage: str,
        normalized_distance: float,
        dynamic_line: Optional[float],
        dynamic_threshold_low: Optional[float],
        dynamic_threshold_high: Optional[float],
        hand_speed: float,
        action: Optional[str],
        elapsed: Optional[float],
        window_len: int,
    ) -> None:
        if not self.testing_output:
            return

        def _fmt(value: Optional[float]) -> str:
            if value is None:
                return "None"
            return f"{value:.3f}"

        action_label = action or "None"
        elapsed_str = _fmt(elapsed)
        print(
            "[PinchTest]",
            f"stage={stage}","\t",
            f"action={action_label}","\t",
            f"hold={self.is_holding}","\t",
            f"pitch={self.is_pitching}","\t",
            f"elapsed={elapsed_str}","\t",
        )

    def update(self, normalized_distance: float, hand_speed: float) -> Optional[str]:
        # Optionally freeze dynamic thresholds while holding (pre-pitch)
        if not (self.freeze_thresholds_during_hold and self.is_holding and not self.is_pitching):
            self.normalized_distance_window.append(normalized_distance)

        if len(self.normalized_distance_window) < self.window_size:
            self._debug_state(
                stage="warmup",
                normalized_distance=normalized_distance,
                dynamic_line=None,
                dynamic_threshold_low=None,
                dynamic_threshold_high=None,
                hand_speed=hand_speed,
                action=None,
                elapsed=None,
                window_len=len(self.normalized_distance_window),
            )
            return None

        dynamic_line = float(np.median(list(self.normalized_distance_window)))
        dynamic_threshold_low = dynamic_line - self.threshold_margin
        dynamic_threshold_high = dynamic_line + self.threshold_margin

        self.dynamic_line_history.append(dynamic_line)
        self.dynamic_threshold_low_history.append(dynamic_threshold_low)
        self.dynamic_threshold_high_history.append(dynamic_threshold_high)
        self.normalized_history.append(normalized_distance)

        window_len = len(self.normalized_distance_window)
        action: Optional[str] = None
        stage = "hold_check"

        if not self.is_holding:
            if normalized_distance < dynamic_threshold_low:
                self.is_holding = True
                self.start_time = time.time()
                self.click_return_level = dynamic_threshold_low
                self.release_return_level_up = dynamic_line
                stage = "enter_hold"
            else:
                stage = "await_hold"
            self._debug_state(
                stage=stage,
                normalized_distance=normalized_distance,
                dynamic_line=dynamic_line,
                dynamic_threshold_low=dynamic_threshold_low,
                dynamic_threshold_high=dynamic_threshold_high,
                hand_speed=hand_speed,
                action=None,
                elapsed=None,
                window_len=window_len,
            )
            return None

        elapsed = time.time() - (self.start_time or time.time())
        stage = "holding"

        if not self.is_pitching:
            if elapsed <= self.stability_duration and normalized_distance > (self.click_return_level or 0):
                self.is_holding = False
                action = "click"
                stage = "click"
            if elapsed > self.stability_duration:
                self.is_pitching = True
                self.release_return_level_low = dynamic_line
                if self.release_return_level_up is not None:
                    self.release_return_level = self.release_return_level_low + (
                        (self.release_return_level_up - self.release_return_level_low) / 4.0
                    )
                action = "pitch"
                stage = "pitch"

        if action is None:
            release_condition = (
                normalized_distance > dynamic_threshold_high
                or dynamic_line > (self.release_return_level or float("inf"))
            )
            if release_condition:
                if hand_speed > self.low_speed_threshold:
                    stage = "skip_rel_s"
                else:
                    self.is_holding = False
                    self.is_pitching = False
                    action = "release"
                    stage = "release"
            else:
                stage = "holding"

        self._debug_state(
            stage=stage,
            normalized_distance=normalized_distance,
            dynamic_line=dynamic_line,
            dynamic_threshold_low=dynamic_threshold_low,
            dynamic_threshold_high=dynamic_threshold_high,
            hand_speed=hand_speed,
            action=action,
            elapsed=elapsed,
            window_len=window_len,
        )
        return action
