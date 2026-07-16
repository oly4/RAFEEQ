from dataclasses import dataclass
from pathlib import Path

import pytest

from rafeeq_robot.detection.trained_detector import (
    FEATURE_NAMES,
    STATIC_FEATURES,
    SmoothingConfig,
    TemporalTracker,
    VoteSmoother,
    compute_window_features,
    extract_static_features,
    verify_model_artifact,
)


@dataclass
class Landmark:
    x: float = 0.5
    y: float = 0.5
    visibility: float = 1


def test_static_features_use_pixel_aware_torso_angle() -> None:
    landmarks = [Landmark() for _ in range(33)]
    landmarks[11] = Landmark(0.4, 0.2)
    landmarks[12] = Landmark(0.6, 0.2)
    landmarks[23] = Landmark(0.45, 0.5)
    landmarks[24] = Landmark(0.55, 0.5)

    features = extract_static_features(landmarks, (480, 640, 3))

    assert len(features) == len(STATIC_FEATURES)
    assert features[0] == pytest.approx(0, abs=1e-4)
    assert features[1] == pytest.approx(0.5)
    assert features[2] == pytest.approx(0.2)


def test_temporal_tracker_emits_velocity_after_warmup() -> None:
    tracker = TemporalTracker(horizon_seconds=0.4, minimum_history_seconds=0.25)
    first = [0.0] * len(STATIC_FEATURES)
    second = first.copy()
    first[1] = 0.4
    second[1] = 0.7

    assert tracker.update(0.0, first) is None
    result = tracker.update(0.3, second)

    assert result is not None
    assert len(result) == len(FEATURE_NAMES)
    assert result[6] == pytest.approx(1.0)


def test_window_feature_statistics_match_training_order() -> None:
    rows = [[float(index)] * len(FEATURE_NAMES) for index in range(5)]

    result = compute_window_features(rows)

    assert len(result) == len(FEATURE_NAMES) * 4 + len(STATIC_FEATURES)
    assert result[:4] == pytest.approx([2.0, 2**0.5, 0.0, 4.0])
    assert result[-len(STATIC_FEATURES) :] == pytest.approx([4.0] * len(STATIC_FEATURES))


def test_vote_smoother_requires_a_sustained_majority() -> None:
    smoother = VoteSmoother(SmoothingConfig(0.5, 0.8, 0.6, 4))

    assert not smoother.update(0.0, 0.9)
    assert not smoother.update(0.1, 0.9)
    assert not smoother.update(0.2, 0.2)
    assert smoother.update(0.3, 0.9)
    smoother.reset()
    assert not smoother.update(1.0, 0.9)


def test_model_artifact_checksum_is_enforced(tmp_path: Path) -> None:
    model = tmp_path / "model.pkl"
    model.write_bytes(b"not the pinned model")

    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_model_artifact(model)
