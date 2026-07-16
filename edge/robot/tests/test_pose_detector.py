from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from rafeeq_robot.detection.pose_detector import PoseFallHeuristic


@dataclass
class Landmark:
    x: float = 0
    y: float = 0
    visibility: float = 0


def pose(points: dict[int, tuple[float, float]]) -> list[Landmark]:
    landmarks = [Landmark() for _ in range(33)]
    for index, (x, y) in points.items():
        landmarks[index] = Landmark(x=x, y=y, visibility=1)
    return landmarks


UPRIGHT = pose(
    {
        11: (0.44, 0.24),
        12: (0.56, 0.24),
        23: (0.46, 0.48),
        24: (0.54, 0.48),
        25: (0.46, 0.68),
        26: (0.54, 0.68),
        27: (0.45, 0.90),
        28: (0.55, 0.90),
    }
)
HORIZONTAL_LOW = pose(
    {
        11: (0.24, 0.63),
        12: (0.24, 0.75),
        23: (0.50, 0.65),
        24: (0.50, 0.75),
        25: (0.68, 0.66),
        26: (0.68, 0.74),
        27: (0.88, 0.67),
        28: (0.88, 0.73),
    }
)
PARTIALLY_VISIBLE_HORIZONTAL = pose(
    {
        11: (0.30, 0.59),
        12: (0.31, 0.70),
        23: (0.57, 0.61),
        24: (0.58, 0.71),
    }
)


def test_sustained_upright_to_horizontal_transition_triggers_possible_fall() -> None:
    detector = PoseFallHeuristic(confirmation_frames=3)
    now = datetime.now(timezone.utc)
    assert not detector.evaluate(UPRIGHT, now).is_possible_fall

    results = [
        detector.evaluate(HORIZONTAL_LOW, now + timedelta(milliseconds=100 * index))
        for index in range(1, 4)
    ]

    assert [result.is_possible_fall for result in results] == [False, False, True]
    assert {
        "torso_horizontal",
        "body_aspect_horizontal",
        "low_body_position",
        "vertical_descent",
    }.issubset(results[-1].reason_codes)


def test_clear_low_horizontal_pose_triggers_even_if_upright_frame_was_missed() -> None:
    detector = PoseFallHeuristic(confirmation_frames=2)
    now = datetime.now(timezone.utc)

    results = [
        detector.evaluate(HORIZONTAL_LOW, now + timedelta(milliseconds=100 * index))
        for index in range(4)
    ]

    assert [result.is_possible_fall for result in results[:2]] == [False, True]
    assert "clear_low_horizontal_posture" in results[1].reason_codes


def test_partial_pose_on_sofa_still_triggers_after_upright_transition() -> None:
    detector = PoseFallHeuristic(confirmation_frames=3)
    now = datetime.now(timezone.utc)
    detector.evaluate(UPRIGHT, now)

    results = [
        detector.evaluate(
            PARTIALLY_VISIBLE_HORIZONTAL,
            now + timedelta(milliseconds=100 * index),
        )
        for index in range(1, 4)
    ]

    assert results[-1].is_possible_fall
    assert "torso_horizontal" in results[-1].reason_codes
