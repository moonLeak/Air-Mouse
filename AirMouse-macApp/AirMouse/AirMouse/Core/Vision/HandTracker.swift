import Vision

struct HandLandmarks {
    /// Vision JointName → CGPoint mapping, coordinates normalized to [0,1].
    /// Vision coordinate origin is bottom-left, Y-axis points up.
    let points: [VNHumanHandPoseObservation.JointName: CGPoint]

    var wrist:     CGPoint { points[.wrist] ?? .zero }
    var thumbTip:  CGPoint { points[.thumbTip] ?? .zero }     // 4
    var thumbIP:   CGPoint { points[.thumbIP] ?? .zero }      // 3
    var indexTip:  CGPoint { points[.indexTip] ?? .zero }     // 8
    var indexDIP:  CGPoint { points[.indexDIP] ?? .zero }     // 7
    var middleTip: CGPoint { points[.middleTip] ?? .zero }    // 12
    var middleDIP: CGPoint { points[.middleDIP] ?? .zero }    // 11
    var indexMCP:  CGPoint { points[.indexMCP] ?? .zero }     // 5
    var middleMCP: CGPoint { points[.middleMCP] ?? .zero }    // 9
    var ringMCP:   CGPoint { points[.ringMCP] ?? .zero }      // 13
    var littleMCP: CGPoint { points[.littleMCP] ?? .zero }    // 17

    /// Palm center: average of wrist + four MCP joints
    var palmCenter: CGPoint {
        let pts = [wrist, indexMCP, middleMCP, ringMCP, littleMCP]
        let x = pts.map(\.x).reduce(0, +) / Double(pts.count)
        let y = pts.map(\.y).reduce(0, +) / Double(pts.count)
        return CGPoint(x: x, y: y)
    }

    /// Returns a copy with all x coordinates flipped (1.0 − x).
    /// Use for front-facing cameras so hand movement matches screen-space intuition.
    func mirroredHorizontally() -> HandLandmarks {
        let flipped = points.mapValues { CGPoint(x: 1.0 - $0.x, y: $0.y) }
        return HandLandmarks(points: flipped)
    }
}

class HandTracker {
    private let request = VNDetectHumanHandPoseRequest()

    init() {
        request.maximumHandCount = 1
    }

    /// Process one frame, return detected hand landmarks (nil if no hand detected).
    func process(pixelBuffer: CVPixelBuffer,
                 orientation: CGImagePropertyOrientation = .up) -> HandLandmarks? {
        let handler = VNImageRequestHandler(cvPixelBuffer: pixelBuffer,
                                            orientation: orientation)
        do {
            try handler.perform([request])
        } catch {
            print("Vision error: \(error)")
            return nil
        }

        guard let observation = request.results?.first else { return nil }

        guard let recognizedPoints = try? observation.recognizedPoints(.all) else {
            return nil
        }

        // Filter low-confidence points (confidence < 0.5 is unreliable)
        let filtered = recognizedPoints.compactMapValues { point -> CGPoint? in
            guard point.confidence > 0.5 else { return nil }
            return CGPoint(x: point.x, y: point.y)
        }

        // Require the 5 joints used to compute palmCenter — if any are missing, the frame is too
        // noisy to be useful (this prevents false-positive detections where all coords are (0,0)).
        let palmKeys: [VNHumanHandPoseObservation.JointName] = [
            .wrist, .indexMCP, .middleMCP, .ringMCP, .littleMCP
        ]
        guard palmKeys.allSatisfy({ filtered[$0] != nil }) else {
            return nil
        }

        return HandLandmarks(points: filtered)
    }
}
