from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class EntryDebounceConfig:
    debounce_ms: int = 220
    stable_frames: int = 4
    jitter_px: float = 6.0
    softstart_ms: int = 250
    gain0: float = 0.25
    lost_tol: int = 5
    mode_movement: str = "freeze"

    def __post_init__(self) -> None:
        self.debounce_ms = max(0, int(self.debounce_ms))
        self.stable_frames = max(1, int(self.stable_frames))
        self.jitter_px = max(0.0, float(self.jitter_px))
        self.softstart_ms = max(0, int(self.softstart_ms))
        self.gain0 = float(max(0.0, min(1.0, self.gain0)))
        self.lost_tol = max(0, int(self.lost_tol))
        mode = (self.mode_movement or "freeze").lower()
        if mode not in {"freeze", "lowgain"}:
            mode = "freeze"
        self.mode_movement = mode


@dataclass
class EntryGateOutput:
    out_xy: Optional[Tuple[int, int]]
    allow_actions: bool
    gain: float
    status: str


class HandEntryGate:
    """State machine that debounces hand entry to avoid accidental actions."""

    def __init__(self, config: EntryDebounceConfig) -> None:
        self.config = config
        self._status: str = "no_hand"
        self._frames_without_hand = 0
        self._first_detect_ms: Optional[float] = None
        self._stable_frame_count = 0
        self._last_cam_xy: Optional[Tuple[float, float]] = None
        self._release_ms: Optional[float] = None
        self._last_output: Optional[Tuple[float, float]] = None

    def prime_output(self, position: Tuple[int, int]) -> None:
        self._last_output = (float(position[0]), float(position[1]))

    def reset(self, *, preserve_output: bool = True) -> None:
        self._status = "no_hand"
        self._frames_without_hand = 0
        self._first_detect_ms = None
        self._stable_frame_count = 0
        self._last_cam_xy = None
        self._release_ms = None
        if not preserve_output:
            self._last_output = None

    def update(
        self,
        *,
        hand_present: bool,
        cam_xy: Optional[Tuple[float, float]],
        screen_xy: Optional[Tuple[int, int]],
        timestamp_ms: float,
    ) -> EntryGateOutput:
        if not hand_present:
            self._frames_without_hand += 1
            if self._status == "buffer" or self._frames_without_hand > self.config.lost_tol:
                self.reset(preserve_output=True)
            status = "active" if self._status == "active" else "no_hand"
            return EntryGateOutput(
                out_xy=self._current_output(),
                allow_actions=False,
                gain=0.0,
                status=status,
            )

        self._frames_without_hand = 0

        if self._status == "no_hand":
            self._status = "buffer"
            self._first_detect_ms = timestamp_ms
            self._stable_frame_count = 0
            self._last_cam_xy = None

        if self._status == "buffer":
            self._update_stability(cam_xy)
            if self._is_ready(timestamp_ms):
                self._status = "active"
                self._release_ms = timestamp_ms
                self._first_detect_ms = None
                self._stable_frame_count = 0

        gain = self._compute_gain(timestamp_ms)
        out_xy = self._apply_gain(screen_xy, gain)
        allow_actions = hand_present and self._status == "active"

        return EntryGateOutput(
            out_xy=out_xy,
            allow_actions=allow_actions,
            gain=gain,
            status=self._status if hand_present else "no_hand",
        )

    def _current_output(self) -> Optional[Tuple[int, int]]:
        if self._last_output is None:
            return None
        return (int(round(self._last_output[0])), int(round(self._last_output[1])))

    def _apply_gain(self, screen_xy: Optional[Tuple[int, int]], gain: float) -> Optional[Tuple[int, int]]:
        if screen_xy is None:
            return self._current_output()

        if self._last_output is None:
            self._last_output = (float(screen_xy[0]), float(screen_xy[1]))
            return (int(round(self._last_output[0])), int(round(self._last_output[1])))

        target_x = float(screen_xy[0])
        target_y = float(screen_xy[1])
        new_x = self._last_output[0] + gain * (target_x - self._last_output[0])
        new_y = self._last_output[1] + gain * (target_y - self._last_output[1])

        self._last_output = (new_x, new_y)
        return (int(round(new_x)), int(round(new_y)))

    def _compute_gain(self, timestamp_ms: float) -> float:
        if self._status != "active":
            if self.config.mode_movement == "lowgain":
                return self.config.gain0
            return 0.0

        if self.config.softstart_ms <= 0 or self._release_ms is None:
            return 1.0

        elapsed = max(0.0, timestamp_ms - self._release_ms)
        progress = min(1.0, elapsed / self.config.softstart_ms)
        start_gain = self.config.gain0
        return start_gain + (1.0 - start_gain) * progress

    def _update_stability(self, cam_xy: Optional[Tuple[float, float]]) -> None:
        if cam_xy is None:
            self._stable_frame_count = 0
            self._last_cam_xy = None
            return

        if self._last_cam_xy is None:
            self._stable_frame_count = 1
        else:
            distance = math.hypot(cam_xy[0] - self._last_cam_xy[0], cam_xy[1] - self._last_cam_xy[1])
            if distance <= self.config.jitter_px:
                self._stable_frame_count += 1
            else:
                self._stable_frame_count = 1
        self._last_cam_xy = cam_xy

    def _is_ready(self, timestamp_ms: float) -> bool:
        if self._first_detect_ms is None:
            return False
        elapsed = timestamp_ms - self._first_detect_ms
        return elapsed >= self.config.debounce_ms and self._stable_frame_count >= self.config.stable_frames
