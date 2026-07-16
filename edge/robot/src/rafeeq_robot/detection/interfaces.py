from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field


class FallDetectionResult(BaseModel):
    is_possible_fall: bool
    confidence: float = Field(ge=0, le=1)
    reason_codes: list[str] = Field(default_factory=list)
    timestamp: datetime


class FallDetectionStrategy(Protocol):
    def analyze(self, frame: Any, timestamp: datetime) -> FallDetectionResult: ...
