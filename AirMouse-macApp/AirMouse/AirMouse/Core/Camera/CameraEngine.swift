import AVFoundation

enum CameraError: Error {
    case cannotAddInput
    case cannotAddOutput
}

protocol CameraEngineDelegate: AnyObject {
    func cameraEngine(_ engine: CameraEngine,
                      didOutput pixelBuffer: CVPixelBuffer,
                      timestamp: CMTime)
    /// Called when the camera session is interrupted (e.g. phone camera disconnected).
    func cameraEngineWasInterrupted(_ engine: CameraEngine)
    /// Called when the camera session interruption ends and streaming resumes.
    func cameraEngineInterruptionEnded(_ engine: CameraEngine)
}

class CameraEngine: NSObject {

    weak var delegate: CameraEngineDelegate?

    /// Whether this camera should be horizontally mirrored (true for built-in FaceTime HD).
    let isMirrored: Bool

    /// Actual pixel buffer dimensions reported by the first received frame.
    /// Defaults to CGSize.zero until the first frame arrives.
    private(set) var frameSize: CGSize = .zero

    private let cameraQueue = DispatchQueue(label: "com.airmouse.camera", qos: .userInteractive)
    private(set) var session: AVCaptureSession!
    private var output: AVCaptureVideoDataOutput!
    private var preview: AVCaptureVideoPreviewLayer!

    // MARK: - Camera classification

    /// Returns true if the device is an iPhone/iPad Continuity Camera (not a built-in Mac camera).
    static func isContinuityCamera(_ d: AVCaptureDevice) -> Bool {
        if #available(macOS 14.0, *) {
            return d.deviceType == .continuityCamera
        }
        // macOS 13: continuity cameras appear as builtInWideAngle — detect by name
        let name = d.localizedName.lowercased()
        return name.contains("iphone") || name.contains("ipad")
    }

    // MARK: - Camera selection

    static func selectCamera() -> AVCaptureDevice? {
        // Build device type list (macOS-version-safe)
        var deviceTypes: [AVCaptureDevice.DeviceType] = [.builtInWideAngleCamera]
        if #available(macOS 14.0, *) {
            deviceTypes += [.external, .continuityCamera]
        }

        let allDevices = AVCaptureDevice.DiscoverySession(
            deviceTypes: deviceTypes,
            mediaType: .video,
            position: .unspecified
        ).devices.filter { $0.isConnected }

        print("[AirMouse] selectCamera: found \(allDevices.count) device(s): \(allDevices.map { $0.localizedName })")

        // 1. Preferred device from settings (respects explicit user selection)
        if let savedID = SettingsManager.shared.preferredCameraID,
           let device = allDevices.first(where: { $0.uniqueID == savedID }) {
            print("[AirMouse] selectCamera: using settings-preferred '\(device.localizedName)'")
            return device
        }

        // 2. First non-continuity camera (built-in FaceTime HD, USB webcam, etc.)
        if let builtIn = allDevices.first(where: { !isContinuityCamera($0) }) {
            print("[AirMouse] selectCamera: using built-in '\(builtIn.localizedName)'")
            return builtIn
        }

        // 3. Last resort: continuity camera (iPhone) if nothing else is available
        if let any = allDevices.first {
            print("[AirMouse] selectCamera: fallback to '\(any.localizedName)' (no built-in found)")
            return any
        }

        print("[AirMouse] selectCamera: no camera found")
        return nil
    }

    // MARK: - Lifecycle

    init(device: AVCaptureDevice, isMirrored: Bool = false) throws {
        self.isMirrored = isMirrored
        print("[AirMouse] CameraEngine.init: device=\(device.localizedName), connected=\(device.isConnected), isMirrored=\(isMirrored)")
        print("[AirMouse] CameraEngine.init: camera authStatus=\(AVCaptureDevice.authorizationStatus(for: .video).rawValue) (0=notDet,1=restricted,2=denied,3=authorized)")
        super.init()
        do {
            try setupSession(device: device)
            print("[AirMouse] CameraEngine.init: setupSession completed OK")
        } catch {
            print("[AirMouse] CameraEngine.init: setupSession threw error: \(error)")
            throw error
        }
        registerSessionNotifications()
    }

    var previewLayer: AVCaptureVideoPreviewLayer {
        if preview == nil {
            preview = AVCaptureVideoPreviewLayer(session: session)
            preview.videoGravity = .resizeAspect   // Fix hand offset: use full frame without cropping
            // Mirror the preview for front-facing cameras so the image is not reversed.
            if isMirrored {
                preview.connection?.automaticallyAdjustsVideoMirroring = false
                preview.connection?.isVideoMirrored = true
            }
        }
        return preview
    }

    func start() {
        print("[AirMouse] CameraEngine.start: starting session synchronously...")
        cameraQueue.sync { [weak self] in
            guard let self = self else { return }
            print("[AirMouse] CameraEngine.start: calling session.startRunning()...")
            self.session.startRunning()
            print("[AirMouse] CameraEngine.start: started, isRunning=\(self.session.isRunning)")
            if !self.session.isRunning {
                print("[AirMouse] CameraEngine.start: ⚠️ isRunning=false after startRunning — check runtimeError notification above for the cause")
            }
        }
    }

    func stop() {
        print("[AirMouse] CameraEngine.stop: dispatching stopRunning...")
        cameraQueue.async { [weak self] in
            guard let self = self else { return }
            print("[AirMouse] CameraEngine.stop: calling session.stopRunning(), isRunning=\(self.session.isRunning)")
            self.session.stopRunning()
            print("[AirMouse] CameraEngine.stop: stopped, isRunning=\(self.session.isRunning)")
        }
    }

    // MARK: - Session Notifications

    private func registerSessionNotifications() {
        let nc = NotificationCenter.default

        nc.addObserver(self,
                       selector: #selector(sessionDidStartRunning(_:)),
                       name: .AVCaptureSessionDidStartRunning,
                       object: session)

        nc.addObserver(self,
                       selector: #selector(sessionDidStopRunning(_:)),
                       name: .AVCaptureSessionDidStopRunning,
                       object: session)

        nc.addObserver(self,
                       selector: #selector(sessionRuntimeError(_:)),
                       name: .AVCaptureSessionRuntimeError,
                       object: session)

        nc.addObserver(self,
                       selector: #selector(sessionWasInterrupted(_:)),
                       name: .AVCaptureSessionWasInterrupted,
                       object: session)

        nc.addObserver(self,
                       selector: #selector(sessionInterruptionEnded(_:)),
                       name: .AVCaptureSessionInterruptionEnded,
                       object: session)

        print("[AirMouse] CameraEngine: session notifications registered")
    }

    @objc private func sessionDidStartRunning(_ notification: Notification) {
        print("[AirMouse] ✅ AVCaptureSession DID START RUNNING")
    }

    @objc private func sessionDidStopRunning(_ notification: Notification) {
        print("[AirMouse] ⏹ AVCaptureSession DID STOP RUNNING")
    }

    @objc private func sessionRuntimeError(_ notification: Notification) {
        if let error = notification.userInfo?[AVCaptureSessionErrorKey] as? AVError {
            print("[AirMouse] ❌ SESSION RUNTIME ERROR code=\(error.code.rawValue): \(error.localizedDescription)")
            print("[AirMouse] ❌ Error userInfo: \(error.errorUserInfo)")
            if error.code == .operationNotAllowed {
                print("[AirMouse] ❌ → operationNotAllowed: Camera TCC permission may not be fully granted for this bundle")
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) { [weak self] in
                guard let self = self else { return }
                print("[AirMouse] Attempting session restart after runtime error...")
                self.cameraQueue.async {
                    self.session.startRunning()
                    print("[AirMouse] Restart attempt: isRunning=\(self.session.isRunning)")
                }
            }
        } else {
            print("[AirMouse] ❌ SESSION RUNTIME ERROR (non-AVError): \(notification.userInfo ?? [:])")
        }
    }

    @objc private func sessionWasInterrupted(_ notification: Notification) {
        print("[AirMouse] ⚠️ SESSION INTERRUPTED userInfo=\(notification.userInfo ?? [:]) — likely another app took the camera, or Continuity Camera disconnected")
        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }
            self.delegate?.cameraEngineWasInterrupted(self)
        }
    }

    @objc private func sessionInterruptionEnded(_ notification: Notification) {
        print("[AirMouse] ✅ SESSION INTERRUPTION ENDED — restarting...")
        cameraQueue.async { [weak self] in
            self?.session.startRunning()
        }
        DispatchQueue.main.async { [weak self] in
            guard let self = self else { return }
            self.delegate?.cameraEngineInterruptionEnded(self)
        }
    }

    deinit {
        NotificationCenter.default.removeObserver(self)
        print("[AirMouse] CameraEngine deinit")
    }

    // MARK: - Setup

    private func setupSession(device: AVCaptureDevice) throws {
        print("[AirMouse] CameraEngine.setupSession: starting...")
        session = AVCaptureSession()
        session.sessionPreset = .vga640x480
        print("[AirMouse] CameraEngine.setupSession: session created with preset vga640x480")

        let input = try AVCaptureDeviceInput(device: device)
        print("[AirMouse] CameraEngine.setupSession: AVCaptureDeviceInput created OK")
        guard session.canAddInput(input) else {
            print("[AirMouse] CameraEngine.setupSession: cannotAddInput")
            throw CameraError.cannotAddInput
        }
        session.addInput(input)
        print("[AirMouse] CameraEngine.setupSession: input added to session")

        output = AVCaptureVideoDataOutput()
        output.videoSettings = [
            kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA
        ]
        output.alwaysDiscardsLateVideoFrames = true
        output.setSampleBufferDelegate(self, queue: cameraQueue)
        print("[AirMouse] CameraEngine.setupSession: output configured")

        guard session.canAddOutput(output) else {
            print("[AirMouse] CameraEngine.setupSession: cannotAddOutput")
            throw CameraError.cannotAddOutput
        }
        session.addOutput(output)
        print("[AirMouse] CameraEngine.setupSession: output added, setup complete")
    }
}

// MARK: - AVCaptureVideoDataOutputSampleBufferDelegate

extension CameraEngine: AVCaptureVideoDataOutputSampleBufferDelegate {
    private static var frameCount: Int = 0

    func captureOutput(_ output: AVCaptureOutput,
                       didOutput sampleBuffer: CMSampleBuffer,
                       from connection: AVCaptureConnection) {
        guard let pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer) else {
            print("[AirMouse] captureOutput: no pixelBuffer from sampleBuffer")
            return
        }
        Self.frameCount += 1
        if Self.frameCount % 120 == 1 {
            print("[AirMouse] captureOutput: frame #\(Self.frameCount), size=\(CVPixelBufferGetWidth(pixelBuffer))x\(CVPixelBufferGetHeight(pixelBuffer))")
        }
        // Record actual frame dimensions on first frame (or if they change).
        let w = CVPixelBufferGetWidth(pixelBuffer)
        let h = CVPixelBufferGetHeight(pixelBuffer)
        let size = CGSize(width: w, height: h)
        if frameSize != size { frameSize = size }

        let timestamp = CMSampleBufferGetPresentationTimeStamp(sampleBuffer)
        delegate?.cameraEngine(self, didOutput: pixelBuffer, timestamp: timestamp)
    }
}
