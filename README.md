# AirMouse — 手势控制鼠标

用摄像头识别手部姿态，把手势映射成鼠标操作：移动光标、左键点击/拖拽、右键、滚动。无需接触设备。
项目起点：2024-11-18 Protolab 手势识别。

## 目录

| 目录 | 内容 | 技术 | 状态 |
|---|---|---|---|
| [`AirMouse-macApp/`](AirMouse-macApp/) | macOS 原生 App（菜单栏 + 标定窗口），含 PRD / TechSpec；`ios/`、`shared/` 为预留 | Swift, SwiftUI, Vision, CGEvent | **主线，开发中** |
| [`AirMouse-Python/`](AirMouse-Python/) | Python 模块化版本（ROI 判定框、卡尔曼滤波、GUI） | Python, MediaPipe, OpenCV | 稳定版（2025-11） |
| [`AirMouse-Python-Packaging/`](AirMouse-Python-Packaging/) | 把 Python 版打成 macOS `.app` / `.dmg` 的脚本 | PyInstaller | 可用 |
| [`Tools/`](Tools/) | 实验小工具：手部监控器、参考长度计算器、双目视觉、多点触控模拟 | Python | 参考 |
| [`Archive/`](Archive/) | 早期版本与重构前脚本（2024-11） | Python | 仅存档 |

> `Assets/`（数据集、演示视频、思维导图）只保存在本地，不上传。

## 快速开始

**macOS App**：用 Xcode 打开 `AirMouse-macApp/AirMouse/AirMouse.xcodeproj`，详见该目录的 `README.md` 与 `CLAUDE.md`。

**Python 版**：
```bash
cd AirMouse-Python
python3.11 -m venv venv311 && source venv311/bin/activate
pip install -r requirements.txt
python -m airmouse
```

**打包 Python 版**：见 `AirMouse-Python-Packaging/安装说明.md` 与 `build_mac.sh`。

## 说明
- 虚拟环境、`dist/`、`build/` 不在版本库中，需本地生成。
- macOS 需授予 **摄像头** 与 **辅助功能** 权限。
