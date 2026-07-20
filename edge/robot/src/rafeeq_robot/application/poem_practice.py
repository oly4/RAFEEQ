from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

import httpx

from rafeeq_robot.application.outbox_service import OutboxService
from rafeeq_robot.config import RobotSettings
from rafeeq_robot.hardware.interfaces import SpeakerAdapter, VoiceInputAdapter
from rafeeq_robot.hardware.simulation.adapters import format_console_text


@dataclass(frozen=True)
class PoemPrompt:
    title: str
    poem_start: str
    expected_completion: str

    @property
    def hint(self) -> str:
        words = self.expected_completion.strip().split()
        if not words:
            return "تذكر أول كلمة من التكملة."
        return " ".join(words[: min(3, len(words))])


class PoemPracticeService:
    """Voice-driven poem completion activity for patient memory support."""

    def __init__(
        self,
        settings: RobotSettings,
        outbox: OutboxService,
        speaker: SpeakerAdapter,
    ) -> None:
        self.settings = settings
        self.outbox = outbox
        self.speaker = speaker
        self._access_token = settings.rafeeq_voice_access_token.strip()

    def can_handle(self, transcript: str) -> bool:
        return _extract_poem_query(transcript) is not None

    def handle_text(self, transcript: str, voice_input: VoiceInputAdapter) -> bool:
        query = _extract_poem_query(transcript)
        if query is None:
            return False

        poem = self._select_poem(query)
        if poem is None:
            self._record_action(transcript, "ما لقيت قصيدة جاهزة. أضف قصيدة من الأنشطة أولاً.")
            self.speaker.speak(
                "ما لقيت قصيدة جاهزة. أضف قصيدة من صفحة الأنشطة أولاً، وبعدها أقدر أختبرك.",
                "ar",
            )
            return True

        self._record_action(
            transcript,
            f"نبدأ تمرين قصيدة {poem.title}.",
            {"poem_title": poem.title},
        )
        self.speaker.speak(
            f"أبشر. نبدأ قصيدة {poem.title}. اسمع البداية، وبعدها كمل اللي تتذكره.",
            "ar",
        )
        self.speaker.speak(poem.poem_start, "ar")
        for attempt in range(1, 3):
            self.speaker.speak(
                "كمل القصيدة الآن."
                if attempt == 1
                else f"تلميح: {poem.hint}. جرّب مرة ثانية بهدوء.",
                "ar",
            )
            _wait_until_done_speaking(self.speaker)
            answer = voice_input.listen_text(max(6, self.settings.voice_listen_seconds))
            if answer:
                print(f"Poem answer attempt {attempt}: {format_console_text(answer)}")
            else:
                print(f"Poem answer attempt {attempt}: <no speech>")
            if answer and _is_matching_completion(answer, poem.expected_completion):
                self._record_poem_result(poem, transcript, answer, matched=True, attempt=attempt)
                self.speaker.speak("صح عليك، ممتاز. كملتها بشكل جميل.", "ar")
                return True
            if attempt == 1:
                self._record_poem_result(poem, transcript, answer or "", matched=False, attempt=attempt)

        self._record_poem_result(poem, transcript, "", matched=False, attempt=2)
        self.speaker.speak(
            f"ولا يهمك. التكملة هي: {poem.expected_completion}. نعيدها مرة ثانية وقت ما تحب.",
            "ar",
        )
        return True

    def _select_poem(self, query: str) -> PoemPrompt | None:
        poems = self._load_saved_poems() or _BUILT_IN_POEMS
        if not poems:
            return None
        normalized_query = _normalize_text(query)
        if not normalized_query:
            return poems[0]
        scored = [
            (
                max(
                    SequenceMatcher(None, normalized_query, _normalize_text(poem.title)).ratio(),
                    1.0 if normalized_query in _normalize_text(poem.title) else 0.0,
                ),
                poem,
            )
            for poem in poems
        ]
        score, poem = max(scored, key=lambda item: item[0])
        return poem if score >= 0.35 else poems[0]

    def _load_saved_poems(self) -> list[PoemPrompt]:
        device_poems = self._load_device_saved_poems()
        if device_poems:
            return device_poems
        token = self._get_access_token()
        if not token:
            return []
        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(
                    (
                        f"{self.settings.backend_base_url.rstrip('/')}"
                        f"/api/v1/patients/{self.settings.rafeeq_patient_id}/activities/poems"
                    ),
                    headers={"Authorization": f"Bearer {token}"},
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            print(f"Could not load saved poems from backend; using local poems: {exc}")
            return []
        if not isinstance(data, list):
            return []
        poems: list[PoemPrompt] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            poem_start = str(item.get("poem_start") or "").strip()
            expected = str(item.get("expected_completion") or "").strip()
            if title and poem_start and expected:
                poems.append(PoemPrompt(title, poem_start, expected))
        return poems

    def _load_device_saved_poems(self) -> list[PoemPrompt]:
        if not self.settings.rafeeq_device_secret:
            return []
        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(
                    f"{self.settings.backend_base_url.rstrip('/')}/device-api/v1/activities/poems",
                    headers={
                        "X-Device-Id": self.settings.rafeeq_device_id,
                        "X-Device-Secret": self.settings.rafeeq_device_secret,
                    },
                )
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            print(f"Could not load device poems from backend; trying voice auth: {exc}")
            return []
        return _poems_from_payload(data)

    def _get_access_token(self) -> str:
        if self._access_token:
            return self._access_token
        email = self.settings.rafeeq_voice_caregiver_email.strip()
        password = self.settings.rafeeq_voice_caregiver_password.strip()
        if not email or not password:
            return ""
        try:
            with httpx.Client(timeout=10) as client:
                response = client.post(
                    f"{self.settings.backend_base_url.rstrip('/')}/api/v1/auth/login",
                    json={"email": email, "password": password},
                )
                response.raise_for_status()
                token = str(response.json().get("access_token") or "").strip()
        except Exception as exc:
            print(f"Could not authenticate poem voice client; using local poems: {exc}")
            return ""
        self._access_token = token
        return token

    def _record_action(
        self,
        transcript: str,
        assistant_text: str,
        extra: dict[str, object] | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "action": "start_poem_test",
            "transcript": transcript,
            "assistant_text": assistant_text,
            "used_openai": False,
        }
        if extra:
            payload.update(extra)
        self.outbox.record("voice_app_action", payload)

    def _record_poem_result(
        self,
        poem: PoemPrompt,
        transcript: str,
        answer: str,
        *,
        matched: bool,
        attempt: int,
    ) -> None:
        self.outbox.record(
            "voice_poem_practice",
            {
                "poem_title": poem.title,
                "transcript": transcript,
                "answer_transcript": answer,
                "matched": matched,
                "attempt": attempt,
            },
        )


def _extract_poem_query(transcript: str) -> str | None:
    normalized = _normalize_text(transcript)
    if not normalized:
        return None
    trigger_patterns = (
        r"(?:ابد[اأ]?\s*)?(?:اختبار|تمرين)?\s*(?:ال)?(?:قصيده|قصيدة)\s*(.*)",
        r"(?:اختبرني|دربني)\s*(?:في|على)?\s*(?:ال)?(?:قصيده|قصيدة)?\s*(.*)",
        r"(?:start|begin|run)\s+(?:the\s+)?poem\s*(.*)",
        r"poem\s+(?:test|practice)\s*(.*)",
    )
    for pattern in trigger_patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _is_matching_completion(answer: str, expected: str) -> bool:
    normalized_answer = _normalize_text(answer)
    normalized_expected = _normalize_text(expected)
    if not normalized_answer or not normalized_expected:
        return False
    return (
        normalized_answer in normalized_expected
        or normalized_expected in normalized_answer
        or SequenceMatcher(None, normalized_answer, normalized_expected).ratio() >= 0.72
    )


def _wait_until_done_speaking(speaker: SpeakerAdapter) -> None:
    is_speaking = getattr(speaker, "is_speaking", None)
    while callable(is_speaking) and is_speaking():
        time.sleep(0.1)


def _normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ى": "ي",
        "ة": "ه",
        "ؤ": "و",
        "ئ": "ي",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = re.sub(r"[^\w\s\u0600-\u06FF]", " ", text.lower())
    return " ".join(text.split())


_BUILT_IN_POEMS: list[PoemPrompt] = [
    PoemPrompt("صوت صفير البلبل", "صوت صفير البلبل", "هيج قلبي الثمل"),
    PoemPrompt("إذا الشعب يوما أراد الحياة", "إذا الشعب يوما أراد الحياة", "فلا بد أن يستجيب القدر"),
    PoemPrompt("قفا نبك", "قفا نبك من ذكرى حبيب ومنزل", "بسقط اللوى بين الدخول فحومل"),
    PoemPrompt("Twinkle", "Twinkle twinkle little star", "how I wonder what you are"),
]


def _poems_from_payload(data: object) -> list[PoemPrompt]:
    if not isinstance(data, list):
        return []
    poems: list[PoemPrompt] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        poem_start = str(item.get("poem_start") or "").strip()
        expected = str(item.get("expected_completion") or "").strip()
        if title and poem_start and expected:
            poems.append(PoemPrompt(title, poem_start, expected))
    return poems
