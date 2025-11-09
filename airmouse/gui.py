from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText


class AirMouseGUI:
    """Simple Tkinter-based control panel for launching AirMouse with custom parameters."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("AirMouse Control Panel")

        self.process: subprocess.Popen | None = None
        self.log_thread: threading.Thread | None = None

        self._init_vars()
        self._build_layout()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #
    def _init_vars(self) -> None:
        self.camera_index_var = tk.StringVar(value="0")
        self.frame_scale_var = tk.StringVar(value="0.6")
        self.mirror_horizontal_var = tk.BooleanVar(value=True)
        self.mirror_vertical_var = tk.BooleanVar(value=True)

        self.monitor_enabled_var = tk.BooleanVar(value=True)
        self.monitor_camera_var = tk.BooleanVar(value=True)
        self.monitor_graph_var = tk.BooleanVar(value=False)
        self.monitor_skeleton_var = tk.BooleanVar(value=False)

        self.pinch_margin_var = tk.StringVar(value="0.15")
        self.pinch_stability_var = tk.StringVar(value="0.2")
        self.scroll_speed_factor_var = tk.StringVar(value="0.5")
        self.scroll_smoothness_var = tk.StringVar(value="0.8")

        self.status_var = tk.StringVar(value="Ready")

    def _build_layout(self) -> None:
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill="both", expand=True)

        camera_frame = ttk.LabelFrame(main, text="Camera")
        camera_frame.pack(fill="x", expand=True, pady=(0, 10))
        self._add_labeled_entry(camera_frame, "Camera index", self.camera_index_var, 0)
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

        gesture_frame = ttk.LabelFrame(main, text="Gesture tuning")
        gesture_frame.pack(fill="x", expand=True, pady=(0, 10))
        self._add_labeled_entry(gesture_frame, "Pinch margin", self.pinch_margin_var, 0)
        self._add_labeled_entry(gesture_frame, "Pinch stability (s)", self.pinch_stability_var, 1)
        self._add_labeled_entry(gesture_frame, "Scroll speed factor", self.scroll_speed_factor_var, 2)
        self._add_labeled_entry(gesture_frame, "Scroll smoothness", self.scroll_smoothness_var, 3)

        control_frame = ttk.Frame(main)
        control_frame.pack(fill="x", pady=(0, 10))
        self.start_button = ttk.Button(control_frame, text="Start AirMouse", command=self.start_airmouse)
        self.start_button.pack(side="left", padx=(0, 8))
        self.stop_button = ttk.Button(control_frame, text="Stop", command=self.stop_airmouse, state="disabled")
        self.stop_button.pack(side="left")
        ttk.Label(control_frame, textvariable=self.status_var).pack(side="right")

        log_frame = ttk.LabelFrame(main, text="Log")
        log_frame.pack(fill="both", expand=True)
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
            messagebox.showinfo("AirMouse", "AirMouse is already running.")
            return

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

    def stop_airmouse(self) -> None:
        if not self.process or self.process.poll() is not None:
            self._set_running(False)
            return

        self._append_log("Stopping AirMouse...\n")
        self.process.terminate()
        try:
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
        pinch_margin = self._parse_float(self.pinch_margin_var.get(), "Pinch margin")
        pinch_stability = self._parse_float(self.pinch_stability_var.get(), "Pinch stability")
        scroll_speed = self._parse_float(self.scroll_speed_factor_var.get(), "Scroll speed factor")
        scroll_smoothness = self._parse_float(self.scroll_smoothness_var.get(), "Scroll smoothness")

        env["AIRMOUSE_CAMERA_INDEX"] = str(camera_index)
        env["AIRMOUSE_FRAME_SCALE"] = str(frame_scale)
        env["AIRMOUSE_MIRROR_HORIZONTAL"] = self._bool_to_env(self.mirror_horizontal_var.get())
        env["AIRMOUSE_MIRROR_VERTICAL"] = self._bool_to_env(self.mirror_vertical_var.get())
        env["AIRMOUSE_MONITOR_ENABLED"] = self._bool_to_env(self.monitor_enabled_var.get())
        env["AIRMOUSE_MONITOR_SHOW_CAMERA"] = self._bool_to_env(self.monitor_camera_var.get())
        env["AIRMOUSE_MONITOR_SHOW_GRAPH"] = self._bool_to_env(self.monitor_graph_var.get())
        env["AIRMOUSE_MONITOR_DRAW_SKELETON"] = self._bool_to_env(self.monitor_skeleton_var.get())
        env["AIRMOUSE_PINCH_MARGIN"] = str(pinch_margin)
        env["AIRMOUSE_PINCH_STABILITY"] = str(pinch_stability)
        env["AIRMOUSE_SCROLL_SPEED_FACTOR"] = str(scroll_speed)
        env["AIRMOUSE_SCROLL_SMOOTHNESS"] = str(scroll_smoothness)

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

    def _append_log(self, text: str) -> None:
        self.log_widget.configure(state="normal")
        self.log_widget.insert("end", text)
        self.log_widget.see("end")
        self.log_widget.configure(state="disabled")

    def _set_running(self, running: bool) -> None:
        if running:
            self.status_var.set("Running")
            self.start_button.configure(state="disabled")
            self.stop_button.configure(state="normal")
        else:
            self.status_var.set("Ready")
            self.start_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
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
