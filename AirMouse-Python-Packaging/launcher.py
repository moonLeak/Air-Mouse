#!/usr/bin/env python3
"""
Air Mouse — 启动入口

架构说明：
  tkinter 与 cv2.imshow 都需要主线程。
  解决方案：用 root.quit() 暂停 tkinter 事件循环，
  在主线程直接运行 AirMouse 核心，结束后恢复 tkinter。
  全程单进程，macOS 权限不会失效。
"""
from __future__ import annotations

import json
import os
import sys
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

APP_NAME    = "Air Mouse"
APP_VERSION = "1.0.0"
SETTINGS_FILE = Path.home() / ".airmouse_settings.json"

PERMISSION_GUIDE = (
    "首次使用前，请在系统中完成以下授权：\n\n"
    "📷  摄像头权限\n"
    "    首次点击「开始使用」后，系统会弹窗请求，点击「好」即可。\n\n"
    "🖱  辅助功能权限（控制鼠标必需）\n"
    "    1. 打开「系统设置」→「隐私与安全性」\n"
    "    2. 点击左侧「辅助功能」\n"
    "    3. 找到「Air Mouse」并开启开关\n\n"
    "授权后若仍无效，请完全退出 Air Mouse 再重新打开。"
)


# ─── 路径工具 ─────────────────────────────────────────────────────────────────

def _ensure_airmouse_importable() -> None:
    """在开发模式下将 ../AirMouse 加入 sys.path，打包模式下包已在 bundle 里。"""
    try:
        import airmouse  # noqa: F401 — 已可导入则直接返回
        return
    except ImportError:
        pass
    _here = os.path.dirname(os.path.abspath(__file__))
    _src  = os.path.normpath(os.path.join(_here, "..", "AirMouse"))
    if os.path.isdir(_src) and _src not in sys.path:
        sys.path.insert(0, _src)


# ─── 摄像头检测 ───────────────────────────────────────────────────────────────

def _detect_cameras(max_check: int = 6) -> list[tuple[int, str]]:
    try:
        import cv2
    except ImportError:
        return [(0, "摄像头 0（内置）")]
    cameras: list[tuple[int, str]] = []
    for i in range(max_check):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                label = f"摄像头 {i}" + ("（内置）" if i == 0 else "（外接）")
                cameras.append((i, label))
            cap.release()
    return cameras or [(0, "摄像头 0（内置）")]


# ─── 设置持久化 ───────────────────────────────────────────────────────────────

def _load_settings() -> dict:
    try:
        if SETTINGS_FILE.exists():
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_settings(data: dict) -> None:
    try:
        SETTINGS_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


# ─── GUI ──────────────────────────────────────────────────────────────────────

class AirMouseApp:
    """Air Mouse 中文控制面板。"""

    def __init__(self) -> None:
        self._settings     = _load_settings()
        self._cameras      = _detect_cameras()
        self._adv_visible  = False
        self._pending_start = False   # 触发主线程运行核心的信号
        self._pending_env: dict[str, str] = {}

        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.resizable(False, False)

        self._init_vars()
        self._build_ui()
        self._center_window()

        # 窗口关闭按钮 → 退出 mainloop
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── 变量 ────────────────────────────────────────────────────────────────
    def _init_vars(self) -> None:
        s = self._settings
        cam_labels = [lbl for _, lbl in self._cameras]
        saved = s.get("cam_label", cam_labels[0] if cam_labels else "摄像头 0（内置）")
        if saved not in cam_labels and cam_labels:
            saved = cam_labels[0]

        self._cam_var      = tk.StringVar(value=saved)
        self._padding_var  = tk.StringVar(value=str(s.get("roi_padding",  "0.05")))
        self._touchpad_var = tk.StringVar(value=str(s.get("touchpad_mult","2.5")))
        self._show_cam_var = tk.BooleanVar(value=bool(s.get("show_cam",   True)))
        self._skeleton_var = tk.BooleanVar(value=bool(s.get("skeleton",   False)))
        self._anchor_var   = tk.BooleanVar(value=bool(s.get("anchor",     True)))
        self._status_var   = tk.StringVar(value="就绪")

    # ── UI 构建 ─────────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        BG, CARD, BLUE, TEXT, MUTE = "#f5f5f7", "#ffffff", "#007AFF", "#1d1d1f", "#6e6e73"
        self.root.configure(background=BG)

        st = ttk.Style(self.root)
        st.theme_use("default")
        st.configure("Main.TFrame",         background=BG)
        st.configure("Card.TFrame",         background=CARD)
        st.configure("Title.TLabel",        background=BG,   foreground=TEXT, font=("PingFang SC", 22, "bold"))
        st.configure("Sub.TLabel",          background=BG,   foreground=MUTE, font=("PingFang SC", 12))
        st.configure("Body.TLabel",         background=CARD, foreground=TEXT, font=("PingFang SC", 11))
        st.configure("Perm.TLabel",         background=CARD, foreground="#3c3c43", font=("PingFang SC", 10), justify="left")
        st.configure("Status.TLabel",       background=BG,   foreground=BLUE, font=("PingFang SC", 11))
        st.configure("StatusLead.TLabel",   background=BG,   foreground=TEXT, font=("PingFang SC", 11))
        st.configure("Start.TButton",       font=("PingFang SC", 13, "bold"), padding=(0, 10))
        st.configure("Stop.TButton",        font=("PingFang SC", 13),         padding=(0, 10))
        st.configure("Adv.TButton",         background=BG,   foreground=BLUE, font=("PingFang SC", 11), padding=(0, 4))
        st.configure("Card.TLabelframe",    background=CARD, relief="solid",  borderwidth=1, bordercolor="#e0e0e5")
        st.configure("Card.TLabelframe.Label", background=CARD, foreground=MUTE, font=("PingFang SC", 10))

        main = ttk.Frame(self.root, style="Main.TFrame", padding=(0, 8, 0, 16))
        main.pack(fill="both", expand=True)

        # 标题
        hdr = ttk.Frame(main, style="Main.TFrame")
        hdr.pack(fill="x", padx=24, pady=(20, 4))
        ttk.Label(hdr, text="🖱  Air Mouse",      style="Title.TLabel").pack(anchor="w")
        ttk.Label(hdr, text="手势控制鼠标，解放双手", style="Sub.TLabel").pack(anchor="w", pady=(2, 0))
        ttk.Separator(main, orient="horizontal").pack(fill="x", padx=24, pady=12)

        # 摄像头选择
        cam_card = ttk.LabelFrame(main, text="  摄像头  ", style="Card.TLabelframe", padding=(12, 8))
        cam_card.pack(fill="x", padx=24, pady=(0, 10))
        cam_row = ttk.Frame(cam_card, style="Card.TFrame"); cam_row.pack(fill="x")
        ttk.Label(cam_row, text="选择摄像头", style="Body.TLabel").pack(side="left")
        ttk.Combobox(
            cam_row, textvariable=self._cam_var,
            values=[lbl for _, lbl in self._cameras],
            state="readonly", width=22,
        ).pack(side="right")

        # 授权说明
        perm_card = ttk.LabelFrame(main, text="  ⚠  首次使用授权指南  ", style="Card.TLabelframe", padding=(12, 8))
        perm_card.pack(fill="x", padx=24, pady=(0, 14))
        ttk.Label(perm_card, text=PERMISSION_GUIDE, style="Perm.TLabel",
                  wraplength=358, justify="left").pack(anchor="w")

        # 开始 / 停止按钮
        btn_frame = ttk.Frame(main, style="Main.TFrame")
        btn_frame.pack(fill="x", padx=24, pady=(0, 8))
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)

        self._start_btn = ttk.Button(btn_frame, text="▶  开始使用",
                                     command=self._request_start, style="Start.TButton")
        self._start_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        # 运行时停止靠 ESC 键（cv2 窗口），此按钮在运行时不可用
        self._stop_btn = ttk.Button(btn_frame, text="■  停止（ESC）",
                                    command=lambda: None,
                                    style="Stop.TButton", state="disabled")
        self._stop_btn.grid(row=0, column=1, sticky="ew", padx=(6, 0))

        # 状态
        sr = ttk.Frame(main, style="Main.TFrame"); sr.pack(fill="x", padx=24, pady=(4, 0))
        ttk.Label(sr, text="状态：",             style="StatusLead.TLabel").pack(side="left")
        ttk.Label(sr, textvariable=self._status_var, style="Status.TLabel").pack(side="left")

        # 高级设置（可折叠）
        self._adv_toggle = ttk.Button(main, text="▸  高级设置",
                                      command=self._toggle_advanced, style="Adv.TButton")
        self._adv_toggle.pack(anchor="w", padx=24, pady=(12, 0))
        self._adv_frame = ttk.LabelFrame(main, text="  高级设置  ",
                                         style="Card.TLabelframe", padding=(12, 8))
        self._build_advanced(self._adv_frame)

        ttk.Label(main, text=f"v{APP_VERSION}", style="Sub.TLabel").pack(
            anchor="e", padx=24, pady=(8, 0))

        self.root.geometry("420x590")

    def _build_advanced(self, parent: ttk.LabelFrame) -> None:
        def row(label: str, factory):
            f = ttk.Frame(parent, style="Card.TFrame"); f.pack(fill="x", pady=3)
            ttk.Label(f, text=label, style="Body.TLabel").pack(side="left")
            factory(f).pack(side="right")

        row("ROI 边缘留白",
            lambda f: ttk.Entry(f, textvariable=self._padding_var, width=8))
        row("手掌触控板大小（× 手掌宽）",
            lambda f: ttk.Entry(f, textvariable=self._touchpad_var, width=8))
        row("显示摄像头画面",
            lambda f: ttk.Checkbutton(f, variable=self._show_cam_var))
        row("显示手部骨架",
            lambda f: ttk.Checkbutton(f, variable=self._skeleton_var))
        row("显示锚点标记",
            lambda f: ttk.Checkbutton(f, variable=self._anchor_var))

    def _toggle_advanced(self) -> None:
        if self._adv_visible:
            self._adv_frame.pack_forget()
            self._adv_toggle.configure(text="▸  高级设置")
            self.root.geometry("420x590"); self._adv_visible = False
        else:
            self._adv_frame.pack(fill="x", padx=24, pady=(0, 8))
            self._adv_toggle.configure(text="▾  高级设置")
            self.root.geometry("420x750"); self._adv_visible = True

    # ── 启动逻辑 ─────────────────────────────────────────────────────────────
    def _request_start(self) -> None:
        """验证参数、保存设置，然后通过 root.quit() 把控制权交回主线程运行核心。"""
        cam_idx = self._get_cam_index()
        try:
            padding  = float(self._padding_var.get())
            touchpad = float(self._touchpad_var.get())
            assert 0.0 <= padding < 0.5, "ROI 边缘留白须在 0.0 ~ 0.49 之间"
            assert touchpad > 0,         "手掌触控板大小须大于 0"
        except (ValueError, AssertionError) as exc:
            messagebox.showerror("参数错误", str(exc))
            return

        # 持久化设置
        _save_settings({
            "cam_label":    self._cam_var.get(),
            "roi_padding":  padding,
            "touchpad_mult": touchpad,
            "show_cam":     self._show_cam_var.get(),
            "skeleton":     self._skeleton_var.get(),
            "anchor":       self._anchor_var.get(),
        })

        # 准备传给核心的环境变量
        self._pending_env = {
            "AIRMOUSE_CAMERA_INDEX":        str(cam_idx),
            "AIRMOUSE_ROI_EDGE_PADDING":    str(padding),
            "AIRMOUSE_TOUCHPAD_MULTIPLIER": str(touchpad),
            "AIRMOUSE_MONITOR_ENABLED":     "true",
            "AIRMOUSE_MONITOR_SHOW_CAMERA": "true" if self._show_cam_var.get() else "false",
            "AIRMOUSE_MONITOR_DRAW_SKELETON": "true" if self._skeleton_var.get() else "false",
            "AIRMOUSE_MONITOR_DRAW_ANCHOR": "true" if self._anchor_var.get() else "false",
        }

        self._pending_start = True
        self.root.quit()   # 退出 mainloop，让 run() 里的 while 循环接管

    # ── 辅助方法 ─────────────────────────────────────────────────────────────
    def _get_cam_index(self) -> int:
        label = self._cam_var.get()
        for idx, lbl in self._cameras:
            if lbl == label:
                return idx
        return 0

    def _set_ui_running(self, running: bool) -> None:
        if running:
            self._start_btn.configure(state="disabled")
            self._stop_btn.configure(state="normal")
            self._status_var.set("运行中…  （按摄像头窗口的 ESC 键停止）")
        else:
            self._start_btn.configure(state="normal")
            self._stop_btn.configure(state="disabled")
            self._status_var.set("就绪")

    def _center_window(self) -> None:
        self.root.update_idletasks()
        w  = self.root.winfo_reqwidth()
        h  = self.root.winfo_reqheight()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")

    def _on_close(self) -> None:
        self._pending_start = False
        self.root.quit()   # 退出 mainloop，run() 里的 while 检测到 _pending_start=False 后退出

    # ── 主入口 ───────────────────────────────────────────────────────────────
    def run(self) -> None:
        """
        主循环：
          mainloop() ← 等待用户操作
            ↓ 用户点「开始使用」→ root.quit()
          运行 AirMouse 核心（主线程，cv2.imshow 正常工作）
            ↓ 用户按 ESC
          root.deiconify() → 回到 mainloop()
        """
        while True:
            self._set_ui_running(False)
            self.root.deiconify()
            self.root.mainloop()          # 阻塞，直到 root.quit() 被调用

            if not self._pending_start:
                break                     # 用户关闭窗口，正常退出

            self._pending_start = False

            # 隐藏启动窗口，全屏交给 cv2
            self.root.withdraw()
            self._set_ui_running(True)
            self.root.update()            # 确保窗口真正隐藏

            # 注入配置环境变量
            for k, v in self._pending_env.items():
                os.environ[k] = v

            # ── 在主线程运行 AirMouse 核心 ───────────────────────────────
            error_info: str | None = None
            try:
                _ensure_airmouse_importable()
                from airmouse.app import AirMouseApplication  # type: ignore
                from airmouse.config import load_config        # type: ignore
                config = load_config()
                core   = AirMouseApplication(config)
                core.run()                 # 阻塞，直到用户按 ESC
            except ImportError as exc:
                error_info = (
                    f"无法加载 Air Mouse 核心模块：\n{exc}\n\n"
                    "请确认 AirMouse 文件夹与 Air Mouse Python APP 在同一目录下。"
                )
            except Exception:
                error_info = traceback.format_exc()
            # ─────────────────────────────────────────────────────────────

            # 恢复启动窗口
            self.root.deiconify()
            if error_info:
                messagebox.showerror(
                    "Air Mouse 出错",
                    f"程序运行时遇到错误，请截图发给开发者：\n\n{error_info[-900:]}",
                )


# ─── 入口 ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = AirMouseApp()
    app.run()
