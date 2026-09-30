import AVFoundation
import SwiftUI

@main
struct AirMouseApp: App {
    @StateObject private var session: SessionController
    @StateObject private var cameraWindow: CameraWindowController
    private let settingsWindow = SettingsWindowController()

    init() {
        let sessionCtrl = SessionController()
        _session = StateObject(wrappedValue: sessionCtrl)

        let windowCtrl = CameraWindowController()
        _cameraWindow = StateObject(wrappedValue: windowCtrl)
        windowCtrl.bind(to: sessionCtrl)
    }

    var body: some Scene {
        MenuBarExtra {
            MenuBarMenuView(session: session, settingsWindow: settingsWindow)
        } label: {
            Image(systemName: session.state == .active
                  ? "hand.raised.fill"
                  : "hand.raised")
        }
        .menuBarExtraStyle(.menu)
    }
}

// MARK: - Menu Bar Menu

struct MenuBarMenuView: View {
    @ObservedObject var session: SessionController
    let settingsWindow: SettingsWindowController

    var body: some View {
        Group {
            Text(statusText)
                .foregroundColor(.secondary)

            Divider()

            Button(session.isActive ? "Stop AirMouse" : "Start AirMouse") {
                if session.isActive {
                    session.stopSession()
                } else {
                    session.startSession()
                }
            }

            Divider()

            Menu("Camera") {
                ForEach(availableCameras, id: \.uniqueID) { cam in
                    Button(action: {
                        session.selectPreferredCamera(uniqueID: cam.uniqueID)
                    }) {
                        if cam.uniqueID == session.selectedCameraID {
                            Label(cam.localizedName, systemImage: "checkmark")
                        } else {
                            Text(cam.localizedName)
                        }
                    }
                }
            }

            Button("Settings…") {
                settingsWindow.show()
            }

            Divider()

            Button("Quit AirMouse") {
                NSApp.terminate(nil)
            }
            .keyboardShortcut("q")
        }
    }

    private var statusText: String {
        switch session.state {
        case .idle:               return "AirMouse — Idle"
        case .waitingForHand:     return "AirMouse — Waiting for hand"
        case .calibrating(let n): return "AirMouse — Calibrating (\(n))"
        case .active:             return "AirMouse — Active"
        }
    }

    private var availableCameras: [AVCaptureDevice] {
        if #available(macOS 14.0, *) {
            return AVCaptureDevice.DiscoverySession(
                deviceTypes: [.builtInWideAngleCamera, .external],
                mediaType: .video,
                position: .unspecified
            ).devices.filter { $0.isConnected }
        } else {
            return AVCaptureDevice.DiscoverySession(
                deviceTypes: [.builtInWideAngleCamera],
                mediaType: .video,
                position: .unspecified
            ).devices.filter { $0.isConnected }
        }
    }
}
