# AirMouse App — macOS / iOS

> 基于现有 Python AirMouse 核心逻辑，面向 Apple 平台的原生 App 项目。

## 目录结构

```
AirMouse-App/
├── macos/        macOS 应用（SwiftUI / AppKit）
├── ios/          iOS 应用（SwiftUI）
├── shared/       macOS 与 iOS 共用的业务逻辑（Swift Package）
└── docs/         设计文档、原型图、技术方案
```

## 开发计划（待定）

- [ ] 技术选型：Vision framework vs. MediaPipe for iOS
- [ ] 核心手势识别移植（捏合点击、滚动、拖拽）
- [ ] ROI 判定框 & 卡尔曼滤波平滑移植
- [ ] macOS 鼠标控制（CGEvent / Accessibility API）
- [ ] iOS 触控板模拟（外接设备 or 系统扩展）
- [ ] GUI 控制面板（SwiftUI）
- [ ] TestFlight / Mac App Store 发布配置

## 参考

- 核心 Python 实现：`../AirMouse/`
- 历史版本参考：`../开发历史/`
