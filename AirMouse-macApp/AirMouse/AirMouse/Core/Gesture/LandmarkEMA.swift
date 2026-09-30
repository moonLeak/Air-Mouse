import CoreGraphics
import Vision

/// Exponential Moving Average filter applied to the five hand landmarks that
/// are used for gesture-distance computation.
///
/// Formula (per joint, per axis):
///   smoothed[t] = α × raw[t] + (1 − α) × smoothed[t−1]
///
/// α = 0.5 balances noise suppression and responsiveness:
///   • Reduces Vision's ~±2% frame-to-frame jitter by ~50 %
///   • Introduces only ~1 frame of lag at 30 fps (≈ 33 ms)
///
/// Industry reference: EMA / low-pass pre-filtering of landmarks before
/// computing inter-joint distances is recommended by Google's MediaPipe team
/// for camera-only (RGB, no depth) gesture pipelines.
struct LandmarkEMA {

    let alpha: Double
    private(set) var initialized: Bool = false

    // Smoothed positions for the five gesture-critical joints.
    private var thumbTip:  CGPoint = .zero
    private var indexTip:  CGPoint = .zero
    private var middleTip: CGPoint = .zero
    private var indexMCP:  CGPoint = .zero
    private var littleMCP: CGPoint = .zero

    init(alpha: Double = 0.5) {
        self.alpha = alpha
    }

    /// Feed one raw frame; returns a copy of the input landmarks with the five
    /// gesture joints replaced by their EMA-smoothed values.
    mutating func update(_ lm: HandLandmarks) -> HandLandmarks {
        if !initialized {
            // Seed with the first frame so the first output is the raw value,
            // not a blend with zeros.
            thumbTip  = lm.thumbTip
            indexTip  = lm.indexTip
            middleTip = lm.middleTip
            indexMCP  = lm.indexMCP
            littleMCP = lm.littleMCP
            initialized = true
        } else {
            thumbTip  = blend(thumbTip,  lm.thumbTip)
            indexTip  = blend(indexTip,  lm.indexTip)
            middleTip = blend(middleTip, lm.middleTip)
            indexMCP  = blend(indexMCP,  lm.indexMCP)
            littleMCP = blend(littleMCP, lm.littleMCP)
        }

        // Build a new points dictionary with the smoothed values overlaid.
        var pts = lm.points
        pts[.thumbTip]  = thumbTip
        pts[.indexTip]  = indexTip
        pts[.middleTip] = middleTip
        pts[.indexMCP]  = indexMCP
        pts[.littleMCP] = littleMCP
        return HandLandmarks(points: pts)
    }

    /// Discard smoothed state.  Call when the hand leaves frame so stale values
    /// don't contaminate the first frame of the next appearance.
    mutating func reset() {
        initialized = false
    }

    // MARK: - Private

    private func blend(_ old: CGPoint, _ new: CGPoint) -> CGPoint {
        CGPoint(
            x: alpha * new.x + (1.0 - alpha) * old.x,
            y: alpha * new.y + (1.0 - alpha) * old.y
        )
    }
}
