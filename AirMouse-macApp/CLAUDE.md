# AirMouse — Claude Code 上下文

## 这是什么项目

macOS 原生 App（Swift + SwiftUI），通过前置摄像头识别手部姿态，将手势映射为鼠标操作。
无接触控制电脑：移动光标、左键点击/拖拽、右键点击、滚动。

**完整规格文档：**
- 产品需求：`docs/PRD.md`
- 技术规格：`docs/TechSpec.md` ← 开始开发前必读

## 技术栈（只用系统框架，零外部依赖）

- **Swift 5.9+**, macOS 13+ 最低支持，针对 Apple Silicon 调优
- **AVFoundation** — 摄像头采集（640×480，30fps）
- **Apple Vision Framework** — 手部关键点识别（VNDetectHumanHandPoseRequest，ANE 加速）
- **Core Graphics / CGEvent** — 鼠标事件模拟
- **SwiftUI + AppKit** — UI（MenuBarExtra + 标定窗口）

## 项目目录结构

```
AirMouse/                          ← Xcode 项目根
├── App/
│   └── AirMouseApp.swift          @main，声明 MenuBarExtra
├── Core/
│   ├── Camera/CameraEngine.swift
│   ├── Vision/HandTracker.swift
│   ├── Gesture/
│   │   ├── GestureModels.swift    共用数据结构
│   │   ├── KalmanFilter.swift
│   │   ├── PinchDetector.swift    拇指-食指 → 左键/拖拽
│   │   ├── ScrollDetector.swift   拇指-中指 → 右键/滚动
│   │   ├── FistDetector.swift     握拳 → 结束 Session
│   │   └── ROIManager.swift       坐标映射 + 多显示器
│   ├── Mouse/MouseController.swift
│   └── Session/SessionController.swift  ← 核心状态机
├── UI/
│   ├── CalibrationWindow.swift
│   ├── MenuBarController.swift
│   └── CameraPreviewView.swift
└── Settings/SettingsManager.swift
```

## Session 状态机（核心逻辑）

```
waitingForHand → calibrating(3s倒计时) → active → ending(握拳3s倒计时) → waitingForHand
```

- **active 状态**：ROIManager 映射坐标 → KalmanFilter 平滑 → MouseController 移动鼠标
- **手消失时**：active 状态不退出，暂停鼠标，等手回来
- **结束方式**：握拳 3 秒 OR Option+Escape 快捷键

## 手势定义

| 手势 | 检测 | 动作 |
|------|------|------|
| 光标移动 | 手掌中心 → ROI → 屏幕坐标 + Kalman | mouseMoved |
| 左键单击 | 拇指-食指捏合 < 0.2s | leftMouseDown/Up |
| 左键拖拽 | 拇指-食指捏合 ≥ 0.2s | leftMouseDown 持续 |
| 右键单击 | 拇指-中指捏合 < 0.25s | rightMouseDown/Up |
| 滚动 | 拇指-中指捏合 + 手移动 | scrollWheel + 惯性 |
| 结束会话 | 握拳持续 3s | → ending 状态 |

## 关键算法参数（初始值）

```swift
// 归一化距离
normalized_4to8  = dist(thumbTip, indexTip) / dist(thumbIP, indexDIP)
normalized_4to12 = dist(thumbTip, middleTip) / dist(thumbIP, middleDIP)

// 动态阈值（5帧中位数）
thresholdMargin = 0.15   // 基线 ± 0.15

// Kalman 滤波
lowSpeedThreshold = 200.0  // px/s，低速时增大测量噪声
measurementNoise_low  = 0.5   // 低速（高平滑）
measurementNoise_high = 0.05  // 高速（快响应）

// ROI
touchpadMultiplier = 2.5   // ROI 宽 = 手掌宽 × 2.5
edgePadding = 0.05         // 边缘补偿
```

## ⚠️ 最容易踩的坑

1. **坐标系**：Vision 坐标原点左下角（Y 向上）；CGEvent 原点左上角（Y 向下）。
   映射到屏幕时需要转换：`cgEventY = mainScreenHeight - nsScreenY`

2. **Sandbox 必须关闭**：CGEvent.post() 在沙盒里静默失败，鼠标不动不报错。
   Entitlements 里 `com.apple.security.app-sandbox = false`

3. **Accessibility 权限**：没有权限时 CGEvent 同样静默失败。
   用 `AXIsProcessTrusted()` 检查，未授权时调用 `AXIsProcessTrustedWithOptions` 弹提示。

4. **AVCaptureSession.startRunning() 必须在非主线程**：在主线程调用会卡 UI 约 0.5s。
   用 `cameraQueue.async { session.startRunning() }`

5. **Vision 置信度**：confidence < 0.5 的关键点不可靠，需过滤。

## 当前进度

✅ CameraEngine / ✅ HandTracker / ✅ GestureModels / ✅ KalmanFilter
✅ PinchDetector / ✅ ScrollDetector / ✅ FistDetector / ✅ ROIManager
✅ MouseController / ✅ SessionController / ✅ CameraPreviewView / ✅ CalibrationWindow / ✅ AirMouseApp

**App 已能编译运行，Menu Bar 图标正常，权限（Camera + Accessibility）已授权。**

### 已知 Bug（待修复）

**Bug 1 — 摄像头不启动（指示灯不亮，画面全黑）**
- Camera 权限已给，Accessibility 权限已给
- `SessionController.startSession()` 的 `catch` 块静默吞错误，`CameraEngine.init` 或 `engine.start()` 可能失败但无日志
- 需要在 `SessionController.init()`、`startSession()`、`CameraEngine.start()` 的所有 catch/关键路径加 `print` 日志，找到具体失败点
- 鼠标控制正常（Stop 时鼠标会移动），说明 Accessibility/CGEvent 没问题

**Bug 2 — 点 Stop 时鼠标跳到左上角**
- `enterActive()` 里 mouse 跳到 `combinedScreenRect().center` → `toCGEventCoordinate()`
- 怀疑坐标计算返回 (0,0) 或负值
- 需要 print `cgCenter` 的实际值确认

### 修复步骤
1. 先加日志（不改逻辑），rebuild，点 Start，看 console 输出
2. 根据日志定位 Bug 1 根因并修复
3. 修复 Bug 2 坐标计算

## 开发顺序建议

1. CameraEngine（先跑通摄像头预览）
2. HandTracker（验证 21 个关键点输出）
3. KalmanFilter + ROIManager（坐标映射）
4. MouseController（鼠标移动）
5. PinchDetector（左键）
6. ScrollDetector（右键 + 滚动）
7. FistDetector（结束手势）
8. SessionController（串联所有模块）
9. UI（CalibrationWindow + MenuBar）

每完成一步用 `xcodebuild` 编译验证，不要累积错误。

## Python 参考实现

已有可运行的 Python 版本（同一仓库）：
```
../AirMouse/airmouse/gestures/pinch.py    ← PinchDetector 参考
../AirMouse/airmouse/gestures/scroll.py   ← ScrollDetector 参考
../AirMouse/airmouse/control/mouse.py     ← KalmanFilter 参考
../AirMouse/airmouse/roi/manager.py       ← ROIManager 参考
```
算法逻辑与 Python 版保持一致，换 Swift 语法即可。
