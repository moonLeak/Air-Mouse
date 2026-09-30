import AppKit
import Combine
import SwiftUI
import Vision

// MARK: - Bone connections

private let boneConnections: [(VNHumanHandPoseObservation.JointName, VNHumanHandPoseObservation.JointName)] = [
    (.wrist, .thumbCMC),
    (.thumbCMC, .thumbMP),
    (.thumbMP, .thumbIP),
    (.thumbIP, .thumbTip),
    (.wrist, .indexMCP),
    (.indexMCP, .indexPIP),
    (.indexPIP, .indexDIP),
    (.indexDIP, .indexTip),
    (.wrist, .middleMCP),
    (.middleMCP, .middlePIP),
    (.middlePIP, .middleDIP),
    (.middleDIP, .middleTip),
    (.wrist, .ringMCP),
    (.ringMCP, .ringPIP),
    (.ringPIP, .ringDIP),
    (.ringDIP, .ringTip),
    (.wrist, .littleMCP),
    (.littleMCP, .littlePIP),
    (.littlePIP, .littleDIP),
    (.littleDIP, .littleTip),
]

// MARK: - Coordinate mapping helper

/// Computes the sub-rect (in view-local points) where the camera frame is actually
/// rendered when using AVLayerVideoGravity.resizeAspect inside a given view size.
/// Vision normalised coordinates [0,1]×[0,1] are relative to the full camera frame,
/// so we must map them into this sub-rect — not the full view — to avoid the offset
/// that occurs when the camera aspect ratio differs from the view aspect ratio.
///
/// - Parameters:
///   - frameSize:  Actual pixel dimensions of the CVPixelBuffer (e.g. 640×480).
///   - viewSize:   Current size of the SwiftUI view in points.
/// - Returns: A CGRect in view-local coordinates describing the visible image area.
func resizeAspectRect(frameSize: CGSize, viewSize: CGSize) -> CGRect {
    guard frameSize.width > 0, frameSize.height > 0,
          viewSize.width  > 0, viewSize.height > 0 else {
        return CGRect(origin: .zero, size: viewSize)
    }
    let frameAspect = frameSize.width  / frameSize.height
    let viewAspect  = viewSize.width   / viewSize.height

    let displayedW: CGFloat
    let displayedH: CGFloat
    if frameAspect > viewAspect {
        // Frame is wider → letterbox: black bars on top & bottom
        displayedW = viewSize.width
        displayedH = viewSize.width / frameAspect
    } else {
        // Frame is taller → pillarbox: black bars on left & right
        displayedH = viewSize.height
        displayedW = viewSize.height * frameAspect
    }
    let originX = (viewSize.width  - displayedW) / 2
    let originY = (viewSize.height - displayedH) / 2
    return CGRect(x: originX, y: originY, width: displayedW, height: displayedH)
}

/// Map a Vision normalised point (origin bottom-left, y-axis up) into view coordinates
/// taking letterboxing / pillarboxing into account.
func visionToView(_ p: CGPoint, displayRect: CGRect) -> CGPoint {
    CGPoint(
        x: displayRect.minX + p.x * displayRect.width,
        y: displayRect.minY + (1.0 - p.y) * displayRect.height   // flip Y
    )
}

// MARK: - Hand Skeleton Overlay

struct HandSkeletonOverlayView: View {
    let landmarks: HandLandmarks
    /// Actual camera frame size in pixels — needed for correct coordinate mapping.
    let frameSize: CGSize

    var body: some View {
        GeometryReader { geometry in
            let viewSize  = geometry.size
            let dispRect  = resizeAspectRect(frameSize: frameSize, viewSize: viewSize)

            // Bones
            Path { path in
                for (a, b) in boneConnections {
                    guard let pa = landmarks.points[a],
                          let pb = landmarks.points[b] else { continue }
                    path.move(to:    visionToView(pa, displayRect: dispRect))
                    path.addLine(to: visionToView(pb, displayRect: dispRect))
                }
            }
            .stroke(Color.white.opacity(0.75), lineWidth: 1.5)

            // Joints
            ForEach(Array(landmarks.points.keys), id: \.rawValue) { joint in
                if let pt = landmarks.points[joint] {
                    let mapped = visionToView(pt, displayRect: dispRect)
                    Circle()
                        .fill(Color.white.opacity(0.9))
                        .frame(width: 5, height: 5)
                        .position(x: mapped.x, y: mapped.y)
                }
            }
        }
    }
}

// MARK: - ROI Overlay

struct ROIOverlayView: View {
    /// ROI in Vision normalised coordinates [0,1]×[0,1].
    let roi: CGRect
    /// Actual camera frame size in pixels.
    let frameSize: CGSize
    /// True = ROI fully inside frame (including redundancy margin).
    let isValid: Bool
    /// True = calibration locked (ROI frozen); false = still tracking.
    let isLocked: Bool

    var body: some View {
        GeometryReader { geometry in
            let viewSize = geometry.size
            let dispRect = resizeAspectRect(frameSize: frameSize, viewSize: viewSize)

            // Map the ROI corners (Vision y-axis is bottom-up)
            let topLeft  = visionToView(CGPoint(x: roi.minX, y: roi.maxY), displayRect: dispRect)
            let topRight = visionToView(CGPoint(x: roi.maxX, y: roi.maxY), displayRect: dispRect)
            let botLeft  = visionToView(CGPoint(x: roi.minX, y: roi.minY), displayRect: dispRect)

            let viewROI = CGRect(
                x: topLeft.x,
                y: topLeft.y,
                width: topRight.x - topLeft.x,
                height: botLeft.y  - topLeft.y
            )

            // Consistent macOS rounded-rectangle border.
            // Corner radius scales with the shorter side for proportional appearance.
            let cornerRadius: CGFloat = min(viewROI.width, viewROI.height) * 0.06

            let strokeColor: Color = isValid
                ? .white
                : Color.orange.opacity(0.85)        // orange = redundancy margin clipped
            let lineWidth:   CGFloat = isLocked ? 2.0 : 1.5
            let opacity:     Double  = isLocked ? 1.0 : 0.75

            RoundedRectangle(cornerRadius: cornerRadius)
                .stroke(strokeColor.opacity(opacity), lineWidth: lineWidth)
                .frame(width: viewROI.width, height: viewROI.height)
                .position(x: viewROI.midX, y: viewROI.midY)
        }
    }
}

// MARK: - Info Bar

/// Bottom pill overlay: camera name on the left, live FPS on the right.
private struct InfoBarView: View {
    @ObservedObject var session: SessionController

    var body: some View {
        HStack(spacing: 8) {
            // Status dot: green when active, dim otherwise
            Circle()
                .fill(session.state == .active
                      ? Color.green
                      : Color.white.opacity(0.45))
                .frame(width: 6, height: 6)

            Text(session.selectedCameraName)
                .lineLimit(1)
                .truncationMode(.tail)

            Spacer()

            if session.fps > 0 {
                Text("\(session.fps) FPS")
                    .monospacedDigit()
                    .foregroundStyle(.white.opacity(0.7))
            }
        }
        .font(.system(size: 11, weight: .medium))
        .foregroundStyle(.white)
        .padding(.horizontal, 12)
        .padding(.vertical, 7)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 10))
    }
}

// MARK: - Camera Overlay View (always-on)

struct CameraOverlayView: View {
    @ObservedObject var session: SessionController

    var body: some View {
        ZStack {
            // ── Main camera stack (clipped with rounded corners) ──────────
            ZStack {
                // Layer 1: camera preview (or dark placeholder)
                Group {
                    if let engine = session.cameraEngine {
                        CameraPreviewView(previewLayer: engine.previewLayer)
                    } else {
                        Color.black.opacity(0.35)
                    }
                }

                // Layer 2: hand skeleton
                if let lm = session.latestLandmarks {
                    HandSkeletonOverlayView(
                        landmarks: lm,
                        frameSize: session.cameraEngine?.frameSize ?? CGSize(width: 640, height: 480)
                    )
                }

                // Layer 3: ROI rectangle
                if let roi = session.currentROI {
                    let isLocked = (session.state == .active)
                    ROIOverlayView(
                        roi: roi,
                        frameSize: session.cameraEngine?.frameSize ?? CGSize(width: 640, height: 480),
                        isValid: session.roiIsValid,
                        isLocked: isLocked
                    )
                }

                // Layer 4a: Gesture feedback label (top-right)
                if let label = session.gestureLabel {
                    VStack {
                        HStack {
                            Spacer()
                            Text(label)
                                .font(.system(size: 13, weight: .semibold, design: .rounded))
                                .foregroundColor(.white)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 6)
                                .background(.ultraThinMaterial, in: Capsule())
                                .padding(.top, 14)
                                .padding(.trailing, 14)
                        }
                        Spacer()
                    }
                    .transition(.opacity.animation(.easeInOut(duration: 0.2)))
                }

                // Layer 4b: Out-of-bounds warning pill (top)
                if session.currentROI != nil && !session.roiIsValid {
                    VStack {
                        HStack(spacing: 6) {
                            Image(systemName: "arrow.up.and.down.and.arrow.left.and.right")
                                .font(.system(size: 12, weight: .medium))
                            Text("Move hand toward center")
                                .font(.system(size: 13, weight: .medium))
                        }
                        .foregroundColor(.white)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 6)
                        .background(.ultraThinMaterial, in: Capsule())
                        .padding(.top, 14)
                        Spacer()
                    }
                }

                // Layer 5: Prompt text (above info bar)
                if !promptText.isEmpty {
                    VStack {
                        Spacer()
                        Text(promptText)
                            .font(.system(size: 14, weight: .regular))
                            .foregroundColor(.white)
                            .shadow(color: .black.opacity(0.6), radius: 3)
                            .padding(.bottom, 46) // clear the info bar
                    }
                }

                // Layer 6: Countdown (calibration or stop-gesture; stop takes priority)
                if let stopCd = session.stopHoldCountdown {
                    VStack(spacing: 4) {
                        Text("\(stopCd)")
                            .font(.system(size: 64, weight: .thin))
                            .foregroundColor(.orange)
                            .shadow(color: .black.opacity(0.6), radius: 6)
                        Text("Hold to stop")
                            .font(.system(size: 13, weight: .medium))
                            .foregroundColor(.orange.opacity(0.9))
                            .shadow(color: .black.opacity(0.5), radius: 2)
                    }
                } else if let cd = countdownValue {
                    Text("\(cd)")
                        .font(.system(size: 64, weight: .thin))
                        .foregroundColor(.white)
                        .shadow(color: .black.opacity(0.6), radius: 6)
                }

                // Layer 7: Camera disconnected overlay
                if session.cameraInterrupted {
                    ZStack {
                        Color.black.opacity(0.55)
                        VStack(spacing: 8) {
                            Image(systemName: "camera.fill.badge.ellipsis")
                                .font(.system(size: 32))
                                .foregroundColor(.white)
                            Text("Camera disconnected")
                                .font(.system(size: 14, weight: .medium))
                                .foregroundColor(.white)
                            Text("Reconnecting…")
                                .font(.system(size: 12))
                                .foregroundColor(.white.opacity(0.7))
                        }
                    }
                }

                // Layer 8: Info bar (bottom)
                VStack {
                    Spacer()
                    InfoBarView(session: session)
                        .padding(.horizontal, 10)
                        .padding(.bottom, 10)
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
        // Frosted glass fills any letterbox / pillarbox gaps and window corners.
        .background(.ultraThinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private var promptText: String {
        switch session.state {
        case .waitingForHand: return "Show your hand to the camera"
        case .calibrating:    return session.roiIsValid ? "Hold still — calibrating" : "Keep hand inside the frame"
        default:              return ""
        }
    }

    private var countdownValue: Int? {
        switch session.state {
        case .calibrating(let n): return n > 0 ? n : nil
        default:                  return nil
        }
    }
}

// MARK: - Aspect-ratio-locked NSWindow

/// NSWindow subclass that enforces a fixed content aspect ratio.
/// The user can freely resize but the proportions stay locked.
private class AspectRatioWindow: NSWindow {
    var lockedAspectRatio: CGFloat = 4.0 / 3.0   // default; updated once frame size is known

    override func constrainFrameRect(_ frameRect: NSRect, to screen: NSScreen?) -> NSRect {
        return super.constrainFrameRect(frameRect, to: screen)
    }
}

// MARK: - Camera Window Controller

class CameraWindowController: ObservableObject {

    private var window: AspectRatioWindow?
    private var cancellables = Set<AnyCancellable>()
    private weak var sessionRef: SessionController?

    /// Minimum window width in points.
    private let minWidth: CGFloat = 280

    func bind(to session: SessionController) {
        sessionRef = session

        session.$state
            .receive(on: DispatchQueue.main)
            .sink { [weak self] state in
                self?.updateVisibility(for: state, session: session)
            }
            .store(in: &cancellables)

        // Update aspect ratio whenever frame size changes.
        session.$cameraEngine
            .compactMap { $0 }
            .receive(on: DispatchQueue.main)
            .sink { [weak self] engine in
                // Poll until the frame size arrives (it's set on first frame).
                self?.scheduleAspectRatioUpdate(engine: engine)
            }
            .store(in: &cancellables)
    }

    // MARK: Visibility

    private func updateVisibility(for state: SessionState, session: SessionController) {
        switch state {
        case .idle:
            hide()
        default:
            show(session: session)
        }
    }

    // MARK: Show / Hide

    private func show(session: SessionController) {
        if window == nil {
            createWindow(session: session)
        }
        NSApp.activate(ignoringOtherApps: true)
        window?.makeKeyAndOrderFront(nil)
    }

    private func hide() {
        window?.orderOut(nil)
    }

    func close() {
        hide()
        window?.close()
        window = nil
    }

    // MARK: Window creation

    private func createWindow(session: SessionController) {
        let initialSize = NSSize(width: 1280, height: 720)
        let contentRect = NSRect(origin: .zero, size: initialSize)

        let win = AspectRatioWindow(
            contentRect: contentRect,
            styleMask: [.titled, .closable, .miniaturizable, .resizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        win.title = "AirMouse"
        win.titleVisibility = .hidden
        win.titlebarAppearsTransparent = true
        // Transparent backing so .ultraThinMaterial in the SwiftUI view blurs
        // whatever is behind the window (Liquid Glass effect).
        win.isOpaque = false
        win.backgroundColor = .clear
        win.hasShadow = true
        win.minSize = NSSize(width: minWidth, height: minWidth / win.lockedAspectRatio)

        // Lock aspect ratio via contentAspectRatio (NSWindow built-in).
        win.contentAspectRatio = initialSize

        let hosting = NSHostingController(rootView: CameraOverlayView(session: session))
        win.contentViewController = hosting
        win.center()

        window = win
    }

    // MARK: Aspect ratio update

    /// Polls for the actual frame size and updates the window's aspect ratio constraint.
    /// The frame size is only available after the first camera frame arrives.
    private func scheduleAspectRatioUpdate(engine: CameraEngine) {
        // Check immediately, then retry every 0.1 s for up to 3 s.
        var attempts = 0
        func attempt() {
            guard engine.frameSize != .zero else {
                attempts += 1
                guard attempts < 30 else { return }
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) { attempt() }
                return
            }
            self.applyAspectRatio(engine.frameSize)
        }
        attempt()
    }

    private func applyAspectRatio(_ size: CGSize) {
        guard size.width > 0, size.height > 0 else { return }
        let ratio = size.width / size.height
        window?.lockedAspectRatio = ratio
        window?.contentAspectRatio = NSSize(width: size.width, height: size.height)
        // Resize the window to match if it was created with a different ratio.
        if let win = window {
            let currentW = win.frame.width
            let newH = currentW / ratio
            var f = win.frame
            f.size.height = newH
            win.setFrame(f, display: true, animate: false)
            win.minSize = NSSize(width: minWidth, height: minWidth / ratio)
        }
        print("[AirMouse] CameraWindow: aspect ratio updated to \(size.width)×\(size.height)")
    }
}
