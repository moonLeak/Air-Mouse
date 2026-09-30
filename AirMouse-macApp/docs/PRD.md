# AirMouse — macOS Product Requirements Document

**版本** 0.2  
**日期** 2026-05-14  
**作者** Carson  
**状态** 草稿

---

## 1. 产品概述

AirMouse 是一个 macOS 原生应用，通过前置摄像头实时识别手部姿态，将手势映射为鼠标操作，实现无接触控制电脑。目标是流畅、低延迟、对 Apple Silicon 深度调优的体验。

**核心价值主张**  
手脏、在工作台不想触碰鼠标时，抬起一只手就能操控屏幕。视觉上足够 fancy，技术上足够扎实。

**产品定位**  
作品集项目。目标受众：开发者 + 对新交互感兴趣的普通用户。

---

## 2. 目标与非目标

### 目标（当前版本）
- 实现核心手势控制：移动、左键、右键、拖拽、滚动
- 支持多显示器布局
- Menu Bar 常驻，无感运行
- 清晰的标定流程（对开发者友好即可，暂不做消费者级引导）
- 打包为可分发的 `.dmg`，代码签名 + 公证

### 非目标（明确排除）
- iOS 版本
- Windows 版本
- App Store 上架
- 首次启动权限引导（Permission Onboarding）
- 自定义手势 / 插件系统
- 多手支持

---

## 3. 技术栈

| 层级 | 技术选型 | 说明 |
|------|----------|------|
| 语言 | Swift 5.9+ | 全程 Swift，无 Objective-C |
| UI | SwiftUI | 标定窗口、Menu Bar |
| 手部追踪 | Apple Vision Framework (`VNDetectHumanHandPoseRequest`) | 跑在 Apple Neural Engine，M 芯片原生 |
| 鼠标控制 | Core Graphics (`CGEvent`) | 模拟鼠标事件，需 Accessibility 权限 |
| 相机采集 | AVFoundation (`AVCaptureSession`) | 直接采集，不走 Vision 的相机管理 |
| 滤波平滑 | 手写 Kalman Filter（Swift 移植自 Python 版） | |
| 最低系统版本 | macOS 13 Ventura | VNHumanHandPoseObservation 稳定版 |
| 目标硬件 | Apple Silicon（M 系列）| 针对 ANE 调优，不测试 Intel |
| 打包分发 | DMG + 代码签名 + Notarization | 无 App Store |

---

## 4. 系统架构

```
┌─────────────────────────────────────────────────────┐
│                     App Entry                        │
│              (AppDelegate / @main)                   │
└────────────────┬────────────────┬───────────────────┘
                 │                │
    ┌────────────▼──────┐  ┌──────▼──────────────┐
    │   Menu Bar UI     │  │  Calibration Window  │
    │  (NSStatusItem)   │  │    (SwiftUI View)    │
    └────────────┬──────┘  └──────┬───────────────┘
                 │                │
    ┌────────────▼────────────────▼───────────────┐
    │              SessionController               │
    │   (状态机：idle → calibrating → active)      │
    └──┬──────────────┬──────────────┬────────────┘
       │              │              │
┌──────▼──────┐ ┌─────▼──────┐ ┌───▼────────────┐
│CameraEngine │ │HandTracker │ │ MouseController │
│(AVFoundation│ │(Vision FW) │ │  (CGEvent)      │
└──────┬──────┘ └─────┬──────┘ └───▲────────────┘
       │              │             │
       └──────────────▼─────────────┤
                 ┌──────────────────┤
                 │  GestureEngine   │
                 │  ├ KalmanFilter  │
                 │  ├ PinchDetector │
                 │  ├ ScrollDetector│
                 │  ├ FistDetector  │
                 │  └ ROIManager    │
                 └──────────────────┘
```

---

## 5. Session 生命周期

### 5.1 状态机

```
[idle]
  │  App 启动
  ▼
[waiting_for_hand]   ← 白窗口显示，"Show your hand to the camera"
  │  检测到手部
  ▼
[calibrating]        ← 显示手部骨骼，倒计时 3s，"Hold still to calibrate"
  │  倒计时结束
  ▼
[active]             ← 白窗口消失，Menu Bar 图标变色，手势控制鼠标
  │  握拳 3s / Option+Escape
  ▼
[ending]             ← 白窗口重新显示，握拳倒计时 3s
  │  倒计时结束
  ▼
[waiting_for_hand]   ← 回到初始等待状态
```

### 5.2 各状态详细行为

**waiting_for_hand**
- 白色小窗口居中显示（尺寸约 400×300pt）
- 摄像头预览填满窗口
- 文字叠加：`"Show your hand to the camera"`
- 无手部检测时循环等待

**calibrating**
- 检测到手部后立即进入
- 在摄像头画面上叠加手部关键点（21个点 + 骨骼连线）
- 文字变为：`"Hold still  3…"`，每秒更新
- 英文副文字（小号）：`Calibrating position`
- 倒计时期间若手部消失 → 重置回 waiting_for_hand

**active**
- 白窗口隐藏（`window.orderOut(nil)`）
- Menu Bar 图标变为激活态（实心 / 高亮色）
- 手势控制鼠标（详见第 6 节）
- 鼠标初始位置：标定完成时跳至屏幕中心

**ending**
- 白窗口重新出现
- 显示握拳倒计时：`"Fist detected  3…"`
- 倒计时结束 → 回到 waiting_for_hand，Menu Bar 图标恢复默认态
- 若握拳中途松开 → 取消倒计时，回到 active

---

## 6. 手势规格

### 6.1 关键点索引（与 MediaPipe 一致）

```
拇指尖   = 4    拇指第一关节 = 3
食指尖   = 8    食指第一关节 = 7
中指尖   = 12   中指第一关节 = 11
手腕     = 0
手掌中心 = (0 + 5 + 9 + 13 + 17) 五点均值（近似）
```

### 6.2 归一化距离

所有捏合距离使用参考长度归一化，消除手离摄像头远近的影响：

```
normalized_4to8  = dist(4, 8) / dist(3, 7)   // 拇指-食指
normalized_4to12 = dist(4, 12) / dist(3, 11)  // 拇指-中指
```

### 6.3 手势定义

| 手势 | 检测方法 | 触发动作 |
|------|----------|----------|
| 光标移动 | 手掌中心位置 → ROI 映射 → 屏幕坐标，经 Kalman 滤波 | `CGEvent mouseMoved` |
| 左键单击 | normalized_4to8 < 低阈值，持续 < 0.2s 后释放 | `CGEvent leftMouseDown/Up` |
| 左键拖拽 | normalized_4to8 < 低阈值，持续 ≥ 0.2s | `CGEvent leftMouseDown`（按住），松开时 `leftMouseUp` |
| 右键单击 | normalized_4to12 < 低阈值，持续 < 0.25s 后释放 | `CGEvent rightMouseDown/Up` |
| 滚动 | normalized_4to12 < 低阈值持续，手掌移动量 → 滚动量，带惯性衰减 | `CGEvent scrollWheel` |
| 结束 Session | 五指全部弯曲（fist），持续 ≥ 3s | 触发 ending 状态 |

### 6.4 Kalman 滤波参数（初始值，可调）

```
过程噪声  Q = 0.01
测量噪声  R = 0.1（低速时增大 R 以增加平滑）
低速阈值  = 200 px/s（低于此值切换到高平滑模式）
```

### 6.5 捏合阈值动态计算

使用滑动窗口（5帧）中位数作为动态基线，避免因距离镜头不同导致阈值失效：

```
dynamic_baseline = median(last 5 frames)
low_threshold  = dynamic_baseline - 0.15
high_threshold = dynamic_baseline + 0.15
```

### 6.6 握拳检测（Fist）

五根手指的 curl 值均超过阈值视为握拳。使用 VNHumanHandPoseObservation 的 `recognizedPoints` 计算各指 MCP→PIP→TIP 的弯曲角度，全部 > 90° 即判定。

---

## 7. ROI 与多显示器映射

### 7.1 单显示器

ROI（绿框）在摄像头画面中的位置通过手掌宽度自适应确定（Python 版逻辑直接移植）。ROI 内的相对坐标线性映射到屏幕坐标。

### 7.2 多显示器

```
1. 获取 NSScreen.screens（包含每个屏幕的 frame，坐标系为 macOS 虚拟桌面坐标）
2. 计算所有屏幕的 union bounding box → combinedRect
3. 计算 combinedRect 的 centroid
4. Camera ROI 中心 ↔ combinedRect centroid 对齐
5. 手在 ROI 内的相对位置 → combinedRect 内的绝对坐标
6. CGEvent 使用此绝对坐标，macOS 自动路由到对应屏幕
```

示意：
```
显示器A (0,0,1920,1080)    显示器B (1920,0,1920,1080)
┌──────────────────┐        ┌──────────────────┐
│                  │        │                  │
│     Screen 1     ├────────┤     Screen 2     │
│                  │        │                  │
└──────────────────┘        └──────────────────┘
combined bounding box: (0, 0, 3840, 1080)
centroid: (1920, 540)
```

### 7.3 边缘映射补偿

ROI 边缘内缩 5%（`edge_padding = 0.05`），手掌接近 ROI 边缘时提前映射到屏幕边缘，便于触达角落。

---

## 8. 权限需求

| 权限 | 用途 | 申请时机 |
|------|------|----------|
| Camera | AVCaptureSession 采集摄像头 | 首次启动时系统自动弹出 |
| Accessibility | CGEvent 模拟鼠标事件 | 首次启动时引导至系统设置（MVP 阶段简单提示即可） |

`Info.plist` 需添加：
```xml
NSCameraUsageDescription
AXIsProcessTrusted() 检查 + 引导开启
```

---

## 9. UI 规格

### 9.1 标定窗口

- 尺寸：400 × 300 pt，固定大小，不可调整
- 背景：纯白 `#FFFFFF`
- 摄像头预览：铺满窗口，圆角 12pt
- 文字叠加：白色，居中，`SF Pro Display` 20pt Regular
- 倒计时数字：白色，居中，`SF Pro Display` 72pt Thin
- 窗口级别：`NSWindow.Level.floating`（保持在其他窗口上方）
- 无标题栏（`NSWindow.StyleMask.borderless`）

### 9.2 Menu Bar 图标

- 默认态：手形图标，线条风格，`NSImage` template（自动适配深色/浅色模式）
- 激活态：实心手形图标 + 绿色圆点
- 点击 Menu Bar 图标：弹出菜单
  - `Start / Stop`（对应当前状态）
  - `Quit AirMouse`

---

## 10. 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Option + Escape` | 立即结束当前 Session，回到 waiting_for_hand |

---

## 11. 分阶段计划

### Phase 1 — MVP（当前目标）

**目标**：核心功能跑通，开发者可用。

- [ ] Xcode 项目初始化（SwiftUI App，Menu Bar Extra）
- [ ] AVFoundation 相机采集
- [ ] Apple Vision 手部关键点识别（21点）
- [ ] Kalman 滤波（移植自 Python 版）
- [ ] PinchDetector：左键单击 + 拖拽
- [ ] ScrollDetector：右键单击 + 滚动 + 惯性
- [ ] FistDetector：握拳检测
- [ ] ROIManager：自适应 ROI，多显示器映射
- [ ] SessionController 状态机
- [ ] 标定窗口 UI（SwiftUI）
- [ ] Menu Bar 图标（默认态 + 激活态）
- [ ] `Option + Escape` 快捷键
- [ ] 握拳 3s 结束 Session（含倒计时 UI）
- [ ] CGEvent 鼠标控制（移动、点击、拖拽、滚动）
- [ ] 基本 Accessibility 权限检查

**不做**：设置面板、视觉打磨、权限引导流程、错误处理完善。

### Phase 2 — 可分发版本

**目标**：能发给别人用的 `.dmg`。

- [ ] 代码签名（Apple Developer 账号）
- [ ] Notarization（`notarytool`）
- [ ] DMG 打包脚本
- [ ] App 图标（1024×1024）
- [ ] 权限引导 UI（Camera + Accessibility）
- [ ] 异常处理（摄像头不可用、权限被拒等）
- [ ] 性能调优（目标：M 芯片上 < 5% CPU）
- [ ] 自动启动选项（Login Item）

### Phase 3 — 产品化（待定）

- [ ] 灵敏度调节设置面板
- [ ] 手势自定义
- [ ] 产品官网 + 下载页
- [ ] 用户反馈收集

---

## 12. 性能指标（目标）

| 指标 | 目标值 |
|------|--------|
| 端到端延迟（手势 → 鼠标响应） | < 30ms |
| CPU 占用（active 状态，M 芯片） | < 5% |
| 内存占用 | < 80MB |
| 帧率（Vision 处理） | 30fps |
| 首帧检测时间（手入画面 → 识别到） | < 100ms |

---

## 13. 已决策事项

| 问题 | 决策 |
|------|------|
| 技术路线 | Route C：全 Swift 原生重写 |
| 追踪框架 | Apple Vision Framework（ANE 加速） |
| 分发方式 | DMG，不上 App Store |
| 运行形态 | Menu Bar 常驻，无主窗口 |
| 多显示器策略 | combined bounding box + centroid 映射 |
| Session 结束方式 | 握拳 3s + Option+Escape |
| 标定后窗口 | 自动隐藏，结束时重现 |
| 目标硬件 | Apple Silicon only（M1 及以上） |
| iOS 支持 | 不在当前计划内 |
| Windows 支持 | 不在当前计划内 |
| App 名称 | **AirMouse**（已确认） |
| 标定抖动容忍 | 允许一定抖动，仅当手完全离开画面时才重置倒计时 |
| 摄像头选择 | 默认前置内置摄像头；合盖时选第一个可用设备；设置面板支持手动选择 |

---

## 14. 开放问题

- [x] App 名称最终确认 → AirMouse
- [x] 标定抖动处理 → 允许抖动，手完全离开画面才重置
- [x] 摄像头优先级 → 默认前置，合盖时第一可用，设置里可手选
- [ ] 握拳结束时鼠标是否应该跳回屏幕中心？
