from __future__ import annotations

import signal
import time
import math
from typing import Optional, Tuple

import cv2
import numpy as np

from airmouse.config import AppConfig, load_config
from airmouse.control import EntryDebounceConfig, HandEntryGate, HandMotionEstimator, MousePointer
from airmouse.gestures import GestureAction, PinchClickGesture, ScrollGesture
from airmouse.io import CameraStream
from airmouse.monitoring import Monitor
from airmouse.utils import calculate_distance, calculate_normalized_distance
from airmouse.vision import HandTracker
from airmouse.roi import ROIConfig, ROIManager, ROIResult

HAND_CONNECTIONS: Tuple[Tuple[int, int], ...] = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17),
)
SKELETON_COLOR: Tuple[int, int, int] = (140, 184, 218)

class AirMouseApplication:
    """Top-level orchestration for the AirMouse pipeline."""

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        self.config = config or load_config()
        self.pointer = MousePointer()
        self.motion = HandMotionEstimator(self.config.motion)
        entry_gate_config = getattr(self.config, "entry_gate", EntryDebounceConfig())
        self.entry_gate = HandEntryGate(entry_gate_config)
        self.entry_gate.prime_output(self.pointer.position)
        roi_config = getattr(self.config, "roi", ROIConfig())
        self.roi_manager = ROIManager(roi_config)
        # Hand gesture recognisers configured from AppConfig
        self.pinch_gesture = PinchClickGesture(
            window_size=self.config.pinch_gesture.window_size,
            stability_duration=self.config.pinch_gesture.stability_duration,
            threshold_margin=self.config.pinch_gesture.threshold_margin,
            low_speed_threshold=self.config.pinch_gesture.low_speed_threshold,
            freeze_thresholds_during_hold=self.config.pinch_gesture.freeze_thresholds_during_hold,
        )
        self.scroll_gesture = ScrollGesture(
            window_size=self.config.scroll_gesture.window_size,
            stability_duration=self.config.scroll_gesture.stability_duration,
            threshold_margin=self.config.scroll_gesture.threshold_margin,
            stability_radius=self.config.scroll_gesture.stability_radius,
            low_speed_threshold=self.config.scroll_gesture.low_speed_threshold,
            smoothness=self.config.scroll_gesture.smoothness,
            decay=self.config.scroll_gesture.decay,
            speed_factor=self.config.scroll_gesture.speed_factor,
        )
        if self.config.monitor.enabled:
            monitor_cfg = self.config.monitor
            self.monitor = Monitor(
                frame_num_max=monitor_cfg.graph.frame_num_max,
                base_y=monitor_cfg.graph.base_y,
                scale_factor=monitor_cfg.graph.scale_factor,
                horizontal_scale=monitor_cfg.graph.horizontal_scale,
                pinch_debug_enabled=monitor_cfg.display.pinch_debug_terminal,
                draw_skeleton=monitor_cfg.display.draw_skeleton,
            )
        else:
            self.monitor = None

        self._last_raw_position = None
        self._left_pressed = False  # robust press latch synced with gesture state
        self._running = False

    def run(self) -> None:
        self._running = True
        camera_stream = CameraStream(self.config.camera)
        hand_tracker = HandTracker(self.config.hand_tracker)

        def _handle_signal(signum, frame):
            self.stop()

        previous_signal_handlers = {
            signal.SIGINT: signal.getsignal(signal.SIGINT),
            signal.SIGTERM: signal.getsignal(signal.SIGTERM),
        }
        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)

        try:
            for frame in camera_stream.frames():
                if not self._running:
                    break

                frame_start = time.time()
                hand_move_speed = 0.0
                pinch_action_label = None
                scroll_action_labels = []

                # Diagnostics values for overlay
                normalized_4to8_val = None
                normalized_4to12_val = None
                pinch_dyn = pinch_low = pinch_high = None
                scroll_dyn = scroll_low = scroll_high = None

                frame_height, frame_width = frame.shape[:2]
                timestamp_ms = frame_start * 1000.0
                hand_list = list(hand_tracker.process(frame))
                main_hand = hand_list[0] if hand_list else None

                gate_output = None
                gate_status = "no_hand"
                gate_gain = 0.0
                allow_actions = False
                anchor_norm = None
                roi_result = None

                if main_hand is None:
                    gate_output = self.entry_gate.update(
                        hand_present=False,
                        cam_xy=None,
                        screen_xy=None,
                        timestamp_ms=timestamp_ms,
                    )
                    gate_status = gate_output.status
                    gate_gain = gate_output.gain
                    self.pinch_gesture.reset()
                    self.scroll_gesture.reset()
                    self._last_raw_position = None
                    if self.monitor:
                        self.monitor.log_pinch_debug(**self.pinch_gesture.get_debug_state())
                    roi_result = self.roi_manager.update(
                        timestamp=frame_start,
                        frame_size=(frame_width, frame_height),
                        hand_present=False,
                        cx=None,
                        cy=None,
                        scale=None,
                        gate_status=gate_status,
                    )
                else:
                    anchor_norm = self.motion.get_pointer_anchor(main_hand)
                    x, y = self.motion.map_to_screen(main_hand)

                    raw_position = (x, y)
                    hand_move_speed = self.motion.update_speed(raw_position)
                    smooth_x, smooth_y = self.motion.smooth(x, y, hand_move_speed)
                    cam_xy = (anchor_norm[0] * frame_width, anchor_norm[1] * frame_height)

                    xs = [lm.x for lm in main_hand.landmark]
                    ys = [lm.y for lm in main_hand.landmark]
                    min_x, max_x = min(xs), max(xs)
                    min_y, max_y = min(ys), max(ys)
                    bbox_width_px = max(1.0, (max_x - min_x) * frame_width)
                    bbox_height_px = max(1.0, (max_y - min_y) * frame_height)
                    scale_px = math.hypot(bbox_width_px, bbox_height_px)
                    cx_px = ((min_x + max_x) / 2.0) * frame_width
                    cy_px = ((min_y + max_y) / 2.0) * frame_height

                    gate_output = self.entry_gate.update(
                        hand_present=True,
                        cam_xy=cam_xy,
                        screen_xy=(smooth_x, smooth_y),
                        timestamp_ms=timestamp_ms,
                    )
                    gate_status = gate_output.status
                    gate_gain = gate_output.gain
                    allow_actions = gate_output.allow_actions

                    target_xy = gate_output.out_xy or (smooth_x, smooth_y)
                    if target_xy is not None:
                        self.pointer.move_to(int(target_xy[0]), int(target_xy[1]))

                    roi_result = self.roi_manager.update(
                        timestamp=frame_start,
                        frame_size=(frame_width, frame_height),
                        hand_present=True,
                        cx=cx_px,
                        cy=cy_px,
                        scale=scale_px,
                        gate_status=gate_status,
                    )
                    allow_actions = allow_actions and roi_result.state in {"active", "snap_hold"}

                    thumb_tip = main_hand.landmark[4]
                    index_tip = main_hand.landmark[8]
                    middle_tip = main_hand.landmark[12]
                    distance_4to8 = calculate_distance(thumb_tip, index_tip)
                    reference_4to8 = calculate_distance(main_hand.landmark[3], main_hand.landmark[7])
                    distance_4to12 = calculate_distance(thumb_tip, middle_tip)
                    reference_4to12 = calculate_distance(main_hand.landmark[3], main_hand.landmark[11])

                    normalized_4to8 = calculate_normalized_distance(distance_4to8, reference_4to8)
                    normalized_4to8_val = normalized_4to8
                    normalized_4to12 = calculate_normalized_distance(distance_4to12, reference_4to12)
                    normalized_4to12_val = normalized_4to12

                    self._draw_hand_overlay(frame, main_hand, anchor_norm)
                    if allow_actions:
                        pinch_action = self.pinch_gesture.update(normalized_4to8, hand_move_speed)
                        if self.monitor:
                            self.monitor.log_pinch_debug(**self.pinch_gesture.get_debug_state())
                        if pinch_action:
                            pinch_action_label = pinch_action
                            if pinch_action == "click":
                                self.pointer.click_left()
                            elif pinch_action == "pitch":
                                self.pointer.press_left()
                                self._left_pressed = True
                            elif pinch_action == "release":
                                self.pointer.release_left()
                                self._left_pressed = False

                        anchor_position = self._last_raw_position
                        scroll_actions = self.scroll_gesture.update(
                            normalized_4to12,
                            (smooth_x, smooth_y),
                            anchor_position,
                            hand_move_speed,
                        )

                        for action in scroll_actions:
                            self._handle_scroll_action(action)
                            scroll_action_labels.append(action.kind)
                    else:
                        self.pinch_gesture.reset()
                        self.scroll_gesture.reset()
                        if self.monitor:
                            self.monitor.log_pinch_debug(**self.pinch_gesture.get_debug_state())

                    self._last_raw_position = raw_position

                    if self.monitor:
                        if self.pinch_gesture.dynamic_line_history:
                            self.monitor.update_curve_data(
                                "4to8",
                                self.pinch_gesture.dynamic_line_history[-1],
                                self.pinch_gesture.dynamic_threshold_low_history[-1],
                                self.pinch_gesture.dynamic_threshold_high_history[-1],
                                normalized_4to8,
                            )
                            pinch_dyn = self.pinch_gesture.dynamic_line_history[-1]
                            pinch_low = self.pinch_gesture.dynamic_threshold_low_history[-1]
                            pinch_high = self.pinch_gesture.dynamic_threshold_high_history[-1]
                        if self.scroll_gesture.dynamic_line_history:
                            self.monitor.update_curve_data(
                                "4to12",
                                self.scroll_gesture.dynamic_line_history[-1],
                                self.scroll_gesture.dynamic_threshold_low_history[-1],
                                self.scroll_gesture.dynamic_threshold_high_history[-1],
                                normalized_4to12,
                            )
                            scroll_dyn = self.scroll_gesture.dynamic_line_history[-1]
                            scroll_low = self.scroll_gesture.dynamic_threshold_low_history[-1]
                            scroll_high = self.scroll_gesture.dynamic_threshold_high_history[-1]
                        action_text = ",".join(filter(None, [pinch_action_label, *scroll_action_labels])) or "none"
                        self.monitor.log_data(time.time(), action_text, normalized_4to8, normalized_4to12)

                if roi_result:
                    self._draw_roi_overlay(frame, roi_result)

                mirrored_frame = cv2.flip(frame, 1)
                fps = 1.0 / max(time.time() - frame_start, 1e-6)

                # Robust state-sync: if gesture thinks we're pitching but we somehow
                # missed the one-shot 'pitch' event, press once here.
                if self.pinch_gesture.is_pitching and not self._left_pressed:
                    self.pointer.press_left()
                    self._left_pressed = True
                # If no longer pitching nor holding but button is down, release.
                if not self.pinch_gesture.is_pitching and not self.pinch_gesture.is_holding and self._left_pressed:
                    self.pointer.release_left()
                    self._left_pressed = False

                if self.monitor:
                    monitor_cfg = self.config.monitor
                    # Compose overlay lines for HOLD-related diagnostics
                    lines = []
                    lines.append(
                        f"Pinch norm(4-8): {normalized_4to8_val:.3f}" if normalized_4to8_val is not None else "Pinch norm(4-8): N/A"
                    )
                    if pinch_dyn is not None:
                        lines.append(f"Pinch dyn/low/high: {pinch_dyn:.3f}/{pinch_low:.3f}/{pinch_high:.3f}")
                    lines.append(
                        f"Pinch hold:{self.pinch_gesture.is_holding} pitch:{self.pinch_gesture.is_pitching}"
                    )
                    # Add more internals helpful for pitch debugging
                    elapsed = (time.time() - (self.pinch_gesture.start_time or time.time())) if self.pinch_gesture.is_holding else 0.0
                    lines.append(
                        f"Pinch elapsed:{elapsed:.2f}s clickLevel:{getattr(self.pinch_gesture, 'click_return_level', None)}"
                    )
                    lines.append(
                        f"Pinch release up/low/level: {getattr(self.pinch_gesture, 'release_return_level_up', None)} / "
                        f"{getattr(self.pinch_gesture, 'release_return_level_low', None)} / "
                        f"{getattr(self.pinch_gesture, 'release_return_level', None)}"
                    )
                    lines.append(f"Entry gate: {gate_status} gain:{gate_gain:.2f} allow:{allow_actions}")
                    if roi_result:
                        lines.append(
                            f"ROI state:{roi_result.state} show:{roi_result.show_box} countdown:{roi_result.countdown_value}"
                        )
                    lines.append(
                        "Pinch params: "
                        f"win={self.pinch_gesture.window_size} "
                        f"stab={self.pinch_gesture.stability_duration:.2f}s "
                        f"margin={self.pinch_gesture.threshold_margin:.2f} "
                        f"lowspd={self.pinch_gesture.low_speed_threshold:.0f} "
                        f"freeze={self.pinch_gesture.freeze_thresholds_during_hold}"
                    )

                    lines.append(
                        f"Scroll norm(4-12): {normalized_4to12_val:.3f}" if normalized_4to12_val is not None else "Scroll norm(4-12): N/A"
                    )
                    if scroll_dyn is not None:
                        lines.append(f"Scroll dyn/low/high: {scroll_dyn:.3f}/{scroll_low:.3f}/{scroll_high:.3f}")
                    lines.append(
                        f"Scroll hold:{self.scroll_gesture.is_holding} pitch:{self.scroll_gesture.is_pitching}"
                    )
                    lines.append(
                        "Scroll params: "
                        f"win={self.scroll_gesture.window_size} "
                        f"stab={self.scroll_gesture.stability_duration:.2f}s "
                        f"margin={self.scroll_gesture.threshold_margin:.2f} "
                        f"lowspd={self.scroll_gesture.low_speed_threshold:.0f}"
                    )

                    if monitor_cfg.display.show_camera_feed:
                        self.monitor.display_camera_feed(mirrored_frame, hand_move_speed, fps, lines)

                    if monitor_cfg.display.show_graph_window:
                        graph_frame = np.zeros(
                            (monitor_cfg.graph.height, monitor_cfg.graph.width, 3), dtype=np.uint8
                        )
                        self.monitor.display_graphs(graph_frame)
                        cv2.imshow("Graph Monitor", graph_frame)
                else:
                    cv2.imshow("Camera Feed", mirrored_frame)

                if cv2.waitKey(1) & 0xFF == 27:
                    break

        finally:
            for sig, handler in previous_signal_handlers.items():
                signal.signal(sig, handler)
            self._running = False
            camera_stream.release()
            hand_tracker.close()
            cv2.destroyAllWindows()

    def stop(self) -> None:
        self._running = False

    def _draw_hand_overlay(
        self,
        frame,
        hand_landmarks,
        anchor_norm: Optional[Tuple[float, float]],
    ) -> None:
        if not self.config.monitor.display.draw_skeleton:
            return

        if frame is None or hand_landmarks is None:
            return

        height, width = frame.shape[:2]
        if height == 0 or width == 0:
            return

        def _to_pixel(nx: float, ny: float) -> Tuple[int, int]:
            px = int(round(nx * width))
            py = int(round(ny * height))
            px = max(0, min(width - 1, px))
            py = max(0, min(height - 1, py))
            return px, py

        landmark_pixels = [_to_pixel(landmark.x, landmark.y) for landmark in hand_landmarks.landmark]

        for start_idx, end_idx in HAND_CONNECTIONS:
            start_point = landmark_pixels[start_idx]
            end_point = landmark_pixels[end_idx]
            cv2.line(frame, start_point, end_point, SKELETON_COLOR, 2)

        for px, py in landmark_pixels:
            cv2.circle(frame, (px, py), 4, SKELETON_COLOR, -1)

        if anchor_norm is None:
            return

        anchor_px, anchor_py = _to_pixel(anchor_norm[0], anchor_norm[1])
        cross_size = 6

        def _clamp_point(px: int, py: int) -> Tuple[int, int]:
            px = max(0, min(width - 1, px))
            py = max(0, min(height - 1, py))
            return px, py

        top_left = _clamp_point(anchor_px - cross_size, anchor_py - cross_size)
        bottom_right = _clamp_point(anchor_px + cross_size, anchor_py + cross_size)
        top_right = _clamp_point(anchor_px + cross_size, anchor_py - cross_size)
        bottom_left = _clamp_point(anchor_px - cross_size, anchor_py + cross_size)

        cv2.line(frame, top_left, bottom_right, SKELETON_COLOR, 2)
        cv2.line(frame, top_right, bottom_left, SKELETON_COLOR, 2)

    def _draw_roi_overlay(self, frame, roi_result: ROIResult) -> None:
        if frame is None or roi_result is None:
            return

        box_color = (0, 255, 0)
        thickness = 2

        if roi_result.roi_box and roi_result.show_box:
            x0, y0, w, h = roi_result.roi_box
            top_left = (max(0, x0), max(0, y0))
            bottom_right = (min(frame.shape[1] - 1, x0 + w), min(frame.shape[0] - 1, y0 + h))
            cv2.rectangle(frame, top_left, bottom_right, box_color, thickness)

            if roi_result.state == "snap_hold":
                corner_len = max(6, int(min(w, h) * 0.12))
                corners = [
                    ((x0, y0), (x0 + corner_len, y0)),
                    ((x0, y0), (x0, y0 + corner_len)),
                    ((x0 + w, y0), (x0 + w - corner_len, y0)),
                    ((x0 + w, y0), (x0 + w, y0 + corner_len)),
                    ((x0, y0 + h), (x0 + corner_len, y0 + h)),
                    ((x0, y0 + h), (x0, y0 + h - corner_len)),
                    ((x0 + w, y0 + h), (x0 + w - corner_len, y0 + h)),
                    ((x0 + w, y0 + h), (x0 + w, y0 + h - corner_len)),
                ]
                for start, end in corners:
                    cv2.line(frame, start, end, box_color, thickness)

        if roi_result.state == "out_of_bounds":
            message = "Move hand back into view"
            font_scale = max(frame.shape[1], frame.shape[0]) / 900.0
            font_scale = max(0.6, min(1.0, font_scale))
            text_size, _ = cv2.getTextSize(message, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 2)
            pos = ((frame.shape[1] - text_size[0]) // 2, int(40 + text_size[1]))
            cv2.putText(frame, message, pos, cv2.FONT_HERSHEY_SIMPLEX, font_scale, (200, 200, 200), 2, cv2.LINE_AA)

        if roi_result.state == "countdown" and roi_result.countdown_value and roi_result.countdown_value > 0:
            text = str(roi_result.countdown_value)
            font_scale = max(frame.shape[1], frame.shape[0]) / 450.0
            font_scale = max(1.0, min(3.0, font_scale))
            thickness_ct = 4
            text_size, _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness_ct)
            text_x = (frame.shape[1] - text_size[0]) // 2
            text_y = (frame.shape[0] + text_size[1]) // 2
            cv2.putText(frame, text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), thickness_ct, cv2.LINE_AA)

    def _handle_scroll_action(self, action: GestureAction) -> None:
        if action.kind == "right_click":
            self.pointer.click_right()
        elif action.kind == "scroll":
            self.pointer.scroll(action.dx, action.dy)
        elif action.kind in {"scroll_start", "scroll_end"}:
            return
        else:
            raise ValueError(f"Unknown scroll action: {action.kind}")
