from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable, Optional

import cv2
import mediapipe as mp


@dataclass
class HandTrackerConfig:
    min_detection_confidence: float = 0.5
    min_tracking_confidence: float = 0.3
    max_num_hands: int = 1


class HandTracker:
    """Wrapper around MediaPipe Hands."""

    def __init__(self, config: Optional[HandTrackerConfig] = None) -> None:
        self.config = config or HandTrackerConfig()
        print(
            f"[HandTracker] 正在初始化 MediaPipe Hands "
            f"(detection={self.config.min_detection_confidence}, "
            f"tracking={self.config.min_tracking_confidence}, "
            f"max_hands={self.config.max_num_hands})…"
        )
        t0 = time.perf_counter()
        self._hands = mp.solutions.hands.Hands(
            max_num_hands=self.config.max_num_hands,
            min_detection_confidence=self.config.min_detection_confidence,
            min_tracking_confidence=self.config.min_tracking_confidence,
        )
        elapsed = time.perf_counter() - t0
        print(f"[HandTracker] MediaPipe 初始化完成，耗时 {elapsed:.2f}s")

    def process(self, frame) -> Iterable:
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self._hands.process(rgb_frame)
        return results.multi_hand_landmarks or []

    def close(self) -> None:
        self._hands.close()

    def __enter__(self) -> "HandTracker":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
