from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import atan2, degrees
from pathlib import Path
from typing import Any, Sequence

from rafeeq_robot.detection.interfaces import FallDetectionResult

_SHOULDERS = (11, 12)
_HIPS = (23, 24)
_BODY_POINTS = (11, 12, 23, 24, 25, 26, 27, 28)


@dataclass(frozen=True)
class PoseMetrics:
    torso_angle_from_vertical: float
    body_aspect_ratio: float
    hip_y: float
    descent: float
    recently_upright: bool
    candidate_frames: int
    stationary_fall_candidate: bool = False


class PoseFallHeuristic:
    """Stateful pose heuristic for laptop-camera fall detection.

    The preferred signal is still an upright-to-horizontal transition. For demos
    with laptop webcams, MediaPipe can miss the exact standing frame or lose the
    legs during the fall, so a very clear low horizontal posture is also treated
    as a possible fall and then verified by RAFEEQ's emergency state machine.
    """

    def __init__(self, confirmation_frames: int = 3, upright_memory_seconds: float = 10.0) -> None:
        self.confirmation_frames = confirmation_frames
        self.upright_memory_seconds = upright_memory_seconds
        self._last_upright_at: datetime | None = None
        self._upright_hip_y: float | None = None
        self._candidate_frames = 0
        self.last_metrics: PoseMetrics | None = None

    def evaluate(self, landmarks: Sequence[Any], timestamp: datetime) -> FallDetectionResult:
        raw = self._measure(landmarks)
        if raw is None:
            self._candidate_frames = max(0, self._candidate_frames - 1)
            self.last_metrics = None
            return self._result(False, 0.0, [], timestamp)

        torso_angle, aspect_ratio, hip_y = raw
        upright = torso_angle <= 35 and aspect_ratio <= 0.95
        if upright:
            self._last_upright_at = timestamp
            self._upright_hip_y = hip_y
            self._candidate_frames = 0

        recently_upright = (
            self._last_upright_at is not None
            and (timestamp - self._last_upright_at).total_seconds() <= self.upright_memory_seconds
        )
        descent = hip_y - (self._upright_hip_y if self._upright_hip_y is not None else hip_y)
        # Laptop webcams often lose the patient's lower body when they sit/fall
        # onto a sofa or mat. Keep the transition path, but also allow a clear
        # low horizontal posture because the camera may miss the warm-up frame.
        torso_horizontal = torso_angle >= 40
        body_horizontal = aspect_ratio >= 0.80
        low_body = hip_y >= 0.43
        descended = descent >= 0.04
        very_horizontal = torso_angle >= 55 or aspect_ratio >= 1.10
        very_low_body = hip_y >= 0.50
        transition_candidate = (
            recently_upright
            and low_body
            and (descended or very_horizontal)
            and (torso_horizontal or body_horizontal)
        )
        stationary_candidate = (
            not upright
            and very_low_body
            and very_horizontal
            and (torso_horizontal or body_horizontal)
        )
        candidate = transition_candidate or stationary_candidate
        if candidate:
            self._candidate_frames += 1
        elif not upright:
            self._candidate_frames = max(0, self._candidate_frames - 1)

        reasons = []
        if torso_horizontal:
            reasons.append("torso_horizontal")
        if body_horizontal:
            reasons.append("body_aspect_horizontal")
        if low_body:
            reasons.append("low_body_position")
        if descended:
            reasons.append("vertical_descent")
        if stationary_candidate:
            reasons.append("clear_low_horizontal_posture")

        triggered = self._candidate_frames >= self.confirmation_frames
        angle_score = min(1.0, max(0.0, (torso_angle - 45) / 45))
        aspect_score = min(1.0, max(0.0, (aspect_ratio - 0.8) / 1.2))
        descent_score = min(1.0, max(0.0, descent / 0.25))
        confidence = min(0.98, 0.35 + 0.3 * angle_score + 0.2 * aspect_score + 0.15 * descent_score)
        self.last_metrics = PoseMetrics(
            torso_angle_from_vertical=torso_angle,
            body_aspect_ratio=aspect_ratio,
            hip_y=hip_y,
            descent=descent,
            recently_upright=recently_upright,
            candidate_frames=self._candidate_frames,
            stationary_fall_candidate=stationary_candidate,
        )
        if triggered:
            self._candidate_frames = 0
        return self._result(triggered, confidence, reasons if triggered else [], timestamp)

    def _measure(self, landmarks: Sequence[Any]) -> tuple[float, float, float] | None:
        if len(landmarks) <= max(_BODY_POINTS):
            return None
        required = [landmarks[index] for index in _SHOULDERS + _HIPS]
        if any(not self._visible(point) for point in required):
            return None
        visible_body = [
            landmarks[index] for index in _BODY_POINTS if self._visible(landmarks[index])
        ]
        # Shoulders and hips are enough to recognize a horizontal torso. Knees and
        # ankles are commonly hidden by a sofa or leave a laptop camera's frame.
        if len(visible_body) < 4:
            return None

        shoulder_x = self._average(landmarks[index].x for index in _SHOULDERS)
        shoulder_y = self._average(landmarks[index].y for index in _SHOULDERS)
        hip_x = self._average(landmarks[index].x for index in _HIPS)
        hip_y = self._average(landmarks[index].y for index in _HIPS)
        dx = abs(hip_x - shoulder_x)
        dy = abs(hip_y - shoulder_y)
        torso_angle = degrees(atan2(dx, max(dy, 1e-6)))

        xs = [float(point.x) for point in visible_body]
        ys = [float(point.y) for point in visible_body]
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        aspect_ratio = width / max(height, 1e-6)
        return torso_angle, aspect_ratio, hip_y

    @staticmethod
    def _visible(point: Any) -> bool:
        visibility = getattr(point, "visibility", 1.0)
        return visibility is None or float(visibility) >= 0.35

    @staticmethod
    def _average(values: Any) -> float:
        items = list(values)
        return sum(float(value) for value in items) / len(items)

    @staticmethod
    def _result(
        triggered: bool,
        confidence: float,
        reasons: list[str],
        timestamp: datetime,
    ) -> FallDetectionResult:
        return FallDetectionResult(
            is_possible_fall=triggered,
            confidence=confidence,
            reason_codes=reasons,
            timestamp=timestamp,
        )


class MediaPipePoseFallDetector:
    """MediaPipe pose inference adapter for OpenCV BGR frames."""

    def __init__(self, model_path: str | Path, confirmation_frames: int = 3) -> None:
        import mediapipe as mp  # type: ignore[import-not-found,import-untyped]

        path = Path(model_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(path)),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.35,
            min_pose_presence_confidence=0.35,
            min_tracking_confidence=0.35,
        )
        self._mp = mp
        self._landmarker = mp.tasks.vision.PoseLandmarker.create_from_options(options)
        self._heuristic = PoseFallHeuristic(confirmation_frames=confirmation_frames)
        self.last_landmarks: Sequence[Any] = []
        self.last_metrics: PoseMetrics | None = None
        self._timestamp_ms = 0

    def analyze(self, frame: Any, timestamp: datetime) -> FallDetectionResult:
        import cv2  # type: ignore[import-not-found]

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        self._timestamp_ms = max(
            self._timestamp_ms + 1,
            int(timestamp.timestamp() * 1000),
        )
        result = self._landmarker.detect_for_video(image, self._timestamp_ms)
        if not result.pose_landmarks:
            self.last_landmarks = []
            self.last_metrics = None
            return FallDetectionResult(
                is_possible_fall=False,
                confidence=0,
                reason_codes=[],
                timestamp=timestamp,
            )
        self.last_landmarks = result.pose_landmarks[0]
        detection = self._heuristic.evaluate(self.last_landmarks, timestamp)
        self.last_metrics = self._heuristic.last_metrics
        return detection

    def close(self) -> None:
        self._landmarker.close()
