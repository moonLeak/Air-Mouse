import Combine
import Foundation

class SettingsManager: ObservableObject {
    static let shared = SettingsManager()

    // MARK: - Camera

    var preferredCameraID: String? {
        get { UserDefaults.standard.string(forKey: "preferredCameraID") }
        set { UserDefaults.standard.set(newValue, forKey: "preferredCameraID") }
    }

    // MARK: - Mouse movement speed
    /// Speed multiplier that controls ROI size.  ROI = 2.5 × palmWidth / mouseSpeedMultiplier.
    /// Higher → smaller ROI → faster cursor.  Lower → larger ROI → slower cursor.
    /// Range 0.1 – 10.0; default 1.0 (standard ROI).
    @Published var mouseSpeedMultiplier: Double {
        didSet { UserDefaults.standard.set(mouseSpeedMultiplier, forKey: "mouseSpeedMultiplier") }
    }

    // MARK: - Scroll speed
    /// Multiplier for ScrollDetector.speedFactor.
    /// Range 0.1 – 2.0; default 1.0.
    @Published var scrollSpeedMultiplier: Double {
        didSet { UserDefaults.standard.set(scrollSpeedMultiplier, forKey: "scrollSpeedMultiplier") }
    }

    // MARK: - Stop gestures

    /// Whether the fist-hold gesture can trigger Stop. Default off (high false-positive rate).
    @Published var fistStopEnabled: Bool {
        didSet { UserDefaults.standard.set(fistStopEnabled, forKey: "fistStopEnabled") }
    }

    /// Whether the thumb+pinky pinch gesture can trigger Stop.
    @Published var pinkyPinchStopEnabled: Bool {
        didSet { UserDefaults.standard.set(pinkyPinchStopEnabled, forKey: "pinkyPinchStopEnabled") }
    }

    /// Seconds a stop gesture must be held continuously before triggering Stop.
    /// Applies to both fist and pinky-pinch. Default 3 s.
    @Published var stopHoldDuration: Double {
        didSet { UserDefaults.standard.set(stopHoldDuration, forKey: "stopHoldDuration") }
    }

    // MARK: - Init

    private init() {
        let ud = UserDefaults.standard
        mouseSpeedMultiplier  = ud.object(forKey: "mouseSpeedMultiplier")  as? Double ?? 1.0
        scrollSpeedMultiplier = ud.object(forKey: "scrollSpeedMultiplier") as? Double ?? 1.0
        fistStopEnabled       = ud.object(forKey: "fistStopEnabled")       as? Bool   ?? false
        pinkyPinchStopEnabled = ud.object(forKey: "pinkyPinchStopEnabled") as? Bool   ?? true
        stopHoldDuration      = ud.object(forKey: "stopHoldDuration")      as? Double ?? 3.0
    }
}
