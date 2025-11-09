from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class ROIConfig:
    base_scale: float = 1.2  # Global multiplier A
    width_ratio: float = 1.5  # k_w
    height_ratio: float = 1.0  # k_h
    min_width_frac: float = 0.15
    max_width_frac: float = 0.70
    fit_margin: float = 16.0
    countdown_seconds: float = 3.0
    freeze_seconds: float = 5.0
    lost_tol: int = 8
    position_smooth_beta: float = 0.25
    size_smooth_beta: float = 0.20


@dataclass
class ROIResult:
    state: str
    roi_box: Optional[Tuple[int, int, int, int]]
    show_box: bool
    countdown_value: Optional[int]
    frozen_remaining: Optional[float]


class ROIManager:
    """Beginner-friendly ROI state machine matching the final specification."""

    def __init__(self, config: ROIConfig) -> None:
        self.config = config
        self._state: str = "idle"
        self._roi_center: Optional[Tuple[float, float]] = None
        self._roi_size: Optional[Tuple[float, float]] = None
        self._countdown_remaining: Optional[float] = None
        self._countdown_visible: bool = False
        self._last_timestamp: Optional[float] = None
        self._lost_frames: int = 0
        self._frozen_until: Optional[float] = None

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #
    def reset(self) -> None:
        self._state = "idle"
        self._roi_center = None
        self._roi_size = None
        self._countdown_remaining = None
        self._countdown_visible = False
        self._last_timestamp = None
        self._lost_frames = 0
        self._frozen_until = None

    def update(
        self,
        *,
        timestamp: float,
        frame_size: Tuple[int, int],
        hand_present: bool,
        cx: Optional[float],
        cy: Optional[float],
        scale: Optional[float],
    ) -> ROIResult:
        width, height = frame_size
        dt = 0.0 if self._last_timestamp is None else max(timestamp - self._last_timestamp, 0.0)
        self._last_timestamp = timestamp

        if not hand_present or cx is None or cy is None or scale is None:
            return self._handle_no_hand(timestamp, frame_size)

        self._lost_frames = 0

        if self._state == "idle":
            self._enter_preview(scale, frame_size, cx, cy)

        if self._state == "frozen":
            self._state = "active"
            self._frozen_until = None

        if self._state == "preview":
            self._update_preview(scale, frame_size, cx, cy, dt)

        if self._state == "active":
            # ROI remains locked; nothing to update other than ensuring it still fits
            if not self._roi_fits(self._roi_center, self._roi_size, frame_size):
                # If somehow out of bounds (e.g. extreme resize), hide but keep state.
                pass

        return self._finalize_result(frame_size, timestamp)

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #
    def _handle_no_hand(self, timestamp: float, frame_size: Tuple[int, int]) -> ROIResult:
        self._lost_frames += 1

        if self._lost_frames < self.config.lost_tol:
            # Treat as transient loss; keep current state without changes.
            return self._finalize_result(frame_size, timestamp)

        if self._state in {"idle"}:
            return ROIResult(state="idle", roi_box=None, show_box=False, countdown_value=None, frozen_remaining=None)

        if self._state == "preview":
            # Hand left before locking; reset immediately.
            self.reset()
            return ROIResult(state="idle", roi_box=None, show_box=False, countdown_value=None, frozen_remaining=None)

        if self._state == "active":
            self._state = "frozen"
            self._frozen_until = timestamp + self.config.freeze_seconds
            self._lost_frames = 0
            return self._finalize_result(frame_size, timestamp)

        if self._state == "frozen":
            if self._frozen_until is None or timestamp >= self._frozen_until:
                self.reset()
                return ROIResult(state="idle", roi_box=None, show_box=False, countdown_value=None, frozen_remaining=None)
            return self._finalize_result(frame_size, timestamp)

        return ROIResult(state=self._state, roi_box=None, show_box=False, countdown_value=None, frozen_remaining=None)

    def _enter_preview(self, scale: float, frame_size: Tuple[int, int], cx: float, cy: float) -> None:
        self._state = "preview"
        self._countdown_remaining = self.config.countdown_seconds
        size = self._compute_size(scale, frame_size[0])
        if not self._roi_fits((cx, cy), size, frame_size):
            self._roi_center = None
            self._roi_size = size
            self._countdown_visible = False
        else:
            self._roi_center = (cx, cy)
            self._roi_size = size
            self._countdown_visible = True

    def _update_preview(
        self,
        scale: float,
        frame_size: Tuple[int, int],
        cx: float,
        cy: float,
        dt: float,
    ) -> None:
        size = self._compute_size(scale, frame_size[0])
        self._roi_size = self._smooth_size(size, dt)

        fits_candidate = self._roi_fits((cx, cy), self._roi_size, frame_size)
        if fits_candidate:
            self._roi_center = self._smooth_center((cx, cy), dt)
            self._countdown_visible = True
            if self._countdown_remaining is not None:
                self._countdown_remaining = max(0.0, self._countdown_remaining - dt)
                if self._countdown_remaining <= 0.0:
                    self._lock_active(frame_size)
        else:
            # Pause countdown, keep ROI hidden until user moves back.
            self._countdown_visible = False

    def _lock_active(self, frame_size: Tuple[int, int]) -> None:
        if self._roi_center is None or self._roi_size is None:
            # Nothing to lock; reset instead.
            self.reset()
            return

        # Clamp once more to ensure the locked ROI is valid.
        cx, cy = self._roi_center
        clamped_center = self._clamp_center((cx, cy), self._roi_size, frame_size)
        self._roi_center = clamped_center
        self._state = "active"
        self._countdown_remaining = None
        self._countdown_visible = False

    def _compute_size(self, scale: float, frame_width: int) -> Tuple[float, float]:
        scale = max(scale, 1e-6)
        width = self.config.base_scale * self.config.width_ratio * scale
        height = self.config.base_scale * self.config.height_ratio * scale

        min_w = self.config.min_width_frac * frame_width if self.config.min_width_frac > 0 else 0.0
        max_w = self.config.max_width_frac * frame_width if self.config.max_width_frac > 0 else float("inf")
        width = max(min_w, min(max_w, width))

        # Height is derived proportionally; ensure at least a few pixels.
        height = max(1.0, height)
        return width, height

    def _smooth_size(self, target: Tuple[float, float], dt: float) -> Tuple[float, float]:
        if self._roi_size is None:
            return target
        beta = self.config.size_smooth_beta
        current_w, current_h = self._roi_size
        target_w, target_h = target
        new_w = current_w + beta * (target_w - current_w)
        new_h = current_h + beta * (target_h - current_h)
        return new_w, new_h

    def _smooth_center(self, target: Tuple[float, float], dt: float) -> Tuple[float, float]:
        if self._roi_center is None:
            return target
        beta = self.config.position_smooth_beta
        current_x, current_y = self._roi_center
        target_x, target_y = target
        new_x = current_x + beta * (target_x - current_x)
        new_y = current_y + beta * (target_y - current_y)
        return new_x, new_y

    def _clamp_center(
        self,
        center: Tuple[float, float],
        size: Tuple[float, float],
        frame_size: Tuple[int, int],
    ) -> Tuple[float, float]:
        margin = self.config.fit_margin
        width, height = size
        frame_w, frame_h = frame_size
        min_x = margin + width / 2.0
        max_x = frame_w - margin - width / 2.0
        min_y = margin + height / 2.0
        max_y = frame_h - margin - height / 2.0
        clamped_x = max(min_x, min(max_x, center[0]))
        clamped_y = max(min_y, min(max_y, center[1]))
        return clamped_x, clamped_y

    def _roi_fits(
        self,
        center: Optional[Tuple[float, float]],
        size: Optional[Tuple[float, float]],
        frame_size: Tuple[int, int],
    ) -> bool:
        if center is None or size is None:
            return False
        margin = self.config.fit_margin
        width, height = size
        frame_w, frame_h = frame_size
        half_w = width / 2.0
        half_h = height / 2.0
        return (
            center[0] - half_w >= margin
            and center[0] + half_w <= frame_w - margin
            and center[1] - half_h >= margin
            and center[1] + half_h <= frame_h - margin
        )

    def _current_box(self) -> Optional[Tuple[int, int, int, int]]:
        if self._roi_center is None or self._roi_size is None:
            return None
        cx, cy = self._roi_center
        width, height = self._roi_size
        x0 = int(round(cx - width / 2.0))
        y0 = int(round(cy - height / 2.0))
        return (x0, y0, int(round(width)), int(round(height)))

    def _finalize_result(self, frame_size: Tuple[int, int], timestamp: float) -> ROIResult:
        roi_box = self._current_box()
        show_box = False
        countdown_value: Optional[int] = None
        frozen_remaining: Optional[float] = None

        if self._state == "preview":
            show_box = self._countdown_visible and roi_box is not None
            if self._countdown_remaining is not None:
                countdown_value = max(0, math.ceil(self._countdown_remaining))
                if countdown_value == 0 and self._state != "active":
                    countdown_value = None
        elif self._state == "active":
            show_box = roi_box is not None
        elif self._state == "frozen":
            if self._frozen_until is None:
                self.reset()
                return ROIResult(state="idle", roi_box=None, show_box=False, countdown_value=None, frozen_remaining=None)
            frozen_remaining = max(0.0, self._frozen_until - timestamp)
            if frozen_remaining <= 0.0:
                self.reset()
                return ROIResult(state="idle", roi_box=None, show_box=False, countdown_value=None, frozen_remaining=None)
            show_box = roi_box is not None

        return ROIResult(
            state=self._state,
            roi_box=roi_box if show_box else None,
            show_box=show_box,
            countdown_value=countdown_value,
            frozen_remaining=frozen_remaining,
        )
