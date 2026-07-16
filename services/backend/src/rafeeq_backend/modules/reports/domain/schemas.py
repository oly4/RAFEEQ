from datetime import date

from pydantic import BaseModel, Field


class ReportSummary(BaseModel):
    period: str = "all"
    range_start: date
    range_end: date
    routine_completion_rate: float
    medication_adherence_rate: float
    missed_medication_count: int
    memory_activities_completed: int
    total_activity_sessions: int
    conversation_interactions: int
    emergency_count: int
    average_emergency_acknowledgment_seconds: float | None
    device_online_percentage: float
    medication_adherence_trend: list[float] = Field(default_factory=list)
    memory_activity_trend: list[int] = Field(default_factory=list)
    disclaimer: str
