# AirMouse（模块化重构）

## 运行
- 激活虚拟环境：`source venv311/bin/activate`
- 启动程序：`python -m airmouse`
- `MEDIAPIPE_DISABLE_GPU` 默认在入口中关闭，如需使用 GPU 可自行导出环境变量。
## 首次安装
```bash
cd AirMouse-Python
python3.11 -m venv venv311
source venv311/bin/activate
pip install -r requirements.txt
python -m airmouse
```
> `venv311/` 不在版本库中，需要本地创建。macOS 需授予摄像头与辅助功能权限。

## 配置
可以通过环境变量覆盖默认参数，例如：

```bash
export AIRMOUSE_CAMERA_INDEX=2          # 指定摄像头索引（默认 2，可设为 0/1 使用内置摄像头）
export AIRMOUSE_FRAME_SCALE=0.6         # 摄像头画面缩放比例
export AIRMOUSE_MONITOR_ENABLED=false   # 关闭调试监视器窗口
export AIRMOUSE_MIRROR_HORIZONTAL=true  # 启用左右镜像（默认 true）
export AIRMOUSE_MIRROR_VERTICAL=true    # 启用上下镜像（默认 true）
export AIRMOUSE_ROI_EDGE_PADDING=0.05   # 判定框边缘映射提前量（0~0.49，越大越容易碰到屏幕边缘）
export AIRMOUSE_ROI_COUNTDOWN_SECONDS=3 # 进入判定框锁定前的倒计时秒数
export AIRMOUSE_ROI_EXIT_COUNTDOWN=5    # 离开判定框后重新判定的倒计时秒数
export AIRMOUSE_ROI_AUTO_RESET=true     # 离开判定框后是否自动重新判定
export AIRMOUSE_TOUCHPAD_MULTIPLIER=2.5 # 触控板尺寸为手掌宽度的 n 倍，并保持与屏幕相同的长宽比
```

更多变量见 `airmouse/config.py`。

镜像选项会同时作用于 GUI 预览与识别流程，确保看到的画面方向和鼠标移动方向保持一致。鼠标移动采用“手掌中心 ↔ 判定框”点对点映射：当打叉的手掌中心离开绿色判定框时会立即暂停鼠标，并启动 5 秒倒计时，倒计时结束后需重新进入框才能重新锁定。

图形曲线窗口默认已关闭（`AIRMOUSE_MONITOR_SHOW_GRAPH=false`），界面只展示镜像后的摄像头预览与 ROI 绿色框，如需诊断可手动开启。

当前版本默认使用 Mac 前置 FaceTime 可运行：ffmpeg -f avfoundation -list_devices true -i ""

## 图形界面
若希望在启动前可视化地调整相机、监视器或手势参数，可运行 Tkinter GUI：

```bash
source venv311/bin/activate
python -m airmouse.gui
```

界面支持：
- 设置相机索引、画面缩放
- 切换画面左右/上下镜像预处理（同步作用于识别逻辑）
- 调整“ROI edge padding”因子，决定手掌中心距离框边多少就视为触碰屏幕边缘
- 设置进入/重新进入倒计时与“离开判定框后自动重新判定”开关
- 控制触控板尺寸（n × 手掌宽度，始终匹配屏幕长宽比）
- 控制调试监视器开关、骨骼/锚点是否绘制、是否显示图表窗口
- 调整捏合/滚动手势的阈值与速度参数
- 直接查看 AirMouse 运行日志，并随时停止/重新启动

## 模块结构
- `airmouse/app.py`：顶层应用编排，连接摄像头、手势识别、鼠标控制和可视化。
- `airmouse/config.py`：集中管理参数加载，支持环境变量覆盖。
- `airmouse/io/camera.py`：封装 OpenCV 摄像头读取与缩放。
- `airmouse/vision/hand_tracker.py`：MediaPipe Hands 追踪器包装。
- `airmouse/control/mouse.py`：鼠标控制与手势到屏幕坐标映射（含卡尔曼滤波）。
- `airmouse/gestures/pinch.py`：拇指-食指捏合手势（左键点击/拖拽）。
- `airmouse/gestures/scroll.py`：拇指-中指捏合手势（右键、滚动、惯性滚动）。
- `airmouse/monitoring/monitor.py`：调试曲线与相机画面展示。
- `airmouse/utils/geometry.py`：通用几何与速度计算。
- `airmouse/gui.py`：基于 Tkinter 的简单控制面板，可通过 GUI 启动/停止 AirMouse 并调整常用参数。

旧版 `airmouse/legacy.py` 已退役并会主动提示改用新入口。

## 打包成 .app / .dmg
见 `packaging/`：`cd packaging && ./build_mac.sh`（详见 `packaging/安装说明.md`）。
