# -*- mode: python ; coding: utf-8 -*-
"""
AirMouse.spec — PyInstaller 打包配置
用法：在 Air Mouse Python APP/ 目录下执行
    pyinstaller AirMouse.spec --clean --noconfirm
"""
import os
import sys

# ── 路径定义 ─────────────────────────────────────────────────────────────────
HERE    = os.path.dirname(os.path.abspath(SPEC))          # Air Mouse Python APP/
SRC_DIR = os.path.normpath(os.path.join(HERE, "..", "AirMouse"))  # ../AirMouse/

# ── 定位 mediapipe 模型文件 ──────────────────────────────────────────────────
import mediapipe as _mp
MP_DIR = os.path.dirname(_mp.__file__)

# ── 定位 cv2 ─────────────────────────────────────────────────────────────────
import cv2 as _cv2
CV2_DIR = os.path.dirname(_cv2.__file__)

# ─────────────────────────────────────────────────────────────────────────────
block_cipher = None

a = Analysis(
    [os.path.join(HERE, "launcher.py")],
    pathex=[SRC_DIR],          # 使 'import airmouse' 可以找到源包
    binaries=[],
    datas=[
        # mediapipe 模型文件（必须包含，否则运行时找不到）
        (os.path.join(MP_DIR, "modules"),  "mediapipe/modules"),
        (os.path.join(MP_DIR, "python"),   "mediapipe/python"),
    ],
    hiddenimports=[
        # airmouse 子模块（PyInstaller 静态分析可能遗漏）
        "airmouse",
        "airmouse.main",
        "airmouse.app",
        "airmouse.config",
        "airmouse.toggle",
        "airmouse.legacy",
        "airmouse.utils",
        "airmouse.control",
        "airmouse.control.entry_gate",
        "airmouse.control.mouse",
        "airmouse.gestures",
        "airmouse.gestures.pinch",
        "airmouse.gestures.scroll",
        "airmouse.gestures.special",
        "airmouse.io",
        "airmouse.io.camera",
        "airmouse.monitoring",
        "airmouse.roi",
        "airmouse.roi.manager",
        "airmouse.vision",
        "airmouse.vision.hand_tracker",
        # 第三方
        "cv2",
        "mediapipe",
        "mediapipe.python",
        "mediapipe.python.solutions",
        "mediapipe.python.solutions.hands",
        "mediapipe.python.solutions.drawing_utils",
        "pynput",
        "pynput.mouse",
        "pynput.keyboard",
        "pynput._util",
        "pynput._util.darwin",
        "pyautogui",
        "scipy",
        "scipy.ndimage",
        "scipy.spatial",
        # macOS 原生绑定
        "pyobjc",
        "objc",
        "AppKit",
        "Foundation",
        "Quartz",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "IPython",
        "notebook",
        "pytest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AirMouse",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # 不显示终端窗口
    disable_windowed_traceback=False,
    argv_emulation=False,   # macOS 下关闭 argv 模拟，避免与 --core 冲突
    target_arch=None,       # 自动匹配当前 CPU 架构（arm64 / x86_64）
    codesign_identity=None,
    entitlements_file=os.path.join(HERE, "entitlements.plist"),
    icon=(
        os.path.join(HERE, "assets", "icon.icns")
        if os.path.exists(os.path.join(HERE, "assets", "icon.icns"))
        else None
    ),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="AirMouse",
)

app = BUNDLE(
    coll,
    name="Air Mouse.app",
    icon=(
        os.path.join(HERE, "assets", "icon.icns")
        if os.path.exists(os.path.join(HERE, "assets", "icon.icns"))
        else None
    ),
    bundle_identifier="com.local.AirMouse",
    info_plist={
        # 基本信息
        "CFBundleName":              "Air Mouse",
        "CFBundleDisplayName":       "Air Mouse",
        "CFBundleIdentifier":        "com.local.AirMouse",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion":           "1",
        # 系统要求
        "LSMinimumSystemVersion":    "13.0",
        "NSHighResolutionCapable":   True,
        "LSApplicationCategoryType": "public.app-category.utilities",
        # 权限描述（macOS 必须，否则拒绝摄像头访问）
        "NSCameraUsageDescription":
            "Air Mouse 需要使用摄像头来识别您的手部动作，以实现鼠标光标的手势控制。",
        "NSMicrophoneUsageDescription":
            "本应用不使用麦克风。",
        # 外观
        "NSRequiresAquaSystemAppearance": False,
        "NSPrincipalClass":          "NSApplication",
    },
)
