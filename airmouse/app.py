from __future__ import annotations

import signal
import time
import math
from typing import Optional, Tuple

import cv2
import numpy as np

from airmouse.config import AppConfig, FramePreprocessConfig, load_config
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

    ROI_EXIT_COUNTDOWN_SEC = 5.0

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        self.config = config or load_config()
        preprocess_config = getattr(self.config, "preprocess", FramePreprocessConfig())
        self.preprocess = preprocess_config
        self._mirror_horizontal = bool(preprocess_config.mirror_horizontal)
        self._mirror_vertical = bool(preprocess_config.mirror_vertical)
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
        self._roi_exit_deadline: Optional[float] = None

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
            for raw_frame in camera_stream.frames():
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

                processed_frame = self._preprocess_frame(raw_frame)
                frame_height, frame_width = processed_frame.shape[:2]
                timestamp_ms = frame_start * 1000.0
                hand_list = list(hand_tracker.process(processed_frame))
                main_hand = hand_list[0] if hand_list else None

                gate_output = None
                gate_status = "no_hand"
                gate_gain = 0.0
                allow_actions = False
                anchor_norm = None
                anchor_px = None
                anchor_py = None
                roi_result = None
                display_hand = None
                roi_exit_countdown = None

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
                    self._roi_exit_deadline = None
                    if self.monitor:
                        self.monitor.log_pinch_debug(**self.pinch_gesture.get_debug_state())
                    roi_result = self.roi_manager.update(
                        timestamp=frame_start,
                        frame_size=(frame_width, frame_height),
                        hand_present=False,
                        cx=None,
                        cy=None,
                        scale=None,
                    )
                else:
                    anchor_norm = self.motion.get_pointer_anchor(main_hand)
                    anchor_px = anchor_norm[0] * frame_width
                    anchor_py = anchor_norm[1] * frame_height
                    display_hand = main_hand
                    cam_xy = (anchor_px, anchor_py)

                    xs = [lm.x for lm in main_hand.landmark]
                    ys = [lm.y for lm in main_hand.landmark]
                    min_x, max_x = min(xs), max(xs)
                    min_y, max_y = min(ys), max(ys)
                    bbox_width_px = max(1.0, (max_x - min_x) * frame_width)
                    bbox_height_px = max(1.0, (max_y - min_y) * frame_height)
                    scale_px = math.hypot(bbox_width_px, bbox_height_px)
                    cx_px = ((min_x + max_x) / 2.0) * frame_width
                    cy_px = ((min_y + max_y) / 2.0) * frame_height

                    roi_result = self.roi_manager.update(
                        timestamp=frame_start,
                        frame_size=(frame_width, frame_height),
                        hand_present=True,
                        cx=cx_px,
                        cy=cy_px,
                        scale=scale_px,
                    )

                    roi_target = None
                    roi_box = roi_result.roi_box if roi_result else None
                    roi_active = roi_result.state == "active" and roi_box is not None
                    anchor_in_roi = (
                        roi_active and self._point_inside_roi(anchor_px, anchor_py, roi_box)
                    )
                    roi_exit_countdown, timed_out = self._update_roi_exit_timer(
                        roi_active, anchor_in_roi, frame_start
                    )
                    if timed_out:
                        continue
                    if anchor_in_roi and roi_box is not None:
                        roi_target = self._map_roi_to_screen(roi_box, anchor_px, anchor_py)

                    gate_input_xy = roi_target or self.pointer.position

                    gate_output = self.entry_gate.update(
                        hand_present=True,
                        cam_xy=cam_xy,
                        screen_xy=gate_input_xy,
                        timestamp_ms=timestamp_ms,
                    )
                    gate_status = gate_output.status
                    gate_gain = gate_output.gain
                    allow_actions = gate_output.allow_actions and roi_active and anchor_in_roi

                    previous_target_xy = self._last_raw_position
                    smooth_coords: Optional[Tuple[int, int]] = None
                    final_target_xy = gate_output.out_xy if anchor_in_roi else None
                    if final_target_xy is not None:
                        final_target_xy = (int(final_target_xy[0]), int(final_target_xy[1]))
                        hand_move_speed = self.motion.update_speed(final_target_xy)
                        smooth_x, smooth_y = self.motion.smooth(
                            final_target_xy[0], final_target_xy[1], hand_move_speed
                        )
                        smooth_coords = (smooth_x, smooth_y)
                        self.pointer.move_to(smooth_x, smooth_y)
                        self._last_raw_position = final_target_xy
                    else:
                        hand_move_speed = 0.0

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

                        anchor_position = previous_target_xy
                        scroll_actions = self.scroll_gesture.update(
                            normalized_4to12,
                            smooth_coords or self.pointer.position,
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

                if display_hand is not None:
                    self._draw_hand_overlay(processed_frame, display_hand, anchor_norm)
                if roi_result:
                    self._draw_roi_overlay(
                        processed_frame,
                        roi_result,
                        exit_countdown=roi_exit_countdown,
                    )

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
                    if monitor_cfg.display.show_camera_feed:
                        self.monitor.display_camera_feed(processed_frame)

                    if monitor_cfg.display.show_graph_window:
                        graph_frame = np.zeros(
                            (monitor_cfg.graph.height, monitor_cfg.graph.width, 3), dtype=np.uint8
                        )
                        self.monitor.display_graphs(graph_frame)
                        cv2.imshow("Graph Monitor", graph_frame)
                else:
                    cv2.imshow("Camera Feed", processed_frame)

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

        landmark_pixels = [
            self._normalized_to_display_pixel(landmark.x, landmark.y, width, height)
            for landmark in hand_landmarks.landmark
        ]

        for start_idx, end_idx in HAND_CONNECTIONS:
            start_point = landmark_pixels[start_idx]
            end_point = landmark_pixels[end_idx]
            cv2.line(frame, start_point, end_point, SKELETON_COLOR, 2)

        for px, py in landmark_pixels:
            cv2.circle(frame, (px, py), 4, SKELETON_COLOR, -1)

        if anchor_norm is None:
            return

        anchor_x = min(max(anchor_norm[0], 0.0), 1.0)
        anchor_y = min(max(anchor_norm[1], 0.0), 1.0)
        anchor_px = int(round(anchor_x * (width - 1)))
        anchor_py = int(round(anchor_y * (height - 1)))
        anchor_px = max(0, min(width - 1, anchor_px))
        anchor_py = max(0, min(height - 1, anchor_py))
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

    def _draw_roi_overlay(
        self,
        frame,
        roi_result: ROIResult,
        *,
        exit_countdown: Optional[float] = None,
    ) -> None:
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

        if roi_result.state == "preview" and not roi_result.show_box:
            message = "Move hand inside frame to continue"
            font_scale = max(frame.shape[1], frame.shape[0]) / 900.0
            font_scale = max(0.6, min(1.2, font_scale))
            text_size, _ = cv2.getTextSize(message, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 2)
            pos = ((frame.shape[1] - text_size[0]) // 2, int(40 + text_size[1]))
            cv2.putText(frame, message, pos, cv2.FONT_HERSHEY_SIMPLEX, font_scale, (200, 200, 200), 2, cv2.LINE_AA)

        if roi_result.state == "preview" and roi_result.countdown_value and roi_result.countdown_value > 0:
            text = str(roi_result.countdown_value)
            font_scale = max(frame.shape[1], frame.shape[0]) / 450.0
            font_scale = max(1.0, min(3.0, font_scale))
            thickness_ct = 4
            text_size, _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness_ct)
            text_x = (frame.shape[1] - text_size[0]) // 2
            text_y = (frame.shape[0] + text_size[1]) // 2
            cv2.putText(frame, text, (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), thickness_ct, cv2.LINE_AA)

        if roi_result.state == "frozen" and roi_result.frozen_remaining:
            message = f"Frozen {roi_result.frozen_remaining:.1f}s"
            font_scale = max(frame.shape[1], frame.shape[0]) / 900.0
            font_scale = max(0.6, min(1.2, font_scale))
            text_size, _ = cv2.getTextSize(message, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 2)
            pos = ((frame.shape[1] - text_size[0]) // 2, int(frame.shape[0] * 0.12))
            cv2.putText(frame, message, pos, cv2.FONT_HERSHEY_SIMPLEX, font_scale, (180, 255, 180), 2, cv2.LINE_AA)

        if exit_countdown is not None and exit_countdown > 0.0:
            message = f"Re-center in {exit_countdown:.1f}s"
            font_scale = max(frame.shape[1], frame.shape[0]) / 1200.0
            font_scale = max(0.5, min(1.0, font_scale))
            text_size, _ = cv2.getTextSize(message, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 2)
            pos = ((frame.shape[1] - text_size[0]) // 2, int(frame.shape[0] * 0.9))
            cv2.putText(frame, message, pos, cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 200, 255), 2, cv2.LINE_AA)

    def _map_roi_to_screen(self, roi_box: Tuple[int, int, int, int], cx_px: float, cy_px: float) -> Tuple[int, int]:
        x0, y0, w, h = roi_box
        w = max(w, 1)
        h = max(h, 1)
        u = (cx_px - x0) / w
        v = (cy_px - y0) / h
        u = float(min(max(u, 0.0), 1.0))
        v = float(min(max(v, 0.0), 1.0))

        screen_width = self.motion.config.screen_width
        screen_height = self.motion.config.screen_height
        screen_x = int(round(u * screen_width))
        screen_y = int(round(v * screen_height))
        return screen_x, screen_y

    def _preprocess_frame(self, frame):
        if self._mirror_horizontal and self._mirror_vertical:
            return cv2.flip(frame, -1)
        if self._mirror_horizontal:
            return cv2.flip(frame, 1)
        if self._mirror_vertical:
            return cv2.flip(frame, 0)
        return frame

    def _normalized_to_display_pixel(self, nx: float, ny: float, width: int, height: int) -> Tuple[int, int]:
        nx = min(max(nx, 0.0), 1.0)
        ny = min(max(ny, 0.0), 1.0)
        px = int(round(nx * (width - 1)))
        py = int(round(ny * (height - 1)))
        px = max(0, min(width - 1, px))
        py = max(0, min(height - 1, py))
        return px, py

    def _point_inside_roi(
        self,
        px: Optional[float],
        py: Optional[float],
        roi_box: Optional[Tuple[int, int, int, int]],
    ) -> bool:
        if px is None or py is None or roi_box is None:
            return False
        x0, y0, w, h = roi_box
        return x0 <= px <= x0 + w and y0 <= py <= y0 + h

    def _update_roi_exit_timer(
        self,
        roi_active: bool,
        anchor_in_roi: bool,
        timestamp: float,
    ) -> Tuple[Optional[float], bool]:
        if not roi_active:
            self._roi_exit_deadline = None
            return None, False
        if anchor_in_roi:
            self._roi_exit_deadline = None
            return None, False

        if self._roi_exit_deadline is None:
            self._roi_exit_deadline = timestamp + self.ROI_EXIT_COUNTDOWN_SEC

        remaining = max(0.0, self._roi_exit_deadline - timestamp)
        if remaining <= 0.0:
            self._roi_exit_deadline = None
            self._handle_roi_timeout()
            return None, True
        return remaining, False

    def _handle_roi_timeout(self) -> None:
        self.roi_manager.reset()
        self.entry_gate.reset(preserve_output=True)
        self.pinch_gesture.reset()
        self.scroll_gesture.reset()
        self._last_raw_position = None
        if self._left_pressed:
            self.pointer.release_left()
            self._left_pressed = False

    def _handle_scroll_action(self, action: GestureAction) -> None:
        if action.kind == "right_click":
            self.pointer.click_right()
        elif action.kind == "scroll":
            self.pointer.scroll(action.dx, action.dy)
        elif action.kind in {"scroll_start", "scroll_end"}:
            return
        else:
            raise ValueError(f"Unknown scroll action: {action.kind}")
