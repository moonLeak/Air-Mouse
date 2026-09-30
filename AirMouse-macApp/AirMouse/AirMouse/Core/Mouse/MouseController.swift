import AppKit
import CoreGraphics

/// Encapsulates CGEvent mouse operations.
/// All event posting must happen on the main thread — the caller is responsible.
class MouseController {

    private var currentPosition: CGPoint = .zero
    private var isDragging: Bool = false

    // MARK: - Mouse movement

    func moveTo(_ point: CGPoint) {
        currentPosition = point
        // While dragging, macOS requires .leftMouseDragged so that the dragged
        // object follows the cursor continuously.  Using .mouseMoved during a drag
        // causes items to jump only at release — the classic "discontinuous drag" bug.
        let eventType: CGEventType = isDragging ? .leftMouseDragged : .mouseMoved
        let event = CGEvent(mouseEventSource: nil,
                            mouseType: eventType,
                            mouseCursorPosition: point,
                            mouseButton: .left)
        event?.post(tap: .cghidEventTap)
    }

    // MARK: - Left click / drag

    func leftClick() {
        postMouseEvent(.leftMouseDown)
        postMouseEvent(.leftMouseUp)
    }

    func dragBegin() {
        isDragging = true
        postMouseEvent(.leftMouseDown)
    }

    func dragEnd() {
        guard isDragging else { return }  // don't post mouseUp at (0,0) if never dragging
        isDragging = false
        postMouseEvent(.leftMouseUp)
    }

    // MARK: - Right click

    func rightClick() {
        postMouseEvent(.rightMouseDown)
        postMouseEvent(.rightMouseUp)
    }

    // MARK: - Scroll

    func scroll(dx: Int, dy: Int) {
        let event = CGEvent(scrollWheelEvent2Source: nil,
                            units: .pixel,
                            wheelCount: 2,
                            wheel1: Int32(dy),
                            wheel2: Int32(dx),
                            wheel3: 0)
        event?.post(tap: .cghidEventTap)
    }

    // MARK: - Accessibility

    static func checkAccessibility() -> Bool {
        return AXIsProcessTrusted()
    }

    static func requestAccessibility() {
        let options = [kAXTrustedCheckOptionPrompt.takeRetainedValue() as String: true]
        AXIsProcessTrustedWithOptions(options as CFDictionary)
    }

    // MARK: - Private

    private func postMouseEvent(_ type: CGEventType) {
        let isRightButton = type == .rightMouseDown || type == .rightMouseUp
        let event = CGEvent(mouseEventSource: nil,
                            mouseType: type,
                            mouseCursorPosition: currentPosition,
                            mouseButton: isRightButton ? .right : .left)
        event?.post(tap: .cghidEventTap)
    }
}
