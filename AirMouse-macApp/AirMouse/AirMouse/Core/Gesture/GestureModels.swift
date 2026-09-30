import CoreGraphics

/// Unified gesture action produced by detectors and consumed by MouseController.
enum GestureAction {
    case leftClick
    case dragBegin
    case dragEnd
    case rightClick
    case scroll(dx: Int, dy: Int)
    case scrollEnd
}
