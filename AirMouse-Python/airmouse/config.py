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
    show_graph_window: bool = False
    draw_skeleton: bool = False
    draw_anchor: bool = True
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
class FramePreprocessConfig:
    mirror_horizontal: bool = True
    mirror_vertical: bool = True


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
    preprocess: FramePreprocessConfig
    roi_edge_padding: float
    roi_exit_countdown: float
    roi_auto_reset: bool


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
    preprocess = FramePreprocessConfig(
        mirror_horizontal=_env_bool("AIRMOUSE_MIRROR_HORIZONTAL", True),
        mirror_vertical=_env_bool("AIRMOUSE_MIRROR_VERTICAL", False),  # 大多数摄像头（包括 FaceTime）不需要垂直翻转
    )
    roi_exit_countdown = _env_float("AIRMOUSE_ROI_EXIT_COUNTDOWN", 5.0)
    roi_auto_reset = _env_bool("AIRMOUSE_ROI_AUTO_RESET", True)
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
    screen_aspect_ratio = 1.0
    if motion.screen_height:
        screen_aspect_ratio = max(0.01, motion.screen_width / float(motion.screen_height))
    monitor_display = MonitorDisplayConfig(
        show_camera_feed=_env_bool("AIRMOUSE_MONITOR_SHOW_CAMERA", True),
        show_graph_window=_env_bool("AIRMOUSE_MONITOR_SHOW_GRAPH", False),
        draw_skeleton=_env_bool("AIRMOUSE_MONITOR_DRAW_SKELETON", False),
        draw_anchor=_env_bool("AIRMOUSE_MONITOR_DRAW_ANCHOR", True),
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
        debounce_ms=_env_int("AIRMOUSE_ENTRY_DEBOUNCE_MS", 220),
        stable_frames=_env_int("AIRMOUSE_ENTRY_STABLE_FRAMES", 4),
        jitter_px=_env_float("AIRMOUSE_ENTRY_JITTER_PX", 6.0),
        softstart_ms=_env_int("AIRMOUSE_ENTRY_SOFTSTART_MS", 250),
        gain0=_env_float("AIRMOUSE_ENTRY_GAIN0", 0.25),
        lost_tol=_env_int("AIRMOUSE_ENTRY_LOST_TOL", 5),
        mode_movement=_env_str("AIRMOUSE_ENTRY_MODE", "freeze"),
    )
    roi_base_scale = _env_float("AIRMOUSE_ROI_BASE_SCALE", 1.2)
    roi_width_ratio = _env_float("AIRMOUSE_ROI_WIDTH_RATIO", 1.5)
    roi_height_ratio = _env_float("AIRMOUSE_ROI_HEIGHT_RATIO", 1.0)
    touchpad_multiplier = _env_float(
        "AIRMOUSE_TOUCHPAD_MULTIPLIER",
        roi_base_scale * roi_width_ratio,
    )
    roi = ROIConfig(
        base_scale=roi_base_scale,
        width_ratio=roi_width_ratio,
        height_ratio=roi_height_ratio,
        touchpad_width_multiplier=touchpad_multiplier,
        target_aspect_ratio=screen_aspect_ratio,
        min_width_frac=_env_float("AIRMOUSE_ROI_MIN_WIDTH_FRAC", 0.15),
        max_width_frac=_env_float("AIRMOUSE_ROI_MAX_WIDTH_FRAC", 0.70),
        fit_margin=_env_float("AIRMOUSE_ROI_FIT_MARGIN", 16.0),
        countdown_seconds=_env_float("AIRMOUSE_ROI_COUNTDOWN_SECONDS", 3.0),
        freeze_seconds=_env_float("AIRMOUSE_ROI_FREEZE_SECONDS", 5.0),
        lost_tol=_env_int("AIRMOUSE_ROI_LOST_TOL", 8),
        position_smooth_beta=_env_float("AIRMOUSE_ROI_POSITION_BETA", 0.25),
        size_smooth_beta=_env_float("AIRMOUSE_ROI_SIZE_BETA", 0.20),
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
        preprocess=preprocess,
        roi_edge_padding=_env_float("AIRMOUSE_ROI_EDGE_PADDING", 0.05),
        roi_exit_countdown=roi_exit_countdown,
        roi_auto_reset=roi_auto_reset,
    )
