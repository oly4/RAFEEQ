from __future__ import annotations

from datetime import datetime, timedelta, timezone

import cv2
import numpy as np

from rafeeq_robot.detection.webcam_demo import FrameMotionFallDetector


def _frame(rect: tuple[int, int, int, int] | None = None) -> np.ndarray:
    image = np.zeros((240, 320, 3), dtype=np.uint8)
    if rect is not None:
        x, y, width, height = rect
        cv2.rectangle(image, (x, y), (x + width, y + height), (255, 255, 255), -1)
    return image


def test_motion_detector_triggers_on_upright_to_low_horizontal_fall() -> None:
    detector = FrameMotionFallDetector(confirmation_frames=1, min_area_ratio=0.01)
    now = datetime.now(timezone.utc)

    for index in range(6):
        assert not detector.analyze(_frame(), now + timedelta(milliseconds=index * 80)).is_possible_fall

    upright = _frame((142, 35, 36, 150))
    detector.analyze(upright, now + timedelta(seconds=1))

    fall = _frame((78, 150, 170, 46))
    result = detector.analyze(fall, now + timedelta(seconds=2))

    assert result.is_possible_fall
    assert "motion_low_horizontal" in result.reason_codes


def test_motion_detector_triggers_on_clear_low_horizontal_posture_without_upright_memory() -> None:
    detector = FrameMotionFallDetector(confirmation_frames=1, min_area_ratio=0.01)
    now = datetime.now(timezone.utc)

    for index in range(6):
        detector.analyze(_frame(), now + timedelta(milliseconds=index * 80))

    result = detector.analyze(_frame((60, 150, 190, 42)), now + timedelta(seconds=1))

    assert result.is_possible_fall
    assert "motion_clear_low_horizontal" in result.reason_codes


def test_motion_detector_does_not_trigger_on_upright_person() -> None:
    detector = FrameMotionFallDetector(confirmation_frames=1, min_area_ratio=0.01)
    now = datetime.now(timezone.utc)

    for index in range(6):
        detector.analyze(_frame(), now + timedelta(milliseconds=index * 80))

    result = detector.analyze(_frame((142, 35, 36, 150)), now + timedelta(seconds=1))

    assert not result.is_possible_fall
