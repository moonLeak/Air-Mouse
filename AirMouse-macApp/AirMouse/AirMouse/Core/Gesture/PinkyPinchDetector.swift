import CoreGraphics
import Foundation
import Vision

/// Detects a thumb-tip + little-finger-tip pinch held continuously for
/// `SettingsManager.shared.stopHoldDuration` seconds, then signals stop.
///
/// Normalized distance = distance(thumbTip, littleTip) / distance(wrist, littleMCP).
/// The wrist→littleMCP span is a robust proxy for hand scale.
class PinkyPinchDetector {

    /// Below this normalized ratio the thumb and little finger are considered pinched.
    private let pinchThreshold: Double = 0.75

    private var pinchStartTime: Date?

    // MARK: - Update

    /// Call once per hand-tracking frame.
    /// - Returns: seconds the pinch has been continuously held, or nil if not pinching.
    func update(landmarks: HandLandmarks) -> TimeInterval? {
        if isPinching(landmarks: landmarks) {
            if pinchStartTime == nil { pinchStartTime = Date() }
            return Date().timeIntervalSince(pinchStartTime!)
        } else {
            pinchStartTime = nil
            return nil
        }
    }

    func reset() {
        pinchStartTime = nil
    }

    // MARK: - Private

    private func isPinching(landmarks: HandLandmarks) -> Bool {
        let thumbTip  = landmarks.thumbTip
        let littleTip = landmarks.points[.littleTip] ?? .zero

        // If littleTip wasn't detected with sufficient confidence, skip.
        if littleTip == .zero { return false }

        // Reference: wrist → littleMCP (palm-width proxy, always available).
        let refDist = hypot(landmarks.wrist.x - landmarks.littleMCP.x,
                            landmarks.wrist.y - landmarks.littleMCP.y)
        guard refDist > 1e-6 else { return false }

        let tipDist = hypot(thumbTip.x - littleTip.x,
                            thumbTip.y - littleTip.y)
        return tipDist / refDist < pinchThreshold
    }
}
