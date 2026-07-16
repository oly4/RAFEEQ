from rafeeq_robot.application.outbox_service import OutboxService
from rafeeq_robot.hardware.interfaces import SpeakerAdapter


_MESSAGES = {
    "ar": {
        "sos": "تم إرسال طلب المساعدة. خلك هادي، وبنوصل لأهلك التنبيه.",
        "fall_question": "انتبهت إنك ممكن طحت. طمني، أنت بخير؟ اضغط إس إذا أنت بخير، أو إتش إذا تحتاج مساعدة.",
        "safe": "الحمد لله. ما راح أرسل تنبيه طارئ.",
        "alert": "ما وصلني رد، أرسلت تنبيه طارئ لأهلك.",
    },
    "en": {
        "sos": "A help request has been sent. Stay calm; we will contact you.",
        "fall_question": "Possible fall detected. Are you okay? Press S for safe or H for help.",
        "safe": "You are marked safe. No emergency alert will be sent.",
        "alert": "An emergency alert has been recorded for the caregiver.",
    },
}


class EmergencyManager:
    def __init__(
        self,
        outbox: OutboxService,
        speaker: SpeakerAdapter,
        locale: str = "ar",
    ) -> None:
        self.outbox = outbox
        self.speaker = speaker
        self.locale = locale if locale in _MESSAGES else "ar"
        self.active_fall_event_id: str | None = None

    def _speak(self, message: str) -> None:
        self.speaker.speak(_MESSAGES[self.locale][message], self.locale)

    def trigger_sos(self) -> str:
        event = self.outbox.record("sos_pressed", {})
        self._speak("sos")
        return event.event_id

    def trigger_possible_fall(self, confidence: float, reason_codes: list[str]) -> str:
        event = self.outbox.record(
            "possible_fall_detected",
            {"confidence": confidence, "reason_codes": reason_codes},
        )
        self.active_fall_event_id = event.event_id
        self._speak("fall_question")
        return event.event_id

    def finish_fall_verification(self, outcome: str) -> str:
        if self.active_fall_event_id is None:
            raise RuntimeError("No fall verification is active")
        if outcome not in ("safe", "help", "timeout"):
            raise ValueError("Unknown fall verification outcome")
        event = self.outbox.record(
            "fall_verification_result",
            {"related_event_id": self.active_fall_event_id, "outcome": outcome},
        )
        self._speak("safe" if outcome == "safe" else "alert")
        self.active_fall_event_id = None
        return event.event_id
