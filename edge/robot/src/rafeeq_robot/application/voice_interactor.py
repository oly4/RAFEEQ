from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Literal

from rafeeq_robot.application.emergency_manager import EmergencyManager
from rafeeq_robot.application.language import choose_locale_text, detect_spoken_locale
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
        locale = detect_spoken_locale(transcript)
        intent, confidence = self._classify(transcript)
        self.outbox.record(
            "voice_command_recognized",
            {
                "intent": intent,
                "confidence": confidence,
                "source": source,
                "locale": locale,
            },
        )
        if intent == "confirm_reminder":
            return self._complete_latest_reminder(locale)
        if intent == "snooze_reminder":
            return self._snooze_latest_reminder(locale)
        if intent == "decline_reminder":
            return self._decline_latest_reminder(locale)
        if intent == "medication_status_question":
            return self._answer_medication_status(locale)
        if intent == "task_status_question":
            return self._answer_task_status(transcript, locale)
        if intent == "request_help":
            return self._request_help(locale)
        if intent == "repeat_message":
            message = choose_locale_text(
                locale,
                "حاضر، سأكرر التذكير عند موعده.",
                "Sure. I will repeat the reminder at its scheduled time.",
            )
            self.speaker.speak(message, locale)
            return VoiceResult(intent, True, message)
        message = choose_locale_text(
            locale,
            "لم أفهم جيداً. هل أخذت الدواء؟ قل نعم، لا، أو ذكرني لاحقاً.",
            "I did not understand clearly. Did you take the medicine? Say yes, no, or remind me later.",
        )
        self.speaker.speak(message, locale)
        return VoiceResult(intent, False, message)

    def _complete_latest_reminder(self, locale: str) -> VoiceResult:
        occurrence_id = self.reminders.latest_prompted_occurrence_id()
        if occurrence_id is None:
            message = choose_locale_text(
                locale,
                "لا يوجد تذكير دواء نشط الآن.",
                "There is no active medicine reminder right now.",
            )
            self.speaker.speak(message, locale)
            return VoiceResult("confirm_reminder", False, message)
        self.reminders.complete(occurrence_id, "patient_voice")
        message = choose_locale_text(
            locale,
            "تم تسجيل الدواء. الله يعطيك العافية.",
            "Done. I recorded the medicine as taken.",
        )
        self.speaker.speak(message, locale)
        return VoiceResult("confirm_reminder", True, message)

    def _snooze_latest_reminder(self, locale: str) -> VoiceResult:
        occurrence_id = self.reminders.latest_prompted_occurrence_id()
        if occurrence_id is None:
            message = choose_locale_text(
                locale,
                "لا يوجد تذكير دواء نشط الآن.",
                "There is no active medicine reminder right now.",
            )
            self.speaker.speak(message, locale)
            return VoiceResult("snooze_reminder", False, message)
        self.reminders.snooze(occurrence_id, self.snooze_minutes, "patient_voice")
        message = choose_locale_text(
            locale,
            f"حسناً، سأذكرك مرة أخرى بعد {self.snooze_minutes} دقائق.",
            f"Okay. I will remind you again in {self.snooze_minutes} minutes.",
        )
        self.speaker.speak(message, locale)
        return VoiceResult("snooze_reminder", True, message)

    def _decline_latest_reminder(self, locale: str) -> VoiceResult:
        occurrence_id = self.reminders.latest_prompted_occurrence_id()
        if occurrence_id is None:
            message = choose_locale_text(
                locale,
                "لا يوجد تذكير دواء نشط الآن.",
                "There is no active medicine reminder right now.",
            )
            self.speaker.speak(message, locale)
            return VoiceResult("decline_reminder", False, message)
        self.reminders.mark_missed(occurrence_id, "patient_voice")
        message = choose_locale_text(
            locale,
            "تم تسجيل أن الدواء لم يؤخذ الآن.",
            "Done. I recorded that the medicine was not taken now.",
        )
        self.speaker.speak(message, locale)
        return VoiceResult("decline_reminder", True, message)

    def _request_help(self, locale: str) -> VoiceResult:
        if self.emergencies is None:
            message = choose_locale_text(
                locale,
                "سأحاول طلب المساعدة عند توفر خدمة الطوارئ.",
                "I will try to request help when emergency service is available.",
            )
            self.speaker.speak(message, locale)
            return VoiceResult("request_help", False, message)
        self.emergencies.trigger_sos()
        message = choose_locale_text(
            locale,
            "تم طلب المساعدة. ابق هادئاً، سيتم تنبيه العائلة.",
            "Help has been requested. Stay calm; your family will be alerted.",
        )
        self.speaker.speak(message, locale)
        return VoiceResult("request_help", True, message)

    def _answer_medication_status(self, locale: str) -> VoiceResult:
        completed_at = self.reminders.latest_completed_medication_at()
        if completed_at is None:
            message = choose_locale_text(
                locale,
                "لا يوجد عندي تسجيل أن الدواء أُخذ بعد.",
                "I do not have a record that the medicine was taken yet.",
            )
            self.speaker.speak(message, locale)
            return VoiceResult("medication_status_question", False, message)

        if completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=timezone.utc)
        completed_at = completed_at.astimezone(timezone.utc)
        elapsed = datetime.now(timezone.utc) - completed_at
        elapsed_minutes = max(0, round(elapsed.total_seconds() / 60))

        if 25 <= elapsed_minutes <= 35:
            message = choose_locale_text(
                locale,
                "نعم، لقد أخذت الدواء قبل نصف ساعة.",
                "Yes, the medicine was taken about half an hour ago.",
            )
        elif elapsed_minutes < 2:
            message = choose_locale_text(
                locale,
                "نعم، لقد أخذت الدواء قبل لحظات.",
                "Yes, the medicine was taken just now.",
            )
        elif elapsed_minutes < 60:
            message = choose_locale_text(
                locale,
                f"نعم، لقد أخذت الدواء قبل {elapsed_minutes} دقيقة.",
                f"Yes, the medicine was taken {elapsed_minutes} minutes ago.",
            )
        else:
            elapsed_hours = max(1, round(elapsed_minutes / 60))
            message = choose_locale_text(
                locale,
                f"نعم، لقد أخذت الدواء قبل {elapsed_hours} ساعة.",
                f"Yes, the medicine was taken {elapsed_hours} hours ago.",
            )

        self.speaker.speak(message, locale)
        return VoiceResult("medication_status_question", True, message)

    def _answer_task_status(self, transcript: str, locale: str) -> VoiceResult:
        task_status = self.reminders.find_task_status(transcript)
        if task_status is None:
            message = choose_locale_text(
                locale,
                "لا توجد عندي مهمة متزامنة بهذا الاسم الآن. افتح التطبيق ثم نفذ المزامنة.",
                "I do not have a synced task with that name right now. Open the app and sync it.",
            )
            self.speaker.speak(message, locale)
            return VoiceResult("task_status_question", False, message)

        if task_status.status == "completed":
            message = choose_locale_text(
                locale,
                f"نعم، تم تسجيل أن مهمة {task_status.title} أُنجزت.",
                f"Yes, {task_status.title} is recorded as completed.",
            )
            handled = True
        elif task_status.status in ("missed", "skipped"):
            message = choose_locale_text(
                locale,
                f"تم تسجيل أن مهمة {task_status.title} لم تكتمل.",
                f"{task_status.title} is recorded as not completed.",
            )
            handled = True
        elif task_status.status == "snoozed":
            message = choose_locale_text(
                locale,
                f"لا، مهمة {task_status.title} مؤجلة ولم تُسجل كمكتملة بعد.",
                f"No, {task_status.title} is snoozed and is not completed yet.",
            )
            handled = False
        else:
            message = choose_locale_text(
                locale,
                f"لا، مهمة {task_status.title} لم تُسجل كمكتملة بعد.",
                f"No, {task_status.title} is not recorded as completed yet.",
            )
            handled = False

        self.speaker.speak(message, locale)
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
