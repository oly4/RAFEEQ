from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Literal

from rafeeq_robot.application.emergency_manager import EmergencyManager
from rafeeq_robot.application.outbox_service import OutboxService
from rafeeq_robot.application.reminder_service import ReminderService
from rafeeq_robot.hardware.interfaces import SpeakerAdapter

VoiceIntent = Literal[
    "confirm_reminder",
    "snooze_reminder",
    "decline_reminder",
    "medication_status_question",
    "task_status_question",
    "request_help",
    "repeat_message",
    "openai_conversation",
    "unknown",
]


@dataclass(frozen=True)
class VoiceResult:
    intent: VoiceIntent
    handled: bool
    message: str


class VoiceIntentRouter:
    """Command-oriented voice router for simulated text or speech transcripts."""

    def __init__(
        self,
        reminders: ReminderService,
        outbox: OutboxService,
        speaker: SpeakerAdapter,
        emergencies: EmergencyManager | None = None,
        snooze_minutes: int = 10,
    ) -> None:
        self.reminders = reminders
        self.outbox = outbox
        self.speaker = speaker
        self.emergencies = emergencies
        self.snooze_minutes = snooze_minutes

    def handle_text(self, transcript: str, source: str = "simulated_text") -> VoiceResult:
        intent, confidence = self._classify(transcript)
        self.outbox.record(
            "voice_command_recognized",
            {
                "intent": intent,
                "confidence": confidence,
                "source": source,
            },
        )
        if intent == "confirm_reminder":
            return self._complete_latest_reminder()
        if intent == "snooze_reminder":
            return self._snooze_latest_reminder()
        if intent == "decline_reminder":
            return self._decline_latest_reminder()
        if intent == "medication_status_question":
            return self._answer_medication_status()
        if intent == "task_status_question":
            return self._answer_task_status(transcript)
        if intent == "request_help":
            return self._request_help()
        if intent == "repeat_message":
            message = "حاضر، سأكرر التذكير عند موعده."
            self.speaker.speak(message, "ar")
            return VoiceResult(intent, True, message)
        message = "لم أفهم جيداً. هل أخذت الدواء؟ قل نعم، لا، أو ذكرني لاحقاً."
        self.speaker.speak(message, "ar")
        return VoiceResult(intent, False, message)

    def _complete_latest_reminder(self) -> VoiceResult:
        occurrence_id = self.reminders.latest_prompted_occurrence_id()
        if occurrence_id is None:
            message = "لا يوجد تذكير دواء نشط الآن."
            self.speaker.speak(message, "ar")
            return VoiceResult("confirm_reminder", False, message)
        self.reminders.complete(occurrence_id, "patient_voice")
        message = "تم تسجيل الدواء. الله يعطيك العافية."
        self.speaker.speak(message, "ar")
        return VoiceResult("confirm_reminder", True, message)

    def _snooze_latest_reminder(self) -> VoiceResult:
        occurrence_id = self.reminders.latest_prompted_occurrence_id()
        if occurrence_id is None:
            message = "لا يوجد تذكير دواء نشط الآن."
            self.speaker.speak(message, "ar")
            return VoiceResult("snooze_reminder", False, message)
        self.reminders.snooze(occurrence_id, self.snooze_minutes, "patient_voice")
        message = f"حسناً، سأذكرك مرة أخرى بعد {self.snooze_minutes} دقائق."
        self.speaker.speak(message, "ar")
        return VoiceResult("snooze_reminder", True, message)

    def _decline_latest_reminder(self) -> VoiceResult:
        occurrence_id = self.reminders.latest_prompted_occurrence_id()
        if occurrence_id is None:
            message = "لا يوجد تذكير دواء نشط الآن."
            self.speaker.speak(message, "ar")
            return VoiceResult("decline_reminder", False, message)
        self.reminders.mark_missed(occurrence_id, "patient_voice")
        message = "تم تسجيل أن الدواء لم يؤخذ الآن."
        self.speaker.speak(message, "ar")
        return VoiceResult("decline_reminder", True, message)

    def _request_help(self) -> VoiceResult:
        if self.emergencies is None:
            message = "سأحاول طلب المساعدة عند توفر خدمة الطوارئ."
            self.speaker.speak(message, "ar")
            return VoiceResult("request_help", False, message)
        self.emergencies.trigger_sos()
        message = "تم طلب المساعدة. ابق هادئاً، سيتم تنبيه العائلة."
        self.speaker.speak(message, "ar")
        return VoiceResult("request_help", True, message)

    def _answer_medication_status(self) -> VoiceResult:
        completed_at = self.reminders.latest_completed_medication_at()
        if completed_at is None:
            message = "لا يوجد عندي تسجيل أن الدواء أُخذ بعد."
            self.speaker.speak(message, "ar")
            return VoiceResult("medication_status_question", False, message)

        if completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=timezone.utc)
        completed_at = completed_at.astimezone(timezone.utc)
        elapsed = datetime.now(timezone.utc) - completed_at
        elapsed_minutes = max(0, round(elapsed.total_seconds() / 60))

        if 25 <= elapsed_minutes <= 35:
            message = "نعم، لقد أخذت الدواء قبل نصف ساعة."
        elif elapsed_minutes < 2:
            message = "نعم، لقد أخذت الدواء قبل لحظات."
        elif elapsed_minutes < 60:
            message = f"نعم، لقد أخذت الدواء قبل {elapsed_minutes} دقيقة."
        else:
            elapsed_hours = max(1, round(elapsed_minutes / 60))
            message = f"نعم، لقد أخذت الدواء قبل {elapsed_hours} ساعة."

        self.speaker.speak(message, "ar")
        return VoiceResult("medication_status_question", True, message)

    def _answer_task_status(self, transcript: str) -> VoiceResult:
        task_status = self.reminders.find_task_status(transcript)
        if task_status is None:
            message = "لا توجد عندي مهمة متزامنة بهذا الاسم الآن. افتح التطبيق ثم نفذ المزامنة."
            self.speaker.speak(message, "ar")
            return VoiceResult("task_status_question", False, message)

        if task_status.status == "completed":
            message = f"نعم، تم تسجيل أن مهمة {task_status.title} أُنجزت."
            handled = True
        elif task_status.status in ("missed", "skipped"):
            message = f"تم تسجيل أن مهمة {task_status.title} لم تكتمل."
            handled = True
        elif task_status.status == "snoozed":
            message = f"لا، مهمة {task_status.title} مؤجلة ولم تُسجل كمكتملة بعد."
            handled = False
        else:
            message = f"لا، مهمة {task_status.title} لم تُسجل كمكتملة بعد."
            handled = False

        self.speaker.speak(message, "ar")
        return VoiceResult("task_status_question", handled, message)

    def _classify(self, transcript: str) -> tuple[VoiceIntent, float]:
        text = _normalize_arabic(transcript)
        if not text:
            return "unknown", 0.0
        if _is_medication_status_question(text):
            return "medication_status_question", 0.92
        if _is_task_status_question(text):
            return "task_status_question", 0.86
        if any(phrase in text for phrase in ("نعم", "اخذ", "أخذ", "تم", "yes", "taken", "i took")):
            return "confirm_reminder", 0.95
        if any(phrase in text for phrase in ("لاحق", "بعد", "ذكرني", "snooze", "later")):
            return "snooze_reminder", 0.9
        if any(phrase in text for phrase in ("لا", "ما اخذ", "لم اخذ", "no", "skip", "decline")):
            return "decline_reminder", 0.85
        if any(phrase in text for phrase in ("ساعد", "مساعدة", "طوارئ", "help", "emergency")):
            return "request_help", 0.95
        if any(phrase in text for phrase in ("كرر", "repeat", "again")):
            return "repeat_message", 0.85
        return "unknown", 0.2


def _normalize_arabic(text: str) -> str:
    normalized = text.strip().casefold()
    normalized = normalized.translate(
        str.maketrans(
            {
                "أ": "ا",
                "إ": "ا",
                "آ": "ا",
                "ٱ": "ا",
                "ى": "ي",
                "ؤ": "و",
                "ئ": "ي",
                "ة": "ه",
                "ـ": "",
            }
        )
    )
    normalized = re.sub(r"[\u064b-\u065f\u0670]", "", normalized)
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _is_medication_status_question(text: str) -> bool:
    medicine_words = (
        "دواء",
        "دوا",
        "دوائي",
        "الدواء",
        "medicine",
        "medication",
        "med",
        "meds",
        "pill",
        "pills",
        "medcin",
        "medcine",
    )
    status_words = (
        "هل اخذت",
        "متى اخذت",
        "اذا اخذت",
        "لو اخذت",
        "اخذت الدوا",
        "اخذت الدواء",
        "خبرني",
        "علمني",
        "قل لي",
        "قول لي",
        "تاكد",
        "تحقق",
        "او لا",
        "did you take",
        "did i take",
        "did i eat",
        "did you eat",
        "have i taken",
        "have i ate",
        "when did you take",
        "when did i take",
        "tell me",
        "let me know",
        "check",
        "status",
        "or not",
        "whether",
        "if i take",
        "if i took",
        "if i eat",
        "if i ate",
        "took my",
        "take my",
        "eat my",
    )
    if not any(word in text for word in medicine_words):
        return False
    return any(phrase in text for phrase in status_words)


def _is_task_status_question(text: str) -> bool:
    task_words = (
        "مهمه",
        "نشاط",
        "روتين",
        "واجب",
        "غداء",
        "فطور",
        "عشاء",
        "اكل",
        "ماء",
        "تمرين",
        "قران",
        "قراءه",
        "task",
        "activity",
        "routine",
        "lunch",
        "breakfast",
        "dinner",
        "meal",
        "water",
        "exercise",
        "reading",
    )
    status_words = (
        "هل",
        "متى",
        "انجزت",
        "خلصت",
        "سويت",
        "عملت",
        "اكملت",
        "تم",
        "او لا",
        "did i",
        "did you",
        "have i",
        "have you",
        "done",
        "finish",
        "finished",
        "complete",
        "completed",
        "or not",
        "status",
        "let me know",
        "tell me",
        "check",
    )
    return any(word in text for word in task_words) and any(
        phrase in text for phrase in status_words
    )
