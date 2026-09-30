import math
import time
from typing import Iterable, Optional, Sequence, Tuple


Point = Tuple[float, float]


def calculate_distance(point1, point2) -> float:
    """Return Euclidean distance between two points or MediaPipe landmarks."""
    if isinstance(point1, tuple) and isinstance(point2, tuple):
        return math.sqrt((point1[0] - point2[0]) ** 2 + (point1[1] - point2[1]) ** 2)
    if hasattr(point1, "x") and hasattr(point2, "x"):
        return math.sqrt((point1.x - point2.x) ** 2 + (point1.y - point2.y) ** 2)
    raise ValueError("Unsupported point types for distance calculation")


def calculate_normalized_distance(distance: float, reference: float) -> float:
    """Normalize a distance measurement against a reference baseline."""
    if reference == 0:
        raise ValueError("Reference distance cannot be zero.")
    return distance / reference


def calculate_speed(
    previous_position: Optional[Point],
    current_position: Point,
    last_update_time: float,
) -> float:
    """Compute movement speed between two positions."""
    if previous_position is None:
        return 0.0

    distance = calculate_distance(previous_position, current_position)
    time_diff = max(time.time() - last_update_time, 1e-6)

    return distance / time_diff


def calculate_center(points: Sequence[Point], weights: Optional[Iterable[float]] = None) -> Point:
    """Compute the weighted centroid of a collection of points."""
    if not points:
        raise ValueError("Points sequence cannot be empty.")

    if weights is None:
        weights = [1.0] * len(points)

    weights = list(weights)
    if len(points) != len(weights):
        raise ValueError("Points and weights must have the same length.")

    weighted_sum_x = sum(p[0] * w for p, w in zip(points, weights))
    weighted_sum_y = sum(p[1] * w for p, w in zip(points, weights))
    weight_total = sum(weights)

    if weight_total == 0:
        raise ValueError("Sum of weights must be non-zero.")

    return weighted_sum_x / weight_total, weighted_sum_y / weight_total
