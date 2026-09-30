from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
import pyautogui
from pynput.mouse import Controller as MouseController, Button


def _detect_screen_size() -> Tuple[int, int]:
    try:
        return pyautogui.size()
    except Exception:
        # Fallback to a safe default when display information is unavailable.
        return 1920, 1080


class MousePointer:
    """Wrapper around pynput mouse controller."""

    def __init__(self, controller: Optional[MouseController] = None) -> None:
        self._controller = controller or MouseController()

    @property
    def position(self) -> Tuple[int, int]:
        pos = self._controller.position
        return int(pos[0]), int(pos[1])

    def move_to(self, x: int, y: int) -> None:
        self._controller.position = (int(x), int(y))

    def click_left(self) -> None:
        self._controller.click(Button.left)

    def press_left(self) -> None:
        self._controller.press(Button.left)

    def release_left(self) -> None:
        self._controller.release(Button.left)

    def click_right(self) -> None:
        self._controller.click(Button.right)

    def scroll(self, dx: int, dy: int) -> None:
        self._controller.scroll(dx, dy)


@dataclass
class HandMotionConfig:
    screen_width: int
    screen_height: int
    extend_ratio_x: float
    extend_ratio_y: float
    low_speed_threshold: float

    @classmethod
    def from_defaults(
        cls,
        extend_ratio_x: float = 2.5,
        extend_ratio_y: float = 2.5,
        low_speed_threshold: float = 200.0,
    ) -> "HandMotionConfig":
        width, height = _detect_screen_size()
        return cls(width, height, extend_ratio_x, extend_ratio_y, low_speed_threshold)


class HandMotionEstimator:
    """Compute pointer motions from MediaPipe landmarks."""

    def __init__(self, config: Optional[HandMotionConfig] = None) -> None:
        self.config = config or HandMotionConfig.from_defaults()
        self._previous_position: Optional[Tuple[int, int]] = None
        self._last_update_time = time.time()
        self._kalman_filter_x = _KalmanFilter(self.config.low_speed_threshold)
        self._kalman_filter_y = _KalmanFilter(self.config.low_speed_threshold)

    def get_pointer_anchor(self, hand_landmarks) -> Tuple[float, float]:
        """Return the normalized hand center used for pointer mapping."""
        joint_indices = [0, 1, 2, 5, 13, 17]
        joint_weights = [3, 2, 1, 1, 1, 1]

        x_values = [hand_landmarks.landmark[i].x for i in joint_indices]
        y_values = [hand_landmarks.landmark[i].y for i in joint_indices]

        norm_x = sum(x * w for x, w in zip(x_values, joint_weights)) / sum(joint_weights)
        norm_y = sum(y * w for y, w in zip(y_values, joint_weights)) / sum(joint_weights)

        return norm_x, norm_y

    def map_to_screen(self, hand_landmarks) -> Tuple[int, int]:
        norm_x, norm_y = self.get_pointer_anchor(hand_landmarks)

        extended_x = max(0.0, min(1.0, (norm_x - 0.5) * self.config.extend_ratio_x + 0.5))
        extended_y = max(0.0, min(1.0, (norm_y - 0.5) * self.config.extend_ratio_y + 0.5))

        x = int((1.0 - extended_x) * self.config.screen_width)
        y = int(extended_y * self.config.screen_height)

        return x, y

    def update_speed(self, current_position: Tuple[int, int]) -> float:
        now = time.time()
        if self._previous_position is None:
            self._previous_position = current_position
            self._last_update_time = now
            return 0.0

        distance = math.sqrt(
            (current_position[0] - self._previous_position[0]) ** 2
            + (current_position[1] - self._previous_position[1]) ** 2
        )
        time_diff = max(now - self._last_update_time, 1e-6)

        self._previous_position = current_position
        self._last_update_time = now

        return distance / time_diff

    def smooth(self, x: int, y: int, hand_speed: float) -> Tuple[int, int]:
        smooth_x = self._kalman_filter_x.update(x, hand_speed)
        smooth_y = self._kalman_filter_y.update(y, hand_speed)
        return int(smooth_x), int(smooth_y)


class _KalmanFilter:
    def __init__(self, low_speed_threshold: float) -> None:
        self.low_speed_threshold = low_speed_threshold
        self.Q_factor = 10.0
        self.R_factor = 0.1
        self.dt = 1.0
        self.A = np.array([[1.0, self.dt], [0.0, 1.0]])
        self.H = np.array([[1.0, 0.0]])
        self.Q = np.array([[1.0, 0.0], [0.0, 3.0]]) * self.Q_factor
        self.R = np.array([[10.0]]) * self.R_factor
        self.P = np.eye(2)
        self.x = np.zeros((2, 1))

    def update(self, measurement: float, speed: float) -> float:
        if speed < self.low_speed_threshold:
            self.Q_factor = 0.05
            self.R_factor = 20.0
            self.x[1, 0] = 0.0
        else:
            self.Q_factor = float(np.clip(speed / 200.0, 0.1, 10.0))
            self.R_factor = float(np.clip(10.0 / (speed + 1.0), 0.1, 10.0))

        self.Q = np.array([[1.0, 0.0], [0.0, 3.0]]) * self.Q_factor
        self.R = np.array([[10.0]]) * self.R_factor

        self.x = self.A @ self.x
        self.P = self.A @ self.P @ self.A.T + self.Q

        innovation = measurement - (self.H @ self.x)
        S = self.H @ self.P @ self.H.T + self.R
        K = self.P @ self.H.T @ np.linalg.inv(S)
        self.x = self.x + K @ innovation
        self.P = (np.eye(2) - K @ self.H) @ self.P

        return float(self.x[0, 0])
