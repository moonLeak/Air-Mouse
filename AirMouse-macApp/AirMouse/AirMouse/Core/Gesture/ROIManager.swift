import AppKit
import CoreGraphics
import Foundation

/// Manages the adaptive Region of Interest within the camera frame
/// and maps normalized Vision coordinates to NSScreen coordinates.
/// Handles multi-display setups via combined screen bounding box.
class ROIManager {

    /// Speed multiplier from Settings (0.1–10.0).
    /// Standard ROI = 2.5 × palmWidth. Actual ROI = standardROI / speedMultiplier.
    /// Higher value → smaller ROI → faster cursor. Lower value → larger ROI → slower.
    var speedMultiplier: Double = 1.0

    /// Base ROI-to-palm scaling factor. ROI width = baseScale × palmWidth / speedMultiplier.
    let baseScale: Double = 2.5

    var edgePadding: Double = 0.05
    var smoothingBeta: Double = 0.25

    /// Aspect ratio of the actual camera frame (width / height).
    /// Must be set from CameraEngine.frameSize before the first begin() call.
    /// Default 4:3 covers most built-in Mac cameras until the real value arrives.
    var cameraAspectRatio: Double = 4.0 / 3.0

    private(set) var currentROI: CGRect?

    /// True when the ROI rectangle lies fully within the normalised [0,1]×[0,1] camera frame.
    /// Mirrors Python's _roi_fits() logic. When false the calibration countdown should pause
    /// and the ROI overlay should be hidden.
    private(set) var isValid: Bool = false

    private var smoothedCenter: CGPoint?
    private var smoothedSize: CGSize?

    private var combinedScreenRect: CGRect

    init() {
        combinedScreenRect = Self.combinedScreenRect()
    }

    // MARK: - ROI lifecycle

    /// Initialize ROI from the first hand frame.
    func begin(landmarks: HandLandmarks) {
        let (center, size) = computeROI(landmarks: landmarks)
        smoothedCenter = center
        smoothedSize = size
        updateCurrentROI()
    }

    /// Update ROI with new landmarks each frame (includes exponential smoothing).
    func update(landmarks: HandLandmarks) {
        guard let prevCenter = smoothedCenter,
              let prevSize = smoothedSize else {
            begin(landmarks: landmarks)
            return
        }

        let (newCenter, newSize) = computeROI(landmarks: landmarks)
        let beta = smoothingBeta

        smoothedCenter = CGPoint(
            x: prevCenter.x * (1 - beta) + newCenter.x * beta,
            y: prevCenter.y * (1 - beta) + newCenter.y * beta
        )
        smoothedSize = CGSize(
            width:  prevSize.width  * (1 - beta) + newSize.width  * beta,
            height: prevSize.height * (1 - beta) + newSize.height * beta
        )

        updateCurrentROI()
    }

    // MARK: - Coordinate mapping

    /// Map a normalized Vision point (origin bottom-left) to NSScreen coordinates.
    /// Returns nil if ROI has not been established.
    func mapToScreen(normalizedPoint: CGPoint) -> CGPoint? {
        guard let roi = currentROI, roi.width > 0, roi.height > 0 else {
            return nil
        }

        // Relative position within ROI, clamped
        var u = (normalizedPoint.x - roi.minX) / roi.width
        var v = (normalizedPoint.y - roi.minY) / roi.height
        u = min(1, max(0, u))
        v = min(1, max(0, v))

        // Edge compensation: allow reaching screen edges when hand is near ROI edge
        let pad = edgePadding
        u = ((u - pad) / (1.0 - 2 * pad)).clamped(to: 0...1)
        v = ((v - pad) / (1.0 - 2 * pad)).clamped(to: 0...1)

        return CGPoint(
            x: combinedScreenRect.minX + u * combinedScreenRect.width,
            y: combinedScreenRect.minY + v * combinedScreenRect.height
        )
    }

    /// Refresh screen layout (call when displays change).
    func updateScreenLayout() {
        combinedScreenRect = Self.combinedScreenRect()
    }

    func reset() {
        currentROI = nil
        smoothedCenter = nil
        smoothedSize = nil
        isValid = false
    }

    // MARK: - Multi-display (static helpers)

    /// Union bounding box of all connected NSScreen frames.
    static func combinedScreenRect() -> CGRect {
        let frames = NSScreen.screens.map { $0.frame }
        let minX = frames.map(\.minX).min() ?? 0
        let minY = frames.map(\.minY).min() ?? 0
        let maxX = frames.map(\.maxX).max() ?? 1920
        let maxY = frames.map(\.maxY).max() ?? 1080
        return CGRect(x: minX, y: minY,
                      width: maxX - minX, height: maxY - minY)
    }

    /// Convert from NSScreen coordinates (origin bottom-left) to CGEvent coordinates (origin top-left).
    static func toCGEventCoordinate(_ nsPoint: CGPoint) -> CGPoint {
        let mainHeight = NSScreen.screens.first?.frame.height ?? 1080
        return CGPoint(x: nsPoint.x, y: mainHeight - nsPoint.y)
    }

    // MARK: - Private

    private func computeROI(landmarks: HandLandmarks) -> (center: CGPoint, size: CGSize) {
        // Palm width reference: index MCP (5) → little MCP (17).
        // These knuckle points are stable (unlike fingertips) and scale with hand distance.
        let indexMCP  = landmarks.indexMCP
        let littleMCP = landmarks.littleMCP
        let palmWidth = hypot(indexMCP.x - littleMCP.x, indexMCP.y - littleMCP.y)

        // Standard ROI width = baseScale × palmWidth.
        // Actual ROI = standard / speedMultiplier:
        //   speedMultiplier > 1 → smaller ROI → faster cursor
        //   speedMultiplier < 1 → larger  ROI → slower cursor
        let standardWidth = baseScale * max(palmWidth, 0.01)
        let roiWidth = standardWidth / max(0.01, speedMultiplier)

        // The ROI must APPEAR as a screen-aspect-ratio rectangle when rendered on the
        // camera preview.  Vision normalised coords are relative to the camera frame, so
        // a unit square maps to cameraAspect:1 on screen.  To get a displayed aspect of
        // screenAspect we need: normalizedW / normalizedH * cameraAspect = screenAspect
        // => normalizedH = normalizedW * cameraAspect / screenAspect
        let screenAspect = combinedScreenRect.width / max(1, combinedScreenRect.height)
        let roiHeight = roiWidth * cameraAspectRatio / max(1e-6, screenAspect)

        print("[ROIManager] computeROI: palmWidth=\(String(format:"%.3f",palmWidth)) standard=\(String(format:"%.3f",standardWidth)) speed=\(speedMultiplier) roiW=\(String(format:"%.3f",roiWidth))")

        return (landmarks.palmCenter, CGSize(width: roiWidth, height: roiHeight))
    }

    private func updateCurrentROI() {
        guard let center = smoothedCenter, let size = smoothedSize else {
            if isValid { print("[ROIManager] isValid: true → false (no center/size)") }
            isValid = false
            return
        }
        let rect = CGRect(
            x: center.x - size.width / 2,
            y: center.y - size.height / 2,
            width: size.width,
            height: size.height
        )
        currentROI = rect
        let newValid = roiFitsNormalizedSpace(rect)
        if newValid != isValid {
            print("[ROIManager] isValid: \(isValid) → \(newValid) roi=\(rect.debugDescription)")
        }
        isValid = newValid
    }

    /// The redundancy fraction applied to each side of the ROI for the validity check.
    /// A value of 0.20 means the ROI must have at least 20% of its own width/height as
    /// clearance from every camera-frame edge.  This ensures the hand is still fully
    /// visible even when the palm centre reaches the ROI boundary.
    var redundancyFraction: Double = 0.20

    /// Returns true when the ROI rectangle — expanded by redundancyFraction on every side —
    /// still lies fully within [0,1]×[0,1].
    private func roiFitsNormalizedSpace(_ rect: CGRect) -> Bool {
        let dx = rect.width  * redundancyFraction
        let dy = rect.height * redundancyFraction
        return rect.minX - dx >= 0
            && rect.minY - dy >= 0
            && rect.maxX + dx <= 1
            && rect.maxY + dy <= 1
    }
}

private extension Comparable {
    func clamped(to limits: ClosedRange<Self>) -> Self {
        min(max(self, limits.lowerBound), limits.upperBound)
    }
}
