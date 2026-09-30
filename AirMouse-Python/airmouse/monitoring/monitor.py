from __future__ import annotations

import csv
import os
import time
from collections import deque
from typing import Deque, Dict, Optional, Sequence, Tuple

import cv2
import numpy as np
import mediapipe as mp

from airmouse.utils import calculate_distance

mp_drawing = mp.solutions.drawing_utils
mp_styles = mp.solutions.drawing_styles
mp_hands = mp.solutions.hands


class Monitor:
    """Runtime visualisation for debugging gesture thresholds."""

    def __init__(
        self,
        frame_num_max: int = 300,
        base_y: int = 300,
        scale_factor: int = 200,
        horizontal_scale: int = 3,
        pinch_debug_enabled: bool = False,
        draw_skeleton: bool = False,
    ) -> None:
        self.frame_num_max = frame_num_max
        self.base_y = base_y
        self.scale_factor = scale_factor
        self.horizontal_scale = horizontal_scale
        self.pinch_debug_enabled = pinch_debug_enabled
        self.draw_skeleton = draw_skeleton
        self.start_time = time.time()
        self.data_log: list[list[float]] = []
        self.previous_middle_tip: Optional[Tuple[float, float]] = None

        if self.pinch_debug_enabled:
            print("[Monitor] Pinch debug output enabled")
        if self.draw_skeleton:
            print("[Monitor] Hand skeleton overlay enabled")

        def new_curve() -> Dict[str, Deque[float]]:
            return {
                "dynamic_line": deque(maxlen=frame_num_max),
                "threshold_low": deque(maxlen=frame_num_max),
                "threshold_high": deque(maxlen=frame_num_max),
                "normalized": deque(maxlen=frame_num_max),
            }

        self.curve_data = {
            "4to8": new_curve(),
            "4to12": new_curve(),
        }

    def update_curve_data(
        self,
        key: str,
        dynamic_line: float,
        threshold_low: float,
        threshold_high: float,
        normalized: float,
    ) -> None:
        self.curve_data[key]["dynamic_line"].append(dynamic_line)
        self.curve_data[key]["threshold_low"].append(threshold_low)
        self.curve_data[key]["threshold_high"].append(threshold_high)
        self.curve_data[key]["normalized"].append(normalized)

    def update_middle_finger_displacement(self, current_middle_tip: Tuple[float, float]) -> float:
        if self.previous_middle_tip is None:
            self.previous_middle_tip = current_middle_tip
            return 0.0

        displacement = calculate_distance(self.previous_middle_tip, current_middle_tip)
        self.previous_middle_tip = current_middle_tip
        return displacement

    def draw_graph(self, frame, data: Sequence[float], color, position_y: int) -> None:
        for i in range(1, len(data)):
            x1 = (i - 1) * self.horizontal_scale
            y1 = int(position_y - data[i - 1] * self.scale_factor)
            x2 = i * self.horizontal_scale
            y2 = int(position_y - data[i] * self.scale_factor)
            cv2.line(frame, (x1, y1), (x2, y2), color, 2)

    def display_graphs(self, graph_frame) -> None:
        height, _, _ = graph_frame.shape
        base_y_4to8 = height // 2
        base_y_4to12 = height

        self.draw_graph(graph_frame, self.curve_data["4to8"]["dynamic_line"], (105, 105, 105), base_y_4to8)
        # Use a distinct color for the low threshold to differentiate the three reference lines
        self.draw_graph(graph_frame, self.curve_data["4to8"]["threshold_low"], (0, 255, 0), base_y_4to8)
        self.draw_graph(graph_frame, self.curve_data["4to8"]["threshold_high"], (105, 105, 105), base_y_4to8)
        self.draw_graph(graph_frame, self.curve_data["4to8"]["normalized"], (255, 255, 0), base_y_4to8)

        self.draw_graph(graph_frame, self.curve_data["4to12"]["dynamic_line"], (105, 105, 105), base_y_4to12)
        # Use the same distinct color for low threshold here as well
        self.draw_graph(graph_frame, self.curve_data["4to12"]["threshold_low"], (0, 255, 0), base_y_4to12)
        self.draw_graph(graph_frame, self.curve_data["4to12"]["threshold_high"], (105, 105, 105), base_y_4to12)
        self.draw_graph(graph_frame, self.curve_data["4to12"]["normalized"], (0, 0, 255), base_y_4to12)

    def display_camera_feed(self, frame) -> None:
        cv2.imshow("Camera Feed", frame)

    def draw_hand_skeleton(self, frame, hand_landmarks) -> None:
        if not self.draw_skeleton:
            return
        mp_drawing.draw_landmarks(
            frame,
            hand_landmarks,
            mp_hands.HAND_CONNECTIONS,
            mp_styles.get_default_hand_landmarks_style(),
            mp_styles.get_default_hand_connections_style(),
        )

    def log_pinch_debug(self, *, stage: str, action: Optional[str], is_holding: bool, is_pitching: bool, elapsed: Optional[float]) -> None:
        if not self.pinch_debug_enabled:
            return

        elapsed_text = "None" if elapsed is None else f"{elapsed:.3f}"
        action_text = action or "None"
        print(
            "[PinchDebug]",
            f"stage={stage}",
            f"action={action_text}",
            f"hold={is_holding}",
            f"pitch={is_pitching}",
            f"elapsed={elapsed_text}",
        )

    def log_data(self, time_stamp: float, action: str, normalized_4to8: float, normalized_4to12: float) -> None:
        self.data_log.append([time_stamp, action, normalized_4to8, normalized_4to12])

    def export_data(self) -> str:
        downloads_folder = os.path.join(os.path.expanduser("~"), "Downloads")
        file_path = os.path.join(downloads_folder, "Monitor_data.csv")

        with open(file_path, mode="w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["Timestamp", "Action", "4to8 Normalized", "4to12 Normalized"])
            writer.writerows(self.data_log)
        return file_path
