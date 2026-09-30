from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any, Dict, List, Tuple

import cv2


def _scan_cameras(max_index: int = 10) -> List[Tuple[int, str]]:
    """扫描当前系统可用的摄像头，返回 (index, 标签) 列表。

    通过依次尝试 index 0..max_index 来枚举，能成功打开且读取到帧的
    才算可用。在 macOS 上优先使用 AVFoundation 后端。
    """
    import platform
    results: List[Tuple[int, str]] = []
    for idx in range(max_index + 1):
        cap = None
        try:
            if platform.system() == "Darwin":
                cap = cv2.VideoCapture(idx, cv2.CAP_AVFOUNDATION)
            else:
                cap = cv2.VideoCapture(idx)

            if not cap.isOpened():
                continue

            # 实际读一帧验证可用性，最多等 3 秒
            ready = threading.Event()
            result_box: list = [False]

            def _check(c=cap, box=result_box, ev=ready):
                ret, _ = c.read()
                box[0] = ret
                ev.set()

            t = threading.Thread(target=_check, daemon=True)
            t.start()
            t.join(timeout=3.0)

            if result_box[0]:
                results.append((idx, f"Camera {idx}"))
        except Exception:
            pass
        finally:
            if cap is not None:
                cap.release()
    return results


class AirMouseGUI:
    """Simple Tkinter-based control panel for launching AirMouse with custom parameters."""
    SETTINGS_FILE = Path.home() / ".airmouse_gui_settings.json"

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("AirMouse Control Panel")
        style = ttk.Style(self.root)
        style.configure("Action.TButton", padding=(40, 20), font=("Helvetica", 12))

        self.process: subprocess.Popen | None = None
        self.log_thread: threading.Thread | None = None

        # 可用摄像头列表：[(index, label), ...]
        self._available_cameras: List[Tuple[int, str]] = []

        self._init_vars()
        self._build_layout()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # 启动时在后台自动扫描摄像头
        threading.Thread(target=self._scan_cameras_bg, daemon=True).start()

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #
    def _scan_cameras_bg(self) -> None:
        """后台扫描可用摄像头，完成后更新 UI。"""
        self.root.after(0, lambda: self.camera_scan_btn.configure(state="disabled", text="扫描中…"))
        cameras = _scan_cameras()
        self._available_cameras = cameras
        self.root.after(0, lambda: self._update_camera_dropdown(cameras))

    def _update_camera_dropdown(self, cameras: List[Tuple[int, str]]) -> None:
        """用扫描结果更新摄像头下拉菜单。"""
        self.camera_scan_btn.configure(state="normal", text="🔄 重新扫描")
        if not cameras:
            self.camera_combo["values"] = ["（未找到摄像头）"]
            self.camera_combo.current(0)
            self.camera_index_var.set("0")
            return

        labels = [f"{label}  (index={idx})" for idx, label in cameras]
        self.camera_combo["values"] = labels

        # 选中上次保存的 index（如有）
        saved_idx = int(self.camera_index_var.get())
        found = next((i for i, (idx, _) in enumerate(cameras) if idx == saved_idx), None)
        if found is not None:
            self.camera_combo.current(found)
        else:
            self.camera_combo.current(0)
            self.camera_index_var.set(str(cameras[0][0]))

        self.camera_combo.bind("<<ComboboxSelected>>", self._on_camera_selected)

    def _on_camera_selected(self, _event=None) -> None:
        """用户在下拉菜单选择摄像头时更新 camera_index_var。"""
        sel = self.camera_combo.current()
        if 0 <= sel < len(self._available_cameras):
            self.camera_index_var.set(str(self._available_cameras[sel][0]))

    def _init_vars(self) -> None:
        saved = self._load_saved_settings()

        self.camera_index_var = tk.StringVar(value=str(saved.get("camera_index", "0")))
        self.frame_scale_var = tk.StringVar(value=str(saved.get("frame_scale", "0.6")))
        self.mirror_horizontal_var = tk.BooleanVar(value=bool(saved.get("mirror_horizontal", True)))
        self.mirror_vertical_var = tk.BooleanVar(value=bool(saved.get("mirror_vertical", False)))
        self.roi_edge_padding_var = tk.StringVar(value=str(saved.get("roi_edge_padding", "0.05")))
        self.roi_entry_countdown_var = tk.StringVar(value=str(saved.get("roi_entry_countdown", "3.0")))
        self.roi_exit_countdown_var = tk.StringVar(value=str(saved.get("roi_exit_countdown", "5.0")))
        self.roi_auto_reset_var = tk.BooleanVar(value=bool(saved.get("roi_auto_reset", True)))
        self.touchpad_multiplier_var = tk.StringVar(value=str(saved.get("touchpad_multiplier", "2.5")))

        self.monitor_enabled_var = tk.BooleanVar(value=bool(saved.get("monitor_enabled", True)))
        self.monitor_camera_var = tk.BooleanVar(value=bool(saved.get("monitor_camera", True)))
        self.monitor_graph_var = tk.BooleanVar(value=bool(saved.get("monitor_graph", False)))
        self.monitor_skeleton_var = tk.BooleanVar(value=bool(saved.get("monitor_skeleton", False)))
        self.monitor_anchor_var = tk.BooleanVar(value=bool(saved.get("monitor_anchor", True)))

        self.pinch_margin_var = tk.StringVar(value=str(saved.get("pinch_margin", "0.15")))
        self.pinch_stability_var = tk.StringVar(value=str(saved.get("pinch_stability", "0.2")))
        self.scroll_speed_factor_var = tk.StringVar(value=str(saved.get("scroll_speed_factor", "0.5")))
        self.scroll_smoothness_var = tk.StringVar(value=str(saved.get("scroll_smoothness", "0.8")))

        self.status_var = tk.StringVar(value="Ready")

    def _build_layout(self) -> None:
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill="both", expand=True)

        camera_frame = ttk.LabelFrame(main, text="Camera")
        camera_frame.pack(fill="x", expand=True, pady=(0, 10))

        # 摄像头选择行：下拉 + 扫描按钮
        ttk.Label(camera_frame, text="Camera").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.camera_combo = ttk.Combobox(camera_frame, width=28, state="readonly")
        self.camera_combo["values"] = [f"Camera {self.camera_index_var.get()}  (index={self.camera_index_var.get()})"]
        self.camera_combo.current(0)
        self.camera_combo.grid(row=0, column=1, sticky="w", pady=4)
        self.camera_scan_btn = ttk.Button(
            camera_frame, text="🔄 重新扫描", command=lambda: threading.Thread(target=self._scan_cameras_bg, daemon=True).start()
        )
        self.camera_scan_btn.grid(row=0, column=2, padx=(8, 0), pady=4, sticky="w")

        self._add_labeled_entry(camera_frame, "Frame scale", self.frame_scale_var, 1)
        ttk.Checkbutton(
            camera_frame, text="Mirror horizontally", variable=self.mirror_horizontal_var
        ).grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(
            camera_frame, text="Mirror vertically", variable=self.mirror_vertical_var
        ).grid(row=3, column=0, columnspan=2, sticky="w")

        monitor_frame = ttk.LabelFrame(main, text="Monitor Overlay")
        monitor_frame.pack(fill="x", expand=True, pady=(0, 10))
        ttk.Checkbutton(
            monitor_frame, text="Enable monitor windows", variable=self.monitor_enabled_var
        ).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(
            monitor_frame, text="Show camera feed", variable=self.monitor_camera_var
        ).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(
            monitor_frame, text="Show graph window", variable=self.monitor_graph_var
        ).grid(row=2, column=0, sticky="w")
        ttk.Checkbutton(
            monitor_frame, text="Draw skeleton overlay", variable=self.monitor_skeleton_var
        ).grid(row=3, column=0, sticky="w")
        ttk.Checkbutton(
            monitor_frame, text="Show anchor marker", variable=self.monitor_anchor_var
        ).grid(row=4, column=0, sticky="w")

        pointer_frame = ttk.LabelFrame(main, text="Pointer mapping")
        pointer_frame.pack(fill="x", expand=True, pady=(0, 10))
        self._add_labeled_entry(
            pointer_frame, "ROI edge padding", self.roi_edge_padding_var, 0
        )
        ttk.Label(pointer_frame, text="(0.0 - 0.49, default 0.05)").grid(
            row=0, column=2, sticky="w"
        )
        self._add_labeled_entry(
            pointer_frame, "Entry countdown (s)", self.roi_entry_countdown_var, 1
        )
        self._add_labeled_entry(
            pointer_frame, "Re-entry countdown (s)", self.roi_exit_countdown_var, 2
        )
        self._add_labeled_entry(
            pointer_frame, "Touchpad size (× palm width)", self.touchpad_multiplier_var, 3
        )
        ttk.Label(pointer_frame, text="(n > 0, default 2.5)").grid(row=3, column=2, sticky="w")
        ttk.Checkbutton(
            pointer_frame,
            text="Auto re-center when hand leaves",
            variable=self.roi_auto_reset_var,
        ).grid(row=4, column=0, columnspan=2, sticky="w")

        gesture_frame = ttk.LabelFrame(main, text="Gesture tuning")
        gesture_frame.pack(fill="x", expand=True, pady=(0, 10))
        self._add_labeled_entry(gesture_frame, "Pinch margin", self.pinch_margin_var, 0)
        self._add_labeled_entry(gesture_frame, "Pinch stability (s)", self.pinch_stability_var, 1)
        self._add_labeled_entry(gesture_frame, "Scroll speed factor", self.scroll_speed_factor_var, 2)
        self._add_labeled_entry(gesture_frame, "Scroll smoothness", self.scroll_smoothness_var, 3)

        control_frame = ttk.Frame(main)
        control_frame.pack(fill="x", pady=(0, 10))
        self.start_button = ttk.Button(
            control_frame, text="Start AirMouse", command=self.start_airmouse, style="Action.TButton"
        )
        self.start_button.pack(side="left", padx=(0, 8))
        self.stop_button = ttk.Button(
            control_frame, text="Stop", command=self.stop_airmouse, state="disabled", style="Action.TButton"
        )
        self.stop_button.pack(side="left")
        ttk.Label(control_frame, textvariable=self.status_var).pack(side="right")

        log_frame = ttk.LabelFrame(main, text="日志 (遇到问题请点「📋 复制日志」发给开发者)")
        log_frame.pack(fill="both", expand=True)

        log_btn_bar = ttk.Frame(log_frame)
        log_btn_bar.pack(fill="x", pady=(4, 0))
        ttk.Button(log_btn_bar, text="📋 复制日志", command=self._copy_log).pack(side="left", padx=4)
        ttk.Button(log_btn_bar, text="🗑 清空日志", command=self._clear_log).pack(side="left", padx=4)

        self.log_widget = ScrolledText(log_frame, height=12, state="disabled")
        self.log_widget.pack(fill="both", expand=True)

    def _add_labeled_entry(self, parent: ttk.LabelFrame, label: str, var: tk.StringVar, row: int) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        entry = ttk.Entry(parent, textvariable=var, width=12)
        entry.grid(row=row, column=1, sticky="w", pady=4)

    # ------------------------------------------------------------------ #
    # Process management
    # ------------------------------------------------------------------ #
    def start_airmouse(self) -> None:
        if self.process and self.process.poll() is None:
            self._append_log("Restarting AirMouse...\n")
            self.stop_airmouse(wait_for_exit=True)

        try:
            env = self._build_env()
        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc))
            return

        cmd = [sys.executable, "-m", "airmouse"]
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
            )
        except OSError as exc:
            messagebox.showerror("Failed to start", f"Unable to launch AirMouse: {exc}")
            self.process = None
            return

        self._set_running(True)
        self._append_log("Launching AirMouse...\n")

        self.log_thread = threading.Thread(target=self._capture_output, daemon=True)
        self.log_thread.start()

        threading.Thread(target=self._wait_for_exit, daemon=True).start()

    def stop_airmouse(self, *, wait_for_exit: bool = False) -> None:
        if not self.process or self.process.poll() is not None:
            self._set_running(False)
            return

        self._append_log("Stopping AirMouse...\n")
        self.process.terminate()
        try:
            if wait_for_exit:
                self.process.wait(timeout=5)
            else:
                self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._append_log("Force killing AirMouse.\n")
            self.process.kill()
        finally:
            self._set_running(False)

    def _capture_output(self) -> None:
        if not self.process or not self.process.stdout:
            return
        for line in self.process.stdout:
            self._append_log(line)

    def _wait_for_exit(self) -> None:
        if not self.process:
            return
        returncode = self.process.wait()
        self.root.after(
            0,
            lambda: self._handle_process_exit(returncode),
        )

    def _handle_process_exit(self, returncode: int) -> None:
        if returncode == 0:
            self._append_log("AirMouse exited cleanly.\n")
        else:
            self._append_log(f"AirMouse exited with code {returncode}.\n")
        self._set_running(False)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _build_env(self) -> dict[str, str]:
        env = os.environ.copy()

        camera_index = self._parse_int(self.camera_index_var.get(), "Camera index")
        frame_scale = self._parse_float(self.frame_scale_var.get(), "Frame scale")
        edge_padding = self._parse_float(self.roi_edge_padding_var.get(), "ROI edge padding")
        if not 0.0 <= edge_padding < 0.5:
            raise ValueError("ROI edge padding must be between 0.0 and 0.49.")
        entry_countdown = self._parse_float(self.roi_entry_countdown_var.get(), "Entry countdown")
        if entry_countdown <= 0:
            raise ValueError("Entry countdown must be positive.")
        exit_countdown = self._parse_float(self.roi_exit_countdown_var.get(), "Re-entry countdown")
        if exit_countdown <= 0:
            raise ValueError("Re-entry countdown must be positive.")
        touchpad_multiplier = self._parse_float(self.touchpad_multiplier_var.get(), "Touchpad multiplier")
        if touchpad_multiplier <= 0:
            raise ValueError("Touchpad multiplier must be positive.")
        pinch_margin = self._parse_float(self.pinch_margin_var.get(), "Pinch margin")
        pinch_stability = self._parse_float(self.pinch_stability_var.get(), "Pinch stability")
        scroll_speed = self._parse_float(self.scroll_speed_factor_var.get(), "Scroll speed factor")
        scroll_smoothness = self._parse_float(self.scroll_smoothness_var.get(), "Scroll smoothness")

        env["AIRMOUSE_CAMERA_INDEX"] = str(camera_index)
        env["AIRMOUSE_FRAME_SCALE"] = str(frame_scale)
        env["AIRMOUSE_MIRROR_HORIZONTAL"] = self._bool_to_env(self.mirror_horizontal_var.get())
        env["AIRMOUSE_MIRROR_VERTICAL"] = self._bool_to_env(self.mirror_vertical_var.get())
        env["AIRMOUSE_ROI_EDGE_PADDING"] = str(edge_padding)
        env["AIRMOUSE_ROI_COUNTDOWN_SECONDS"] = str(entry_countdown)
        env["AIRMOUSE_ROI_EXIT_COUNTDOWN"] = str(exit_countdown)
        env["AIRMOUSE_ROI_AUTO_RESET"] = self._bool_to_env(self.roi_auto_reset_var.get())
        env["AIRMOUSE_TOUCHPAD_MULTIPLIER"] = str(touchpad_multiplier)
        env["AIRMOUSE_MONITOR_ENABLED"] = self._bool_to_env(self.monitor_enabled_var.get())
        env["AIRMOUSE_MONITOR_SHOW_CAMERA"] = self._bool_to_env(self.monitor_camera_var.get())
        env["AIRMOUSE_MONITOR_SHOW_GRAPH"] = self._bool_to_env(self.monitor_graph_var.get())
        env["AIRMOUSE_MONITOR_DRAW_SKELETON"] = self._bool_to_env(self.monitor_skeleton_var.get())
        env["AIRMOUSE_MONITOR_DRAW_ANCHOR"] = self._bool_to_env(self.monitor_anchor_var.get())
        env["AIRMOUSE_PINCH_MARGIN"] = str(pinch_margin)
        env["AIRMOUSE_PINCH_STABILITY"] = str(pinch_stability)
        env["AIRMOUSE_SCROLL_SPEED_FACTOR"] = str(scroll_speed)
        env["AIRMOUSE_SCROLL_SMOOTHNESS"] = str(scroll_smoothness)

        settings = {
            "camera_index": camera_index,
            "frame_scale": frame_scale,
            "mirror_horizontal": self.mirror_horizontal_var.get(),
            "mirror_vertical": self.mirror_vertical_var.get(),
            "roi_edge_padding": edge_padding,
            "roi_entry_countdown": entry_countdown,
            "roi_exit_countdown": exit_countdown,
            "roi_auto_reset": self.roi_auto_reset_var.get(),
            "touchpad_multiplier": touchpad_multiplier,
            "monitor_enabled": self.monitor_enabled_var.get(),
            "monitor_camera": self.monitor_camera_var.get(),
            "monitor_graph": self.monitor_graph_var.get(),
            "monitor_skeleton": self.monitor_skeleton_var.get(),
            "monitor_anchor": self.monitor_anchor_var.get(),
            "pinch_margin": pinch_margin,
            "pinch_stability": pinch_stability,
            "scroll_speed_factor": scroll_speed,
            "scroll_smoothness": scroll_smoothness,
        }
        self._persist_settings(settings)

        return env

    @staticmethod
    def _parse_int(value: str, label: str) -> int:
        try:
            return int(value)
        except ValueError as exc:
            raise ValueError(f"{label} must be an integer.") from exc

    @staticmethod
    def _parse_float(value: str, label: str) -> float:
        try:
            return float(value)
        except ValueError as exc:
            raise ValueError(f"{label} must be a number.") from exc

    @staticmethod
    def _bool_to_env(value: bool) -> str:
        return "true" if value else "false"

    def _load_saved_settings(self) -> Dict[str, Any]:
        path = self.SETTINGS_FILE
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                return data
        except Exception:
            return {}
        return {}

    def _persist_settings(self, settings: Dict[str, Any]) -> None:
        try:
            with self.SETTINGS_FILE.open("w", encoding="utf-8") as handle:
                json.dump(settings, handle, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _append_log(self, text: str) -> None:
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", text)
        self.log_widget.see("end")
        self.log_widget.configure(state="disabled")

    def _copy_log(self) -> None:
        """把日志区域的全部内容复制到系统剪贴板。"""
        content = self.log_widget.get("1.0", "end-1c").strip()
        if not content:
            messagebox.showinfo("复制日志", "日志为空，请先运行 AirMouse。")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.root.update()  # 确保窗口关闭后剪贴板仍可用
        messagebox.showinfo("复制日志", "日志已复制到剪贴板 ✅\n可直接粘贴发给开发者。")

    def _clear_log(self) -> None:
        """清空日志区域。"""
        self.log_widget.configure(state="normal")
        self.log_widget.delete("1.0", "end")
        self.log_widget.configure(state="disabled")

    def _set_running(self, running: bool) -> None:
        if running:
            self.status_var.set("Running")
            self.start_button.configure(state="normal", text="Restart")
            self.stop_button.configure(state="normal")
            self.recenter_button.configure(state="normal")
        else:
            self.status_var.set("Ready")
            self.start_button.configure(state="normal", text="Start AirMouse")
            self.stop_button.configure(state="disabled")
            self.recenter_button.configure(state="disabled")
            self.process = None

    def _on_close(self) -> None:
        self.stop_airmouse()
        self.root.after(200, self.root.destroy)

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    gui = AirMouseGUI()
    gui.run()


if __name__ == "__main__":
    main()
