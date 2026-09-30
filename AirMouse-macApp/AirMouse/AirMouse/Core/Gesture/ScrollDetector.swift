import CoreGraphics
import Foundation

/// Detects thumb-middle pinch gestures, distinguishing right-click from scroll,
/// with inertia decay after pinch release.
///
/// Uses palm-normalised absolute distance (thumbTip–middleTip / palmWidth) with
/// fixed hysteresis thresholds — no sliding-window baseline.  Same pattern as
/// PinchDetector; see that file for rationale.
class ScrollDetector {

    // MARK: - Tunable parameters

    /// Fraction of palm width below which fingers are considered pinched.
    var closeThreshold: Double = 0.12

    /// Fraction of palm width above which fingers are considered open.
    var openThreshold: Double = 0.20

    /// Hold duration that separates right-click (short) from scroll (long).
    var stabilityDuration: TimeInterval = 0.20

    /// Pixels of cursor movement that immediately start scrolling (skips right-click window).
    var stabilityRadius: Double = 30.0

    /// Scroll delta multiplier per pixel of hand movement.
    var speedFactor: Double = 0.35

    /// Inertia velocity decay per frame.
    var decayFactor: Double = 0.8

    // MARK: - Debug
    /// Set to true to print dist every frame — use for threshold calibration only.
    var debugLogging: Bool = true

    // MARK: - Private

    private enum State: Equatable {
        case idle
        case holding(startTime: Date, anchor: CGPoint)
        case scrolling(scrollAnchor: CGPoint)
        case inertia(velocity: CGPoint)
    }

    private var state: State = .idle

    // MARK: - Update

    /// Process one frame. Returns zero or more gesture actions triggered this frame.
    /// - Parameters:
    ///   - palmNormDist: thumbTip–middleTip distance divided by palm width.
    ///   - screenPoint: current cursor position in screen coordinates.
    func update(palmNormDist: Double,
                screenPoint: CGPoint) -> [GestureAction] {
        if debugLogging {
            let stateTag: String
            switch state {
            case .idle:             stateTag = "idle    "
            case .holding:         stateTag = "holding "
            case .scrolling:       stateTag = "scroll  "
            case .inertia:         stateTag = "inertia "
            }
            print("[SCROLL-DBG] \(stateTag) dist=\(f(palmNormDist))")
        }

        switch state {
        case .idle:
            if palmNormDist < closeThreshold {
                print("[ScrollDetector] idle → holding  dist=\(f(palmNormDist))")
                state = .holding(startTime: Date(), anchor: screenPoint)
            }

        case .holding(let startTime, let anchor):
            let elapsed = Date().timeIntervalSince(startTime)
            let moved = hypot(screenPoint.x - anchor.x, screenPoint.y - anchor.y)

            if palmNormDist > openThreshold {
                if elapsed < stabilityDuration {
                    // Short pinch → right-click
                    print("[ScrollDetector] holding → idle (rightClick)  dist=\(f(palmNormDist)) elapsed=\(f(elapsed))s")
                    state = .idle
                    return [.rightClick]
                } else {
                    // Opened after the stability window without scrolling — clean exit
                    print("[ScrollDetector] holding → idle (late open, no action)  dist=\(f(palmNormDist)) elapsed=\(f(elapsed))s")
                    state = .idle
                }
            } else if elapsed >= stabilityDuration || moved > stabilityRadius {
                // Long hold or significant movement → start scrolling
                print("[ScrollDetector] holding → scrolling  elapsed=\(f(elapsed))s moved=\(String(format:"%.1f",moved))pt")
                state = .scrolling(scrollAnchor: screenPoint)
            }

        case .scrolling(let scrollAnchor):
            if palmNormDist > openThreshold {
                // Fingers opened → transition to inertia.
                // Do NOT emit .scrollEnd here — inertia frames still emit .scroll,
                // which would re-set isScrolling=true in SessionController.
                // .scrollEnd is emitted when inertia truly settles (see below).
                let delta = CGPoint(
                    x: (scrollAnchor.x - screenPoint.x) * speedFactor,
                    y: (scrollAnchor.y - screenPoint.y) * speedFactor
                )
                print("[ScrollDetector] scrolling → inertia  dist=\(f(palmNormDist))")
                state = .inertia(velocity: delta)
                return []   // no scrollEnd yet — still in momentum phase
            }
            // Still scrolling — emit delta and advance anchor
            let delta = CGPoint(
                x: (scrollAnchor.x - screenPoint.x) * speedFactor,
                y: (scrollAnchor.y - screenPoint.y) * speedFactor
            )
            state = .scrolling(scrollAnchor: screenPoint)
            return [.scroll(dx: Int(-delta.x), dy: Int(-delta.y))]

        case .inertia(var velocity):
            velocity.x *= decayFactor
            velocity.y *= decayFactor
            if abs(velocity.x) < 1 && abs(velocity.y) < 1 {
                // Momentum fully decayed — NOW emit scrollEnd so isScrolling is cleared.
                print("[ScrollDetector] inertia → idle (settled, scrollEnd)")
                state = .idle
                return [.scrollEnd]
            }
            state = .inertia(velocity: velocity)
            return [.scroll(dx: Int(-velocity.x), dy: Int(-velocity.y))]
        }
        return []
    }

    // MARK: - Reset

    func reset() {
        if state != .idle {
            print("[ScrollDetector] reset() from state \(state)")
        }
        state = .idle
    }

    // MARK: - Helpers

    private func f(_ v: Double) -> String { String(format: "%.3f", v) }
}
