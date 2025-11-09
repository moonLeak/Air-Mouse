from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Deque, Optional, Tuple

from collections import deque


ROIState = str


@dataclass
class ROIConfig:
    size_scale: float = 6.0
    min_width_frac: float = 0.30
    max_width_frac: float = 0.70
    aspect_ratio: float = 1.0
    size_smooth_beta: float = 0.08
    size_hysteresis: float = 0.10
    size_rate_limit: float = 400.0
    margin_px: float = 16.0
    snap_band_frac: float = 0.05
    hide_band_px: float = 24.0
    hide_ms: int = 250
    lost_tol: int = 8
    freeze_seconds: float = 5.0
    buffer_ms: int = 300
    countdown_seconds: int = 3
    countdown_samples: int = 5
    stability_frames: int = 4


@dataclass
class ROIResult:
    state: ROIState
    roi_box: Optional[Tuple[int, int, int, int]]
    show_box: bool
    countdown_value: Optional[int]


class ROIManager:
    """State machine that manages a camera-space ROI rectangle."""

    def __init__(self, config: ROIConfig) -> None:
        self.config = config
        self._state: ROIState = "idle"
        self._roi_center: Optional[Tuple[float, float]] = None
        self._roi_size: Optional[Tuple[float, float]] = None
        self._size_last_update: Optional[float] = None
        self._buffer_start: Optional[float] = None
        self._countdown_remaining_ms: Optional[float] = None
        self._countdown_positions: Deque[Tuple[float, float]] = deque(maxlen=self.config.countdown_samples)
        self._countdown_last_timestamp: Optional[float] = None
        self._countdown_paused: bool = False
        self._snap_axis: Tuple[bool, bool] = (False, False)
        self._snap_anchor_center: Optional[Tuple[float, float]] = None
        self._snap_push_start: Optional[float] = None
        self._lost_frames: int = 0
        self._freeze_expiry: Optional[float] = None
        self._stability_counter: int = 0

    def reset(self) -> None:
        self._state = "idle"
        self._roi_center = None
        self._roi_size = None
        self._size_last_update = None
        self._buffer_start = None
        self._countdown_remaining_ms = None
        self._countdown_positions.clear()
        self._countdown_last_timestamp = None
        self._countdown_paused = False
        self._snap_axis = (False, False)
        self._snap_anchor_center = None
        self._snap_push_start = None
        self._lost_frames = 0
        self._freeze_expiry = None
        self._stability_counter = 0

    def update(
        self,
        *,
        timestamp: float,
        frame_size: Tuple[int, int],
        hand_present: bool,
        cx: Optional[float],
        cy: Optional[float],
        scale: Optional[float],
        gate_status: Optional[str],
    ) -> ROIResult:
        width, height = frame_size
        if not hand_present or cx is None or cy is None or scale is None:
            self._handle_hand_loss(timestamp)
            return self._finalize_result(frame_size, countdown_value=None)

        self._lost_frames = 0

        if self._state == "idle":
            self._state = "buffer"
            self._buffer_start = timestamp
            self._countdown_positions.clear()
            self._countdown_remaining_ms = None
            self._countdown_last_timestamp = None

        if self._state == "buffer":
            self._update_size(scale, width, timestamp)
            if self._buffer_ready(timestamp, gate_status, cx, cy, width, height):
                self._enter_countdown(timestamp)

        if self._state == "countdown":
            self._update_size(scale, width, timestamp)
            fits = self._center_fits(cx, cy, width, height)
            if fits:
                self._accumulate_countdown_position(cx, cy)
            self._progress_countdown(timestamp, fits)
            if self._countdown_remaining_ms is not None and self._countdown_remaining_ms <= 0:
                self._finalize_countdown(width, height)

        if self._state in {"active", "snap_hold"}:
            self._update_size(scale, width, timestamp)
            self._update_active_state(cx, cy, width, height, timestamp)

        if self._state == "out_of_bounds":
            if self._roi_fits_box(cx, cy, width, height):
                self._stability_counter += 1
                if self._stability_counter >= self.config.stability_frames:
                    clamped_center, _ = self._clamp_center((cx, cy), width, height)
                    self._state = "active"
                    self._roi_center = clamped_center
                    self._snap_axis = (False, False)
                    self._snap_anchor_center = None
                    self._snap_push_start = None
                    self._stability_counter = 0
            else:
                self._stability_counter = 0

        if self._state == "frozen":
            if timestamp <= (self._freeze_expiry or -math.inf):
                self._state = "active"
                self._snap_axis = (False, False)
                self._snap_anchor_center = None
                self._snap_push_start = None
                self._freeze_expiry = None
            else:
                self.reset()
                return self._finalize_result(frame_size, countdown_value=None)

        countdown_value = self._countdown_display_value()
        return self._finalize_result(frame_size, countdown_value=countdown_value)

    # --- Internal helpers ---

    def _handle_hand_loss(self, timestamp: float) -> None:
        self._lost_frames += 1
        if self._state in {"idle", "buffer", "countdown"}:
            if self._lost_frames > self.config.lost_tol:
                self.reset()
            return

        if self._state != "frozen":
            self._state = "frozen"
            self._freeze_expiry = timestamp + self.config.freeze_seconds
        elif timestamp > (self._freeze_expiry or -math.inf):
            self.reset()

    def _buffer_ready(
        self,
        timestamp: float,
        gate_status: Optional[str],
        cx: float,
        cy: float,
        width: int,
        height: int,
    ) -> bool:
        elapsed = timestamp - (self._buffer_start or timestamp)
        gate_ok = gate_status == "active"
        if not gate_ok or elapsed < self.config.buffer_ms / 1000.0:
            return False
        return self._center_fits(cx, cy, width, height)

    def _enter_countdown(self, timestamp: float) -> None:
        self._state = "countdown"
        self._countdown_remaining_ms = self.config.countdown_seconds * 1000.0
        self._countdown_last_timestamp = timestamp
        self._countdown_positions.clear()
        self._countdown_paused = False

    def _progress_countdown(self, timestamp: float, fits: bool) -> None:
        if self._countdown_remaining_ms is None:
            return
        if self._countdown_last_timestamp is None:
            self._countdown_last_timestamp = timestamp

        dt_ms = (timestamp - self._countdown_last_timestamp) * 1000.0
        self._countdown_last_timestamp = timestamp

        if fits:
            self._countdown_remaining_ms = max(0.0, self._countdown_remaining_ms - dt_ms)
            self._countdown_paused = False
        else:
            self._countdown_paused = True

    def _accumulate_countdown_position(self, cx: float, cy: float) -> None:
        self._countdown_positions.append((cx, cy))

    def _countdown_display_value(self) -> Optional[int]:
        if self._state != "countdown" or self._countdown_remaining_ms is None:
            return None
        remaining_sec = math.ceil(self._countdown_remaining_ms / 1000.0)
        return max(0, remaining_sec)

    def _finalize_countdown(self, frame_width: int, frame_height: int) -> None:
        if not self._countdown_positions:
            return

        cx_vals = sorted(pos[0] for pos in self._countdown_positions)
        cy_vals = sorted(pos[1] for pos in self._countdown_positions)
        mid_idx = len(cx_vals) // 2
        center_x = cx_vals[mid_idx]
        center_y = cy_vals[mid_idx]
        self._roi_center = (
            float(self._clamp_center_component(center_x, self._roi_size[0] if self._roi_size else 0, frame_width)),
            float(self._clamp_center_component(center_y, self._roi_size[1] if self._roi_size else 0, frame_height)),
        )
        self._snap_axis = (False, False)
        self._snap_anchor_center = None
        self._state = "active"
        self._countdown_positions.clear()
        self._countdown_remaining_ms = None

    def _update_size(self, scale: float, frame_width: int, timestamp: float) -> None:
        target_width = self._target_width(scale, frame_width)
        if target_width <= 0:
            return
        target_height = max(1.0, target_width * self.config.aspect_ratio)

        if self._roi_size is None:
            self._roi_size = (target_width, target_height)
            self._size_last_update = timestamp
            return

        current_width, current_height = self._roi_size
        rel_change = abs(target_width - current_width) / max(current_width, 1e-6)
        if rel_change < self.config.size_hysteresis:
            target_width = current_width
            target_height = current_height

        beta = self.config.size_smooth_beta
        new_width = current_width + beta * (target_width - current_width)
        new_height = current_height + beta * (target_height - current_height)

        if self._size_last_update is not None:
            dt = max(timestamp - self._size_last_update, 1e-6)
            max_delta = self.config.size_rate_limit * dt
            width_delta = max(-max_delta, min(max_delta, new_width - current_width))
            height_delta = max(-max_delta, min(max_delta, new_height - current_height))
            new_width = current_width + width_delta
            new_height = current_height + height_delta

        self._roi_size = (new_width, new_height)
        self._size_last_update = timestamp

    def _update_active_state(
        self,
        cx: float,
        cy: float,
        frame_width: int,
        frame_height: int,
        timestamp: float,
    ) -> None:
        if self._roi_size is None:
            return

        candidate_center = (cx, cy)
        clamped_center, axes_clamped = self._clamp_center(candidate_center, frame_width, frame_height)

        if self._state == "active":
            if axes_clamped != (False, False):
                self._state = "snap_hold"
                self._snap_axis = axes_clamped
                self._snap_anchor_center = clamped_center
                self._snap_push_start = timestamp
                self._roi_center = clamped_center
            else:
                self._roi_center = clamped_center
            return

        # snap_hold logic
        if self._snap_anchor_center is None:
            self._snap_anchor_center = self._roi_center

        self._roi_center = self._snap_anchor_center

        if self._hide_triggered(candidate_center, frame_width, frame_height, timestamp):
            self._state = "out_of_bounds"
            self._snap_axis = (False, False)
            self._snap_anchor_center = None
            self._snap_push_start = None
            return

        if self._snap_released(candidate_center, frame_width, frame_height):
            self._state = "active"
            self._snap_axis = (False, False)
            self._snap_anchor_center = None
            self._snap_push_start = None
            self._roi_center = clamped_center

    def _hide_triggered(
        self,
        candidate_center: Tuple[float, float],
        frame_width: int,
        frame_height: int,
        timestamp: float,
    ) -> bool:
        hide_band_px = self.config.hide_band_px
        if hide_band_px <= 0 and self.config.hide_ms <= 0:
            return False

        margin = self.config.margin_px
        if self._roi_size is None:
            return False

        width, height = self._roi_size
        left_limit = margin + width / 2.0
        right_limit = frame_width - margin - width / 2.0
        top_limit = margin + height / 2.0
        bottom_limit = frame_height - margin - height / 2.0

        x, y = candidate_center
        beyond_left = x < (left_limit - hide_band_px)
        beyond_right = x > (right_limit + hide_band_px)
        beyond_top = y < (top_limit - hide_band_px)
        beyond_bottom = y > (bottom_limit + hide_band_px)
        if beyond_left or beyond_right or beyond_top or beyond_bottom:
            return True

        if self.config.hide_ms <= 0:
            return False

        if self._snap_push_start is None:
            self._snap_push_start = timestamp
            return False

        return (timestamp - self._snap_push_start) * 1000.0 >= self.config.hide_ms

    def _snap_released(self, candidate_center: Tuple[float, float], frame_width: int, frame_height: int) -> bool:
        if self._roi_size is None:
            return True
        width, height = self._roi_size
        margin = self.config.margin_px
        band_x = width * self.config.snap_band_frac
        band_y = height * self.config.snap_band_frac

        x, y = candidate_center
        left_limit = margin + width / 2.0 + band_x
        right_limit = frame_width - margin - width / 2.0 - band_x
        top_limit = margin + height / 2.0 + band_y
        bottom_limit = frame_height - margin - height / 2.0 - band_y

        release_x = True
        release_y = True
        if self._snap_axis[0]:
            release_x = left_limit <= x <= right_limit
        if self._snap_axis[1]:
            release_y = top_limit <= y <= bottom_limit

        return release_x and release_y

    def _roi_fits_box(self, cx: float, cy: float, frame_width: int, frame_height: int) -> bool:
        if self._roi_size is None:
            return False
        margin = self.config.margin_px
        width, height = self._roi_size
        left = cx - width / 2.0
        top = cy - height / 2.0
        right = left + width
        bottom = top + height
        return (
            left >= margin
            and top >= margin
            and right <= frame_width - margin
            and bottom <= frame_height - margin
        )

    def _center_fits(self, cx: float, cy: float, frame_width: int, frame_height: int) -> bool:
        if self._roi_size is None:
            return False
        return self._roi_fits_box(cx, cy, frame_width, frame_height)

    def _target_width(self, scale: float, frame_width: int) -> float:
        min_width = self.config.min_width_frac * frame_width
        max_width = self.config.max_width_frac * frame_width
        target = self.config.size_scale * scale
        return max(min_width, min(max_width, target))

    def _clamp_center(self, center: Tuple[float, float], frame_width: int, frame_height: int) -> Tuple[Tuple[float, float], Tuple[bool, bool]]:
        if self._roi_size is None:
            return center, (False, False)
        margin = self.config.margin_px
        width, height = self._roi_size
        min_x = margin + width / 2.0
        max_x = frame_width - margin - width / 2.0
        min_y = margin + height / 2.0
        max_y = frame_height - margin - height / 2.0

        clamped_x = min(max(center[0], min_x), max_x)
        clamped_y = min(max(center[1], min_y), max_y)

        clamp_x = not math.isclose(clamped_x, center[0], abs_tol=1e-3)
        clamp_y = not math.isclose(clamped_y, center[1], abs_tol=1e-3)
        return (clamped_x, clamped_y), (clamp_x, clamp_y)

    def _clamp_center_component(self, value: float, size: float, frame_extent: int) -> float:
        if size <= 0:
            return value
        margin = self.config.margin_px
        min_val = margin + size / 2.0
        max_val = frame_extent - margin - size / 2.0
        return min(max(value, min_val), max_val)

    def _finalize_result(self, frame_size: Tuple[int, int], countdown_value: Optional[int]) -> ROIResult:
        if self._roi_center is None or self._roi_size is None:
            return ROIResult(state=self._state, roi_box=None, show_box=False, countdown_value=countdown_value)

        width, height = self._roi_size
        center_x, center_y = self._roi_center
        x0 = int(round(center_x - width / 2.0))
        y0 = int(round(center_y - height / 2.0))
        roi_box = (x0, y0, int(round(width)), int(round(height)))

        show_states = {"active", "snap_hold", "countdown", "buffer", "frozen"}
        show = self._state in show_states and self._roi_fits_box(center_x, center_y, *frame_size)

        if self._state == "countdown" and self._countdown_paused:
            show = False

        if self._state == "out_of_bounds":
            show = False

        return ROIResult(state=self._state, roi_box=roi_box if show else None, show_box=show, countdown_value=countdown_value)
