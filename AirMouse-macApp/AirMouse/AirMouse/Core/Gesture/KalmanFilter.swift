import CoreGraphics
import Foundation

/// Independent 1D Kalman filter. X and Y each get their own instance.
class KalmanFilter1D {
    var processNoise: Double = 0.01
    var measurementNoise: Double = 0.1

    private var estimate: Double = 0
    private var errorCovariance: Double = 1.0

    func update(measurement: Double) -> Double {
        let predictedCovariance = errorCovariance + processNoise
        let kalmanGain = predictedCovariance / (predictedCovariance + measurementNoise)
        estimate = estimate + kalmanGain * (measurement - estimate)
        errorCovariance = (1 - kalmanGain) * predictedCovariance
        return estimate
    }

    func reset(to value: Double) {
        estimate = value
        errorCovariance = 1.0
    }
}

/// 2D Kalman filter with speed-adaptive measurement noise.
class KalmanFilter2D {
    private let filterX = KalmanFilter1D()
    private let filterY = KalmanFilter1D()

    var lowSpeedThreshold: Double = 200.0

    private var lastPoint: CGPoint = .zero
    private var lastTime: Date = Date()

    func update(point: CGPoint) -> CGPoint {
        let now = Date()
        let dt = max(0.001, now.timeIntervalSince(lastTime))
        let speed = hypot(point.x - lastPoint.x, point.y - lastPoint.y) / dt
        lastPoint = point
        lastTime = now

        let adaptedNoise = speed < lowSpeedThreshold ? 0.5 : 0.05
        filterX.measurementNoise = adaptedNoise
        filterY.measurementNoise = adaptedNoise

        return CGPoint(
            x: filterX.update(measurement: point.x),
            y: filterY.update(measurement: point.y)
        )
    }

    func reset(to point: CGPoint) {
        filterX.reset(to: point.x)
        filterY.reset(to: point.y)
    }
}
