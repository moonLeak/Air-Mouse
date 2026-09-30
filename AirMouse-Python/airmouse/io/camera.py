from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Iterator, Optional

import cv2
import platform


@dataclass
class CameraConfig:
    camera_index: int = 0               # 默认相机索引
    frame_scale: float = 0.5            # 读到的画面按比例缩放的系数


def _read_with_timeout(cap: cv2.VideoCapture, timeout: float = 5.0):
    """在独立线程中读取一帧，超时返回 (False, None)。

    macOS 上某些摄像头（Continuity Camera、FaceTime HD 等）的
    cap.read() 会无限阻塞或持续返回 (False, None)，用超时保护
    避免整个程序卡住。
    """
    result: list = [False, None]

    def _read():
        result[0], result[1] = cap.read()

    t = threading.Thread(target=_read, daemon=True)
    t.start()
    t.join(timeout=timeout)
    if t.is_alive():
        # 线程超时，认为读取失败
        return False, None
    return result[0], result[1]


class CameraStream:
    """OpenCV video capture helper with optional downscaling."""

    # 连续读帧失败多少次后报错退出（约 2 秒，按 30fps 估算）
    _MAX_CONSECUTIVE_FAILURES = 60

    def __init__(self, config: Optional[CameraConfig] = None) -> None:
        self.config = config or CameraConfig()
        self._cap = self._open_front_camera()

    def _open_front_camera(self) -> cv2.VideoCapture:
        tried_indices = []
        primary_index = self.config.camera_index

        # 先尝试用户指定的 index，再依次尝试 0-10
        for index in [primary_index, *(i for i in range(0, 11) if i != primary_index)]:
            capture = self._try_open_index(index)
            if capture is not None:
                if index != primary_index:
                    print(
                        f"[Camera] Index {primary_index} 无法使用，"
                        f"已自动切换到 index {index}。"
                        "如需固定使用其他摄像头，请在 GUI 修改 Camera index。"
                    )
                return capture
            tried_indices.append(index)

        tried_repr = ", ".join(str(i) for i in tried_indices)
        raise RuntimeError(
            f"无法打开任何摄像头（已尝试 index：{tried_repr}）。\n"
            "请检查系统权限（隐私与安全性 → 摄像头）是否已授权，"
            "或在 GUI 中更改 Camera index 重试。"
        )

    def _try_open_index(self, index: int) -> Optional[cv2.VideoCapture]:
        """尝试打开指定 index 的摄像头，并验证能否真正读取帧。

        macOS 上 isOpened() 返回 True 并不代表摄像头可用——
        Continuity Camera 和部分外置摄像头会报告"已打开"但
        cap.read() 始终返回 (False, None)。此处做实际读帧验证。
        """
        backends: list[tuple] = []
        if platform.system() == "Darwin":
            backends.append((cv2.CAP_AVFOUNDATION,))
        backends.append(())  # 默认后端兜底

        for backend_args in backends:
            cap = cv2.VideoCapture(index, *backend_args)
            if not cap.isOpened():
                cap.release()
                continue

            # 实际读一帧验证可用性（带超时防止卡死）
            ret, frame = _read_with_timeout(cap, timeout=5.0)
            if ret and frame is not None:
                print(f"[Camera] 成功打开摄像头 index={index}（backend={'AVFoundation' if backend_args else 'default'}）")
                return cap
            cap.release()

        return None

    def frames(self) -> Iterator:
        consecutive_failures = 0

        while self._cap.isOpened():
            ret, frame = self._cap.read()
            if not ret:
                consecutive_failures += 1
                if consecutive_failures >= self._MAX_CONSECUTIVE_FAILURES:
                    raise RuntimeError(
                        f"摄像头（index {self.config.camera_index}）已打开但持续无法读取画面。\n"
                        "可能原因：\n"
                        "  1. 摄像头被其他程序占用\n"
                        "  2. 系统权限未授权（隐私与安全性 → 摄像头）\n"
                        "  3. Camera index 不正确，请在 GUI 中尝试其他 index"
                    )
                continue
            consecutive_failures = 0

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
