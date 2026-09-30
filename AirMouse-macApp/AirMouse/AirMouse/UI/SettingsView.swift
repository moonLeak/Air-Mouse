import SwiftUI

struct SettingsView: View {
    @ObservedObject private var settings = SettingsManager.shared

    var body: some View {
        Form {
            // MARK: Mouse
            Section {
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text("Cursor Sensitivity")
                        Spacer()
                        Text(String(format: "%.1f×", settings.mouseSpeedMultiplier))
                            .foregroundColor(.secondary)
                            .monospacedDigit()
                    }
                    Slider(value: $settings.mouseSpeedMultiplier, in: 0.1...10.0, step: 0.1)
                    Text("Higher = faster (smaller tracking area). Lower = slower (larger tracking area). 1.0 = standard (2.5× palm width).")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text("Scroll Speed")
                        Spacer()
                        Text(String(format: "%.1f×", settings.scrollSpeedMultiplier))
                            .foregroundColor(.secondary)
                            .monospacedDigit()
                    }
                    Slider(value: $settings.scrollSpeedMultiplier, in: 0.1...3.0, step: 0.1)
                    Text("Controls how fast the page scrolls per unit of hand movement.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            } header: {
                Text("Pointer & Scroll")
            }

            // MARK: Stop Gestures
            Section {
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text("Stop hold duration")
                        Spacer()
                        Text(String(format: "%.1f s", settings.stopHoldDuration))
                            .foregroundColor(.secondary)
                            .monospacedDigit()
                    }
                    Slider(value: $settings.stopHoldDuration, in: 1.0...5.0, step: 0.5)
                    Text("How long a stop gesture must be held before AirMouse stops.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                Toggle(isOn: $settings.pinkyPinchStopEnabled) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Thumb + Pinky pinch to Stop")
                        Text("Pinch thumb and little finger for the hold duration.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }

                Toggle(isOn: $settings.fistStopEnabled) {
                    VStack(alignment: .leading, spacing: 2) {
                        HStack(spacing: 6) {
                            Text("Fist to Stop")
                            Text("Experimental")
                                .font(.caption2)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(Color.orange.opacity(0.18))
                                .foregroundColor(.orange)
                                .clipShape(Capsule())
                        }
                        Text("Clenched fist for the hold duration. May trigger accidentally.")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
            } header: {
                Text("Stop Gestures")
            }
        }
        .formStyle(.grouped)
        .frame(width: 400)
        .fixedSize(horizontal: false, vertical: true)
        .padding(.bottom, 8)
    }
}

// MARK: - Settings Window Controller

class SettingsWindowController {
    private var window: NSWindow?

    func show() {
        if window == nil {
            let hosting = NSHostingController(rootView: SettingsView())
            let w = NSWindow(contentViewController: hosting)
            w.title = "AirMouse Settings"
            w.styleMask = [.titled, .closable]
            w.isReleasedWhenClosed = false
            w.center()
            window = w
        }
        NSApp.activate(ignoringOtherApps: true)
        window?.makeKeyAndOrderFront(nil)
    }
}
