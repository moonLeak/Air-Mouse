import CoreGraphics
import Foundation
import Vision

/// Detects a clenched fist by checking curl ratio of all four fingers.
/// A fist held continuously for `SettingsManager.shared.stopHoldDuration` signals stop.
class FistDetector {

    /// Live-reads the shared stop-hold duration so UI changes take effect immediately.
    var requiredDuration: TimeInterval { SettingsManager.shared.stopHoldDuration }

    private var fistStartTime: Date?

    /// Returns the elapsed time since fist was first detected (nil if not currently a fist).
    func update(landmarks: HandLandmarks) -> TimeInterval? {
        if isFist(landmarks: landmarks) {
            if fistStartTime == nil { fistStartTime = Date() }
            return Date().timeIntervalSince(fistStartTime!)
        } else {
            fistStartTime = nil
            return nil
        }
    }

    func reset() {
        fistStartTime = nil
    }

    // MARK: - Private

    private let curlThreshold: Double = 0.5

    private func isFist(landmarks: HandLandmarks) -> Bool {
        let fingers: [(tip: CGPoint, mcp: CGPoint)] = [
            (landmarks.indexTip,  landmarks.indexMCP),
            (landmarks.middleTip, landmarks.middleMCP),
            (landmarks.points[.ringTip]   ?? .zero, landmarks.ringMCP),
            (landmarks.points[.littleTip] ?? .zero, landmarks.littleMCP),
        ]

        for finger in fingers {
            let tipToMCP  = hypot(finger.tip.x - finger.mcp.x, finger.tip.y - finger.mcp.y)
            let mcpToWrist = hypot(finger.mcp.x - landmarks.wrist.x, finger.mcp.y - landmarks.wrist.y)
            if mcpToWrist < 0.001 { continue }
            if tipToMCP / mcpToWrist >= curlThreshold { return false }
        }
        return true
    }
}
