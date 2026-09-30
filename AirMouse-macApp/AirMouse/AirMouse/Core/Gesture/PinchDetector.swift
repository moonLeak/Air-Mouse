import CoreGraphics
import Foundation

/// Detects thumb-index pinch gestures, distinguishing clicks from drags.
///
/// Uses palm-normalised absolute distance (thumbTip–indexTip / palmWidth) with
/// fixed hysteresis thresholds — no sliding-window baseline.  This eliminates
/// the "baseline drift" bug where a slow finger separation never crossed the
/// adaptive high-threshold and left the detector stuck in the pinched state.
///
/// Industry reference: same dual-threshold + hysteresis pattern used by
/// MediaPipe's gesture recogniser for camera-only (no depth) pinch detection.
class PinchDetector {

    // MARK: - Tunable parameters

    /// Fraction of palm width below which fingers are considered pinched.
    /// Enter-pinch threshold (the lower of the two — hysteresis).
    var closeThreshold: Double = 0.12

    /// Fraction of palm width above which fingers are considered open.
    /// Exit-pinch threshold (the higher of the two — hysteresis).
    var openThreshold: Double = 0.20

    /// How long fingers must stay pinched before switching from click → drag.
    var stabilityDuration: TimeInterval = 0.20

    // MARK: - Public state

    var isDragging: Bool { state == .dragging }

    // MARK: - Debug
    /// Set to true to print dist every frame — use for threshold calibration only.
    var debugLogging: Bool = true

    // MARK: - Private

    private enum State: Equatable {
        case idle
        case holding(startTime: Date)
        case dragging
    }

    private var state: State = .idle
    private var frameCount: Int = 0

    // MARK: - Update

    /// Process one frame.
    /// - Parameter palmNormDist: thumbTip–indexTip distance divided by palm width
    ///   (indexMCP–littleMCP).  Computed from EMA-smoothed landmarks.
    ///   Typical range: ~0.04–0.08 when pinched, ~0.30–0.50 when open.
    /// - Returns: A gesture action to execute, or nil.
    func update(palmNormDist: Double) -> GestureAction? {
        frameCount += 1
        if debugLogging {
            // Print every frame so you can see the full dist range during gestures.
            // Format: [PINCH] state dist=X.XXX  (copy a block of these and send to Claude)
            let stateTag: String
            switch state {
            case .idle:             stateTag = "idle   "
            case .holding:         stateTag = "holding"
            case .dragging:        stateTag = "drag   "
            }
            print("[PINCH-DBG] \(stateTag) dist=\(f(palmNormDist))")
        }

        switch state {
        case .idle:
            if palmNormDist < closeThreshold {
                print("[PinchDetector] idle → holding  dist=\(f(palmNormDist))")
                state = .holding(startTime: Date())
            }

        case .holding(let startTime):
            let elapsed = Date().timeIntervalSince(startTime)

            if palmNormDist > openThreshold {
                // Fingers opened before stability window → click
                if elapsed < stabilityDuration {
                    print("[PinchDetector] holding → idle (leftClick)  dist=\(f(palmNormDist)) elapsed=\(f(elapsed))s")
                    state = .idle
                    return .leftClick
                } else {
                    // Opened after stability window but never crossed the dragging
                    // transition (shouldn't normally happen, but handle it cleanly).
                    print("[PinchDetector] holding → idle (late open, no action)  dist=\(f(palmNormDist)) elapsed=\(f(elapsed))s")
                    state = .idle
                }
            } else if elapsed >= stabilityDuration {
                // Still pinched after stability duration → drag
                print("[PinchDetector] holding → dragging  elapsed=\(f(elapsed))s dist=\(f(palmNormDist))")
                state = .dragging
                return .dragBegin
            }

        case .dragging:
            if palmNormDist > openThreshold {
                print("[PinchDetector] dragging → idle (dragEnd)  dist=\(f(palmNormDist))")
                state = .idle
                return .dragEnd
            }
        }
        return nil
    }

    // MARK: - Reset

    func reset() {
        if state != .idle {
            print("[PinchDetector] reset() from state \(state)")
        }
        state = .idle
    }

    // MARK: - Helpers

    private func f(_ v: Double) -> String { String(format: "%.3f", v) }
}
