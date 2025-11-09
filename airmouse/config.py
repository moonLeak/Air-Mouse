from __future__ import annotations

import os
from dataclasses import dataclass, field

from airmouse.control import EntryDebounceConfig, HandMotionConfig
from airmouse.roi import ROIConfig
from airmouse.io import CameraConfig
from airmouse.vision import HandTrackerConfig


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    stripped = value.strip()
    return stripped or default


@dataclass
class MonitorDisplayConfig:
    show_camera_feed: bool = True
    show_graph_window: bool = True
    draw_skeleton: bool = False
    pinch_debug_terminal: bool = False


@dataclass
class MonitorGraphConfig:
    width: int = 1200
    height: int = 800
    frame_num_max: int = 300
    base_y: int = 300
    scale_factor: int = 200
    horizontal_scale: int = 3


@dataclass
class MonitorConfig:
    enabled: bool = True
    display: MonitorDisplayConfig = field(default_factory=MonitorDisplayConfig)
    graph: MonitorGraphConfig = field(default_factory=MonitorGraphConfig)


@dataclass
class AppConfig:
    camera: CameraConfig
    hand_tracker: HandTrackerConfig
    motion: HandMotionConfig
    monitor: MonitorConfig
    entry_gate: EntryDebounceConfig
    roi: ROIConfig
    pinch_gesture: "PinchGestureConfig"
    scroll_gesture: "ScrollGestureConfig"


# --- Gesture configs ---

@dataclass
class PinchGestureConfig:
    window_size: int = 5
    stability_duration: float = 0.2
    threshold_margin: float = 0.15
    low_speed_threshold: float = 200.0
    freeze_thresholds_during_hold: bool = False


@dataclass
class ScrollGestureConfig:
    window_size: int = 5
    stability_duration: float = 0.25
    threshold_margin: float = 0.15
    stability_radius: float = 30.0
    low_speed_threshold: float = 200.0
    smoothness: float = 0.8
    decay: float = 0.9
    speed_factor: float = 0.5


def load_config() -> AppConfig:
    camera_defaults = CameraConfig()

    camera = CameraConfig(
        camera_index=_env_int("AIRMOUSE_CAMERA_INDEX", camera_defaults.camera_index),
        frame_scale=_env_float("AIRMOUSE_FRAME_SCALE", camera_defaults.frame_scale),
    )
    tracker = HandTrackerConfig(
        min_detection_confidence=_env_float("AIRMOUSE_DETECTION_CONFIDENCE", 0.5),
        min_tracking_confidence=_env_float("AIRMOUSE_TRACKING_CONFIDENCE", 0.3),
        max_num_hands=_env_int("AIRMOUSE_MAX_HANDS", 1),
    )
    motion = HandMotionConfig.from_defaults(
        extend_ratio_x=_env_float("AIRMOUSE_EXTEND_RATIO_X", 2.5),
        extend_ratio_y=_env_float("AIRMOUSE_EXTEND_RATIO_Y", 2.5),
        low_speed_threshold=_env_float("AIRMOUSE_LOW_SPEED_THRESHOLD", 200.0),
    )
    monitor_display = MonitorDisplayConfig(
        show_camera_feed=_env_bool("AIRMOUSE_MONITOR_SHOW_CAMERA", True),
        show_graph_window=_env_bool("AIRMOUSE_MONITOR_SHOW_GRAPH", True),
        draw_skeleton=_env_bool("AIRMOUSE_MONITOR_DRAW_SKELETON", True),
        pinch_debug_terminal=_env_bool("AIRMOUSE_MONITOR_PINCH_DEBUG", False),
    )
    monitor_graph = MonitorGraphConfig(
        width=_env_int("AIRMOUSE_MONITOR_WIDTH", 1200),
        height=_env_int("AIRMOUSE_MONITOR_HEIGHT", 800),
        frame_num_max=_env_int("AIRMOUSE_MONITOR_FRAME_MAX", 300),
        base_y=_env_int("AIRMOUSE_MONITOR_BASE_Y", 300),
        scale_factor=_env_int("AIRMOUSE_MONITOR_SCALE_FACTOR", 200),
        horizontal_scale=_env_int("AIRMOUSE_MONITOR_HORIZONTAL_SCALE", 3),
    )
    monitor = MonitorConfig(
        enabled=_env_bool("AIRMOUSE_MONITOR_ENABLED", True),
        display=monitor_display,
        graph=monitor_graph,
    )
    entry_gate = EntryDebounceConfig(
        debounce_ms=_env_int("AIRMOUSE_ENTRY_DEBOUNCE_MS", 1),
        stable_frames=_env_int("AIRMOUSE_ENTRY_STABLE_FRAMES", 4),
        jitter_px=_env_float("AIRMOUSE_ENTRY_JITTER_PX", 6.0),
        softstart_ms=_env_int("AIRMOUSE_ENTRY_SOFTSTART_MS", 250),
        gain0=_env_float("AIRMOUSE_ENTRY_GAIN0", 0.25),
        lost_tol=_env_int("AIRMOUSE_ENTRY_LOST_TOL", 5),
        mode_movement=_env_str("AIRMOUSE_ENTRY_MODE", "freeze"),
    )
    roi = ROIConfig(
        size_scale=_env_float("AIRMOUSE_ROI_SIZE_SCALE", 1.0),
        min_width_frac=_env_float("AIRMOUSE_ROI_MIN_WIDTH_FRAC", 0.30),
        max_width_frac=_env_float("AIRMOUSE_ROI_MAX_WIDTH_FRAC", 0.70),
        aspect_ratio=_env_float("AIRMOUSE_ROI_ASPECT_RATIO", 1.0),
        size_smooth_beta=_env_float("AIRMOUSE_ROI_SIZE_BETA", 0.08),
        size_hysteresis=_env_float("AIRMOUSE_ROI_SIZE_HYSTERESIS", 0.10),
        size_rate_limit=_env_float("AIRMOUSE_ROI_SIZE_RATE_LIMIT", 400.0),
        margin_px=_env_float("AIRMOUSE_ROI_MARGIN_PX", 16.0),
        snap_band_frac=_env_float("AIRMOUSE_ROI_SNAP_BAND_FRAC", 0.05),
        hide_band_px=_env_float("AIRMOUSE_ROI_HIDE_BAND_PX", 24.0),
        hide_ms=_env_int("AIRMOUSE_ROI_HIDE_MS", 250),
        lost_tol=_env_int("AIRMOUSE_ROI_LOST_TOL", 8),
        freeze_seconds=_env_float("AIRMOUSE_ROI_FREEZE_SECONDS", 5.0),
        buffer_ms=_env_int("AIRMOUSE_ROI_BUFFER_MS", 300),
        countdown_seconds=_env_int("AIRMOUSE_ROI_COUNTDOWN_SECONDS", 3),
        countdown_samples=_env_int("AIRMOUSE_ROI_COUNTDOWN_SAMPLES", 5),
        stability_frames=_env_int("AIRMOUSE_ROI_STABILITY_FRAMES", 4),
    )

    pinch = PinchGestureConfig(
        window_size=_env_int("AIRMOUSE_PINCH_WINDOW_SIZE", 5),
        stability_duration=_env_float("AIRMOUSE_PINCH_STABILITY", 0.2),
        threshold_margin=_env_float("AIRMOUSE_PINCH_MARGIN", 0.15),
        low_speed_threshold=_env_float("AIRMOUSE_PINCH_LOW_SPEED", 200.0),
        freeze_thresholds_during_hold=_env_bool("AIRMOUSE_PINCH_FREEZE_HOLD", False),
    )

    scroll = ScrollGestureConfig(
        window_size=_env_int("AIRMOUSE_SCROLL_WINDOW_SIZE", 5),
        stability_duration=_env_float("AIRMOUSE_SCROLL_STABILITY", 0.25),
        threshold_margin=_env_float("AIRMOUSE_SCROLL_MARGIN", 0.15),
        stability_radius=_env_float("AIRMOUSE_SCROLL_RADIUS", 30.0),
        low_speed_threshold=_env_float("AIRMOUSE_SCROLL_LOW_SPEED", 200.0),
        smoothness=_env_float("AIRMOUSE_SCROLL_SMOOTHNESS", 0.8),
        decay=_env_float("AIRMOUSE_SCROLL_DECAY", 0.9),
        speed_factor=_env_float("AIRMOUSE_SCROLL_SPEED_FACTOR", 0.5),
    )

    return AppConfig(
        camera=camera,
        hand_tracker=tracker,
        motion=motion,
        monitor=monitor,
        entry_gate=entry_gate,
        roi=roi,
        pinch_gesture=pinch,
        scroll_gesture=scroll,
    )
