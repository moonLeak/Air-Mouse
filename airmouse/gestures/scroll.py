from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional, Sequence, Tuple

import numpy as np


@dataclass
class GestureAction:
    kind: str
    dx: int = 0
    dy: int = 0


class ScrollGesture:
    """Detect thumb-middle pinch for right-click and scrolling."""

    def __init__(
        self,
        window_size: int = 5,
        stability_duration: float = 0.25,
        threshold_margin: float = 0.15,
        stability_radius: float = 30.0,
        low_speed_threshold: float = 200.0,
        smoothness: float = 0.8,
        decay: float = 0.9,
        speed_factor: float = 0.5,
    ) -> None:
        self.window_size = window_size
        self.stability_duration = stability_duration
        self.threshold_margin = threshold_margin
        self.stability_radius = stability_radius
        self.low_speed_threshold = low_speed_threshold
        self.smoothness = smoothness
        self.decay = decay
        self.speed_factor = speed_factor

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

        self.scroll_active = False
        self.scroll_speed_x = 0.0
        self.scroll_speed_y = 0.0
        self.scroll_anchor: Optional[Tuple[float, float]] = None

    def update(
        self,
        normalized_distance: float,
        current_position: Tuple[int, int],
        anchor_position: Optional[Tuple[int, int]],
        hand_speed: float,
    ) -> List[GestureAction]:
        actions: List[GestureAction] = []

        self.normalized_distance_window.append(normalized_distance)
        if len(self.normalized_distance_window) < self.window_size:
            return actions

        dynamic_line = float(np.median(list(self.normalized_distance_window)))
        dynamic_threshold_low = dynamic_line - self.threshold_margin
        dynamic_threshold_high = dynamic_line + self.threshold_margin

        self.dynamic_line_history.append(dynamic_line)
        self.dynamic_threshold_low_history.append(dynamic_threshold_low)
        self.dynamic_threshold_high_history.append(dynamic_threshold_high)
        self.normalized_history.append(normalized_distance)

        if not self.is_holding:
            if normalized_distance < dynamic_threshold_low:
                self.is_holding = True
                self.start_time = time.time()
                self.click_return_level = dynamic_threshold_low
                self.release_return_level_up = dynamic_line
            return actions

        elapsed = time.time() - (self.start_time or time.time())

        if not self.is_pitching:
            if elapsed <= self.stability_duration and normalized_distance > (self.click_return_level or 0):
                self.is_holding = False
                actions.append(GestureAction(kind="right_click"))
                self._reset_scroll_state()
                return actions

            if (
                (anchor_position is not None and self._distance(current_position, anchor_position) > self.stability_radius)
                or (elapsed > self.stability_duration)
            ):
                self.is_pitching = True
                self.release_return_level_low = dynamic_line
                if self.release_return_level_up is not None:
                    self.release_return_level = self.release_return_level_low + (
                        (self.release_return_level_up - self.release_return_level_low) / 4.0
                    )
                self.scroll_active = True
                self.scroll_anchor = current_position
                actions.append(GestureAction(kind="scroll_start"))
                return actions

        should_release = (
            normalized_distance > dynamic_threshold_high
            or dynamic_line > (self.release_return_level or float("inf"))
        )

        if should_release:
            if hand_speed <= self.low_speed_threshold:
                self.is_holding = False
                self.is_pitching = False
                if self.scroll_active:
                    actions.append(GestureAction(kind="scroll_end"))
                self.scroll_active = False
                self.scroll_anchor = None
            return actions

        if self.scroll_active:
            if self.scroll_anchor is None:
                self.scroll_anchor = current_position

            delta_x = (self.scroll_anchor[0] - current_position[0]) * self.speed_factor
            delta_y = (self.scroll_anchor[1] - current_position[1]) * self.speed_factor

            self.scroll_speed_x = delta_x
            self.scroll_speed_y = delta_y
            self.scroll_anchor = current_position

            if abs(delta_x) > 0 or abs(delta_y) > 0:
                actions.append(
                    GestureAction(
                        kind="scroll",
                        dx=-int(delta_x),
                        dy=-int(delta_y),
                    )
                )
        else:
            decay_x = self.scroll_speed_x * self.smoothness
            decay_y = self.scroll_speed_y * self.smoothness
            if abs(decay_x) > 1 or abs(decay_y) > 1:
                actions.append(
                    GestureAction(
                        kind="scroll",
                        dx=-int(decay_x),
                        dy=-int(decay_y),
                    )
                )
                self.scroll_speed_x *= self.decay
                self.scroll_speed_y *= self.decay
            else:
                self.scroll_speed_x *= self.decay
                self.scroll_speed_y *= self.decay

        return actions

    def _reset_scroll_state(self) -> None:
        self.scroll_active = False
        self.scroll_anchor = None
        self.scroll_speed_x = 0.0
        self.scroll_speed_y = 0.0

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
        self._reset_scroll_state()

    @staticmethod
    def _distance(a: Sequence[float], b: Sequence[float]) -> float:
        return float(np.linalg.norm([a[0] - b[0], a[1] - b[1]]))
