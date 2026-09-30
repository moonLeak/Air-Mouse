import Cocoa

// Minimal AppKit app with frosted glass window that launches the Python AirMouse as a subprocess.

final class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var logTextView: NSTextView!
    var startButton: NSButton!
    var stopButton: NSButton!
    var statusField: NSTextField!

    private var task: Process?
    private var outputPipe: Pipe?

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.appearance = NSAppearance(named: .vibrantLight)
        buildWindow()
        updateButtons(running: false)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return true
    }

    private func buildWindow() {
        let contentRect = NSRect(x: 0, y: 0, width: 520, height: 360)
        window = NSWindow(contentRect: contentRect,
                          styleMask: [.titled, .fullSizeContentView, .closable, .miniaturizable],
                          backing: .buffered,
                          defer: false)
        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
        window.isOpaque = false
        window.backgroundColor = .clear
        window.center()

        // Frosted glass background
        let visualEffect = NSVisualEffectView(frame: contentRect)
        visualEffect.material = .hudWindow // nice subtle blur
        visualEffect.blendingMode = .behindWindow
        visualEffect.state = .active
        visualEffect.wantsLayer = true
        visualEffect.layer?.cornerRadius = 14
        visualEffect.layer?.masksToBounds = true
        window.contentView = visualEffect

        let content = NSView()
        content.translatesAutoresizingMaskIntoConstraints = false
        visualEffect.addSubview(content)
        NSLayoutConstraint.activate([
            content.leadingAnchor.constraint(equalTo: visualEffect.leadingAnchor, constant: 16),
            content.trailingAnchor.constraint(equalTo: visualEffect.trailingAnchor, constant: -16),
            content.topAnchor.constraint(equalTo: visualEffect.topAnchor, constant: 16),
            content.bottomAnchor.constraint(equalTo: visualEffect.bottomAnchor, constant: -16)
        ])

        // Controls row
        let controls = NSStackView()
        controls.orientation = .horizontal
        controls.alignment = .centerY
        controls.spacing = 8
        controls.translatesAutoresizingMaskIntoConstraints = false

        startButton = NSButton(title: "Start", target: self, action: #selector(startTapped))
        startButton.bezelStyle = .rounded

        stopButton = NSButton(title: "Stop", target: self, action: #selector(stopTapped))
        stopButton.bezelStyle = .rounded

        let openLogBtn = NSButton(title: "Open Settings", target: self, action: #selector(openSettings))
        openLogBtn.bezelStyle = .rounded

        statusField = NSTextField(labelWithString: "Ready")
        statusField.textColor = .labelColor

        controls.addArrangedSubview(startButton)
        controls.addArrangedSubview(stopButton)
        controls.addArrangedSubview(NSView()) // spacer
        controls.addArrangedSubview(openLogBtn)
        controls.addArrangedSubview(statusField)

        content.addSubview(controls)
        NSLayoutConstraint.activate([
            controls.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            controls.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            controls.topAnchor.constraint(equalTo: content.topAnchor)
        ])

        // Log view
        let scrollView = NSScrollView()
        scrollView.translatesAutoresizingMaskIntoConstraints = false
        scrollView.drawsBackground = false
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = false

        logTextView = NSTextView()
        logTextView.isEditable = false
        logTextView.drawsBackground = false
        logTextView.textColor = .labelColor
        logTextView.font = .monospacedSystemFont(ofSize: 12, weight: .regular)
        scrollView.documentView = logTextView

        content.addSubview(scrollView)
        NSLayoutConstraint.activate([
            scrollView.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            scrollView.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            scrollView.topAnchor.constraint(equalTo: controls.bottomAnchor, constant: 12),
            scrollView.bottomAnchor.constraint(equalTo: content.bottomAnchor)
        ])

        window.makeKeyAndOrderFront(nil)
    }

    @objc private func startTapped() {
        // If already running, restart
        if task?.isRunning == true {
            stopProcess(forceKillAfter: 2.0)
        }
        startProcess()
    }

    @objc private func stopTapped() {
        stopProcess(forceKillAfter: 2.0)
    }

    @objc private func openSettings() {
        // Opens the JSON settings used by the Python GUI in the default editor
        let path = (FileManager.default.homeDirectoryForCurrentUser as NSURL).appendingPathComponent(".airmouse_gui_settings.json")!.path
        NSWorkspace.shared.openFile(path)
    }

    private func startProcess() {
        guard task == nil || task?.isRunning == false else { return }

        let task = Process()
        let pipe = Pipe()
        outputPipe = pipe

        // Determine repo root: the .app bundle is sitting inside the repo.
        let bundleURL = Bundle.main.bundleURL // .../AirMouse.app
        let repoURL = bundleURL.deletingLastPathComponent() // folder containing .app
        task.currentDirectoryURL = repoURL

        // Pick python interpreter preference order: venv311, venv, system python3
        let fm = FileManager.default
        let candidates = [
            repoURL.appendingPathComponent("venv311/bin/python", isDirectory: false),
            repoURL.appendingPathComponent("venv/bin/python", isDirectory: false)
        ]
        var pythonPath: String = "/usr/bin/env"
        var args: [String] = ["python3", "-m", "airmouse"]
        for url in candidates {
            if fm.isExecutableFile(atPath: url.path) {
                pythonPath = url.path
                args = ["-m", "airmouse"]
                break
            }
        }
        task.launchPath = pythonPath
        task.arguments = args
        task.standardOutput = pipe
        task.standardError = pipe

        // Inherit environment, add a couple of helpful defaults and user settings
        var env = ProcessInfo.processInfo.environment
        env["MEDIAPIPE_DISABLE_GPU"] = env["MEDIAPIPE_DISABLE_GPU"] ?? "1"
        // Load optional settings from ~/.airmouse_gui_settings.json and map to env vars
        for (k, v) in loadEnvFromSettingsJSON() {
            env[k] = v
        }
        task.environment = env

        // Pipe -> text view
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let str = String(data: data, encoding: .utf8) else { return }
            DispatchQueue.main.async {
                self?.appendLog(str)
            }
        }

        do {
            try task.run()
            self.task = task
            updateButtons(running: true)
            setStatus("Running")
            appendLog("Launching AirMouse...\n")
        } catch {
            appendLog("Failed to start AirMouse: \(error.localizedDescription)\n")
            updateButtons(running: false)
            setStatus("Error")
        }

        // Observe exit
        DispatchQueue.global().async { [weak self] in
            task.waitUntilExit()
            DispatchQueue.main.async {
                self?.appendLog("AirMouse exited (code: \(task.terminationStatus)).\n")
                self?.updateButtons(running: false)
                self?.setStatus("Ready")
                self?.outputPipe?.fileHandleForReading.readabilityHandler = nil
                self?.task = nil
            }
        }
    }

    private func stopProcess(forceKillAfter: TimeInterval) {
        guard let t = task else { return }
        appendLog("Stopping AirMouse...\n")
        if t.isRunning {
            t.terminate()
            DispatchQueue.global().asyncAfter(deadline: .now() + forceKillAfter) { [weak self] in
                guard let self, let t = self.task else { return }
                if t.isRunning {
                    self.appendLog("Force killing AirMouse.\n")
                    t.interrupt()
                    t.terminate() // double-terminate; will be ignored if already exited
                }
            }
        }
    }

    private func updateButtons(running: Bool) {
        startButton.title = running ? "Restart" : "Start"
        stopButton.isEnabled = running
    }

    private func setStatus(_ text: String) {
        statusField.stringValue = text
    }

    private func appendLog(_ text: String) {
        let wasAtEnd = logTextView.enclosingScrollView?.verticalScroller?.floatValue ?? 1.0 > 0.99
        let attr = NSAttributedString(string: text, attributes: [
            .foregroundColor: NSColor.labelColor,
            .font: NSFont.monospacedSystemFont(ofSize: 12, weight: .regular)
        ])
        logTextView.textStorage?.append(attr)
        if wasAtEnd {
            logTextView.scrollToEndOfDocument(nil)
        }
    }
}


// MARK: - Settings JSON bridge
extension AppDelegate {
    // Map settings JSON (if present) to AIRMOUSE_* environment variables expected by the Python app.
    fileprivate func loadEnvFromSettingsJSON() -> [String: String] {
        var result: [String: String] = [:]
        let url = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".airmouse_gui_settings.json")
        guard let data = try? Data(contentsOf: url),
              let raw = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return result
        }

        func set(_ key: String, _ value: Any?, transform: (Any) -> String) {
            if let v = value { result[key] = transform(v) }
        }
        func boolEnv(_ any: Any) -> String { (any as? Bool ?? false) ? "true" : "false" }
        func strEnv(_ any: Any) -> String { String(describing: any) }

        set("AIRMOUSE_CAMERA_INDEX", raw["camera_index"], transform: strEnv)
        set("AIRMOUSE_FRAME_SCALE", raw["frame_scale"], transform: strEnv)
        set("AIRMOUSE_MIRROR_HORIZONTAL", raw["mirror_horizontal"], transform: boolEnv)
        set("AIRMOUSE_MIRROR_VERTICAL", raw["mirror_vertical"], transform: boolEnv)
        set("AIRMOUSE_ROI_EDGE_PADDING", raw["roi_edge_padding"], transform: strEnv)
        set("AIRMOUSE_ROI_COUNTDOWN_SECONDS", raw["roi_entry_countdown"], transform: strEnv)
        set("AIRMOUSE_ROI_EXIT_COUNTDOWN", raw["roi_exit_countdown"], transform: strEnv)
        set("AIRMOUSE_ROI_AUTO_RESET", raw["roi_auto_reset"], transform: boolEnv)

        set("AIRMOUSE_MONITOR_ENABLED", raw["monitor_enabled"], transform: boolEnv)
        set("AIRMOUSE_MONITOR_SHOW_CAMERA", raw["monitor_camera"], transform: boolEnv)
        set("AIRMOUSE_MONITOR_SHOW_GRAPH", raw["monitor_graph"], transform: boolEnv)
        set("AIRMOUSE_MONITOR_DRAW_SKELETON", raw["monitor_skeleton"], transform: boolEnv)
        set("AIRMOUSE_MONITOR_DRAW_ANCHOR", raw["monitor_anchor"], transform: boolEnv)

        set("AIRMOUSE_PINCH_MARGIN", raw["pinch_margin"], transform: strEnv)
        set("AIRMOUSE_PINCH_STABILITY", raw["pinch_stability"], transform: strEnv)
        set("AIRMOUSE_SCROLL_SPEED_FACTOR", raw["scroll_speed_factor"], transform: strEnv)
        set("AIRMOUSE_SCROLL_SMOOTHNESS", raw["scroll_smoothness"], transform: strEnv)
        return result
    }
}
@main
struct Main {
    static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.delegate = delegate
        app.setActivationPolicy(.regular)
        app.activate(ignoringOtherApps: true)
        app.run()
    }
}
