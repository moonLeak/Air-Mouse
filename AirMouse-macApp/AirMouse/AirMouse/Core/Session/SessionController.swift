import AppKit
import AVFoundation
import Combine
import CoreGraphics
import Foundation

// MARK: - Session State

enum SessionState: Equatable {
    case idle
    case waitingForHand
    case calibrating(countdown: Int)
    case active
}

// MARK: - SessionController

@MainActor
class SessionController: ObservableObject {

    @Published var state: SessionState = .idle
    @Published var latestLandmarks: HandLandmarks?
    @Published var cameraEngine: CameraEngine?
    /// uniqueID of the camera that is currently (or was last) in use. Drives the checkmark in the Camera menu.
    @Published private(set) var selectedCameraID: String?
    /// Localised display name of the active camera (shown in the info bar).
    @Published private(set) var selectedCameraName: String = "Camera"
    /// Whether the current ROI lies fully within the camera frame. Used by the UI to grey out the ROI box.
    @Published private(set) var roiIsValid: Bool = false
    /// The current (possibly locked) ROI in normalised [0,1]×[0,1] coordinates.
    @Published private(set) var currentROI: CGRect? = nil
    /// Live frames-per-second, updated every second. Zero when idle.
    @Published private(set) var fps: Int = 0
    /// Remaining seconds until stop gesture fires (nil = no stop gesture active).
    @Published private(set) var stopHoldCountdown: Int? = nil
    /// Brief gesture label shown on the camera preview ("Click", "Dragging", "Scrolling").
    @Published private(set) var gestureLabel: String? = nil
    /// True while the camera session is interrupted (e.g. Continuity Camera disconnected).
    @Published private(set) var cameraInterrupted: Bool = false

    private let mouseController = MouseController()
    private let handTracker = HandTracker()
    private let roiManager = ROIManager()
    private let kalmanFilter = KalmanFilter2D()
    private let pinchDetector = PinchDetector()
    private let scrollDetector = ScrollDetector()
    private let fistDetector = FistDetector()
    private let pinkyPinchDetector = PinkyPinchDetector()

    // Calibration timing
    private var calibrationAccumulatedTime: TimeInterval = 0   // only counts valid (in-bounds) frames
    private var lastValidFrameTime: Date?                       // timestamp of the previous valid frame

    // FPS tracking
    private var fpsFrameCount: Int = 0
    private var fpsLastTime: Date = Date()

    // Gesture exclusivity
    /// True while a scroll gesture is in progress. Blocks click/drag detection.
    private var isScrolling: Bool = false

    // EMA landmark smoother — applied before computing gesture distances
    private var emaLandmarks = LandmarkEMA(alpha: 0.5)

    // Speed tracking
    private var lastScreenPoint: CGPoint = .zero
    private var lastFrameTime: Date = Date()

    // Hotkey
    private var hotkeyMonitor: Any?

    var isActive: Bool { state != .idle }

    /// Select a camera immediately: updates the checkmark in the menu right away,
    /// and saves the preference for the next session start.
    func selectPreferredCamera(uniqueID: String) {
        SettingsManager.shared.preferredCameraID = uniqueID
        selectedCameraID = uniqueID
        print("[AirMouse] selectPreferredCamera: saved '\(uniqueID)'")
    }

    init() {
        // IMPORTANT: Do NOT create CameraEngine here.
        // AVCaptureDeviceInput(device:) — called inside CameraEngine.setupSession() — triggers
        // a TCC access check. If called before requestAccess() shows the permission dialog,
        // macOS silently marks the permission as "denied", making it impossible to recover
        // without the user manually toggling the switch in System Settings.
        //
        // Instead we only enumerate devices (safe, no TCC trigger) to save the default
        // camera preference and set selectedCameraID for the menu checkmark.
        if let device = CameraEngine.selectCamera() {
            print("[AirMouse] SessionController.init: default camera '\(device.localizedName)'")
            if SettingsManager.shared.preferredCameraID == nil {
                SettingsManager.shared.preferredCameraID = device.uniqueID
                print("[AirMouse] SessionController.init: saved default camera preference")
            }
            selectedCameraID = device.uniqueID
            // CameraEngine is created later in startSession(), after permission is confirmed.
        } else {
            print("[AirMouse] SessionController.init: no camera found")
        }
    }

    // MARK: - Public lifecycle

    func startSession() {
        // Step 1: camera authorization
        let camStatus = AVCaptureDevice.authorizationStatus(for: .video)
        print("[AirMouse] startSession: camera auth status = \(camStatus.rawValue)")
        switch camStatus {
        case .notDetermined:
            print("[AirMouse] startSession: requesting camera permission...")
            // LSUIElement=YES (background agent) prevents TCC dialogs from appearing.
            // Temporarily switch to .regular so the system dialog has a UI context.
            NSApp.setActivationPolicy(.regular)
            NSApp.activate(ignoringOtherApps: true)
            AVCaptureDevice.requestAccess(for: .video) { [weak self] granted in
                print("[AirMouse] requestAccess callback: granted=\(granted)")
                Task { @MainActor [weak self] in
                    NSApp.setActivationPolicy(.accessory)
                    if granted {
                        self?.startSession()
                    } else {
                        // Dialog was suppressed (e.g. Xcode debug context) — fall back to
                        // opening System Settings so the user can grant manually, then
                        // click Start again.
                        print("[AirMouse] startSession: dialog suppressed — opening System Settings")
                        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera") {
                            NSWorkspace.shared.open(url)
                        }
                    }
                }
            }
            return
        case .denied, .restricted:
            print("[AirMouse] startSession: camera permission denied — opening System Settings")
            if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Camera") {
                NSWorkspace.shared.open(url)
            }
            return
        case .authorized:
            print("[AirMouse] startSession: camera authorized")
        @unknown default:
            break
        }

        // Step 2: accessibility
        print("[AirMouse] startSession: checking accessibility...")
        if !MouseController.checkAccessibility() {
            print("[AirMouse] startSession: accessibility not granted, requesting...")
            MouseController.requestAccessibility()
            return
        }
        print("[AirMouse] startSession: accessibility OK")

        // Step 3: Always recreate CameraEngine so camera preference changes take effect immediately
        guard let device = CameraEngine.selectCamera() else {
            print("[AirMouse] startSession: no camera available — cannot start")
            return
        }
        print("[AirMouse] startSession: (re)creating CameraEngine for '\(device.localizedName)'")
        let isMirrored = !CameraEngine.isContinuityCamera(device)
        do {
            let engine = try CameraEngine(device: device, isMirrored: isMirrored)
            engine.delegate = self
            cameraEngine = engine
            selectedCameraID = device.uniqueID
            selectedCameraName = device.localizedName
            print("[AirMouse] startSession: CameraEngine created OK, isMirrored=\(isMirrored)")
        } catch {
            print("[AirMouse] startSession: CameraEngine init failed: \(error)")
            return
        }

        // Apply current settings values before starting.
        applySettings()

        // Start synchronously so the preview layer has a running session before we show the window
        cameraEngine?.start()
        print("[AirMouse] startSession: engine.start() completed")

        registerHotkey()
        transitionTo(.waitingForHand)
        print("[AirMouse] startSession: transitioned to waitingForHand")
    }

    func stopSession() {
        print("[AirMouse] stopSession: called")
        cameraEngine?.stop()
        cameraEngine = nil   // release old engine so a new one is created on next start
        unregisterHotkey()
        resetAllDetectors()
        mouseController.dragEnd()
        roiManager.reset()
        latestLandmarks = nil
        currentROI = nil
        roiIsValid = false
        calibrationAccumulatedTime = 0
        lastValidFrameTime = nil
        fps = 0
        fpsFrameCount = 0
        stopHoldCountdown = nil
        gestureLabel = nil
        transitionTo(.idle)
        print("[AirMouse] stopSession: transitioned to idle")
    }

    /// Option+Escape or fist-completed: return to waitingForHand
    func endSession() {
        mouseController.dragEnd()
        resetAllDetectors()
        roiManager.reset()
        latestLandmarks = nil
        currentROI = nil
        roiIsValid = false
        calibrationAccumulatedTime = 0
        lastValidFrameTime = nil
        transitionTo(.waitingForHand)
    }

    // MARK: - Frame processing

    private func onHandFrame(landmarks raw: HandLandmarks?, timestamp: Date) {
        // FPS counter — updated once per second.
        fpsFrameCount += 1
        let fpsElapsed = timestamp.timeIntervalSince(fpsLastTime)
        if fpsElapsed >= 1.0 {
            fps = Int((Double(fpsFrameCount) / fpsElapsed).rounded())
            fpsFrameCount = 0
            fpsLastTime = timestamp
        }

        // Apply horizontal mirror for front-facing cameras so hand movement matches screen direction.
        let landmarks = (cameraEngine?.isMirrored == true) ? raw?.mirroredHorizontally() : raw
        switch state {

        case .idle:
            break

        case .waitingForHand:
            guard let lm = landmarks else { return }
            print("[AirMouse] onHandFrame: hand detected → starting calibration, palmCenter=(\(lm.palmCenter.x), \(lm.palmCenter.y))")
            latestLandmarks = lm
            roiManager.begin(landmarks: lm)
            calibrationAccumulatedTime = 0
            lastValidFrameTime = nil
            currentROI = roiManager.isValid ? roiManager.currentROI : nil
            roiIsValid = roiManager.isValid
            transitionTo(.calibrating(countdown: 3))

        case .calibrating:
            guard let lm = landmarks else {
                // Hand lost — reset countdown entirely
                calibrationAccumulatedTime = 0
                lastValidFrameTime = nil
                roiManager.reset()
                latestLandmarks = nil
                currentROI = nil
                roiIsValid = false
                transitionTo(.waitingForHand)
                return
            }
            latestLandmarks = lm
            roiManager.update(landmarks: lm)
            currentROI = roiManager.isValid ? roiManager.currentROI : nil
            roiIsValid = roiManager.isValid

            // Only advance the countdown while the ROI is fully inside the camera frame.
            let now = timestamp
            if roiManager.isValid {
                if let last = lastValidFrameTime {
                    calibrationAccumulatedTime += now.timeIntervalSince(last)
                }
                lastValidFrameTime = now
            } else {
                // ROI out of bounds — reset the entire countdown so the user must
                // hold the ROI inside the frame for a full 3 s on the next attempt.
                if calibrationAccumulatedTime > 0 {
                    print("[AirMouse] calibration: ROI left frame — resetting countdown")
                }
                calibrationAccumulatedTime = 0
                lastValidFrameTime = nil
            }

            let remaining = max(0, 3 - Int(calibrationAccumulatedTime))
            if calibrationAccumulatedTime >= 3.0 {
                enterActive()
            } else {
                transitionTo(.calibrating(countdown: remaining))
            }

        case .active:
            guard let lm = landmarks else {
                // Hand lost — pause detectors, keep active (do NOT reset ROI)
                pinchDetector.reset()
                scrollDetector.reset()
                fistDetector.reset()
                pinkyPinchDetector.reset()
                isScrolling = false       // reset scroll flag so click works after hand re-enters
                emaLandmarks.reset()      // discard stale EMA state so first new frame starts fresh
                latestLandmarks = nil
                return
            }
            latestLandmarks = lm
            // NOTE: roiManager.update() is intentionally NOT called here.
            // The ROI is locked after calibration. Continuous updating causes the ROI to
            // chase the hand, making the mapped screen position always drift back to center.
            // Keep published ROI in sync (it was set in enterActive but may not have published yet).
            if currentROI == nil { currentROI = roiManager.currentROI }

            guard let nsPoint = roiManager.mapToScreen(normalizedPoint: lm.palmCenter) else { return }
            let cgPoint = ROIManager.toCGEventCoordinate(nsPoint)
            let smoothed = kalmanFilter.update(point: cgPoint)

            mouseController.moveTo(smoothed)

            _ = calculateSpeed(from: smoothed)

            // EMA-smooth the gesture-critical landmarks to remove Vision frame noise,
            // then compute palm-normalised absolute distances.
            let sLm = emaLandmarks.update(lm)
            let pn48  = palmNorm48(sLm)
            let pn412 = palmNorm412(sLm)

            // Gesture exclusivity:
            // • While scrolling  → skip click/drag detection entirely.
            // • While dragging   → skip scroll detection entirely.
            let currentlyDragging = pinchDetector.isDragging

            if !isScrolling {
                if let action = pinchDetector.update(palmNormDist: pn48) {
                    handleAction(action)
                }
            } else {
                print("[AirMouse] gesture: skipping pinch (scrolling in progress)")
            }

            if !currentlyDragging {
                for action in scrollDetector.update(palmNormDist: pn412,
                                                    screenPoint: smoothed) {
                    handleAction(action)
                }
            } else {
                print("[AirMouse] gesture: skipping scroll (dragging in progress)")
            }

            // Stop gestures: each fires stopSession() if held for stopHoldDuration.
            let holdRequired = SettingsManager.shared.stopHoldDuration
            var stopHoldActive = false

            if SettingsManager.shared.fistStopEnabled {
                if let fistDuration = fistDetector.update(landmarks: lm) {
                    stopHoldActive = true
                    let remaining = max(1, Int(ceil(holdRequired - fistDuration)))
                    stopHoldCountdown = remaining
                    if fistDuration.truncatingRemainder(dividingBy: 0.5) < 0.05 {
                        print("[AirMouse] stop-fist: holding \(String(format:"%.1f",fistDuration))s / \(holdRequired)s countdown=\(remaining)")
                    }
                    if fistDuration >= holdRequired {
                        print("[AirMouse] stop-fist: triggered → stopSession()")
                        stopSession()
                        return
                    }
                }
            }

            if SettingsManager.shared.pinkyPinchStopEnabled {
                if let pinchDuration = pinkyPinchDetector.update(landmarks: lm) {
                    stopHoldActive = true
                    let remaining = max(1, Int(ceil(holdRequired - pinchDuration)))
                    stopHoldCountdown = remaining
                    if pinchDuration.truncatingRemainder(dividingBy: 0.5) < 0.05 {
                        print("[AirMouse] stop-pinkyPinch: holding \(String(format:"%.1f",pinchDuration))s / \(holdRequired)s countdown=\(remaining)")
                    }
                    if pinchDuration >= holdRequired {
                        print("[AirMouse] stop-pinkyPinch: triggered → stopSession()")
                        stopSession()
                        return
                    }
                }
            }

            // Clear countdown when no stop gesture is held this frame.
            if !stopHoldActive && stopHoldCountdown != nil {
                stopHoldCountdown = nil
            }
        }
    }

    // MARK: - State transitions

    private func enterActive() {
        // Publish the now-locked ROI so the overlay can freeze it.
        currentROI = roiManager.currentROI
        roiIsValid = true

        // Jump mouse to screen center
        let combinedRect = ROIManager.combinedScreenRect()
        let center = combinedRect.center
        let cgCenter = ROIManager.toCGEventCoordinate(center)
        let mainHeight = NSScreen.screens.first?.frame.height ?? 0
        print("[AirMouse] enterActive: combinedScreenRect=\(combinedRect), mainHeight=\(mainHeight)")
        print("[AirMouse] enterActive: nsCenter=\(center) → cgCenter=\(cgCenter)")
        mouseController.moveTo(cgCenter)
        kalmanFilter.reset(to: cgCenter)
        lastScreenPoint = cgCenter
        lastFrameTime = Date()

        transitionTo(.active)
    }

    private func transitionTo(_ newState: SessionState) {
        state = newState
    }

    // MARK: - Hotkey

    private func registerHotkey() {
        hotkeyMonitor = NSEvent.addGlobalMonitorForEvents(matching: .keyDown) { [weak self] event in
            guard event.modifierFlags.contains(.option),
                  event.keyCode == 53 /* Escape */ else { return }
            Task { @MainActor in
                self?.endSession()
            }
        }
    }

    private func unregisterHotkey() {
        if let monitor = hotkeyMonitor {
            NSEvent.removeMonitor(monitor)
            hotkeyMonitor = nil
        }
    }

    // MARK: - Action dispatch

    private func handleAction(_ action: GestureAction) {
        switch action {
        case .leftClick:
            print("[AirMouse] action: leftClick")
            mouseController.leftClick()
            gestureLabel = "Click"
            // Auto-clear after 0.6 s
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { [weak self] in
                if self?.gestureLabel == "Click" { self?.gestureLabel = nil }
            }
        case .dragBegin:
            print("[AirMouse] action: dragBegin")
            mouseController.dragBegin()
            gestureLabel = "Dragging"
        case .dragEnd:
            print("[AirMouse] action: dragEnd")
            mouseController.dragEnd()
            gestureLabel = nil
        case .rightClick:
            print("[AirMouse] action: rightClick")
            mouseController.rightClick()
            gestureLabel = "Right Click"
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { [weak self] in
                if self?.gestureLabel == "Right Click" { self?.gestureLabel = nil }
            }
        case .scroll(let dx, let dy):
            if !isScrolling {
                print("[AirMouse] action: scroll start")
                gestureLabel = "Scrolling"
            }
            isScrolling = true
            mouseController.scroll(dx: dx, dy: dy)
        case .scrollEnd:
            print("[AirMouse] action: scrollEnd → isScrolling=false")
            isScrolling = false
            if gestureLabel == "Scrolling" { gestureLabel = nil }
        }
    }

    private func resetAllDetectors() {
        pinchDetector.reset()
        scrollDetector.reset()
        fistDetector.reset()
        pinkyPinchDetector.reset()
        isScrolling = false
        emaLandmarks.reset()
    }

    /// Apply values from SettingsManager to the detectors / ROI manager.
    func applySettings() {
        let s = SettingsManager.shared
        // Speed multiplier: ROI = baseScale × palmWidth / speedMultiplier
        roiManager.speedMultiplier = s.mouseSpeedMultiplier
        // Base scroll speed factor is 0.35; scale by user's scroll speed preference.
        scrollDetector.speedFactor = 0.35 * s.scrollSpeedMultiplier
    }

    // MARK: - Palm-normalised distances
    //
    // Both functions use the palm width (indexMCP → littleMCP in Vision space) as the
    // normalisation reference.  This automatically scales with hand size AND distance
    // from the camera, giving a stable absolute metric independent of zoom level.
    //
    // Typical values:
    //   pinched  → ~0.04 – 0.10
    //   open     → ~0.30 – 0.50

    /// Thumb-tip to index-tip distance, divided by palm width.  Used by PinchDetector.
    private func palmNorm48(_ lm: HandLandmarks) -> Double {
        let raw  = hypot(lm.thumbTip.x - lm.indexTip.x,  lm.thumbTip.y - lm.indexTip.y)
        let palm = hypot(lm.indexMCP.x  - lm.littleMCP.x, lm.indexMCP.y  - lm.littleMCP.y)
        guard palm > 1e-6 else { return 1.0 }
        return raw / palm
    }

    /// Thumb-tip to middle-tip distance, divided by palm width.  Used by ScrollDetector.
    private func palmNorm412(_ lm: HandLandmarks) -> Double {
        let raw  = hypot(lm.thumbTip.x - lm.middleTip.x,  lm.thumbTip.y - lm.middleTip.y)
        let palm = hypot(lm.indexMCP.x  - lm.littleMCP.x,  lm.indexMCP.y  - lm.littleMCP.y)
        guard palm > 1e-6 else { return 1.0 }
        return raw / palm
    }

    // MARK: - Speed

    private func calculateSpeed(from point: CGPoint) -> Double {
        let now = Date()
        let dt = max(0.001, now.timeIntervalSince(lastFrameTime))
        let speed = hypot(point.x - lastScreenPoint.x, point.y - lastScreenPoint.y) / dt
        lastScreenPoint = point
        lastFrameTime = now
        return speed
    }
}

// MARK: - CameraEngineDelegate

extension SessionController: CameraEngineDelegate {
    private nonisolated(unsafe) static var delegateFrameCount: Int = 0

    nonisolated func cameraEngine(_ engine: CameraEngine,
                                   didOutput pixelBuffer: CVPixelBuffer,
                                   timestamp: CMTime) {
        let landmarks = handTracker.process(pixelBuffer: pixelBuffer)
        let frameSize = engine.frameSize
        Self.delegateFrameCount += 1
        if Self.delegateFrameCount % 120 == 1 {
            let hasHand = landmarks != nil
            print("[AirMouse] delegate: frame #\(Self.delegateFrameCount), handDetected=\(hasHand), frameSize=\(frameSize)")
        }
        Task { @MainActor [weak self] in
            guard let self else { return }
            // Keep ROIManager's camera aspect ratio in sync with the actual frame.
            if frameSize.width > 0 && frameSize.height > 0 {
                let aspect = frameSize.width / frameSize.height
                if abs(self.roiManager.cameraAspectRatio - aspect) > 0.01 {
                    self.roiManager.cameraAspectRatio = aspect
                }
            }
            self.onHandFrame(landmarks: landmarks, timestamp: Date())
        }
    }

    nonisolated func cameraEngineWasInterrupted(_ engine: CameraEngine) {
        Task { @MainActor [weak self] in
            print("[AirMouse] SessionController: camera interrupted → showing overlay")
            self?.cameraInterrupted = true
        }
    }

    nonisolated func cameraEngineInterruptionEnded(_ engine: CameraEngine) {
        Task { @MainActor [weak self] in
            print("[AirMouse] SessionController: camera interruption ended → hiding overlay")
            self?.cameraInterrupted = false
        }
    }
}

// MARK: - CGRect center helper

private extension CGRect {
    var center: CGPoint {
        CGPoint(x: midX, y: midY)
    }
}
