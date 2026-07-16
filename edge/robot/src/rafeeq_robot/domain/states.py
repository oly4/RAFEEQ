from enum import StrEnum


class RobotState(StrEnum):
    STARTING = "starting"
    IDLE = "idle"
    LISTENING = "listening"
    SPEAKING = "speaking"
    REMINDER_ACTIVE = "reminder_active"
    VERIFYING_FALL = "verifying_fall"
    EMERGENCY_ACTIVE = "emergency_active"
    SYNCING = "syncing"
    DEGRADED = "degraded"
    SHUTTING_DOWN = "shutting_down"
