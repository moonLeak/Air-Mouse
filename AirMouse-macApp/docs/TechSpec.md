# AirMouse — 技术规格文档

**版本** 1.0  
**日期** 2026-05-14  
**面向读者** 负责开发的程序员（对本项目零基础）  
**配套文档** `PRD.md`（产品需求）

---

## 目录

1. [项目背景与目标](#1-项目背景与目标)
2. [开发环境要求](#2-开发环境要求)
3. [Xcode 项目初始化](#3-xcode-项目初始化)
4. [目录结构](#4-目录结构)
5. [系统架构总览](#5-系统架构总览)
6. [数据流](#6-数据流)
7. [模块详细规格](#7-模块详细规格)
   - 7.1 CameraEngine
   - 7.2 HandTracker
   - 7.3 KalmanFilter
   - 7.4 PinchDetector
   - 7.5 ScrollDetector
   - 7.6 FistDetector
   - 7.7 ROIManager
   - 7.8 MouseController
   - 7.9 SessionController
   - 7.10 UI — CalibrationWindow
   - 7.11 UI — MenuBarController
   - 7.12 SettingsManager
8. [算法详解](#8-算法详解)
9. [多显示器实现](#9-多显示器实现)
10. [权限配置](#10-权限配置)
11. [构建与打包](#11-构建与打包)
12. [性能要求与调优指南](#12-性能要求与调优指南)
13. [已知约束与注意事项](#13-已知约束与注意事项)

---

## 1. 项目背景与目标

### 这个 App 是什么

AirMouse 是一个 macOS 菜单栏应用。用户启动 App 后，它通过前置摄像头实时识别用户的手部姿态，将手势转换为鼠标操作（移动光标、点击、拖拽、滚动），让用户在不接触鼠标或触控板的情况下控制电脑。

### 参考实现

本项目是对一个已有 Python 版本（`../AirMouse/`）的 Swift 原生重写。Python 版本使用 MediaPipe 做手部追踪，已经过大量迭代验证了手势算法。**开始开发前强烈建议先运行一下 Python 版本**，直观感受目标体验。

Python 版本运行方法（需 Mac，已有 Python 3.11 环境）：
```bash
cd ../AirMouse
source venv311/bin/activate
python -m airmouse
```

### Swift 版本的目标

- 用 Apple Vision Framework 替代 MediaPipe（利用 Apple Neural Engine，M 芯片专属）
- 用 SwiftUI + AppKit 替代 Python Tkinter
- 用 CGEvent 替代 pynput
- 最终交付：可签名分发的 `.dmg`

---

## 2. 开发环境要求

| 工具 | 版本要求 | 说明 |
|------|----------|------|
| macOS | 14 Sonoma 或以上 | 开发机系统 |
| Xcode | 15.0 或以上 | 必须，提供编译器、签名、打包 |
| Swift | 5.9（Xcode 15 内置） | 无需单独安装 |
| Apple Developer 账号 | 个人免费账号即可开发；分发需付费账号（$99/年） | 签名 + 公证需要付费账号 |
| 目标运行硬件 | Apple Silicon（M1/M2/M3/M4）| Intel Mac 不测试 |
| 目标最低系统版本 | macOS 13 Ventura | `VNHumanHandPoseObservation` 在 macOS 11+ 可用，设为 13 留余量 |

**不需要**安装任何第三方包、CocoaPods、SPM 依赖。整个项目只使用 Apple 系统框架。

---

## 3. Xcode 项目初始化

### 3.1 创建项目

1. 打开 Xcode → File → New → Project
2. 选择 **macOS** → **App**
3. 填写：
   - Product Name: `AirMouse`
   - Team: 你的 Apple Developer 账号
   - Bundle Identifier: `com.yourname.airmouse`（自定义）
   - Language: **Swift**
   - User Interface: **SwiftUI**
4. 取消勾选 "Include Tests"（后续手动添加）
5. 取消勾选 "Create Git repository"（已有 git 仓库）

### 3.2 关键配置（Build Settings & Info.plist）

**删除默认 Window Scene**

本项目没有传统主窗口，只有菜单栏图标。需要修改 `Info.plist`，删除 `NSPrincipalClass` 之外默认添加的 Window Scene 配置：

在 `Info.plist` 里删除：
```xml
<key>NSMainStoryboardFile</key>
<string>Main</string>
```

同时在 `AirMouseApp.swift` 里不要声明 `WindowGroup`，改为使用 `MenuBarExtra`（见 7.11 节）。

**Info.plist 必须添加的键：**

```xml
<!-- 摄像头权限说明（必须，否则 App 崩溃） -->
<key>NSCameraUsageDescription</key>
<string>AirMouse needs camera access to track your hand gestures.</string>

<!-- 禁止 App 出现在 Dock -->
<key>LSUIElement</key>
<true/>

<!-- 最低 macOS 版本 -->
<key>LSMinimumSystemVersion</key>
<string>13.0</string>
```

**Entitlements 文件（`AirMouse.entitlements`）：**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <!-- 摄像头 -->
    <key>com.apple.security.device.camera</key>
    <true/>
    <!-- 禁用沙盒（CGEvent 鼠标控制需要） -->
    <key>com.apple.security.app-sandbox</key>
    <false/>
</dict>
</plist>
```

> ⚠️ 注意：关闭沙盒意味着不能上 App Store，但 PRD 明确只做 DMG 分发，这是正确选择。

**Build Settings 修改：**

- `MACOSX_DEPLOYMENT_TARGET` = `13.0`
- `SWIFT_STRICT_CONCURRENCY` = `complete`（推荐，避免并发问题）
- Signing: 选择你的 Team，自动管理签名

---

## 4. 目录结构

```
AirMouse/
├── AirMouse.xcodeproj/
├── AirMouse/
│   ├── App/
│   │   ├── AirMouseApp.swift          # @main 入口，声明 MenuBarExtra
│   │   └── AppDelegate.swift          # 应用生命周期（可选，用于处理退出清理）
│   │
│   ├── Core/
│   │   ├── Camera/
│   │   │   └── CameraEngine.swift     # AVFoundation 摄像头采集
│   │   │
│   │   ├── Vision/
│   │   │   └── HandTracker.swift      # Vision Framework 手部关键点识别
│   │   │
│   │   ├── Gesture/
│   │   │   ├── GestureModels.swift    # 共用数据结构（HandLandmarks, GestureAction 等）
│   │   │   ├── KalmanFilter.swift     # 2D 卡尔曼滤波器
│   │   │   ├── PinchDetector.swift    # 拇指-食指捏合（左键/拖拽）
│   │   │   ├── ScrollDetector.swift   # 拇指-中指捏合（右键/滚动）
│   │   │   ├── FistDetector.swift     # 握拳检测（结束 Session）
│   │   │   └── ROIManager.swift       # ROI 自适应 + 多显示器映射
│   │   │
│   │   ├── Mouse/
│   │   │   └── MouseController.swift  # CGEvent 鼠标事件发送
│   │   │
│   │   └── Session/
│   │       └── SessionController.swift # 主状态机，协调所有模块
│   │
│   ├── UI/
│   │   ├── CalibrationWindow.swift    # 标定窗口（SwiftUI View + NSWindow 包装）
│   │   ├── MenuBarController.swift    # 菜单栏图标 + 菜单
│   │   └── CameraPreviewView.swift    # 摄像头预览（AVCaptureVideoPreviewLayer）
│   │
│   ├── Settings/
│   │   └── SettingsManager.swift      # 用户偏好（摄像头选择、灵敏度等）
│   │
│   └── Resources/
│       ├── Assets.xcassets            # App 图标、Menu Bar 图标
│       └── Info.plist
│
└── AirMouseTests/
    ├── KalmanFilterTests.swift
    ├── PinchDetectorTests.swift
    └── ROIManagerTests.swift
```

---

## 5. 系统架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                          AirMouseApp (@main)                     │
│                    MenuBarExtra + WindowManager                  │
└──────────────────────────────┬──────────────────────────────────┘
                               │ 持有
                    ┌──────────▼──────────┐
                    │  SessionController   │  ← 核心状态机
                    │  (ObservableObject)  │    驱动整个应用
                    └──┬──────┬──────┬───┘
                       │      │      │
          ┌────────────▼─┐  ┌─▼────────────┐  ┌──▼─────────────┐
          │ CameraEngine  │  │  HandTracker  │  │ MouseController│
          │(AVFoundation) │  │(Vision + ANE) │  │  (CGEvent)     │
          └──────┬────────┘  └──────┬────────┘  └────────────────┘
                 │ CMSampleBuffer   │ HandLandmarks        ▲
                 └──────────────────┘                      │
                          │                                │
                 ┌────────▼────────┐                       │
                 │  GestureEngine  │ ── GestureAction ─────┘
                 │                 │
                 │ ┌─────────────┐ │
                 │ │KalmanFilter │ │  （光标平滑）
                 │ ├─────────────┤ │
                 │ │PinchDetector│ │  （左键/拖拽）
                 │ ├─────────────┤ │
                 │ │ScrollDetect │ │  （右键/滚动）
                 │ ├─────────────┤ │
                 │ │FistDetector │ │  （结束会话）
                 │ ├─────────────┤ │
                 │ │ROIManager   │ │  （坐标映射）
                 │ └─────────────┘ │
                 └─────────────────┘
                          │
                 ┌────────▼────────┐
                 │  CalibrationUI  │  （SwiftUI，只在特定状态显示）
                 └─────────────────┘
```

### 线程模型

| 线程 | 职责 |
|------|------|
| Main Thread | SwiftUI 更新、窗口管理、Menu Bar |
| `cameraQueue`（串行） | AVFoundation 帧回调、Vision 推理 |
| Main Thread（dispatch back） | SessionController 状态更新、鼠标事件发送 |

> 所有 UI 更新必须在 Main Thread。所有 Vision 推理在 `cameraQueue`，推理完成后 `DispatchQueue.main.async` 回主线程。

---

## 6. 数据流

每一帧的处理流程（约 33ms @ 30fps）：

```
摄像头采集一帧 (CVPixelBuffer)
    │
    ▼ [cameraQueue]
CameraEngine.didOutput(_:)
    │  包装为 VNImageRequestHandler
    ▼
HandTracker.process(pixelBuffer:)
    │  执行 VNDetectHumanHandPoseRequest
    │  结果：[VNHumanHandPoseObservation]（0 或 1 个，只取一只手）
    │  转换为 HandLandmarks（21个 CGPoint，坐标已归一化到 0~1）
    ▼
SessionController.onHandFrame(landmarks:, timestamp:)  [DispatchQueue.main.async]
    │
    ├── 若 state == .waitingForHand
    │       有手 → 切换到 .calibrating，开始倒计时
    │       无手 → 无动作
    │
    ├── 若 state == .calibrating
    │       有手 → 继续倒计时（允许抖动）
    │       无手 → 重置倒计时
    │       倒计时归零 → 切换到 .active，鼠标跳中央
    │
    └── 若 state == .active
            ROIManager.update(landmarks) → screenPoint: CGPoint
            KalmanFilter.update(screenPoint) → smoothedPoint: CGPoint
            MouseController.moveTo(smoothedPoint)

            PinchDetector.update(normalized_4to8, speed) → GestureAction?
            ScrollDetector.update(normalized_4to12, position, speed) → [GestureAction]
            FistDetector.update(landmarks) → isFist: Bool（连续 3s → 切换到 .ending）

            MouseController.handle(action)
```

---

## 7. 模块详细规格

---

### 7.1 CameraEngine

**文件：** `Core/Camera/CameraEngine.swift`

**职责：** 封装 AVFoundation 摄像头采集，将原始帧以 `CVPixelBuffer` 形式回调给上层。

#### 接口定义

```swift
protocol CameraEngineDelegate: AnyObject {
    func cameraEngine(_ engine: CameraEngine,
                      didOutput pixelBuffer: CVPixelBuffer,
                      timestamp: CMTime)
}

class CameraEngine: NSObject {
    weak var delegate: CameraEngineDelegate?
    
    // 初始化，传入 AVCaptureDevice
    init(device: AVCaptureDevice)
    
    // 开始采集
    func start() throws
    
    // 停止采集
    func stop()
    
    // 获取预览层（用于 UI 显示）
    var previewLayer: AVCaptureVideoPreviewLayer { get }
}
```

#### 实现要点

**摄像头选择逻辑**（在调用 `CameraEngine` 之前由 `SessionController` 决定传哪个 `AVCaptureDevice`）：

```swift
static func selectCamera() -> AVCaptureDevice? {
    // 1. 优先：设置里用户手动选择的摄像头
    if let savedID = SettingsManager.shared.preferredCameraID,
       let device = AVCaptureDevice(uniqueID: savedID),
       device.isConnected {
        return device
    }
    
    // 2. 其次：前置内置摄像头（MacBook 正常状态）
    if let builtIn = AVCaptureDevice.default(
        .builtInWideAngleCamera, for: .video, position: .front) {
        return builtIn
    }
    
    // 3. 兜底：第一个可用视频设备（MacBook 合盖、接外置摄像头时）
    return AVCaptureDevice.DiscoverySession(
        deviceTypes: [.builtInWideAngleCamera, .external],
        mediaType: .video,
        position: .unspecified
    ).devices.first(where: { $0.isConnected })
}
```

**AVCaptureSession 配置：**

```swift
private func setupSession(device: AVCaptureDevice) throws {
    session = AVCaptureSession()
    session.sessionPreset = .vga640x480   // 640×480 足够，保持低延迟
    
    let input = try AVCaptureDeviceInput(device: device)
    guard session.canAddInput(input) else { throw CameraError.cannotAddInput }
    session.addInput(input)
    
    let output = AVCaptureVideoDataOutput()
    output.videoSettings = [
        kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA
    ]
    output.alwaysDiscardsLateVideoFrames = true  // 关键：丢弃来不及处理的帧
    output.setSampleBufferDelegate(self, queue: cameraQueue)
    
    guard session.canAddOutput(output) else { throw CameraError.cannotAddOutput }
    session.addOutput(output)
}
```

**帧回调：**

```swift
extension CameraEngine: AVCaptureVideoDataOutputSampleBufferDelegate {
    func captureOutput(_ output: AVCaptureOutput,
                       didOutput sampleBuffer: CMSampleBuffer,
                       from connection: AVCaptureConnection) {
        guard let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else { return }
        let timestamp = CMSampleBufferGetPresentationTimeStamp(sampleBuffer)
        delegate?.cameraEngine(self, didOutput: pixelBuffer, timestamp: timestamp)
    }
}
```

**注意事项：**
- `session.startRunning()` 必须在**非主线程**调用（否则会阻塞 UI）。用 `cameraQueue.async { self.session.startRunning() }`
- `AVCaptureVideoPreviewLayer` 连接到 Session 后可以直接嵌入 SwiftUI View（通过 `NSViewRepresentable`）

---

### 7.2 HandTracker

**文件：** `Core/Vision/HandTracker.swift`

**职责：** 接收 `CVPixelBuffer`，运行 Apple Vision 手部关键点识别，返回归一化的 21 个关键点坐标。

#### 数据结构

```swift
/// 21 个手部关键点，坐标归一化到 [0,1]
/// 坐标系：Vision 默认坐标原点在左下角，Y 轴向上
/// 注意：与屏幕坐标（原点左上角）不同，需要翻转 Y 轴
struct HandLandmarks {
    /// Vision JointName → CGPoint 映射
    let points: [VNHumanHandPoseObservation.JointName: CGPoint]
    
    // 便捷访问（常用关键点）
    var wrist:      CGPoint { points[.wrist] ?? .zero }
    var thumbTip:   CGPoint { points[.thumbTip] ?? .zero }      // 4
    var thumbIP:    CGPoint { points[.thumbIP] ?? .zero }       // 3
    var indexTip:   CGPoint { points[.indexTip] ?? .zero }      // 8
    var indexDIP:   CGPoint { points[.indexDIP] ?? .zero }      // 7
    var middleTip:  CGPoint { points[.middleTip] ?? .zero }     // 12
    var middleDIP:  CGPoint { points[.middleDIP] ?? .zero }     // 11
    var indexMCP:   CGPoint { points[.indexMCP] ?? .zero }      // 5
    var middleMCP:  CGPoint { points[.middleMCP] ?? .zero }     // 9
    var ringMCP:    CGPoint { points[.ringMCP] ?? .zero }       // 13
    var littleMCP:  CGPoint { points[.littleMCP] ?? .zero }     // 17
    
    /// 手掌中心（5个 MCP 关节 + 手腕的均值）
    var palmCenter: CGPoint {
        let pts = [wrist, indexMCP, middleMCP, ringMCP, littleMCP]
        let x = pts.map(\.x).reduce(0, +) / Double(pts.count)
        let y = pts.map(\.y).reduce(0, +) / Double(pts.count)
        return CGPoint(x: x, y: y)
    }
}
```

#### Vision 关键点与 MediaPipe 索引对照表

| MediaPipe 索引 | Vision JointName | 部位 |
|--------------|-----------------|------|
| 0 | `.wrist` | 手腕 |
| 1 | `.thumbCMC` | 拇指掌骨 |
| 2 | `.thumbMP` | 拇指掌指关节 |
| 3 | `.thumbIP` | 拇指指间关节 |
| 4 | `.thumbTip` | 拇指尖 |
| 5 | `.indexMCP` | 食指掌指关节 |
| 6 | `.indexPIP` | 食指近端指间 |
| 7 | `.indexDIP` | 食指远端指间 |
| 8 | `.indexTip` | 食指尖 |
| 9 | `.middleMCP` | 中指掌指关节 |
| 10 | `.middlePIP` | 中指近端指间 |
| 11 | `.middleDIP` | 中指远端指间 |
| 12 | `.middleTip` | 中指尖 |
| 13 | `.ringMCP` | 无名指掌指关节 |
| ... | ... | ... |
| 17 | `.littleMCP` | 小指掌指关节 |
| 20 | `.littleTip` | 小指尖 |

#### 接口与实现

```swift
class HandTracker {
    private let request = VNDetectHumanHandPoseRequest()
    
    init() {
        request.maximumHandCount = 1   // 只检测一只手
    }
    
    /// 处理一帧，返回检测到的手部关键点（未检测到返回 nil）
    func process(pixelBuffer: CVPixelBuffer,
                 orientation: CGImagePropertyOrientation = .up) -> HandLandmarks? {
        let handler = VNImageRequestHandler(cvPixelBuffer: pixelBuffer,
                                            orientation: orientation)
        do {
            try handler.perform([request])
        } catch {
            print("Vision error: \(error)")
            return nil
        }
        
        guard let observation = request.results?.first else { return nil }
        
        // 提取所有关节点
        guard let recognizedPoints = try? observation.recognizedPoints(.all) else {
            return nil
        }
        
        // 过滤置信度低的点（confidence < 0.5 视为不可靠）
        let filtered = recognizedPoints.compactMapValues { point -> CGPoint? in
            guard point.confidence > 0.5 else { return nil }
            return CGPoint(x: point.x, y: point.y)
        }
        
        return HandLandmarks(points: filtered)
    }
}
```

**关于坐标系：**

Vision Framework 的坐标原点在**左下角**，Y 轴向上（与 UIKit/SwiftUI 的左上角原点相反）。

在 `CameraPreviewView` 里显示骨骼时需要翻转 Y：
```swift
let displayY = 1.0 - normalizedY  // 翻转 Y 轴用于屏幕显示
```

在映射到屏幕坐标时，`NSScreen` 的坐标系原点也在**左下角**（macOS 特有），所以映射到 `NSScreen` 时**不需要**额外翻转 Y。

---

### 7.3 KalmanFilter

**文件：** `Core/Gesture/KalmanFilter.swift`

**职责：** 对手掌中心映射后的屏幕坐标进行平滑，消除手部抖动，同时保证快速移动时响应灵敏。

#### 原理简述（给不熟悉的开发者）

卡尔曼滤波器维护一个对"真实位置"的最优估计。每帧它做两件事：
1. **预测**：根据上一帧的位置和速度，预测这一帧的位置
2. **更新**：结合实际测量值（Vision 检测到的位置），修正预测

关键思想：当手移动很快时，信任测量值更多（响应快）；当手几乎静止时，信任预测值更多（减少抖动）。

#### 实现

```swift
/// 独立的 1D 卡尔曼滤波器，X 和 Y 各用一个实例
class KalmanFilter1D {
    // 过程噪声：越大越相信测量值（响应快但抖动多）
    var processNoise: Double = 0.01
    // 测量噪声：越大越相信预测值（更平滑但响应慢）
    var measurementNoise: Double = 0.1
    
    private var estimate: Double = 0
    private var errorCovariance: Double = 1.0
    
    func update(measurement: Double) -> Double {
        // 预测步骤（简化：假设匀速，这里只做位置滤波）
        let predictedCovariance = errorCovariance + processNoise
        
        // 更新步骤
        let kalmanGain = predictedCovariance / (predictedCovariance + measurementNoise)
        estimate = estimate + kalmanGain * (measurement - estimate)
        errorCovariance = (1 - kalmanGain) * predictedCovariance
        
        return estimate
    }
    
    func reset(to value: Double) {
        estimate = value
        errorCovariance = 1.0
    }
}

/// 2D 卡尔曼滤波器（X、Y 独立处理）
class KalmanFilter2D {
    private let filterX = KalmanFilter1D()
    private let filterY = KalmanFilter1D()
    
    /// 低速阈值（px/s），低于此速度时增加测量噪声以提升平滑度
    var lowSpeedThreshold: Double = 200.0
    
    private var lastPoint: CGPoint = .zero
    private var lastTime: Date = Date()
    
    func update(point: CGPoint) -> CGPoint {
        // 计算当前速度
        let now = Date()
        let dt = max(0.001, now.timeIntervalSince(lastTime))
        let speed = hypot(point.x - lastPoint.x, point.y - lastPoint.y) / dt
        lastPoint = point
        lastTime = now
        
        // 速度自适应：低速时增大测量噪声（更平滑）
        let adaptedNoise = speed < lowSpeedThreshold
            ? 0.5   // 低速：高平滑
            : 0.05  // 高速：快响应
        filterX.measurementNoise = adaptedNoise
        filterY.measurementNoise = adaptedNoise
        
        return CGPoint(
            x: filterX.update(measurement: point.x),
            y: filterY.update(measurement: point.y)
        )
    }
    
    func reset(to point: CGPoint) {
        filterX.reset(to: point.x)
        filterY.reset(to: point.y)
    }
}
```

---

### 7.4 PinchDetector

**文件：** `Core/Gesture/PinchDetector.swift`

**职责：** 检测拇指-食指捏合，区分"短捏（单击）"和"长捏（拖拽）"。

#### 核心算法

**归一化捏合距离：**
```
normalized_4to8 = dist(thumbTip, indexTip) / dist(thumbIP, indexDIP)
```
用指节间距作分母，消除手距摄像头远近的影响。

**动态阈值：**
维护最近 5 帧的 `normalized_4to8` 中位数作为"当前松开时的基线"，捏合阈值 = 基线 - 0.15，释放阈值 = 基线 + 0.15。这样无论手离摄像头多远，阈值都能自适应。

#### 状态机

```
[idle]
  │  normalized_4to8 < low_threshold
  ▼
[holding]  ← 记录开始时间 t0
  │
  ├── 若 t - t0 < 0.2s 且 normalized_4to8 > low_threshold
  │       → 发出 .leftClick，回到 [idle]
  │
  ├── 若 t - t0 >= 0.2s
  │       → 发出 .dragBegin，进入 [dragging]
  │
[dragging]
  │  normalized_4to8 > high_threshold（且手速 < 200px/s）
  ▼
  发出 .dragEnd，回到 [idle]
```

#### 接口

```swift
enum PinchAction {
    case leftClick
    case dragBegin   // 对应 mouseDown
    case dragEnd     // 对应 mouseUp
}

class PinchDetector {
    // 可调参数（均有默认值）
    var windowSize: Int = 5
    var stabilityDuration: TimeInterval = 0.2
    var thresholdMargin: Double = 0.15
    var lowSpeedThreshold: Double = 200.0
    
    var isDragging: Bool { get }  // 供外部检查当前是否在拖拽
    
    /// 每帧调用，返回触发的动作（nil 表示无新动作）
    func update(normalizedDist: Double, handSpeed: Double) -> PinchAction?
    
    /// 手消失时调用
    func reset()
}
```

#### 实现细节

```swift
func update(normalizedDist: Double, handSpeed: Double) -> PinchAction? {
    // 更新滑动窗口
    window.append(normalizedDist)
    if window.count > windowSize { window.removeFirst() }
    guard window.count == windowSize else { return nil }
    
    let baseline = window.sorted()[windowSize / 2]  // 中位数
    let lowThreshold  = baseline - thresholdMargin
    let highThreshold = baseline + thresholdMargin
    
    switch state {
    case .idle:
        if normalizedDist < lowThreshold {
            state = .holding(startTime: Date())
        }
        
    case .holding(let startTime):
        let elapsed = Date().timeIntervalSince(startTime)
        
        if normalizedDist > lowThreshold && elapsed < stabilityDuration {
            // 快速释放 → 单击
            state = .idle
            return .leftClick
        }
        if elapsed >= stabilityDuration {
            // 保持足够长 → 拖拽开始
            state = .dragging
            return .dragBegin
        }
        
    case .dragging:
        let shouldRelease = normalizedDist > highThreshold
        if shouldRelease && handSpeed < lowSpeedThreshold {
            state = .idle
            return .dragEnd
        }
    }
    return nil
}
```

---

### 7.5 ScrollDetector

**文件：** `Core/Gesture/ScrollDetector.swift`

**职责：** 检测拇指-中指捏合，区分"短捏（右键单击）"和"长捏（滚动）"，滚动带惯性衰减。

#### 归一化距离

```
normalized_4to12 = dist(thumbTip, middleTip) / dist(thumbIP, middleDIP)
```

#### 状态机

```
[idle]
  │  normalized_4to12 < low_threshold
  ▼
[holding]  ← 记录开始时间 t0 和锚点位置 anchor
  │
  ├── 若 t - t0 < 0.25s 且释放
  │       → 发出 .rightClick，回到 [idle]
  │
  ├── 若 t - t0 >= 0.25s 或 手移动超过 30px
  │       → 进入 [scrolling]，记录 scrollAnchor = 当前屏幕坐标
  │
[scrolling]  ← 每帧计算 delta，发出 .scroll(dx, dy)
  │  normalized_4to12 > high_threshold（且手速 < 200px/s）
  ▼
  发出 .scrollEnd，进入 [inertia]

[inertia]  ← 每帧速度衰减
  │  速度 < 1px/frame
  ▼
  回到 [idle]
```

#### 滚动量计算

```swift
// 每帧在 [scrolling] 状态下：
let delta = CGPoint(
    x: (scrollAnchor.x - currentScreenPoint.x) * speedFactor,  // speedFactor = 0.5
    y: (scrollAnchor.y - currentScreenPoint.y) * speedFactor
)
scrollAnchor = currentScreenPoint  // 更新锚点（相对滚动）
// 发出 .scroll(dx: Int(-delta.x), dy: Int(-delta.y))
```

#### 惯性衰减

```swift
// 在 [inertia] 状态下：
inertiaVelocity.x *= decayFactor  // decayFactor = 0.85
inertiaVelocity.y *= decayFactor
if abs(inertiaVelocity.x) < 1 && abs(inertiaVelocity.y) < 1 {
    state = .idle
} else {
    // 继续发出 .scroll
}
```

#### 接口

```swift
enum ScrollAction {
    case rightClick
    case scroll(dx: Int, dy: Int)
    case scrollEnd
}

class ScrollDetector {
    var stabilityDuration: TimeInterval = 0.25
    var thresholdMargin: Double = 0.15
    var stabilityRadius: Double = 30.0   // px，超过此距离直接进入滚动
    var speedFactor: Double = 0.5
    var decayFactor: Double = 0.85
    var lowSpeedThreshold: Double = 200.0
    
    func update(normalizedDist: Double,
                screenPoint: CGPoint,
                handSpeed: Double) -> [ScrollAction]
    func reset()
}
```

---

### 7.6 FistDetector

**文件：** `Core/Gesture/FistDetector.swift`

**职责：** 检测握拳手势，连续握拳 3 秒触发 Session 结束。

#### 握拳判断方法

用手指"弯曲比"来判断：对每根手指，计算 TIP 到 MCP 的距离，与 MCP 到 Wrist 的距离相比，比值越小说明手指越弯曲。

```swift
func isFist(landmarks: HandLandmarks) -> Bool {
    // 分别判断四根手指（拇指另行处理）
    let fingers: [(tip: CGPoint, pip: CGPoint, mcp: CGPoint)] = [
        (landmarks.indexTip,  landmarks.points[.indexPIP]  ?? .zero, landmarks.indexMCP),
        (landmarks.middleTip, landmarks.points[.middlePIP] ?? .zero, landmarks.middleMCP),
        (landmarks.points[.ringTip]    ?? .zero,
         landmarks.points[.ringPIP]    ?? .zero,
         landmarks.points[.ringMCP]    ?? .zero),
        (landmarks.points[.littleTip]  ?? .zero,
         landmarks.points[.littlePIP]  ?? .zero,
         landmarks.points[.littleMCP]  ?? .zero),
    ]
    
    let curlThreshold: Double = 0.5  // TIP-to-MCP / MCP-to-Wrist < 0.5 视为弯曲
    
    for finger in fingers {
        let tipToMCP  = dist(finger.tip, finger.mcp)
        let mcpToWrist = dist(finger.mcp, landmarks.wrist)
        if mcpToWrist < 0.001 { continue }
        let ratio = tipToMCP / mcpToWrist
        if ratio >= curlThreshold { return false }  // 有手指未弯曲
    }
    return true
}
```

#### 时序逻辑

```swift
class FistDetector {
    let requiredDuration: TimeInterval = 3.0
    private var fistStartTime: Date? = nil
    
    /// 返回握拳已持续的秒数（nil = 当前不是握拳）
    func update(landmarks: HandLandmarks) -> TimeInterval? {
        if isFist(landmarks: landmarks) {
            if fistStartTime == nil { fistStartTime = Date() }
            let elapsed = Date().timeIntervalSince(fistStartTime!)
            return elapsed  // 调用方判断是否 >= 3s
        } else {
            fistStartTime = nil
            return nil
        }
    }
    
    func reset() { fistStartTime = nil }
}
```

`SessionController` 在收到握拳持续时间 >= 3s 时触发 `.ending` 状态。

---

### 7.7 ROIManager

**文件：** `Core/Gesture/ROIManager.swift`

**职责：**
1. 根据手掌宽度自适应确定摄像头画面中的 ROI 区域（绿框）
2. 将 ROI 内的归一化坐标映射到屏幕（多显示器）坐标

#### ROI 确定逻辑

ROI 的大小基于手掌宽度，保持与屏幕相同的宽高比：

```
palm_width_norm = max_x(landmarks) - min_x(landmarks)  // 归一化宽度
roi_width_norm  = palm_width_norm * touchpad_multiplier  // 默认 multiplier = 2.5
roi_height_norm = roi_width_norm / screen_aspect_ratio

roi_center = palm_center（手掌中心）
```

ROI 中心跟随手掌，但使用低通滤波平滑（避免 ROI 框跳动）：

```swift
// 指数平滑：beta = 0.25（越小越平滑，越大越跟手）
smoothedCenter = smoothedCenter * (1 - beta) + newCenter * beta
smoothedSize   = smoothedSize   * (1 - beta) + newSize   * beta
```

#### 标定状态机

```
[idle] → 手出现 → [countdown: 3s] → 倒计时结束 → [active]
                      │
                      └── 手消失 → 重置回 [idle]（重置倒计时）
```

#### 屏幕坐标映射（含边缘补偿）

```swift
func mapToScreen(normalizedPoint: CGPoint,
                 roi: CGRect,               // ROI 在归一化坐标系中的 rect
                 combinedScreenRect: CGRect, // 所有显示器合并后的 CGRect
                 edgePadding: Double = 0.05) -> CGPoint {
    
    // 1. 手在 ROI 内的相对位置
    var u = (normalizedPoint.x - roi.minX) / roi.width   // 0~1
    var v = (normalizedPoint.y - roi.minY) / roi.height  // 0~1
    u = u.clamped(to: 0...1)
    v = v.clamped(to: 0...1)
    
    // 2. 边缘补偿：让手接近 ROI 边缘时能触达屏幕边缘
    let pad = edgePadding  // 0.05
    u = ((u - pad) / (1.0 - 2 * pad)).clamped(to: 0...1)
    v = ((v - pad) / (1.0 - 2 * pad)).clamped(to: 0...1)
    
    // 3. 映射到合并屏幕坐标系
    let screenX = combinedScreenRect.minX + u * combinedScreenRect.width
    let screenY = combinedScreenRect.minY + v * combinedScreenRect.height
    
    return CGPoint(x: screenX, y: screenY)
}
```

---

### 7.8 MouseController

**文件：** `Core/Mouse/MouseController.swift`

**职责：** 封装所有 `CGEvent` 鼠标操作，提供简洁接口。

#### 权限检查

在任何鼠标操作前必须确认 Accessibility 权限：

```swift
static func checkAccessibility() -> Bool {
    return AXIsProcessTrusted()
}

static func requestAccessibility() {
    let options: CFDictionary = [
        kAXTrustedCheckOptionPrompt.takeRetainedValue() as String: true
    ] as CFDictionary
    AXIsProcessTrustedWithOptions(options)
}
```

#### 接口实现

```swift
class MouseController {
    private var currentPosition: CGPoint = .zero
    
    func moveTo(_ point: CGPoint) {
        currentPosition = point
        let event = CGEvent(mouseEventSource: nil,
                            mouseEventType: .mouseMoved,
                            mouseCursorPosition: point,
                            mouseButton: .left)
        event?.post(tap: .cghidEventTap)
    }
    
    func leftClick() {
        postMouseEvent(.leftMouseDown)
        postMouseEvent(.leftMouseUp)
    }
    
    func dragBegin() {
        postMouseEvent(.leftMouseDown)
    }
    
    func dragEnd() {
        postMouseEvent(.leftMouseUp)
    }
    
    func rightClick() {
        postMouseEvent(.rightMouseDown)
        postMouseEvent(.rightMouseUp)
    }
    
    func scroll(dx: Int, dy: Int) {
        // unit: .pixel 在 Retina 屏上 1 unit ≈ 2pt，根据实际调整
        let event = CGEvent(scrollWheelEvent2Source: nil,
                            units: .pixel,
                            wheelCount: 2,
                            wheel1: Int32(dy),
                            wheel2: Int32(dx),
                            wheel3: 0)
        event?.post(tap: .cghidEventTap)
    }
    
    private func postMouseEvent(_ type: CGEventType) {
        let event = CGEvent(mouseEventSource: nil,
                            mouseEventType: type,
                            mouseCursorPosition: currentPosition,
                            mouseButton: type == .rightMouseDown || type == .rightMouseUp
                                ? .right : .left)
        event?.post(tap: .cghidEventTap)
    }
}
```

> ⚠️ `CGEvent.post(tap:)` 必须在**主线程**调用。

---

### 7.9 SessionController

**文件：** `Core/Session/SessionController.swift`

**职责：** 整个应用的中枢。管理 Session 状态机，协调 Camera、Tracker、Gesture、Mouse 各模块。

#### 状态定义

```swift
enum SessionState: Equatable {
    case idle                          // App 刚启动，摄像头未开
    case waitingForHand                // 摄像头开启，等待手出现
    case calibrating(countdown: Int)   // 倒计时（3、2、1）
    case active                        // 手势控制进行中
    case ending(countdown: Int)        // 握拳结束倒计时（3、2、1）
}
```

#### 核心逻辑（伪代码）

```swift
@MainActor
func onHandFrame(landmarks: HandLandmarks?, timestamp: Date) {
    switch state {
        
    case .waitingForHand:
        guard let lm = landmarks else { return }
        // 有手 → 开始标定
        calibrationStartTime = timestamp
        state = .calibrating(countdown: 3)
        roiManager.begin(landmarks: lm)
        
    case .calibrating(let countdown):
        guard let lm = landmarks else {
            // 手消失 → 重置倒计时（但不回到 waitingForHand 直到完全消失 N 帧）
            resetCalibration()
            return
        }
        roiManager.update(landmarks: lm)
        let elapsed = timestamp.timeIntervalSince(calibrationStartTime)
        let remaining = max(0, 3 - Int(elapsed))
        state = .calibrating(countdown: remaining)
        if remaining == 0 {
            enterActive()
        }
        
    case .active:
        guard let lm = landmarks else {
            // 手消失：暂停鼠标（不退出 active，等手回来）
            gestureEngine.reset()
            return
        }
        
        // ROI 映射
        guard let screenPoint = roiManager.mapToScreen(landmarks: lm) else { return }
        let smoothed = kalmanFilter.update(point: screenPoint)
        mouseController.moveTo(smoothed)
        
        // 手势检测
        let norm4to8  = normalized4to8(lm)
        let norm4to12 = normalized4to12(lm)
        let speed = calculateSpeed(from: smoothed)
        
        if let action = pinchDetector.update(normalizedDist: norm4to8, handSpeed: speed) {
            handlePinchAction(action)
        }
        for action in scrollDetector.update(normalizedDist: norm4to12,
                                             screenPoint: smoothed, handSpeed: speed) {
            handleScrollAction(action)
        }
        
        if let fistDuration = fistDetector.update(landmarks: lm), fistDuration >= 3.0 {
            enterEnding()
        }
        // 握拳倒计时 UI 更新（fistDuration 0~3 → 显示 3、2、1）
        
    case .ending(let countdown):
        // 倒计时到 0 → 回到等待
        if countdown <= 0 { enterWaitingForHand() }
    }
}
```

#### 快捷键注册

```swift
func registerHotkey() {
    // Option + Escape
    NSEvent.addGlobalMonitorForEvents(matching: .keyDown) { [weak self] event in
        guard event.modifierFlags.contains(.option),
              event.keyCode == 53 /* Escape */ else { return }
        self?.endSession()
    }
}
```

---

### 7.10 UI — CalibrationWindow

**文件：** `UI/CalibrationWindow.swift`

**职责：** 在 `waitingForHand` 和 `calibrating` 状态下显示的小窗口。`active` 状态后隐藏，`ending` 时重现。

#### 窗口规格

- 尺寸：400 × 300 pt，固定，不可调整（`resizable` 为 false）
- 层级：`NSWindow.Level.floating`（总在最前）
- 样式：无标题栏，圆角，纯白背景

#### SwiftUI View 结构

```swift
struct CalibrationView: View {
    @ObservedObject var session: SessionController
    
    var body: some View {
        ZStack {
            // 摄像头预览层
            CameraPreviewView(previewLayer: session.cameraEngine.previewLayer)
                .clipShape(RoundedRectangle(cornerRadius: 12))
            
            // 骨骼覆盖层（calibrating 状态时显示）
            if case .calibrating = session.state, let lm = session.latestLandmarks {
                HandSkeletonOverlayView(landmarks: lm)
            }
            
            // 文字提示
            VStack {
                Spacer()
                Text(promptText)
                    .font(.system(size: 18, weight: .regular, design: .default))
                    .foregroundColor(.white)
                    .shadow(radius: 2)
                    .padding(.bottom, 20)
            }
            
            // 倒计时数字（calibrating / ending 时）
            if let countdown = countdownValue {
                Text("\(countdown)")
                    .font(.system(size: 72, weight: .thin))
                    .foregroundColor(.white)
                    .shadow(radius: 4)
            }
        }
        .background(Color.black)  // 摄像头区域
        .frame(width: 400, height: 300)
    }
    
    private var promptText: String {
        switch session.state {
        case .waitingForHand:       return "Show your hand to the camera"
        case .calibrating:          return "Hold still to calibrate"
        case .ending:               return "Fist detected — releasing..."
        default:                    return ""
        }
    }
    
    private var countdownValue: Int? {
        switch session.state {
        case .calibrating(let n):   return n
        case .ending(let n):        return n
        default:                    return nil
        }
    }
}
```

#### 窗口显示/隐藏逻辑

`SessionController` 状态变化时触发：

```swift
// active 状态：隐藏窗口
window.orderOut(nil)

// waitingForHand / calibrating / ending 状态：显示窗口
window.makeKeyAndOrderFront(nil)
window.center()  // 首次显示时居中
```

---

### 7.11 UI — MenuBarController

**文件：** `UI/MenuBarController.swift`

**职责：** 菜单栏图标 + 下拉菜单。

#### SwiftUI MenuBarExtra（推荐方式，macOS 13+）

```swift
@main
struct AirMouseApp: App {
    @StateObject private var session = SessionController()
    
    var body: some Scene {
        // 菜单栏图标
        MenuBarExtra {
            MenuBarMenuView(session: session)
        } label: {
            // 根据状态切换图标
            Image(systemName: session.state == .active
                  ? "hand.raised.fill"
                  : "hand.raised")
        }
        .menuBarExtraStyle(.menu)
    }
}
```

#### 菜单内容

```swift
struct MenuBarMenuView: View {
    @ObservedObject var session: SessionController
    
    var body: some View {
        Group {
            // 状态显示
            Text(statusText).foregroundColor(.secondary)
            Divider()
            
            // 开始 / 停止
            Button(session.isActive ? "Stop AirMouse" : "Start AirMouse") {
                session.isActive ? session.endSession() : session.startSession()
            }
            
            Divider()
            
            // 摄像头选择子菜单
            Menu("Camera") {
                ForEach(availableCameras, id: \.uniqueID) { cam in
                    Button(cam.localizedName) {
                        SettingsManager.shared.preferredCameraID = cam.uniqueID
                        session.restartCamera()
                    }
                }
            }
            
            Divider()
            
            Button("Quit AirMouse") { NSApp.terminate(nil) }
                .keyboardShortcut("q")
        }
    }
}
```

---

### 7.12 SettingsManager

**文件：** `Settings/SettingsManager.swift`

**职责：** 持久化用户偏好，使用 `UserDefaults`。

```swift
class SettingsManager: ObservableObject {
    static let shared = SettingsManager()
    
    @AppStorage("preferredCameraID")
    var preferredCameraID: String? = nil
    
    @AppStorage("kalmanLowSpeedThreshold")
    var kalmanLowSpeedThreshold: Double = 200.0
    
    @AppStorage("pinchThresholdMargin")
    var pinchThresholdMargin: Double = 0.15
    
    @AppStorage("scrollSpeedFactor")
    var scrollSpeedFactor: Double = 0.5
    
    @AppStorage("edgePadding")
    var edgePadding: Double = 0.05
    
    @AppStorage("touchpadMultiplier")
    var touchpadMultiplier: Double = 2.5
}
```

---

## 8. 算法详解

### 8.1 归一化距离计算

```swift
func distance(_ a: CGPoint, _ b: CGPoint) -> Double {
    hypot(a.x - b.x, a.y - b.y)
}

// 拇指-食指归一化距离
func normalized4to8(landmarks: HandLandmarks) -> Double {
    let raw = distance(landmarks.thumbTip, landmarks.indexTip)
    let ref = distance(landmarks.thumbIP,  landmarks.indexDIP)
    guard ref > 1e-6 else { return 1.0 }  // 防除零
    return raw / ref
}

// 拇指-中指归一化距离
func normalized4to12(landmarks: HandLandmarks) -> Double {
    let raw = distance(landmarks.thumbTip,  landmarks.middleTip)
    let ref = distance(landmarks.thumbIP,   landmarks.middleDIP)
    guard ref > 1e-6 else { return 1.0 }
    return raw / ref
}
```

### 8.2 手速计算

```swift
// 在 SessionController 里维护
private var lastScreenPoint: CGPoint = .zero
private var lastFrameTime: Date = Date()

func calculateSpeed(from point: CGPoint) -> Double {
    let now = Date()
    let dt = max(0.001, now.timeIntervalSince(lastFrameTime))
    let speed = hypot(point.x - lastScreenPoint.x,
                      point.y - lastScreenPoint.y) / dt  // px/s
    lastScreenPoint = point
    lastFrameTime = now
    return speed
}
```

### 8.3 动态阈值滑动窗口（中位数）

```swift
// 在 PinchDetector / ScrollDetector 中复用此结构
struct MedianWindow {
    let capacity: Int
    private var buffer: [Double] = []
    
    mutating func append(_ value: Double) {
        buffer.append(value)
        if buffer.count > capacity { buffer.removeFirst() }
    }
    
    var median: Double? {
        guard buffer.count == capacity else { return nil }
        let sorted = buffer.sorted()
        return sorted[capacity / 2]
    }
    
    var isFull: Bool { buffer.count == capacity }
    
    mutating func clear() { buffer.removeAll() }
}
```

---

## 9. 多显示器实现

### 9.1 获取合并屏幕区域

```swift
/// 计算所有显示器的合并 bounding box（macOS 虚拟桌面坐标系）
func combinedScreenRect() -> CGRect {
    let frames = NSScreen.screens.map { $0.frame }
    let minX = frames.map(\.minX).min() ?? 0
    let minY = frames.map(\.minY).min() ?? 0
    let maxX = frames.map(\.maxX).max() ?? 1920
    let maxY = frames.map(\.maxY).max() ?? 1080
    return CGRect(x: minX, y: minY,
                  width: maxX - minX,
                  height: maxY - minY)
}
```

**macOS 坐标系说明：**
- `NSScreen.frame` 的原点在主屏幕**左下角**
- 主屏幕：frame = (0, 0, width, height)
- 右侧外接屏：frame = (主屏宽, 0, 副屏宽, 副屏高)
- 上方外接屏：frame = (0, 主屏高, 副屏宽, 副屏高)（Y 向上）

**CGEvent 坐标系：**
- 原点在主屏幕**左上角**（与 NSScreen 相反）
- 需要转换：`cgEventY = mainScreenHeight - nsScreenY`

```swift
func toCGEventCoordinate(_ nsPoint: CGPoint) -> CGPoint {
    let mainHeight = NSScreen.screens.first?.frame.height ?? 1080
    return CGPoint(x: nsPoint.x, y: mainHeight - nsPoint.y)
}
```

### 9.2 完整映射流程

```swift
func mapHandToScreen(landmarks: HandLandmarks) -> CGPoint? {
    guard let roi = roiManager.currentROI else { return nil }
    
    let palmCenter = landmarks.palmCenter  // 归一化坐标，Vision 坐标系（原点左下）
    
    // ROI 内相对位置（已在 ROIManager 内计算，含边缘补偿）
    let nsPoint = roiManager.mapToScreen(normalizedPoint: palmCenter,
                                          roi: roi,
                                          combinedScreenRect: combinedScreenRect())
    
    // 转换为 CGEvent 坐标
    return toCGEventCoordinate(nsPoint)
}
```

---

## 10. 权限配置

### 10.1 摄像头权限

系统在 App 首次调用 `AVCaptureSession.startRunning()` 时自动弹出授权对话框。

主动检查状态：
```swift
switch AVCaptureDevice.authorizationStatus(for: .video) {
case .authorized:
    startCamera()
case .notDetermined:
    AVCaptureDevice.requestAccess(for: .video) { granted in
        if granted { DispatchQueue.main.async { self.startCamera() } }
    }
case .denied, .restricted:
    showCameraPermissionAlert()
@unknown default:
    break
}
```

### 10.2 Accessibility 权限（鼠标控制）

CGEvent 模拟鼠标需要辅助功能权限。**没有此权限时 `CGEvent.post()` 静默失败（不报错）。**

```swift
func ensureAccessibility() {
    guard !AXIsProcessTrusted() else { return }
    
    // 弹出系统提示，引导用户去「系统设置 → 隐私与安全性 → 辅助功能」
    let options = [kAXTrustedCheckOptionPrompt.takeRetainedValue() as String: true]
    AXIsProcessTrustedWithOptions(options as CFDictionary)
}
```

建议在 `SessionController.startSession()` 时调用，发现无权限时禁止进入 `active` 状态并在 UI 提示。

---

## 11. 构建与打包

### 11.1 开发期本地运行

在 Xcode 里直接 ⌘R 即可，无需特殊配置。

### 11.2 代码签名

需要 Apple Developer 付费账号（$99/年）。在 Xcode → Signing & Capabilities 里选择 Team，勾选"Automatically manage signing"。

### 11.3 Notarization（公证）

分发给其他 Mac 用户时必须公证，否则 macOS Gatekeeper 拦截。

```bash
# 1. 打包为 .app
xcodebuild archive \
  -scheme AirMouse \
  -archivePath ./build/AirMouse.xcarchive

# 2. 导出 .app
xcodebuild -exportArchive \
  -archivePath ./build/AirMouse.xcarchive \
  -exportPath ./build/export \
  -exportOptionsPlist ExportOptions.plist

# 3. 公证
xcrun notarytool submit ./build/export/AirMouse.app \
  --apple-id "your@email.com" \
  --team-id "YOURTEAMID" \
  --password "app-specific-password" \
  --wait

# 4. 装订公证票据
xcrun stapler staple ./build/export/AirMouse.app
```

### 11.4 DMG 打包

```bash
# 使用 create-dmg（brew install create-dmg）
create-dmg \
  --volname "AirMouse" \
  --window-size 600 400 \
  --icon-size 128 \
  --icon "AirMouse.app" 150 200 \
  --app-drop-link 450 200 \
  "AirMouse.dmg" \
  "./build/export/"
```

### 11.5 ExportOptions.plist 模板

```xml
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0">
<dict>
    <key>method</key>
    <string>developer-id</string>  <!-- 非 App Store 分发 -->
    <key>teamID</key>
    <string>YOURTEAMID</string>
    <key>signingStyle</key>
    <string>automatic</string>
</dict>
</plist>
```

---

## 12. 性能要求与调优指南

### 12.1 性能目标

| 指标 | 目标 |
|------|------|
| 端到端延迟（手势→鼠标响应）| < 30ms |
| CPU 占用（active 状态，M 芯片）| < 5% |
| 内存 | < 80MB |
| Vision 推理帧率 | 30fps |

### 12.2 关键调优点

**摄像头分辨率**：使用 `session.sessionPreset = .vga640x480`（640×480），不要用 1080p。Vision 推理时间与分辨率正相关，640×480 已经足够手部追踪精度。

**丢帧策略**：`output.alwaysDiscardsLateVideoFrames = true`，确保处理的始终是最新帧，避免延迟累积。

**Vision 只处理一只手**：`request.maximumHandCount = 1`，节省约 40% 推理时间。

**CGEvent 在主线程**：确保所有鼠标事件在主线程发送，避免线程切换开销。

**Kalman 滤波参数调整**：如果用户反馈延迟感强，减小 `measurementNoise`；如果抖动明显，增大 `measurementNoise`。

**ROI 平滑 beta 值**：`beta = 0.25` 是起始值。如果 ROI 框跳动，减小 beta；如果跟手太慢，增大 beta。

---

## 13. 已知约束与注意事项

**Vision 坐标 vs CGEvent 坐标**：Vision 的归一化坐标原点在左下角，CGEvent 原点在左上角（主屏），务必做转换（见第 9 节），这是最容易踩的坑。

**多显示器 Y 轴方向**：`NSScreen.frame` 的 Y 轴向上，所以"在主屏上方"的副屏 Y 值比主屏大。`CGEvent` 的 Y 轴向下。两套坐标系要小心对应。

**App Sandbox 必须关闭**：`CGEvent.post(tap: .cghidEventTap)` 在沙盒环境里无效，已在 Entitlements 里设置 `com.apple.security.app-sandbox = false`。

**Accessibility 权限静默失败**：没有 Accessibility 权限时 CGEvent 不报错、不崩溃，就是鼠标不动。开发时如果发现鼠标不响应，第一个检查点就是「系统设置 → 辅助功能 → AirMouse 是否已授权」。

**AVCaptureSession 必须在非主线程启动**：`session.startRunning()` 是同步阻塞调用，在主线程调用会卡 UI 约 0.5s，一定要 `cameraQueue.async { session.startRunning() }`。

**Vision 置信度过滤**：置信度 < 0.5 的关键点坐标不可靠，在 `HandTracker` 里已过滤。如果某帧返回 `nil`（手没完全入镜），上层要容忍，不要 crash。

**握拳识别误触**：高速移动时手指可能看起来像握拳，建议在 `FistDetector` 里加速度判断——手速 > 阈值时跳过握拳检测。

**Python 参考版本行为对齐**：开发某个模块时，可以用 Python 版本作为行为基准。Python 版的 `PinchClickGesture`、`ScrollGesture` 逻辑在 `../AirMouse/airmouse/gestures/` 里，是直接的参考实现。
