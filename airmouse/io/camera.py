from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Optional

import cv2
import platform


@dataclass
class CameraConfig:
    camera_index: int = 1               # 默认相机索引
    frame_scale: float = 0.5            # 读到的画面按比例缩放的系数


class CameraStream:
    """OpenCV video capture helper with optional downscaling."""

    def __init__(self, config: Optional[CameraConfig] = None) -> None:
        self.config = config or CameraConfig()

        self._cap = self._open_front_camera()

    def _open_front_camera(self) -> cv2.VideoCapture:
        tried_indices = []
        primary_index = self.config.camera_index

        for index in [primary_index, *(i for i in range(0, 11) if i != primary_index)]:
            capture = self._try_open_index(index)
            if capture is not None:
                return capture
            tried_indices.append(index)

        tried_repr = ", ".join(str(i) for i in tried_indices)
        raise RuntimeError(f"Unable to open camera. Tried indices: {tried_repr}")

    def _try_open_index(self, index: int) -> Optional[cv2.VideoCapture]:
        if platform.system() == "Darwin":
            capture = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
            if capture.isOpened():
                return capture
            capture.release()

        capture = cv2.VideoCapture(index)
        if capture.isOpened():
            return capture
        capture.release()
        return None

    def frames(self) -> Iterator:
        while self._cap.isOpened():
            ret, frame = self._cap.read()
            if not ret:
                continue

            if self.config.frame_scale and self.config.frame_scale != 1.0:
                scale = self.config.frame_scale
                frame = cv2.resize(
                    frame,
                    (int(frame.shape[1] * scale), int(frame.shape[0] * scale)),
                )

            yield frame

    def release(self) -> None:
        if self._cap.isOpened():
            self._cap.release()

    def __enter__(self) -> "CameraStream":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
