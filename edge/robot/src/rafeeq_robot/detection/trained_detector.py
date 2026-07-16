"""Trained temporal fall classifier integrated with RAFEEQ's pose adapter.

The temporal feature design and model artifact are adapted from Ramandeep
Singh's MIT-licensed ``ai-fall-detection-prototype`` at the pinned commit
documented in ``edge/robot/THIRD_PARTY_NOTICES.md``. The classifier only
produces a possible-fall event; RAFEEQ's emergency policy owns verification
and escalation.
"""

from __future__ import annotations

import hmac
import time
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from math import atan2, degrees, sqrt
from pathlib import Path
from typing import Any, Protocol

from rafeeq_robot.detection.interfaces import FallDetectionResult

UPSTREAM_COMMIT = "63a03a0af92e636429a8002cf97cabb8f33349a7"
FALL_MODEL_URL = (
    "https://raw.githubusercontent.com/Ramandeep-AI/"
    f"ai-fall-detection-prototype/{UPSTREAM_COMMIT}/models/fall_detector_window.pkl"
)
FALL_MODEL_SHA256 = "a6d362c7e7a313794ebf6671d4d4e615956995f01869cf191248fc9e21492458"

STATIC_FEATURES = (
    "torso_angle_deg",
    "hip_y_norm",
    "shoulder_y_norm",
    "bbox_w_norm",
    "bbox_h_norm",
    "bbox_aspect",
)
TEMPORAL_FEATURES = ("hip_y_vel", "torso_angle_vel", "bbox_h_vel")
FEATURE_NAMES = STATIC_FEATURES + TEMPORAL_FEATURES
WINDOW_FEATURE_COUNT = len(FEATURE_NAMES) * 4 + len(STATIC_FEATURES)

SEQ_WINDOW_SECONDS = 1.5
SEQ_MIN_SAMPLES = 8
SEQ_MIN_SPAN_SECONDS = 1.0

_LEFT_SHOULDER = 11
_RIGHT_SHOULDER = 12
_LEFT_HIP = 23
_RIGHT_HIP = 24


@dataclass(frozen=True)
class SmoothingConfig:
    probability_threshold: float
    window_seconds: float
    vote_ratio: float
    minimum_votes: int


@dataclass(frozen=True)
class TrainedDetectorMetrics:
    torso_angle_from_vertical: float
    hip_y: float
    body_height_width_ratio: float
    fall_probability: float
    window_ready: bool


class ProbabilityModel(Protocol):
    classes_: Any
    n_features_in_: int

    def predict_proba(self, values: Any) -> Any: ...


def file_sha256(path: str | Path) -> str:
    digest = sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model_artifact(
    path: str | Path,
    expected_sha256: str = FALL_MODEL_SHA256,
) -> None:
    actual = file_sha256(path)
    if not hmac.compare_digest(actual.lower(), expected_sha256.lower()):
        raise ValueError(
            f"Fall model checksum mismatch for {path}: expected {expected_sha256}, got {actual}"
        )


def extract_static_features(
    landmarks: Sequence[Any],
    image_shape: Sequence[int],
) -> list[float]:
    """Return the exact six static features used to train the pinned model."""

    if len(landmarks) < 33 or len(image_shape) < 2:
        raise ValueError("A complete 33-point pose and image dimensions are required")
    height = float(image_shape[0])
    width = float(image_shape[1])
    if height <= 0 or width <= 0:
        raise ValueError("Image dimensions must be positive")

    def point(index: int) -> tuple[float, float]:
        landmark = landmarks[index]
        return float(landmark.x) * width, float(landmark.y) * height

    left_shoulder = point(_LEFT_SHOULDER)
    right_shoulder = point(_RIGHT_SHOULDER)
    left_hip = point(_LEFT_HIP)
    right_hip = point(_RIGHT_HIP)
    shoulder_x = (left_shoulder[0] + right_shoulder[0]) / 2
    shoulder_y = (left_shoulder[1] + right_shoulder[1]) / 2
    hip_x = (left_hip[0] + right_hip[0]) / 2
    hip_y = (left_hip[1] + right_hip[1]) / 2
    torso_angle = degrees(atan2(abs(shoulder_x - hip_x), abs(shoulder_y - hip_y) + 1e-6))

    xs = [float(landmark.x) * width for landmark in landmarks]
    ys = [float(landmark.y) * height for landmark in landmarks]
    bbox_width = max(xs) - min(xs)
    bbox_height = max(ys) - min(ys)
    return [
        torso_angle,
        hip_y / height,
        shoulder_y / height,
        bbox_width / width,
        bbox_height / height,
        min(bbox_height / (bbox_width + 1e-6), 10.0),
    ]


class TemporalTracker:
    """Add time-based velocity features to a stream of static pose features."""

    def __init__(self, horizon_seconds: float = 0.4, minimum_history_seconds: float = 0.25):
        self.horizon_seconds = horizon_seconds
        self.minimum_history_seconds = minimum_history_seconds
        self._samples: deque[tuple[float, list[float]]] = deque()

    def reset(self) -> None:
        self._samples.clear()

    def update(self, sample_time: float, static: list[float]) -> list[float] | None:
        self._samples.append((sample_time, static))
        while self._samples and sample_time - self._samples[0][0] > self.horizon_seconds:
            self._samples.popleft()
        old_time, old = self._samples[0]
        elapsed = sample_time - old_time
        if elapsed < self.minimum_history_seconds:
            return None
        return static + [
            (static[1] - old[1]) / elapsed,
            (static[0] - old[0]) / elapsed,
            (static[4] - old[4]) / elapsed,
        ]


def compute_window_features(feature_rows: Sequence[Sequence[float]]) -> list[float]:
    if not feature_rows:
        raise ValueError("At least one feature row is required")
    width = len(FEATURE_NAMES)
    if any(len(row) != width for row in feature_rows):
        raise ValueError(f"Every feature row must contain {width} values")

    output: list[float] = []
    for index in range(width):
        values = [float(row[index]) for row in feature_rows]
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        output.extend((mean, sqrt(variance), min(values), max(values)))
    output.extend(
        float(feature_rows[-1][index]) - float(feature_rows[0][index])
        for index in range(len(STATIC_FEATURES))
    )
    return output


class WindowFeaturizer:
    def __init__(self) -> None:
        self._samples: deque[tuple[float, list[float]]] = deque()

    def reset(self) -> None:
        self._samples.clear()

    def update(self, sample_time: float, base_features: list[float]) -> list[float] | None:
        self._samples.append((sample_time, base_features))
        while self._samples and sample_time - self._samples[0][0] > SEQ_WINDOW_SECONDS:
            self._samples.popleft()
        if (
            len(self._samples) < SEQ_MIN_SAMPLES
            or sample_time - self._samples[0][0] < SEQ_MIN_SPAN_SECONDS
        ):
            return None
        return compute_window_features([features for _, features in self._samples])


class VoteSmoother:
    def __init__(self, config: SmoothingConfig) -> None:
        self.config = config
        self._votes: deque[tuple[float, bool]] = deque()

    def reset(self) -> None:
        self._votes.clear()

    def update(self, sample_time: float, fall_probability: float) -> bool:
        self._votes.append((sample_time, fall_probability > self.config.probability_threshold))
        while self._votes and sample_time - self._votes[0][0] > self.config.window_seconds:
            self._votes.popleft()
        if len(self._votes) < self.config.minimum_votes:
            return False
        return sum(vote for _, vote in self._votes) / len(self._votes) >= self.config.vote_ratio


class TrainedWindowClassifier:
    """Stateful classifier over an already-estimated MediaPipe pose stream."""

    def __init__(self, model_path: str | Path) -> None:
        verify_model_artifact(model_path)
        import joblib  # type: ignore[import-not-found,import-untyped]

        bundle: Any = joblib.load(model_path)
        if not isinstance(bundle, Mapping):
            raise ValueError("The trained fall model bundle is invalid")
        if bundle.get("type") != "window" or bundle.get("label_policy") != "down":
            raise ValueError("The trained fall model has unexpected metadata")
        model: Any = bundle.get("model")
        if model is None or int(getattr(model, "n_features_in_", -1)) != WINDOW_FEATURE_COUNT:
            raise ValueError("The trained fall model has an incompatible feature shape")
        classes = list(model.classes_)
        if 1 not in classes:
            raise ValueError("The trained fall model does not contain the fall class")
        self._model: ProbabilityModel = model
        self._fall_index = classes.index(1)
        self._smoother = VoteSmoother(self._parse_smoothing(bundle.get("smoothing")))
        self._tracker = TemporalTracker()
        self._window = WindowFeaturizer()
        self._alarm_active = False
        self.last_metrics: TrainedDetectorMetrics | None = None

    @staticmethod
    def _parse_smoothing(raw: Any) -> SmoothingConfig:
        if not isinstance(raw, Mapping):
            raise ValueError("The trained fall model does not include smoothing settings")
        config = SmoothingConfig(
            probability_threshold=float(raw["prob_threshold"]),
            window_seconds=float(raw["window_sec"]),
            vote_ratio=float(raw["vote_ratio"]),
            minimum_votes=int(raw["min_votes"]),
        )
        if not (
            0 <= config.probability_threshold <= 1
            and config.window_seconds > 0
            and 0 < config.vote_ratio <= 1
            and config.minimum_votes > 0
        ):
            raise ValueError("The trained fall model has invalid smoothing settings")
        return config

    def reset(self) -> None:
        self._tracker.reset()
        self._window.reset()
        self._smoother.reset()
        self._alarm_active = False
        self.last_metrics = None

    def evaluate(
        self,
        landmarks: Sequence[Any],
        image_shape: Sequence[int],
        sample_time: float,
        timestamp: datetime,
    ) -> FallDetectionResult:
        static = extract_static_features(landmarks, image_shape)
        base_features = self._tracker.update(sample_time, static)
        window_features = (
            self._window.update(sample_time, base_features) if base_features is not None else None
        )
        probability = 0.0
        alarm = False
        if window_features is not None:
            import numpy as np  # type: ignore[import-not-found]

            values = np.asarray(window_features, dtype=np.float32).reshape(1, -1)
            probability = float(self._model.predict_proba(values)[0][self._fall_index])
            alarm = self._smoother.update(sample_time, probability)
        triggered = alarm and not self._alarm_active
        self._alarm_active = alarm
        self.last_metrics = TrainedDetectorMetrics(
            torso_angle_from_vertical=static[0],
            hip_y=static[1],
            body_height_width_ratio=static[5],
            fall_probability=probability,
            window_ready=window_features is not None,
        )
        return FallDetectionResult(
            is_possible_fall=triggered,
            confidence=probability,
            reason_codes=(
                ["trained_window_classifier", "temporal_pose_transition"] if triggered else []
            ),
            timestamp=timestamp,
        )


class MediaPipeTrainedFallDetector:
    """MediaPipe Tasks pose inference followed by the pinned trained classifier."""

    def __init__(self, pose_model_path: str | Path, fall_model_path: str | Path) -> None:
        import mediapipe as mp  # type: ignore[import-not-found,import-untyped]

        pose_path = Path(pose_model_path)
        if not pose_path.is_file():
            raise FileNotFoundError(pose_path)
        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(pose_path)),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._mp = mp
        self._landmarker = mp.tasks.vision.PoseLandmarker.create_from_options(options)
        self._classifier = TrainedWindowClassifier(fall_model_path)
        self._timestamp_ms = 0
        self.last_landmarks: Sequence[Any] = []
        self.last_metrics: TrainedDetectorMetrics | None = None

    def analyze(self, frame: Any, timestamp: datetime) -> FallDetectionResult:
        import cv2  # type: ignore[import-not-found]

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        self._timestamp_ms = max(self._timestamp_ms + 1, int(timestamp.timestamp() * 1000))
        pose_result = self._landmarker.detect_for_video(image, self._timestamp_ms)
        if not pose_result.pose_landmarks:
            self.last_landmarks = []
            self.last_metrics = None
            self._classifier.reset()
            return FallDetectionResult(
                is_possible_fall=False,
                confidence=0,
                reason_codes=[],
                timestamp=timestamp,
            )
        self.last_landmarks = pose_result.pose_landmarks[0]
        result = self._classifier.evaluate(
            self.last_landmarks,
            frame.shape,
            time.monotonic(),
            timestamp,
        )
        self.last_metrics = self._classifier.last_metrics
        return result

    def close(self) -> None:
        self._landmarker.close()
