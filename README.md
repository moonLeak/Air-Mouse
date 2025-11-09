# AirMouse（模块化重构）

## 运行
- 激活虚拟环境：`source venv311/bin/activate`
- 启动程序：`python -m airmouse`
- `MEDIAPIPE_DISABLE_GPU` 默认在入口中关闭，如需使用 GPU 可自行导出环境变量。
## 本机示例
cd /Users/carson_h/Library/CloudStorage/OneDrive-Personal/Protolab/2024-11-18手势识别/New\ Air\ Mouse
source venv311/bin/activate
python -m airmouse

## 配置
可以通过环境变量覆盖默认参数，例如：

```bash
export AIRMOUSE_CAMERA_INDEX=2          # 指定摄像头索引（默认 2，可设为 0/1 使用内置摄像头）
export AIRMOUSE_FRAME_SCALE=0.6         # 摄像头画面缩放比例
export AIRMOUSE_MONITOR_ENABLED=false   # 关闭调试监视器窗口
```

更多变量见 `airmouse/config.py`。

当前版本默认使用 Mac 前置 FaceTime 可运行：`ffmpeg -f avfoundation -list_devices true -i ""`。

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

旧版 `airmouse/legacy.py` 已退役并会主动提示改用新入口。
