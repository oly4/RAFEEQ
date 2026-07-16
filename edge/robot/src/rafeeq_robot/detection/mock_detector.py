from datetime import datetime
from typing import Any

from rafeeq_robot.detection.interfaces import FallDetectionResult


class MockFallDetector:
    def __init__(self) -> None:
        self.trigger_next = False

    def trigger(self) -> None:
        self.trigger_next = True

    def analyze(self, frame: Any, timestamp: datetime) -> FallDetectionResult:
        triggered = self.trigger_next
        self.trigger_next = False
        return FallDetectionResult(
            is_possible_fall=triggered,
            confidence=0.82 if triggered else 0.05,
            reason_codes=["mock_trigger"] if triggered else [],
            timestamp=timestamp,
        )
